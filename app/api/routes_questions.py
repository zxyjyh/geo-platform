from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.collector import setting
from app.db import get_session
from app.models import Question

router = APIRouter(prefix="/questions", dependencies=[Depends(current_user)])


@router.get("")
def list_questions(session: Session = Depends(get_session)):
    version = setting(session, "question_version", "v3")
    qs = session.scalars(select(Question).where(Question.version == version).order_by(Question.qid))
    return [{"qid": q.qid, "version": q.version, "text": q.text, "branded": q.branded, "scene": q.scene,
             "intent": q.intent, "status": q.status} for q in qs]
