"""事实一致性检测（1d）集成测试。

覆盖：
1. prompt 渲染与 JSON 解析（纯函数）
2. 原句验证
3. 抽取服务（mock LLM）
4. API CRUD（TestClient）
"""

import json
import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.factcheck import (
    PROMPT_V1,
    FactCheckError,
    call_llm,
    extract_and_store,
    extract_claims,
    parse_claims,
    render_prompt,
    verify_sentence,
)
from app.models import Coding, FactClaim, FactItem, Run, Setting
from app.timeutil import now_cst

# API 路由是否已注册到 create_app？
try:
    from app.api import routes_factcheck  # noqa: F401
    _HAS_ROUTES = True
except (ImportError, AttributeError):
    _HAS_ROUTES = False


# ── helpers ──────────────────────────────────────────────────────────


def _make_run(session, run_id="run-001", answer_text="澳觅是澳门最大的外卖平台。"):
    """插入一条最小可用的 Run 行，供 claim 外键引用。"""
    run = Run(
        run_id=run_id,
        round="trial",
        qid="q1",
        question_version="v1",
        platform="doubao",
        channel="api",
        channel_detail="",
        mode="",
        collected_at=now_cst(),
        collect_date=datetime.now().date(),
        rep=1,
        collector="",
        account_ref="",
        location="",
        new_session=True,
        answer_text=answer_text,
        raw_path="",
        sources_visible=False,
        sources_count=0,
        status="valid",
        error=None,
        search_queries="",
        search_rounds=0,
    )
    session.add(run)
    session.commit()
    return run


def _make_fact_item(session, version=1, code="A1", subject="市场地位",
                    correct_claim="澳觅是澳门最大的外卖平台"):
    item = FactItem(
        version=version, code=code, category="identity",
        subject=subject, correct_claim=correct_claim,
        source_ref="", status="active",
    )
    session.add(item)
    session.commit()
    return item


def _login(client, session_factory):
    """创建用户并登录。"""
    from app.auth import hash_password
    from app.models import User
    with session_factory() as s:
        u = User(username="alice", password_hash=hash_password("correct"),
                 is_active=True, created_at=now_cst())
        s.add(u)
        s.commit()
    r = client.post("/api/auth/login", json={"username": "alice", "password": "correct"})
    assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════════
# 1. Prompt 渲染 & JSON 解析（纯函数，不需要 DB）
# ══════════════════════════════════════════════════════════════════════


class TestRenderPrompt:

    def test_render_prompt_contains_items_and_answer(self):
        items = [
            {"code": "A1", "subject": "市场地位", "correct_claim": "澳觅是澳门最大的外卖平台"},
            {"code": "A2", "subject": "商家数", "correct_claim": "合作商家超过5700家"},
        ]
        answer = "澳觅是澳门最大的外卖平台，合作商家超过5700家。"
        result = render_prompt(items, answer)
        assert "A1" in result
        assert "A2" in result
        assert "市场地位" in result
        assert answer in result

    def test_render_prompt_empty_items(self):
        result = render_prompt([], "随便一句话")
        assert "清单为空" in result
        assert "随便一句话" in result


class TestParseClaims:

    def test_parse_claims_valid_json(self):
        raw = json.dumps([
            {"sentence": "澳觅是澳门最大的外卖平台", "code": "A1"},
            {"sentence": "澳觅合作商家超过5700家", "code": None},
        ])
        claims = parse_claims(raw)
        assert len(claims) == 2
        assert claims[0]["sentence"] == "澳觅是澳门最大的外卖平台"
        assert claims[0]["code"] == "A1"
        assert claims[0]["raw_label"] == "known"
        assert claims[1]["code"] is None
        assert claims[1]["raw_label"] == "unknown"

    def test_parse_claims_fenced_json(self):
        inner = json.dumps([{"sentence": "澳觅覆盖全澳门", "code": "A3"}])
        raw = f"```json\n{inner}\n```"
        claims = parse_claims(raw)
        assert len(claims) == 1
        assert claims[0]["sentence"] == "澳觅覆盖全澳门"
        assert claims[0]["code"] == "A3"

    def test_parse_claims_invalid_json_raises(self):
        with pytest.raises(FactCheckError, match="JSON 解析失败"):
            parse_claims("这不是 JSON")

    def test_parse_claims_not_array_raises(self):
        with pytest.raises(FactCheckError, match="期望 JSON 数组"):
            parse_claims('{"sentence": "x", "code": "A1"}')

    def test_parse_claims_missing_sentence_raises(self):
        with pytest.raises(FactCheckError, match="缺少有效的 sentence"):
            parse_claims(json.dumps([{"code": "A1"}]))

    def test_parse_claims_empty_array(self):
        claims = parse_claims("[]")
        assert claims == []


class TestVerifySentence:

    def test_verify_sentence_found(self):
        answer = "澳觅是澳门最大的外卖平台，合作商家超过5700家。"
        assert verify_sentence("澳觅是澳门最大的外卖平台", answer) is True

    def test_verify_sentence_not_found(self):
        answer = "澳觅是澳门最大的外卖平台。"
        assert verify_sentence("澳觅覆盖全澳门", answer) is False

    def test_verify_sentence_strips_whitespace(self):
        answer = "澳觅是澳门最大的外卖平台。"
        assert verify_sentence("  澳觅是澳门最大的外卖平台  ", answer) is True


# ══════════════════════════════════════════════════════════════════════
# 2. 抽取服务（mock LLM）
# ══════════════════════════════════════════════════════════════════════


class TestExtractService:

    def test_extract_claims_filters_invalid_sentences(self, monkeypatch):
        """LLM 返回的 sentence 如果不在原文里，应被过滤掉。"""
        answer = "澳觅是澳门最大的外卖平台。"
        llm_output = json.dumps([
            {"sentence": "澳觅是澳门最大的外卖平台", "code": "A1"},  # 存在于原文
            {"sentence": "澳觅覆盖全澳门", "code": "A2"},            # 不存在于原文
        ])

        def fake_call_llm(prompt, api_key, model=None):
            return llm_output

        monkeypatch.setattr("app.factcheck.call_llm", fake_call_llm)
        claims = extract_claims(answer, [], api_key="test-key")
        assert len(claims) == 1
        assert claims[0]["sentence"] == "澳觅是澳门最大的外卖平台"

    def test_extract_and_store_skips_duplicate(self, session, monkeypatch):
        """同一 run_id + version 不应重复抽取。"""
        run = _make_run(session, run_id="dup-run", answer_text="澳觅是澳门最大的外卖平台。")
        _make_fact_item(session)

        # 先手动插入一条 claim，模拟已经抽取过
        existing = FactClaim(
            run_id=run.run_id, extract_version=1, seq=0,
            sentence="澳觅是澳门最大的外卖平台",
            fact_code="A1", raw_label="known",
            reviewer_decision="pending", note="",
        )
        session.add(existing)
        session.commit()

        called = {"n": 0}

        def fake_call_llm(prompt, api_key, model=None):
            called["n"] += 1
            return "[]"

        monkeypatch.setattr("app.factcheck.call_llm", fake_call_llm)
        result = extract_and_store(session, run, [], api_key="test-key", version=1)
        # 应该跳过，不调用 LLM
        assert called["n"] == 0
        assert result == 0


# ══════════════════════════════════════════════════════════════════════
# 3. API 测试（TestClient）
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def factcheck_app(session_factory):
    """创建带 ARK_API_KEY mock 的 app。"""
    os.environ.setdefault("ARK_API_KEY", "test-key")
    from app.api import create_app
    app = create_app(session_factory)
    return app


@pytest.fixture
def authed_client(factcheck_app, session_factory):
    """已登录的 TestClient。"""
    with TestClient(factcheck_app) as c:
        _login(c, session_factory)
        yield c


@pytest.mark.skipif(not _HAS_ROUTES, reason="routes_factcheck 尚未实现")
class TestFactCheckAPI:

    def test_fact_items_crud(self, authed_client):
        """PUT 写入清单 → GET 返回 → 版本号递增。"""
        items = [
            {"code": "A1", "category": "identity", "subject": "市场地位",
             "correct_claim": "澳觅是澳门最大的外卖平台", "source_ref": ""},
        ]
        # PUT 写入清单（注意：路由接收的是 list，不是 dict）
        r = authed_client.put("/api/settings/fact-items", json=items)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["version"] == 1

        r2 = authed_client.get("/api/settings/fact-items")
        assert r2.status_code == 200
        data = r2.json()
        assert len(data["items"]) == 1
        assert data["version"] == 1

        # 再 PUT 一次，版本应递增
        r3 = authed_client.put("/api/settings/fact-items", json=items)
        assert r3.status_code == 200
        assert r3.json()["version"] == 2

    def test_extract_endpoint(self, authed_client, session_factory, monkeypatch):
        """POST /api/factcheck/extract 触发抽取。"""
        # 先插入 Run + Coding(mention_aomi=True) + FactItem + Setting
        with session_factory() as s:
            run = _make_run(s, run_id="extract-run", answer_text="澳觅是澳门最大的外卖平台。")
            coding = Coding(
                run_id=run.run_id, alias_version=1,
                mention_aomi=True, mention_mfood=False, mention_shanfeng=False,
            )
            s.add(coding)
            _make_fact_item(s)
            s.add(Setting(key="fact_item_version", value="1"))
            s.add(Setting(key="api_channel", value="api-custom"))
            s.commit()

        # mock extract_and_store
        def fake_extract(session, run, items, api_key, version=None, model=None):
            return {"new_claims": 1}

        import app.api.routes_factcheck as routes_mod
        monkeypatch.setattr(routes_mod, "extract_and_store", fake_extract, raising=False)

        r = authed_client.post("/api/factcheck/extract", json={})
        assert r.status_code == 200
        j = r.json()
        assert j["processed"] >= 0
        assert "new_claims" in j

    def test_review_claim(self, authed_client, session_factory):
        """先有 claim → POST review → 检查 reviewer_decision 更新。"""
        with session_factory() as s:
            run = _make_run(s, run_id="review-run", answer_text="澳觅是澳门最大的外卖平台。")
            claim = FactClaim(
                run_id=run.run_id, extract_version=1, seq=0,
                sentence="澳觅是澳门最大的外卖平台",
                fact_code="A1", raw_label="known",
                reviewer_decision="pending", note="",
            )
            s.add(claim)
            s.commit()
            claim_id = claim.id

        r = authed_client.post(
            f"/api/factcheck/claims/{claim_id}/review",
            json={"decision": "confirmed", "note": "确认无误"},
        )
        assert r.status_code == 200

        with session_factory() as s:
            updated = s.get(FactClaim, claim_id)
            assert updated.reviewer_decision == "confirmed"
            assert updated.note == "确认无误"
            assert updated.reviewed_at is not None

    def test_stats_endpoint(self, authed_client, session_factory):
        """GET /api/factcheck/stats 返回正确的计数。"""
        with session_factory() as s:
            run = _make_run(s, run_id="stats-run", answer_text="澳觅是澳门最大的外卖平台。")
            _make_fact_item(s)
            for i, decision in enumerate(["pending", "confirmed", "rejected"]):
                c = FactClaim(
                    run_id=run.run_id, extract_version=1, seq=i,
                    sentence=f"句子{i}", fact_code="A1", raw_label="known",
                    reviewer_decision=decision, note="",
                )
                s.add(c)
            s.commit()

        r = authed_client.get("/api/factcheck/stats")
        assert r.status_code == 200
        j = r.json()
        assert j["total"] == 3
        assert j["pending"] == 1
        assert j["confirmed"] == 1
        assert j["rejected"] == 1
