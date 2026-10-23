from scripts.kb_eval import evaluate, load_rows
from tests.builders import ready_doc
from tests.fakes import FakeEmbedder


def test_evaluate_counts_hits(session, tmp_path):
    ready_doc(session, tmp_path, "年刊", ["葡挞好吃", "澳覓合作商家超5,700家"])
    rows = [
        {"qid": "E01", "question": "澳觅合作商家有多少", "expect_page": "2", "expect_half": "", "expect_text": "合作商家超5,700家"},
        {"qid": "E02", "question": "澳觅合作商家有多少", "expect_page": "1", "expect_half": "", "expect_text": "合作商家超5,700家"},
    ]
    res = evaluate(session, rows, FakeEmbedder())
    assert [r.rank for r in res] == [1, None]


def test_evaluate_unexpected_row_is_recorded_not_counted(session, tmp_path):
    ready_doc(session, tmp_path, "年刊", ["澳覓合作商家超5,700家"])
    rows = [{"qid": "E09", "question": "澳觅合作商家", "expect_page": "", "expect_half": "", "expect_text": ""}]
    [r] = evaluate(session, rows, FakeEmbedder())
    assert r.rank is None and not r.counted and r.top == (1, "", "澳覓合作商家超5,700家")


def test_evaluate_half_must_match_when_given(session, tmp_path):
    ready_doc(session, tmp_path, "年刊", ["澳覓合作商家超5,700家"])  # 竖版页，half 为空串
    rows = [{"qid": "E01", "question": "澳觅合作商家", "expect_page": "1", "expect_half": "R", "expect_text": "合作商家"}]
    assert evaluate(session, rows, FakeEmbedder())[0].rank is None


def test_load_rows_reads_shipped_csv():
    rows = load_rows()
    assert len(rows) == 10 and sum(1 for r in rows if r["expect_page"]) == 8
