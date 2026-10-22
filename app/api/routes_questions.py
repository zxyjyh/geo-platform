from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.collector import setting
from app.db import get_session
from app.models import Question

router = APIRouter(prefix="/questions", dependencies=[Depends(current_user)])


class QuestionCreate(BaseModel):
    qid: str
    text: str
    branded: bool
    scene: str = ""
    intent: str = ""
    status: str = ""


class QuestionUpdate(BaseModel):
    text: str | None = None
    branded: bool | None = None
    scene: str | None = None
    intent: str | None = None
    status: str | None = None


@router.get("")
def list_questions(session: Session = Depends(get_session)):
    version = setting(session, "question_version", "v3")
    qs = session.scalars(select(Question).where(Question.version == version).order_by(Question.qid))
    return [{"qid": q.qid, "version": q.version, "text": q.text, "branded": q.branded, "scene": q.scene,
             "intent": q.intent, "status": q.status} for q in qs]


@router.post("")
def create_question(data: QuestionCreate, session: Session = Depends(get_session)):
    version = setting(session, "question_version", "v3")
    # Check if question already exists
    existing = session.get(Question, (data.qid, version))
    if existing:
        raise HTTPException(status_code=400, detail=f"Question {data.qid} already exists in version {version}")

    q = Question(
        qid=data.qid,
        version=version,
        text=data.text,
        branded=data.branded,
        scene=data.scene,
        intent=data.intent,
        status=data.status
    )
    session.add(q)
    session.commit()
    return {"qid": q.qid, "version": q.version, "text": q.text, "branded": q.branded,
            "scene": q.scene, "intent": q.intent, "status": q.status}


@router.put("/{qid}")
def update_question(qid: str, data: QuestionUpdate, session: Session = Depends(get_session)):
    version = setting(session, "question_version", "v3")
    q = session.get(Question, (qid, version))
    if not q:
        raise HTTPException(status_code=404, detail=f"Question {qid} not found in version {version}")

    if data.text is not None:
        q.text = data.text
    if data.branded is not None:
        q.branded = data.branded
    if data.scene is not None:
        q.scene = data.scene
    if data.intent is not None:
        q.intent = data.intent
    if data.status is not None:
        q.status = data.status

    session.commit()
    return {"qid": q.qid, "version": q.version, "text": q.text, "branded": q.branded,
            "scene": q.scene, "intent": q.intent, "status": q.status}


@router.delete("/{qid}")
def delete_question(qid: str, session: Session = Depends(get_session)):
    version = setting(session, "question_version", "v3")
    q = session.get(Question, (qid, version))
    if not q:
        raise HTTPException(status_code=404, detail=f"Question {qid} not found in version {version}")

    session.delete(q)
    session.commit()
    return {"message": f"Question {qid} deleted"}
