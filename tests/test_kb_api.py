import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.models import KbChunk, KbDoc
from tests.builders import make_pdf_bytes, ready_doc
from tests.conftest import login
from tests.fakes import FakeEmbedder


@pytest.fixture
def kb_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def authed(session_factory, kb_dir, user_alice):
    with TestClient(create_app(session_factory, embedder=FakeEmbedder())) as c:
        assert login(c, "alice", "correct").status_code == 200
        yield c


def init(c, size, title="年刊", filename="a.pdf", status="active"):
    r = c.post("/api/kb/docs", json={"title": title, "filename": filename, "size_bytes": size,
                                     "effective_date": "2026-01-01", "status": status})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def put(c, doc_id, offset, body):
    return c.put(f"/api/kb/docs/{doc_id}/content", params={"offset": offset}, content=body)


def upload(c, data, title="年刊"):
    doc_id = init(c, len(data), title=title)
    assert put(c, doc_id, 0, data).status_code == 200
    return doc_id


def test_upload_in_parts_then_complete_queues_doc(authed, kb_dir):
    data = make_pdf_bytes(["澳觅"])
    doc_id = init(authed, size=len(data))
    assert put(authed, doc_id, 0, data[:100]).json() == {"received_bytes": 100}
    assert put(authed, doc_id, 100, data[100:]).status_code == 200
    r = authed.post(f"/api/kb/docs/{doc_id}/complete")
    assert r.status_code == 200
    j = authed.get(f"/api/kb/docs/{doc_id}").json()
    assert j["process_status"] == "queued" and j["uploaded_by"] == "alice" and len(j["sha256"]) == 64
    assert (kb_dir / f"{doc_id}.pdf").exists() and not (kb_dir / f"{doc_id}.pdf.part").exists()


def test_upload_offset_mismatch_returns_received(authed, kb_dir):
    doc_id = init(authed, size=300)
    put(authed, doc_id, 0, b"%PDF-" + b"x" * 95)
    r = put(authed, doc_id, 0, b"y" * 100)          # 客户端以为没传上，重发第一段
    assert r.status_code == 409 and r.json()["detail"]["received_bytes"] == 100
    assert (kb_dir / f"{doc_id}.pdf.part").stat().st_size == 100   # 重发的字节没有落盘


def test_put_rejects_non_uploading_and_oversize_part(authed, monkeypatch):
    doc_id = upload(authed, make_pdf_bytes(["澳觅"]))
    authed.post(f"/api/kb/docs/{doc_id}/complete")
    assert put(authed, doc_id, 0, b"x").status_code == 409
    import app.api.routes_kb as m
    monkeypatch.setattr(m, "MAX_PART", 10)
    d2 = init(authed, size=100)
    assert put(authed, d2, 0, b"x" * 11).status_code == 413


def test_complete_rejects_non_pdf(authed, kb_dir):
    doc_id = upload(authed, b"hello world, not a pdf")
    assert authed.post(f"/api/kb/docs/{doc_id}/complete").status_code == 422
    assert authed.get(f"/api/kb/docs/{doc_id}").json()["process_status"] == "failed"
    assert not (kb_dir / f"{doc_id}.pdf.part").exists() and not (kb_dir / f"{doc_id}.pdf").exists()


def test_complete_rejects_incomplete_upload(authed):
    doc_id = init(authed, size=300)
    put(authed, doc_id, 0, b"%PDF-" + b"x" * 95)
    assert authed.post(f"/api/kb/docs/{doc_id}/complete").status_code == 409


def test_complete_rejects_duplicate_file(authed):
    data = make_pdf_bytes(["澳觅"])
    first = upload(authed, data, title="第一份")
    assert authed.post(f"/api/kb/docs/{first}/complete").status_code == 200
    second = upload(authed, data, title="第二份")
    r = authed.post(f"/api/kb/docs/{second}/complete")
    assert r.status_code == 409 and "第一份" in str(r.json()["detail"])


def test_init_rejects_too_large_and_non_pdf_name(authed):
    body = {"title": "t", "filename": "a.pdf", "size_bytes": 1024**3 + 1, "effective_date": "2026-01-01",
            "status": "active"}
    assert authed.post("/api/kb/docs", json=body).status_code == 413
    assert authed.post("/api/kb/docs", json={**body, "size_bytes": 0}).status_code == 413
    assert authed.post("/api/kb/docs", json={**body, "size_bytes": 10, "filename": "a.docx"}).status_code == 422
    assert authed.post("/api/kb/docs", json={**body, "size_bytes": 10, "filename": "A.PDF"}).status_code == 200


def test_part_over_declared_size_rejected(authed, kb_dir):
    doc_id = init(authed, size=100)
    assert put(authed, doc_id, 0, b"x" * 150).status_code == 422
    assert not (kb_dir / f"{doc_id}.pdf.part").exists()


def test_patch_status_and_reprocess_rules(authed, session, kb_dir):
    doc_id = init(authed, size=10)
    assert authed.post(f"/api/kb/docs/{doc_id}/reprocess").status_code == 409   # uploading 不允许
    r = authed.patch(f"/api/kb/docs/{doc_id}", json={"status": "inactive", "title": "新标题",
                                                      "effective_date": "2025-05-05"})
    assert r.status_code == 200
    j = authed.get(f"/api/kb/docs/{doc_id}").json()
    assert (j["status"], j["title"], j["effective_date"]) == ("inactive", "新标题", "2025-05-05")
    assert authed.patch(f"/api/kb/docs/{doc_id}", json={"status": "bogus"}).status_code == 422
    ready = ready_doc(session, kb_dir, "x", ["澳觅"])
    assert authed.post(f"/api/kb/docs/{ready.id}/reprocess").status_code == 200
    assert authed.get(f"/api/kb/docs/{ready.id}").json()["process_status"] == "queued"
    assert authed.post(f"/api/kb/docs/{ready.id}/reprocess").status_code == 409   # queued 不允许


def test_delete_removes_rows_and_files(authed, session, kb_dir):
    doc_id = ready_doc(session, kb_dir, "x", ["澳觅"]).id
    (kb_dir / f"{doc_id}.pdf.part").write_bytes(b"x")
    assert authed.delete(f"/api/kb/docs/{doc_id}").status_code == 200
    assert not (kb_dir / f"{doc_id}.pdf").exists() and not (kb_dir / f"{doc_id}.pdf.part").exists()
    session.expire_all()
    assert session.get(KbDoc, doc_id) is None and session.query(KbChunk).count() == 0
    assert authed.delete(f"/api/kb/docs/{doc_id}").status_code == 404


def test_list_docs_newest_first(authed, session, kb_dir):
    a = ready_doc(session, kb_dir, "a", ["澳觅"])
    b = ready_doc(session, kb_dir, "b", ["澳觅"])
    rows = authed.get("/api/kb/docs").json()
    assert [r["id"] for r in rows] == [b.id, a.id] and "pages" not in rows[0]


def test_doc_detail_lists_empty_pages(authed, session, kb_dir):
    doc = ready_doc(session, kb_dir, "x", ["澳觅商家", None])
    j = authed.get(f"/api/kb/docs/{doc.id}").json()
    assert j["empty_pages"] == [2]
    assert [p["page_no"] for p in j["pages"]] == [1, 2] and j["pages"][0]["n_chars"] > 0


def test_file_download_inline(authed, session, kb_dir):
    doc = ready_doc(session, kb_dir, "x", ["澳觅"])
    r = authed.get(f"/api/kb/docs/{doc.id}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline") and r.content.startswith(b"%PDF-")


def test_search_endpoint(authed, session, kb_dir):
    ready_doc(session, kb_dir, "年刊", ["葡挞好吃", "澳觅合作商家超5,700家"])
    r = authed.post("/api/kb/search", json={"query": "澳觅合作商家有多少"})
    assert r.status_code == 200
    top = r.json()[0]
    assert top["doc_title"] == "年刊" and top["page_no"] == 2 and top["effective_date"] == "2026-01-01"
    assert authed.post("/api/kb/search", json={"query": "x", "limit": 21}).status_code == 422


def test_search_without_embedder_returns_503(session_factory, kb_dir, user_alice, monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    with TestClient(create_app(session_factory)) as c:
        login(c, "alice", "correct")
        r = c.post("/api/kb/search", json={"query": "澳觅"})
    assert r.status_code == 503 and "ARK_API_KEY" in r.json()["detail"]


def test_search_embedder_failure_returns_502(session_factory, session, kb_dir, user_alice):
    ready_doc(session, kb_dir, "年刊", ["澳觅"])
    with TestClient(create_app(session_factory, embedder=FakeEmbedder(fail_after=0))) as c:
        login(c, "alice", "correct")
        r = c.post("/api/kb/search", json={"query": "澳觅"})
    assert r.status_code == 502 and "fake embedder" in r.json()["detail"]
