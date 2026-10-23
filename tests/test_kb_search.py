from app.kb.search import search
from tests.builders import ready_doc
from tests.fakes import FakeEmbedder


def test_search_returns_page_and_title(session, tmp_path):
    ready_doc(session, tmp_path, "年刊", ["葡挞好吃", "澳覓合作商家超5,700家"])
    hits = search(session, "澳觅合作商家有多少", FakeEmbedder())
    assert hits[0].doc_title == "年刊" and hits[0].page_no == 2


def test_search_keyword_matches_traditional_doc(session, tmp_path):
    ready_doc(session, tmp_path, "年刊", ["註冊用戶超300萬", "葡挞好吃"])
    hits = search(session, "注册用户", FakeEmbedder())
    assert hits[0].page_no == 1 and hits[0].keyword_rank == 1


def test_search_excludes_inactive_and_unready(session, tmp_path):
    ready_doc(session, tmp_path, "旧版", ["澳觅商家5500"], status="inactive")
    ready_doc(session, tmp_path, "处理失败", ["澳觅商家5600"], process_status="failed")
    ready_doc(session, tmp_path, "现行", ["澳觅商家5700"])
    assert {h.doc_title for h in search(session, "澳觅商家", FakeEmbedder())} == {"现行"}


def test_search_skips_chunks_with_other_dim(session, tmp_path):
    ready_doc(session, tmp_path, "旧模型", ["澳觅"], embedder=FakeEmbedder(dim=32))
    assert search(session, "澳觅", FakeEmbedder(dim=64)) == []


def test_search_blank_query_does_not_call_embedder(session):
    e = FakeEmbedder()
    assert search(session, "   ", e) == [] and e.calls == 0


def test_search_empty_kb(session):
    assert search(session, "澳觅", FakeEmbedder()) == []
