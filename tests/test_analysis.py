from datetime import date, datetime, time, timedelta

import pytest

from app.analysis import (citation_lifecycle, domain_ranking, owned_citations, platform_counts, reference_articles,
                          weak_questions)
from app.collector import run_daily
from app.models import Platform, SourceTag
from app.seed import seed_all
from app.urls import normalize_url
from app.timeutil import CST
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
    # 种子 3 个平台在 trial 里都被引用过；另加一个零引用平台，验证 count=0 也列出（verified=False）
    session.add(Platform(key="zero", name="零引用", domain_suffix="zero.example.com", publishable=True))
    session.commit()
    pc = {p.key: p for p in platform_counts(session, "api-custom", D0, D1)}
    assert len(pc) == 4 and pc["zero"].count == 0 and pc["zero"].verified is False
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


def test_weak_skips_branded_and_healthy(session):
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


def test_ref_articles_latest_is_by_collect_date_not_collected_at(session):
    # 补跑往日时 collected_at 是当下：10-22 的补跑比 10-23 的正常采集 collected_at 更晚，但"最近一次"应是 10-23
    from datetime import datetime

    from app.timeutil import CST
    late = datetime(2026, 10, 24, 9, 0, tzinfo=CST)
    r_old = add_run(session, "Q01", D0, collected_at=late)
    r_new = add_run(session, "Q01", D1)
    add_source(session, r_old, "https://sohu.com/a/9", title="旧标题")
    add_source(session, r_new, "https://sohu.com/a/9", title="新标题")
    assert reference_articles(session, "Q01", "api-custom", D1)[0].title == "新标题"


def test_weak_window_really_limits_to_recent_n(session):
    # 最近 7 天都提到澳觅，更早 10 天都没提到：全取是 7/17 < 50% 会误判；只取最近 7 条是健康的
    for k in range(17):
        d = D1 - timedelta(days=k)
        add_run(session, "Q05", d, mention={"aomi": k < 7}, order={"aomi": 1 if k < 7 else None})
    assert [w.qid for w in weak_questions(session, "api-custom", D1)] == []


# 引用周期：L0 是渠道第一天，L1 = L0+1 …
L0 = date(2026, 9, 1)
L1, L2, L3 = (L0 + timedelta(days=k) for k in (1, 2, 3))
A = "https://www.sohu.com/a/1"


def _cite(session, qid, d, url, channel="api-custom", round_="daily", publish_time=None, rank=1):
    add_source(session, add_run(session, qid, d, channel=channel, round_=round_), url, rank=rank,
               publish_time=publish_time)


def test_lifecycle_basic(session):
    add_run(session, "Q09", L0)                              # 渠道 L0 就有数据
    pt = datetime.combine(L1 - timedelta(days=5), time(9), tzinfo=CST)
    _cite(session, "Q01", L1, "https://m.sohu.com/a/1", publish_time=pt)
    _cite(session, "Q02", L1, A)
    run = add_run(session, "Q04", L3)                        # 这条 run 里 A 出现两次，只算一次被引
    add_source(session, run, A, rank=1)
    add_source(session, run, A + "?utm_source=x", rank=2)
    rows = {l.url_norm: l for l in citation_lifecycle(session, "api-custom", L0, L3)}
    a = rows[normalize_url(A)]
    assert (a.n_citations, a.first_date, a.last_date, a.active_days, a.span_days) == (3, L1, L3, 2, 3)
    assert a.persistence == pytest.approx(2 / 3) and a.energy == pytest.approx(1.5)
    assert (a.lag_days, a.left_censored, a.publish_suspect) == (5, False, False)
    assert a.publish_time == pt


def test_lifecycle_first_day_is_censored(session):        # B 在渠道第一天 L0 就被引用
    pt = datetime.combine(L0 - timedelta(days=3), time(9), tzinfo=CST)
    _cite(session, "Q01", L0, "https://zhihu.com/b", publish_time=pt)
    _cite(session, "Q02", L2, "https://zhihu.com/b")
    b = citation_lifecycle(session, "api-custom", L0, L3)[0]
    assert b.left_censored and b.lag_days is None and b.first_date == L0


def test_lifecycle_window_start_censors(session):         # C 在 L1、L3 被引；窗口从 L1 开始 → L1 是窗口第一个可观测日
    add_run(session, "Q09", L0)
    _cite(session, "Q01", L1, "https://zhihu.com/c")
    _cite(session, "Q02", L3, "https://zhihu.com/c")
    c = citation_lifecycle(session, "api-custom", L1, L3)[0]
    assert c.left_censored and c.first_date == L1
    assert citation_lifecycle(session, "api-custom", L0, L3)[0].left_censored is False


def test_lifecycle_publish_after_first_citation(session):
    add_run(session, "Q09", L0)
    _cite(session, "Q01", L1, "https://zhihu.com/x", publish_time=datetime.combine(L2, time(9), tzinfo=CST))
    x = citation_lifecycle(session, "api-custom", L0, L3)[0]
    assert x.lag_days is None and x.publish_suspect


def test_lifecycle_excludes_other_channel_and_trial(session):
    add_run(session, "Q09", L0)
    _cite(session, "Q01", L1, "https://zhihu.com/y", channel="api-plugin")
    _cite(session, "Q02", L1, "https://zhihu.com/y", round_="trial")
    assert citation_lifecycle(session, "api-custom", L0, L3) == []


def test_lifecycle_order_flags_and_latest_title(session):
    add_run(session, "Q09", L0)
    session.add(SourceTag(url_norm=normalize_url("https://zhihu.com/m"), tag="external_geo")); session.commit()
    _cite(session, "Q01", L2, "https://zhihu.com/n")
    _cite(session, "Q01", L1, "https://zhihu.com/m")
    add_source(session, add_run(session, "Q02", L1), "https://zhihu.com/n", title="旧标题")
    add_source(session, add_run(session, "Q04", L3), "https://zhihu.com/n", title="新标题", is_owned=True)
    rows = citation_lifecycle(session, "api-custom", L0, L3)
    assert [r.url_norm for r in rows] == [normalize_url("https://zhihu.com/n"), normalize_url("https://zhihu.com/m")]
    assert rows[0].title == "新标题" and rows[0].is_owned and not rows[0].external_geo and rows[1].external_geo


def test_platform_counts_attrs_do_not_affect_order(session):
    from app.models import Platform
    session.get(Platform, "sohu").review_strictness = "strict"
    smzdm = session.get(Platform, "smzdm")
    smzdm.review_strictness, smzdm.allows_links, smzdm.notes = "loose", "yes", "可带链接"
    session.commit()
    _cite(session, "Q01", D0, "https://www.sohu.com/a/1")
    _cite(session, "Q02", D0, "https://www.sohu.com/a/2")
    _cite(session, "Q04", D0, "https://www.smzdm.com/p/1")
    pc = platform_counts(session, "api-custom", D0, D0)
    assert [p.key for p in pc[:2]] == ["sohu", "smzdm"]
    assert (pc[0].review_strictness, pc[1].review_strictness, pc[1].allows_links, pc[1].notes) == \
        ("strict", "loose", "yes", "可带链接")
