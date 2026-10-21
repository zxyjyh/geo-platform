import importlib.util
from datetime import date

from app.collector import run_daily
from app.config import ROOT
from app.importer import import_trial
from app.seed import seed_all
from tests.fakes import FakeClient

spec = importlib.util.spec_from_file_location("compare_rounds", ROOT / "scripts" / "compare_rounds.py")
compare_rounds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_rounds)

D = date(2026, 10, 22)


def test_same_responses_compare_identical(session, tmp_path):
    seed_all(session)
    import_trial(session)
    run_daily(session, FakeClient.from_trial("custom"), D, "api-custom", tmp_path, sleep_s=0)
    rows = compare_rounds.compare(session, "trial", D, "api-custom")
    assert len(rows) == 15
    assert all(r.jaccard == 1.0 and r.aomi_a == r.aomi_b for r in rows)


def test_different_sources_lower_jaccard(session, tmp_path):
    seed_all(session)
    import_trial(session)
    other = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "用美团", "annotations": [
        {"type": "url_citation", "url": "https://example.com/x", "title": "x"}]}]}], "usage": {}}
    run_daily(session, FakeClient.from_trial("custom", overrides={"Q01": other}), D, "api-custom", tmp_path, sleep_s=0)
    q01 = {r.qid: r for r in compare_rounds.compare(session, "trial", D, "api-custom")}["Q01"]
    assert q01.jaccard == 0.0 and q01.aomi_a is True and q01.aomi_b is False
