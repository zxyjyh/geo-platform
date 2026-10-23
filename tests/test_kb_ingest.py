import numpy as np
from sqlalchemy import func, select

from app.kb.ingest import process_doc, process_queued, recover_stale_docs
from app.models import KbChunk, KbDoc, KbPage
from tests.builders import add_doc
from tests.fakes import FakeEmbedder


def test_process_doc_happy_path(session, tmp_path):
    doc = add_doc(session, tmp_path, pages=["澳覓合作商家超5,700家", None, "註冊用戶超300萬"], process_status="queued")
    process_doc(session, doc, FakeEmbedder(), tmp_path)
    assert doc.process_status == "ready" and doc.embed_model == "fake"
    assert (doc.n_pages, doc.n_chunks, doc.n_embedded) == (3, 2, 2)
    assert doc.processed_at is not None
    chunks = session.scalars(select(KbChunk).order_by(KbChunk.seq)).all()
    assert [c.page_no for c in chunks] == [1, 3] and "澳觅" in chunks[0].tokens.split()
    assert len(np.frombuffer(chunks[0].embedding, dtype="<f4")) == chunks[0].dim == 64


def test_process_doc_embed_failure_leaves_no_chunks(session, tmp_path):
    doc = add_doc(session, tmp_path, pages=[f"第{i}页澳觅" for i in range(25)], process_status="queued")
    process_doc(session, doc, FakeEmbedder(fail_after=12), tmp_path)
    assert doc.process_status == "failed" and "ArkError" in doc.message
    assert session.scalar(select(func.count()).select_from(KbChunk)) == 0
    assert session.scalar(select(func.count()).select_from(KbPage)) == 25


def test_process_doc_missing_file_fails_gracefully(session, tmp_path):
    doc = add_doc(session, tmp_path, pages=["澳觅"], process_status="queued")
    (tmp_path / f"{doc.id}.pdf").unlink()
    process_doc(session, doc, FakeEmbedder(), tmp_path)
    assert doc.process_status == "failed" and doc.message


def test_process_doc_reprocess_replaces_old_rows(session, tmp_path):
    doc = add_doc(session, tmp_path, pages=["澳觅"], process_status="queued")
    process_doc(session, doc, FakeEmbedder(), tmp_path)
    process_doc(session, doc, FakeEmbedder(), tmp_path)
    assert session.scalar(select(func.count()).select_from(KbChunk)) == 1
    assert session.scalar(select(func.count()).select_from(KbPage)) == 1


def test_recover_stale_requeues_processing_docs(session_factory, tmp_path):
    with session_factory() as s:
        add_doc(s, tmp_path, pages=["x"], process_status="processing")
    assert recover_stale_docs(session_factory) == 1
    with session_factory() as s:
        assert s.scalar(select(KbDoc.process_status)) == "queued"


def test_process_queued_skips_other_states(session_factory, tmp_path):
    with session_factory() as s:
        for st in ("uploading", "ready", "failed", "queued"):
            add_doc(s, tmp_path, pages=["澳觅"], title=st, process_status=st)
    assert process_queued(session_factory, FakeEmbedder(), tmp_path) == 1
    with session_factory() as s:
        states = {d.title: d.process_status for d in s.scalars(select(KbDoc))}
        assert states == {"uploading": "uploading", "ready": "ready", "failed": "failed", "queued": "ready"}
        assert s.scalar(select(func.count()).select_from(KbChunk)) == 1
