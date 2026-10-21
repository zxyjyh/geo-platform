from datetime import date, timedelta

import pytest

from app.analysis import domain_ranking, owned_citations, platform_counts, reference_articles, weak_questions
from app.collector import run_daily
from app.models import SourceTag
from app.seed import seed_all
from app.urls import normalize_url
from tests.builders import add_run, add_source
from tests.fakes import FakeClient

D0, D1 = date(2026, 10, 22), date(2026, 10, 23)
DAYS = [D1 - timedelta(days=k) for k in range(7)]


@pytest.fixture(autouse=True)
def seeded(session):
    seed_all(session)


@pytest.fixture
def daily_from_trial(session, tmp_path):
    run_daily(session, FakeClient.from_trial("custom"), D0, "api-custom", tmp_path, sleep_s=0)


def test_platform_counts_include_zero(session, daily_from_trial):   # fixture：run_daily(FakeClient.from_trial("custom"), D0)
    pc = {p.key: p for p in platform_counts(session, "api-custom", D0, D1)}
    assert len(pc) == 7 and pc["zhihu"].count == 0 and pc["zhihu"].verified is False
    counts = [p.count for p in platform_counts(session, "api-custom", D0, D1)]
    assert counts == sorted(counts, reverse=True)


def test_platform_counts_other_channel_and_qid_filter(session, daily_from_trial):
    assert all(p.count == 0 for p in platform_counts(session, "api-plugin", D0, D1))
    total = sum(p.count for p in platform_counts(session, "api-custom", D0, D1))
    q01 = sum(p.count for p in platform_counts(session, "api-custom", D0, D1, qids=["Q01"]))
    assert 0 <= q01 <= total


def test_domain_ranking_merges_www_and_m(session):
    r = add_run(session, "Q01", D0)
    add_source(session, r, "https://m.sohu.com/a/1", rank=1)
    add_source(session, r, "https://www.sohu.com/a/2", rank=2)
    add_source(session, r, "https://zhihu.com/q/3", rank=3)
    assert domain_ranking(session, "api-custom", D0, D0) == [("sohu.com", 2), ("zhihu.com", 1)]


def test_weak_mention_low(session):         # 某题 7 条 run 里只有 3 条提到澳觅 → reasons == ["mention_low"]
    for k, d in enumerate(DAYS):
        add_run(session, "Q01", d, mention={"aomi": k < 3}, order={"aomi": 1 if k < 3 else None})
    w = {x.qid: x for x in weak_questions(session, "api-custom", D1)}
    assert w["Q01"].reasons == ["mention_low"] and (w["Q01"].n_runs, w["Q01"].aomi_mentions) == (7, 3)


def test_weak_competitor_ahead(session):    # 7 条都提到澳觅，4 条 mFood 排第一、澳觅排第一的只有 2 条
    for k, d in enumerate(DAYS):
        if k < 4:
            order = {"mfood": 1, "aomi": 2}
        elif k < 6:
            order = {"aomi": 1, "mfood": 2}
        else:
            order = {"aomi": 1}
        add_run(session, "Q02", d, mention={"aomi": True, "mfood": "mfood" in order}, order=order)
    w = {x.qid: x for x in weak_questions(session, "api-custom", D1)}
    assert w["Q02"].reasons == ["competitor_ahead"]
    assert (w["Q02"].aomi_first, w["Q02"].competitor_first) == (3, 4)


def test_weak_uses_only_recent_n_and_skips_branded_and_healthy(session):
    for k in range(10):                      # 最近 7 天都提到澳觅，更早 3 天没提到
        d = D1 - timedelta(days=k)
        add_run(session, "Q04", d, mention={"aomi": k < 7}, order={"aomi": 1 if k < 7 else None})
    add_run(session, "Q03", D1)              # 带品牌名的题不参与
    assert weak_questions(session, "api-custom", D1) == []


def test_ref_articles_dedupe_url_variants(session):   # 同一篇文章以 m.sohu.com?utm=… 和 www.sohu.com 两种写法出现 → 一条记录，count == 2
    r1 = add_run(session, "Q01", D0)
    r2 = add_run(session, "Q01", D1)
    add_source(session, r1, "https://m.sohu.com/a/9?utm_source=doubao", title="旧标题")
    add_source(session, r2, "https://www.sohu.com/a/9", title="新标题")
    refs = reference_articles(session, "Q01", "api-custom", D1)
    assert len(refs) == 1
    assert (refs[0].count, refs[0].title, refs[0].url) == (2, "新标题", "https://www.sohu.com/a/9")
    assert refs[0].platform_key == "sohu" and refs[0].external_geo is False


def test_ref_articles_window(session):
    old = add_run(session, "Q01", D1 - timedelta(days=30))
    add_source(session, old, "https://sohu.com/a/old")
    assert reference_articles(session, "Q01", "api-custom", D1, days=30) == []


def test_external_geo_flag(session):        # 给 SourceTag 加一条 external_geo → RefArticle.external_geo is True
    r = add_run(session, "Q01", D0)
    add_source(session, r, "https://m.sohu.com/a/9")
    session.add(SourceTag(url_norm=normalize_url("https://sohu.com/a/9"), tag="external_geo", note="来源不明"))
    session.commit()
    assert reference_articles(session, "Q01", "api-custom", D0)[0].external_geo is True


def test_owned_citations(session):
    r = add_run(session, "Q01", D0)
    add_source(session, r, "https://aomi.mo/x", is_owned=True)
    add_source(session, r, "https://sohu.com/a/1", rank=2)
    assert [s.url for s in owned_citations(session, "api-custom", D0, D0)] == ["https://aomi.mo/x"]
