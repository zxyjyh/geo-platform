from datetime import date

import pytest

from app.collector import run_daily
from app.models import JobRun, Run, Source, SourceTag
from app.seed import seed_all
from app.urls import normalize_url
from tests.fakes import FakeClient

D0, D1 = date(2026, 10, 22), date(2026, 10, 23)
M_FOOD_ONLY = {"output": [{"type": "message", "content": [
    {"type": "output_text", "text": "可以试试 M Food，或者澳觅。", "annotations": [
        {"type": "url_citation", "url": "https://m.sohu.com/a/77?utm_source=x", "title": "搜狐文章", "site_name": "搜狐"}]}]}],
    "usage": {"tool_usage": {"web_search": 2}, "input_tokens": 1000, "output_tokens": 100}}


@pytest.fixture(autouse=True)
def seeded(session):
    seed_all(session)


@pytest.fixture
def seeded_one_day(session, tmp_path):
    # Q01 的回答只用"M Food"这个写法（不含任何现有别名的子串）
    run_daily(session, FakeClient.from_trial("custom", overrides={"Q01": M_FOOD_ONLY}), D0, "api-custom",
              tmp_path, sleep_s=0)


@pytest.fixture
def seeded_daily_two_days(session, tmp_path):
    for d in (D0, D1):
        run_daily(session, FakeClient.from_trial("custom"), d, "api-custom", tmp_path, sleep_s=0)


def test_all_business_routes_require_auth(client):
    for p in ["/api/dashboard", "/api/dashboard/trend", "/api/runs", "/api/runs/x", "/api/questions",
              "/api/sources/domains", "/api/sources/platforms", "/api/sources/owned", "/api/suggestions",
              "/api/settings", "/api/settings/aliases", "/api/settings/platforms", "/api/settings/owned-prefixes",
              "/api/settings/jobs", "/api/settings/users"]:
        assert client.get(p).status_code == 401, p
    assert client.put("/api/settings", json={"weak_recent_n": "3"}).status_code == 401
    assert client.post("/api/settings/jobs/rerun", json={"date": "2026-10-22"}).status_code == 401


def test_dashboard_defaults_to_latest_day(authed, seeded_daily_two_days):   # 不传 date → latest_date 是第二天
    j = authed.get("/api/dashboard").json()
    assert j["date"] == j["latest_date"] == "2026-10-23" and j["channel"] == "api-custom"
    assert j["metrics"]["mention"]["aomi"] == {"num": 8, "den": 10}
    assert j["usage"]["billed_searches"] == 42 and j["usage"]["est_cost_yuan"] is None


def test_dashboard_empty_db(authed):
    j = authed.get("/api/dashboard").json()
    assert j["latest_date"] is None and j["metrics"]["n_valid"] == 0 and j["job"] is None


def test_dashboard_cost_when_prices_set(authed, seeded_one_day):
    authed.put("/api/settings", json={"price_per_search_yuan": "0.01", "price_input_per_1k_yuan": "0.001",
                                      "price_output_per_1k_yuan": "0.002"})
    u = authed.get("/api/dashboard").json()["usage"]
    expect = u["billed_searches"] * 0.01 + u["input_tokens"] / 1000 * 0.001 + u["output_tokens"] / 1000 * 0.002
    assert u["est_cost_yuan"] == pytest.approx(expect)


def test_trend(authed, seeded_daily_two_days):
    t = authed.get("/api/dashboard/trend", params={"start": "2026-10-21", "end": "2026-10-23"}).json()
    assert [x["date"] for x in t] == ["2026-10-21", "2026-10-22", "2026-10-23"] and t[0]["n_valid"] == 0


def test_alias_change_recodes_and_dashboard_uses_new(authed, seeded_one_day):
    before = authed.get("/api/dashboard").json()["metrics"]["mention"]["mfood"]["num"]
    aliases = authed.get("/api/settings/aliases").json()
    aliases["mfood"].append("M Food")                             # fixture 里有 1 题只用"M Food"这个写法（不含已有别名的子串）
    assert authed.put("/api/settings/aliases", json=aliases).status_code == 200
    after = authed.get("/api/dashboard").json()["metrics"]["mention"]["mfood"]["num"]
    assert after == before + 1
    assert authed.get("/api/settings").json()["alias_version"] == "2"
    detail = authed.get("/api/runs/daily-doubao-api-custom-Q01-20261022").json()
    assert detail["coding"]["alias_version"] == 2 and detail["coding"]["mention"]["mfood"] is True


def test_alias_put_rejects_bad_entities(authed):
    assert authed.put("/api/settings/aliases", json={"aomi": ["澳觅"]}).status_code == 422
    assert authed.put("/api/settings/aliases", json={"aomi": [""], "mfood": ["m"], "shanfeng": ["s"]}).status_code == 422


def test_runs_list_filters_and_pagination(authed, seeded_one_day):
    j = authed.get("/api/runs", params={"size": 5}).json()
    assert j["total"] == 15 and len(j["items"]) == 5
    j = authed.get("/api/runs", params={"aomi_mentioned": "false", "size": 100}).json()
    assert all(not it["mention"]["aomi"] for it in j["items"])
    j = authed.get("/api/runs", params={"qid": "Q01"}).json()
    assert j["total"] == 1 and j["items"][0]["question"] == "澳门点外卖用什么APP好？"


def test_run_detail_includes_sources_and_coding(authed, seeded_one_day, session):
    session.add(SourceTag(url_norm=normalize_url("https://sohu.com/a/77"), tag="external_geo", note=""))
    session.commit()
    j = authed.get("/api/runs/daily-doubao-api-custom-Q01-20261022").json()
    assert j["answer_text"].startswith("可以试试") and j["coding"]["mention"]["aomi"] is True
    src = j["sources"][0]
    assert src["platform_key"] == "sohu" and src["is_owned"] is False and src["external_geo"] is True
    assert authed.get("/api/runs/nope").status_code == 404


def test_questions(authed):
    qs = authed.get("/api/questions").json()
    assert len(qs) == 15 and {q["qid"] for q in qs if q["branded"]} == {"Q03", "Q12", "Q13", "Q14", "Q15"}


def test_sources_endpoints_and_tags(authed, seeded_one_day, session):
    p = {"start": "2026-10-22", "end": "2026-10-22"}
    plats = authed.get("/api/sources/platforms", params=p).json()
    assert len(plats) == 7 and {"key", "name", "count", "verified"} <= set(plats[0])
    assert authed.get("/api/sources/domains", params=p).json()[0][1] >= 1
    assert authed.post("/api/sources/tags", json={"url": "http://www.sohu.com/a/77/", "tag": "external_geo",
                                                  "note": "来源不明"}).status_code == 200
    assert session.get(SourceTag, "https://sohu.com/a/77").note == "来源不明"
    assert authed.post("/api/sources/tags", json={"url": "x", "tag": "other"}).status_code == 422
    assert authed.delete("/api/sources/tags", params={"url": "https://m.sohu.com/a/77"}).status_code == 200
    session.expire_all()
    assert session.get(SourceTag, "https://sohu.com/a/77") is None


def test_suggestions_has_notice(authed, seeded_daily_two_days):
    j = authed.get("/api/suggestions").json()
    assert j["notice"] == "排序来自 api-custom 渠道的信源，App 可能不同。"
    assert isinstance(j["items"], list)
    for it in j["items"]:
        assert len(it["platforms"]) == 7 and it["weak"]["reasons"]


def test_rerun_creates_requested_job(authed, session):
    from app.timeutil import today_cst
    today = today_cst()
    r = authed.post("/api/settings/jobs/rerun", json={"date": today.isoformat()})
    assert r.status_code == 200
    jr = session.query(JobRun).one()
    assert (jr.status, jr.run_date, jr.channel, jr.requested_by) == ("requested", today, "api-custom", "alice")
    assert authed.get("/api/settings/jobs").json()[0]["status"] == "requested"


def test_rerun_rejects_past_date(authed):
    # spec §4.3 只允许补跑当天：补跑往日会把今天采到的回答记成那一天的数据
    from datetime import timedelta

    from app.timeutil import today_cst
    assert authed.post("/api/settings/jobs/rerun",
                       json={"date": (today_cst() - timedelta(days=1)).isoformat()}).status_code == 422


def test_rerun_rejects_future_date(authed):
    assert authed.post("/api/settings/jobs/rerun", json={"date": "2999-01-01"}).status_code == 422  # 未来同样拒绝


def test_settings_rejects_unknown_key(authed):           # PUT {"ARK_API_KEY": "x"} → 422
    assert authed.put("/api/settings", json={"ARK_API_KEY": "x"}).status_code == 422
    assert authed.put("/api/settings", json={"alias_version": "9"}).status_code == 422
    assert authed.put("/api/settings", json={"weak_recent_n": "abc"}).status_code == 422
    assert authed.put("/api/settings", json={"api_channel": "web"}).status_code == 422
    assert authed.put("/api/settings", json={"weak_recent_n": "5"}).status_code == 200
    assert authed.get("/api/settings").json()["weak_recent_n"] == "5"


def test_owned_prefix_change_recomputes_sources(authed, seeded_one_day, session):
    r = authed.post("/api/settings/owned-prefixes", json={"name": "搜狐测试", "url_prefix": "sohu.com/a/77"})
    assert r.status_code == 200
    session.expire_all()
    assert session.query(Source).filter_by(is_owned=True).count() >= 1
    assert authed.delete(f"/api/settings/owned-prefixes/{r.json()['id']}").status_code == 200
    session.expire_all()
    assert session.query(Source).filter_by(is_owned=True).count() == 0


def test_platforms_put_recomputes_platform_key(authed, seeded_one_day, session):
    plats = authed.get("/api/settings/platforms").json()
    for p in plats:
        if p["key"] == "sohu":
            p["domain_suffix"] = "nothing.example"
    assert authed.put("/api/settings/platforms", json=plats).status_code == 200
    session.expire_all()
    assert session.query(Source).filter_by(platform_key="sohu").count() == 0


def test_users_create_and_deactivate(authed, session):
    r = authed.post("/api/settings/users", json={"username": "dave", "password": "pw-dave"})
    assert r.status_code == 200
    uid = r.json()["id"]
    assert authed.post("/api/settings/users", json={"username": "dave", "password": "x"}).status_code == 409
    assert authed.patch(f"/api/settings/users/{uid}", json={"is_active": False}).status_code == 200
    me = [u for u in authed.get("/api/settings/users").json() if u["username"] == "alice"][0]
    assert authed.patch(f"/api/settings/users/{me['id']}", json={"is_active": False}).status_code == 422
    assert "password_hash" not in authed.get("/api/settings/users").json()[0]


def test_recode_all_keeps_old_version(session, seeded_one_day):
    from app.coding import recode_all
    from app.models import Alias, Coding

    for a in session.query(Alias).filter_by(version=1).all():
        session.add(Alias(version=2, entity=a.entity, alias=a.alias))
    session.commit()
    assert recode_all(session, 2) == session.query(Run).filter_by(status="valid").count()
    assert session.query(Coding).filter_by(alias_version=1).count() == session.query(Coding).filter_by(alias_version=2).count()
    assert recode_all(session, 2) == 15      # 重跑不产生重复行


def test_alias_change_backfills_runs_written_during_recode(authed, seeded_one_day, session, monkeypatch):
    # 重算进行中采集器又写入一条 run（它读到的还是旧版本 v1）：切到 v2 后它也必须有 v2 编码
    from app.api import routes_settings
    from app.models import Coding
    from tests.builders import add_run

    real = routes_settings.recode_all

    def recode_then_collector_writes(s, v):
        n = real(s, v)
        add_run(session, "Q02", D1, mention={"aomi": True}, order={"aomi": 1}, alias_version=1)
        return n

    monkeypatch.setattr(routes_settings, "recode_all", recode_then_collector_writes)
    aliases = authed.get("/api/settings/aliases").json()
    assert authed.put("/api/settings/aliases", json=aliases).status_code == 200
    session.expire_all()
    assert session.get(Coding, ("daily-doubao-api-custom-Q02-20261023", 2)) is not None


def test_dashboard_gives_cst_today_and_first_date(authed, seeded_daily_two_days):
    # 前端不用浏览器时区算"今天"：由后端按北京时间给出
    from app.timeutil import today_cst
    j = authed.get("/api/dashboard").json()
    assert j["today"] == today_cst().isoformat() and j["first_date"] == "2026-10-22"


def test_dashboard_by_scene(authed, seeded_one_day):
    j = authed.get("/api/dashboard").json()
    scenes = j["by_scene"]
    assert [s["scene"] for s in scenes] == sorted({s["scene"] for s in scenes}, key=[s["scene"] for s in scenes].index)
    assert sum(s["metrics"]["n_valid"] for s in scenes) == j["metrics"]["n_valid"]
    assert sum(s["metrics"]["n_expected"] for s in scenes) == 10          # 只算不带品牌名的题


def test_runs_list_has_aomi_snippet(authed, seeded_one_day):
    it = authed.get("/api/runs", params={"qid": "Q01"}).json()["items"][0]
    assert "澳觅" in it["aomi_snippet"] and it["scene"]
