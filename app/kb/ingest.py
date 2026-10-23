"""知识库入库流水线：解析 PDF → 写页面统计和切片 → 逐片向量化（进度每 10 片落库一次）。"""
import logging
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app import timeutil
from app.kb.embed import Embedder
from app.kb.pdf import parse_pdf
from app.kb.text import tokenize
from app.models import KbChunk, KbDoc, KbPage

log = logging.getLogger("geo.kb")
COMMIT_EVERY = 10  # 每向量化多少个切片提交一次，前端靠 n_embedded 显示进度


def process_doc(session: Session, doc: KbDoc, embedder: Embedder, kb_dir: Path) -> None:
    """处理一份文档，任何异常都落到 doc.process_status="failed" 上，不往外抛。"""
    doc_id = doc.id  # rollback 后 doc 会过期，先记下主键
    doc.process_status, doc.message = "processing", ""
    session.commit()
    try:
        # 重新处理：先清掉旧的页面和切片
        session.execute(delete(KbChunk).where(KbChunk.doc_id == doc_id))
        session.execute(delete(KbPage).where(KbPage.doc_id == doc_id))
        parsed = parse_pdf(kb_dir / f"{doc_id}.pdf")
        session.add_all(KbPage(doc_id=doc_id, page_no=p.page_no, n_chars=p.n_chars, n_images=p.n_images)
                        for p in parsed.pages)
        doc.n_pages, doc.n_chunks, doc.n_embedded = len(parsed.pages), len(parsed.chunks), 0
        session.commit()
        for i, c in enumerate(parsed.chunks, 1):
            v = embedder.embed(c.text)
            session.add(KbChunk(doc_id=doc_id, seq=c.seq, page_no=c.page_no, half=c.half, text=c.text,
                                tokens=" ".join(tokenize(c.text)),
                                embedding=np.asarray(v, dtype="<f4").tobytes(), dim=len(v)))
            if i % COMMIT_EVERY == 0:
                doc.n_embedded = i
                session.commit()
        doc.n_embedded = len(parsed.chunks)
        doc.process_status, doc.embed_model, doc.processed_at = "ready", embedder.model, timeutil.now_cst()
        session.commit()
    except Exception as e:  # noqa: BLE001  失败要落到文档上给页面看，不能让 worker 线程悄悄吞掉
        session.rollback()
        log.exception("知识库文档 %s 处理失败", doc_id)
        # pages 保留（方便看每页字数），chunks 全删（半成品不参与检索）
        session.execute(delete(KbChunk).where(KbChunk.doc_id == doc_id))
        doc = session.get(KbDoc, doc_id)  # rollback 后重新加载
        if doc is None:  # 处理期间文档被删了，没有可记录失败的行
            session.commit()
            return
        doc.process_status, doc.message = "failed", f"{type(e).__name__}: {e}"
        doc.n_embedded = 0
        session.commit()


def process_queued(session_factory: sessionmaker, embedder: Embedder, kb_dir: Path) -> int:
    n = 0
    with session_factory() as session:
        ids = list(session.scalars(select(KbDoc.id).where(KbDoc.process_status == "queued").order_by(KbDoc.id)))
        for doc_id in ids:
            doc = session.get(KbDoc, doc_id)
            if doc is None:  # 排队后被删了，跳过
                continue
            process_doc(session, doc, embedder, kb_dir)
            n += 1
    return n


def recover_stale_docs(session_factory: sessionmaker) -> int:
    """启动时把上次进程留下的 processing 改回 queued：worker 是单实例，不可能有别人在处理。"""
    with session_factory() as session:
        stale = list(session.scalars(select(KbDoc).where(KbDoc.process_status == "processing")))
        for doc in stale:
            doc.process_status = "queued"
        session.commit()
    return len(stale)
