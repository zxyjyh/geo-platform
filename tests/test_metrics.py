from datetime import date

import pytest

from app.metrics import Ratio, daily_metrics, trend
from app.seed import seed_all
from tests.builders import UNBRANDED, add_run

D = date(2026, 10, 22)


@pytest.fixture(autouse=True)
def seeded(session):
    seed_all(session)


@pytest.fixture
def day_with_codings(session):
    """10 题都有效：澳觅 8（其中排第一 4）、mFood 7、闪蜂 5。"""
    for i, qid in enumerate(UNBRANDED):
        m = {"aomi": i < 8, "mfood": 1 <= i <= 7, "shanfeng": i < 5}   # i=4..7 都有 mFood 排在澳觅前
        present = [e for e in ("aomi", "mfood", "shanfeng") if m[e]]
        if i < 4:
            ranking = present                                  # 澳觅第一
        else:
            ranking = [e for e in present if e != "aomi"] + (["aomi"] if m["aomi"] else [])
        add_run(session, qid, D, mention=m, order={e: k + 1 for k, e in enumerate(ranking)})


def test_mention_8_of_10(session, day_with_codings):          # 10 题都有效，其中 8 题提到澳觅
    m = daily_metrics(session, D, "api-custom", 1)
    assert (m.mention["aomi"].num, m.mention["aomi"].den) == (8, 10)
    assert (m.first["aomi"].num, m.n_expected, m.missing_qids, m.selfcheck_failures) == (4, 10, [], [])


def test_branded_and_other_channel_excluded(session):        # Q03 提到澳觅、api-plugin 的数据都不计入
    add_run(session, "Q01", D)
    add_run(session, "Q03", D, mention={"aomi": True}, order={"aomi": 1})
    add_run(session, "Q02", D, channel="api-plugin", mention={"aomi": True}, order={"aomi": 1})
    add_run(session, "Q04", D, round_="trial", mention={"aomi": True}, order={"aomi": 1})
    m = daily_metrics(session, D, "api-custom", 1)
    assert m.n_valid == 1 and m.mention["aomi"] == Ratio(0, 1)


def test_partial_day_denominator_and_missing(session):       # 只有 6 题有效，Q05 failed，另外 3 题完全没有
    for qid in ["Q01", "Q02", "Q04", "Q06", "Q07", "Q08"]:
        add_run(session, qid, D, mention={"aomi": True}, order={"aomi": 1})
    add_run(session, "Q05", D, status="failed")
    m = daily_metrics(session, D, "api-custom", 1)
    assert m.n_valid == 6 and m.mention["aomi"].den == 6 and len(m.missing_qids) == 4
    assert m.missing_qids == ["Q05", "Q09", "Q10", "Q11"]


def test_void_counts_as_missing(session):
    add_run(session, "Q01", D, status="void")
    m = daily_metrics(session, D, "api-custom", 1)
    assert m.n_valid == 0 and "Q01" in m.missing_qids


def test_no_data_day_is_none_not_zero(session):
    m = daily_metrics(session, D, "api-custom", 1)
    assert m.n_valid == 0 and m.mention["aomi"].pct() is None
    assert m.share["aomi"].pct() is None and len(m.missing_qids) == 10


def test_share(session, day_with_codings):                  # 澳觅 8、mFood 7、闪蜂 5 → share aomi == Ratio(8, 20)
    m = daily_metrics(session, D, "api-custom", 1)
    assert m.share == {"aomi": Ratio(8, 20), "mfood": Ratio(7, 20), "shanfeng": Ratio(5, 20)}
    assert m.share["aomi"].pct() == 40.0


def test_only_requested_alias_version(session):
    add_run(session, "Q01", D, mention={"mfood": True}, order={"mfood": 1}, alias_version=2)
    assert daily_metrics(session, D, "api-custom", 1).n_valid == 0
    assert daily_metrics(session, D, "api-custom", 2).mention["mfood"] == Ratio(1, 1)


def test_selfcheck_flags_first_gt_mention(session):         # order_aomi=1 但 mention_aomi=False 的坏数据 → 报 "first_aomi"
    add_run(session, "Q01", D, mention={"aomi": False}, order={"aomi": 1})
    m = daily_metrics(session, D, "api-custom", 1)
    assert "first_aomi" in m.selfcheck_failures


def test_trend_includes_empty_days(session):                # 3 天里只有 1 天有数据 → 输出 3 条
    add_run(session, "Q01", date(2026, 10, 21), mention={"aomi": True}, order={"aomi": 1})
    t = trend(session, date(2026, 10, 20), date(2026, 10, 22), "api-custom", 1)
    assert [m.date for m in t] == [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]
    assert [m.n_valid for m in t] == [0, 1, 0]


def test_duplicate_valid_runs_for_one_question_flagged(session):
    # 同一天同一题出现两条 valid（比如以后别的采集器用了另一套 run_id），不能被字典悄悄吞掉一条
    add_run(session, "Q01", D, mention={"aomi": True}, order={"aomi": 1})
    add_run(session, "Q01", D, run_id="daily-other-Q01", mention={"aomi": False})
    m = daily_metrics(session, D, "api-custom", 1)
    assert "duplicate_qid" in m.selfcheck_failures
