import hashlib
import os
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ark import ArkError
from app.auth import current_user
from app.db import get_session
from app.kb.search import search
from app.models import KbDoc, KbPage, User
from app.timeutil import now_cst

router = APIRouter(prefix="/kb", dependencies=[Depends(current_user)])

MAX_BYTES = 1024**3
MAX_PART = 16 * 1024**2


class DocInit(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    filename: str = Field(min_length=1, max_length=256)
    size_bytes: int
    effective_date: date
    status: Literal["active", "inactive"] = "active"


class DocPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    effective_date: date | None = None
    status: Literal["active", "inactive"] | None = None


class SearchIn(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)


def _kb_dir(request: Request):
    return request.app.state.kb_dir


def _doc(session: Session, doc_id: int, lock: bool = False) -> KbDoc:
    doc = session.get(KbDoc, doc_id, with_for_update=lock)
    if doc is None:
        raise HTTPException(404, "文档不存在")
    return doc


def _brief(d: KbDoc) -> dict:
    return {"id": d.id, "title": d.title, "filename": d.filename, "size_bytes": d.size_bytes,
            "received_bytes": d.received_bytes, "sha256": d.sha256, "effective_date": d.effective_date.isoformat(),
            "status": d.status, "process_status": d.process_status, "n_pages": d.n_pages, "n_chunks": d.n_chunks,
            "n_embedded": d.n_embedded, "embed_model": d.embed_model, "message": d.message,
            "uploaded_by": d.uploaded_by, "created_at": d.created_at.isoformat(),
            "processed_at": d.processed_at.isoformat() if d.processed_at else None}


@router.post("/docs")
def init_upload(body: DocInit, user: User = Depends(current_user), session: Session = Depends(get_session)):
    if not 1 <= body.size_bytes <= MAX_BYTES:
        raise HTTPException(413, "文件大小须在 1 字节到 1GB 之间")
    if not body.filename.lower().endswith(".pdf"):
        raise HTTPException(422, "只支持 PDF 文件")
    doc = KbDoc(title=body.title, filename=body.filename, size_bytes=body.size_bytes, received_bytes=0,
                effective_date=body.effective_date, status=body.status, process_status="uploading", message="",
                uploaded_by=user.username, created_at=now_cst())
    session.add(doc)
    session.commit()
    return {"id": doc.id, "received_bytes": 0}


@router.put("/docs/{doc_id}/content")
async def upload_part(doc_id: int, request: Request, offset: int = Query(ge=0),
                      session: Session = Depends(get_session)):
    doc = _doc(session, doc_id, lock=True)
    if doc.process_status != "uploading":
        raise HTTPException(409, "文档不在上传状态")
    if offset != doc.received_bytes:
        raise HTTPException(409, {"message": "偏移量不对", "received_bytes": doc.received_bytes})
    body = await request.body()
    if len(body) > MAX_PART:
        raise HTTPException(413, "单次上传不能超过 16MB")
    if offset + len(body) > doc.size_bytes:
        raise HTTPException(422, "上传的字节数超过了声明的文件大小")
    part = _kb_dir(request) / f"{doc.id}.pdf.part"
    part.parent.mkdir(parents=True, exist_ok=True)
    with open(part, "ab") as f:
        f.truncate(offset)  # 上次写完文件但没提交时，丢掉没记账的尾巴，保证同一段字节不会写两遍
        f.write(body)
    doc.received_bytes = offset + len(body)  # 与追加写在同一个请求里记账
    session.commit()
    return {"received_bytes": doc.received_bytes}


def _fail(session: Session, doc: KbDoc, part, message: str, code: int):
    doc.process_status = "failed"
    doc.message = message
    session.commit()
    part.unlink(missing_ok=True)
    raise HTTPException(code, message)


@router.post("/docs/{doc_id}/complete")
def complete_upload(doc_id: int, request: Request, session: Session = Depends(get_session)):
    doc = _doc(session, doc_id, lock=True)
    if doc.process_status != "uploading":
        raise HTTPException(409, "文档不在上传状态")
    if doc.received_bytes != doc.size_bytes:
        raise HTTPException(409, {"message": "文件还没传完", "received_bytes": doc.received_bytes})
    kb_dir = _kb_dir(request)
    part = kb_dir / f"{doc.id}.pdf.part"
    h = hashlib.sha256()
    with open(part, "rb") as f:
        head = f.read(5)
        h.update(head)
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    if head != b"%PDF-":
        _fail(session, doc, part, "文件不是有效的 PDF", 422)
    digest = h.hexdigest()
    dup = session.scalars(select(KbDoc).where(KbDoc.sha256 == digest, KbDoc.id != doc.id)).first()
    if dup is not None:
        _fail(session, doc, part, f"这份文件已经上传过：{dup.title}", 409)
    os.replace(part, kb_dir / f"{doc.id}.pdf")
    doc.sha256 = digest
    doc.process_status = "queued"
    session.commit()
    return {"id": doc.id, "process_status": doc.process_status}


@router.get("/docs")
def list_docs(session: Session = Depends(get_session)):
    return [_brief(d) for d in session.scalars(select(KbDoc).order_by(KbDoc.id.desc()))]


@router.get("/docs/{doc_id}")
def get_doc(doc_id: int, session: Session = Depends(get_session)):
    doc = _doc(session, doc_id)
    pages = session.scalars(select(KbPage).where(KbPage.doc_id == doc_id).order_by(KbPage.page_no)).all()
    return {**_brief(doc),
            "pages": [{"page_no": p.page_no, "n_chars": p.n_chars, "n_images": p.n_images} for p in pages],
            "empty_pages": [p.page_no for p in pages if p.n_chars == 0]}


@router.patch("/docs/{doc_id}")
def patch_doc(doc_id: int, body: DocPatch, session: Session = Depends(get_session)):
    doc = _doc(session, doc_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(doc, k, v)
    session.commit()
    return _brief(doc)


@router.post("/docs/{doc_id}/reprocess")
def reprocess_doc(doc_id: int, session: Session = Depends(get_session)):
    doc = _doc(session, doc_id, lock=True)
    if doc.process_status not in ("ready", "failed"):
        raise HTTPException(409, "只有处理完成或失败的文档才能重新处理")
    doc.process_status = "queued"
    session.commit()
    return {"id": doc.id, "process_status": doc.process_status}


@router.delete("/docs/{doc_id}")
def delete_doc(doc_id: int, request: Request, session: Session = Depends(get_session)):
    doc = _doc(session, doc_id)
    session.delete(doc)
    session.commit()
    kb_dir = _kb_dir(request)
    for name in (f"{doc_id}.pdf", f"{doc_id}.pdf.part"):
        (kb_dir / name).unlink(missing_ok=True)
    return {"ok": True}


@router.get("/docs/{doc_id}/file")
def get_file(doc_id: int, request: Request, session: Session = Depends(get_session)):
    doc = _doc(session, doc_id)
    path = _kb_dir(request) / f"{doc.id}.pdf"
    if not path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@router.post("/search")
def search_kb(body: SearchIn, request: Request, session: Session = Depends(get_session)):
    embedder = request.app.state.embedder
    if embedder is None:
        raise HTTPException(503, "没有配置 ARK_API_KEY")
    try:
        hits = search(session, body.query, embedder, limit=body.limit)
    except ArkError as e:
        raise HTTPException(502, f"向量化失败：{e}")
    return [{"chunk_id": h.chunk_id, "doc_id": h.doc_id, "doc_title": h.doc_title,
             "effective_date": h.effective_date.isoformat(), "page_no": h.page_no, "half": h.half, "text": h.text,
             "score": h.score, "semantic_rank": h.semantic_rank, "keyword_rank": h.keyword_rank} for h in hits]
