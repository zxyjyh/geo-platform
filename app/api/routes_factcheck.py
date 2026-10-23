"""事实一致性检测 API（1d 功能）。

路由分两组：
- /settings/fact-items：事实清单 CRUD（设置页用）
- /factcheck/claims、/factcheck/stats、/factcheck/extract：抽取结果查看、人工复核、触发抽取
"""

from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.collector import ROUND, setting
from app.config import get_settings
from app.db import get_session
from app.models import Coding, FactClaim, FactItem, Run, Setting, User
from app.timeutil import now_cst, today_cst

router = APIRouter(dependencies=[Depends(current_user)])

VALID_CATEGORIES = {"identity", "registration", "service", "other"}
VALID_STATUSES = {"active", "retired"}
VALID_DECISIONS = {"confirmed", "rejected", "new_item"}
VALID_FILTERS = {"known", "unknown", "pending"}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class FactItemBody(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    category: Literal["identity", "registration", "service", "other"]
    subject: str = Field(min_length=1, max_length=128)
    correct_claim: str = Field(min_length=1, max_length=1000)
    source_ref: str = Field(default="", max_length=500)
    status: Literal["active", "retired"] = "active"


class ReviewBody(BaseModel):
    decision: Literal["confirmed", "rejected", "new_item"]
    note: str = Field(default="", max_length=500)


class ExtractBody(BaseModel):
    date: Optional[date] = None
    channel: Optional[str] = None


# ---------------------------------------------------------------------------
# /settings/fact-items — 事实清单 CRUD
# ---------------------------------------------------------------------------

def _fact_items_json(session: Session, version: int) -> dict:
    items = session.scalars(
        select(FactItem).where(FactItem.version == version).order_by(FactItem.id)
    ).all()
    return {
        "version": version,
        "items": [
            {
                "code": i.code,
                "category": i.category,
                "subject": i.subject,
                "correct_claim": i.correct_claim,
                "source_ref": i.source_ref,
                "status": i.status,
            }
            for i in items
        ],
    }


@router.get("/settings/fact-items")
def get_fact_items(session: Session = Depends(get_session)):
    version = int(setting(session, "fact_item_version", "0"))
    return _fact_items_json(session, version)


@router.put("/settings/fact-items")
def put_fact_items(body: list[FactItemBody], session: Session = Depends(get_session)):
    """整表替换，升版本（和 BrandMark 同模式）。"""
    # 校验 code 非空（Pydantic 已保证 min_length=1）、同版本内不重复
    codes = [item.code.strip() for item in body]
    if len(codes) != len(set(codes)):
        raise HTTPException(422, "code 不能重复")

    # 清理并校验
    cleaned = []
    for item in body:
        code = item.code.strip()
        subject = item.subject.strip()
        correct_claim = item.correct_claim.strip()
        source_ref = item.source_ref.strip()
        if not code or len(code) > 32:
            raise HTTPException(422, "code 必须非空、不超过 32 字")
        if item.category not in VALID_CATEGORIES:
            raise HTTPException(422, f"category 必须在 {VALID_CATEGORIES} 中")
        if not subject or len(subject) > 128:
            raise HTTPException(422, "subject 必须非空、不超过 128 字")
        if not correct_claim or len(correct_claim) > 1000:
            raise HTTPException(422, "correct_claim 必须非空、不超过 1000 字")
        if len(source_ref) > 500:
            raise HTTPException(422, "source_ref 不超过 500 字")
        if item.status not in VALID_STATUSES:
            raise HTTPException(422, f"status 必须在 {VALID_STATUSES} 中")
        cleaned.append({
            "code": code,
            "category": item.category,
            "subject": subject,
            "correct_claim": correct_claim,
            "source_ref": source_ref,
            "status": item.status,
        })

    # 升版本
    new_version = (session.scalar(select(func.max(FactItem.version))) or 0) + 1
    session.add_all(
        FactItem(version=new_version, **item) for item in cleaned
    )

    # 更新 settings 表
    row = session.get(Setting, "fact_item_version")
    if row is None:
        session.add(Setting(key="fact_item_version", value=str(new_version)))
    else:
        row.value = str(new_version)

    session.commit()
    return _fact_items_json(session, new_version)


# ---------------------------------------------------------------------------
# /factcheck/claims — 抽取结果查看
# ---------------------------------------------------------------------------

def _claim_json(c: FactClaim) -> dict:
    return {
        "id": c.id,
        "run_id": c.run_id,
        "qid": None,  # 下面查询里会 join 拿 qid
        "sentence": c.sentence,
        "fact_code": c.fact_code,
        "raw_label": c.raw_label,
        "reviewer_decision": c.reviewer_decision,
        "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
        "note": c.note,
    }


@router.get("/factcheck/claims")
def get_claims(
    date: Optional[date] = Query(None, description="日期 YYYY-MM-DD"),
    channel: Optional[str] = Query(None, description="渠道"),
    filter: Optional[Literal["known", "unknown", "pending"]] = Query(None, description="过滤"),
    session: Session = Depends(get_session),
):
    """返回抽取结果列表，按 run_id + seq 排序。"""
    q = select(FactClaim, Run.qid).join(Run, FactClaim.run_id == Run.run_id)

    if date is not None:
        q = q.where(Run.collect_date == date)
    if channel is not None:
        q = q.where(Run.channel == channel)
    if filter == "known":
        q = q.where(FactClaim.raw_label == "known")
    elif filter == "unknown":
        q = q.where(FactClaim.raw_label == "unknown")
    elif filter == "pending":
        q = q.where(FactClaim.reviewer_decision == "pending")

    q = q.order_by(FactClaim.run_id, FactClaim.seq)
    rows = session.execute(q).all()

    return [
        {
            "id": claim.id,
            "run_id": claim.run_id,
            "qid": qid,
            "sentence": claim.sentence,
            "fact_code": claim.fact_code,
            "raw_label": claim.raw_label,
            "reviewer_decision": claim.reviewer_decision,
            "reviewed_at": claim.reviewed_at.isoformat() if claim.reviewed_at else None,
            "note": claim.note,
        }
        for claim, qid in rows
    ]


# ---------------------------------------------------------------------------
# /factcheck/stats — 统计概览
# ---------------------------------------------------------------------------

@router.get("/factcheck/stats")
def get_stats(session: Session = Depends(get_session)):
    """返回各状态计数。"""
    total = session.scalar(select(func.count(FactClaim.id))) or 0
    known = session.scalar(
        select(func.count(FactClaim.id)).where(FactClaim.raw_label == "known")
    ) or 0
    unknown = session.scalar(
        select(func.count(FactClaim.id)).where(FactClaim.raw_label == "unknown")
    ) or 0
    pending = session.scalar(
        select(func.count(FactClaim.id)).where(FactClaim.reviewer_decision == "pending")
    ) or 0
    confirmed = session.scalar(
        select(func.count(FactClaim.id)).where(FactClaim.reviewer_decision == "confirmed")
    ) or 0
    rejected = session.scalar(
        select(func.count(FactClaim.id)).where(FactClaim.reviewer_decision == "rejected")
    ) or 0
    return {
        "total": total,
        "known": known,
        "unknown": unknown,
        "pending": pending,
        "confirmed": confirmed,
        "rejected": rejected,
    }


# ---------------------------------------------------------------------------
# /factcheck/claims/{claim_id}/review — 人工复核
# ---------------------------------------------------------------------------

@router.post("/factcheck/claims/{claim_id}/review")
def review_claim(
    claim_id: int,
    body: ReviewBody,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """对单条抽取结果做人工复核。"""
    claim = session.get(FactClaim, claim_id)
    if claim is None:
        raise HTTPException(404, "没有找到该 claim")
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(422, f"decision 必须在 {VALID_DECISIONS} 中")

    claim.reviewer_decision = body.decision
    claim.reviewed_at = now_cst()
    claim.reviewed_by = user.username
    claim.note = body.note.strip()
    session.commit()
    return {
        "id": claim.id,
        "reviewer_decision": claim.reviewer_decision,
        "reviewed_at": claim.reviewed_at.isoformat() if claim.reviewed_at else None,
        "reviewed_by": claim.reviewed_by,
        "note": claim.note,
    }


# ---------------------------------------------------------------------------
# /factcheck/extract — 触发抽取
# ---------------------------------------------------------------------------

@router.post("/factcheck/extract")
def trigger_extract(
    body: ExtractBody,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """对指定日期+渠道下 mention_aomi=True 的 valid run 执行事实抽取。"""
    cfg = get_settings()
    if not cfg.ark_api_key:
        raise HTTPException(500, "缺少环境变量 ARK_API_KEY")

    extract_date = body.date or today_cst()
    channel = body.channel or setting(session, "api_channel", "api-custom")

    # 查出该日期+渠道下 mention_aomi=True 的 valid run
    runs = session.scalars(
        select(Run)
        .join(Coding, Coding.run_id == Run.run_id)
        .where(
            Run.collect_date == extract_date,
            Run.channel == channel,
            Run.round == ROUND,
            Run.status == "valid",
            Coding.mention_aomi.is_(True),
        )
    ).all()

    if not runs:
        return {"processed": 0, "new_claims": 0, "skipped": 0}

    # 获取当前事实清单版本
    version = int(setting(session, "fact_item_version", "0"))
    items = [
        {"code": i.code, "subject": i.subject, "correct_claim": i.correct_claim}
        for i in session.scalars(
            select(FactItem).where(FactItem.version == version)
        )
    ]

    from app.factcheck import extract_and_store

    extract_version = int(setting(session, "fact_extract_version", "1"))
    processed = 0
    new_claims = 0
    skipped = 0
    for run in runs:
        try:
            n = extract_and_store(session, run, items, cfg.ark_api_key, extract_version)
            processed += 1
            new_claims += n
        except Exception:
            skipped += 1

    session.commit()
    return {"processed": processed, "new_claims": new_claims, "skipped": skipped}
