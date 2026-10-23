from datetime import date, datetime

import numpy as np
from sqlalchemy import select, text

from app.models import CST, KbChunk, KbDoc, KbPage


def _doc():
    return KbDoc(title="澳門年鑑", filename="a.pdf", size_bytes=10, effective_date=date(2025, 1, 1),
                 status="active", process_status="uploading", message="", uploaded_by="admin",
                 created_at=datetime(2026, 10, 23, 9, 0, tzinfo=CST))


def test_kb_tables_roundtrip(session):
    emb = np.arange(4, dtype="<f4").tobytes()
    doc = _doc()
    doc.pages = [KbPage(page_no=1, n_chars=100, n_images=0), KbPage(page_no=2, n_chars=0, n_images=3)]
    doc.chunks = [KbChunk(seq=0, page_no=1, half="L", text="澳门人口", tokens="澳门 人口", embedding=emb, dim=4)]
    session.add(doc)
    session.commit()
    session.expire_all()

    got = session.get(KbDoc, doc.id)
    assert (got.received_bytes, got.sha256, got.n_pages, got.n_chunks, got.n_embedded, got.embed_model) == (0, "", 0, 0, 0, "")
    assert got.processed_at is None
    assert got.created_at.tzinfo is not None
    assert got.chunks[0].embedding == emb
    assert np.frombuffer(got.chunks[0].embedding, dtype="<f4").tolist() == [0.0, 1.0, 2.0, 3.0]

    session.delete(got)
    session.commit()
    assert session.scalars(select(KbPage)).all() == []
    assert session.scalars(select(KbChunk)).all() == []


def test_kb_cascade_in_database(session_factory):
    # 不靠 ORM 级联：开 SQLite 外键后直接用 SQL 删文档，库里的 ON DELETE CASCADE 也要生效
    with session_factory() as s:
        s.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
        doc = _doc()
        doc.pages = [KbPage(page_no=1, n_chars=1, n_images=0)]
        doc.chunks = [KbChunk(seq=0, page_no=1, half="", text="x", tokens="x", embedding=b"", dim=0)]
        s.add(doc)
        s.commit()
        s.execute(text("DELETE FROM kb_docs"))
        s.commit()
        assert s.scalars(select(KbPage)).all() == []
        assert s.scalars(select(KbChunk)).all() == []
