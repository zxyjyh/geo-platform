from datetime import date

import pytest

from app.attribution import attribution_daily, match_marks
from app.metrics import Ratio
from app.models import BrandMark, Setting
from app.seed import seed_all
from tests.builders import add_run, add_source

D = date(2026, 10, 22)
AOMI = {"mention": {"aomi": True}, "order": {"aomi": 1}}


@pytest.fixture(autouse=True)
def seeded(session):
    seed_all(session)


def mk(kind, value):
    return BrandMark(version=1, kind=kind, value=value)


def test_match_website_case_insensitive():
    assert [m.value for m in match_marks("官网 AomiApp.com 下载", [mk("website", "aomiapp.com")])] == ["aomiapp.com"]


def test_match_phone_separators():
    m = [mk("phone", "28888888")]
    for t in ("客服 2888-8888", "致电 (2888) 8888", "+853 2888 8888"):
        assert match_marks(t, m), t


def test_match_phone_not_inside_longer_number():
    assert match_marks("订单号 1288888888 99", [mk("phone", "28888888")]) == []


def test_attribution_counts(session):
    session.add(mk("website", "aomiapp.com"))
    session.get(Setting, "brand_mark_version").value = "1"
    session.commit()
    add_run(session, "Q01", D, text="下载澳觅：aomiapp.com", **AOMI)            # 正文给官网
    add_source(session, add_run(session, "Q03", D, text="澳觅", **AOMI),       # 品牌题也算；信源是自有内容
               "https://www.aomiapp.com/a", is_owned=True)
    add_run(session, "Q02", D, text="澳觅", **AOMI)                            # 什么都没有
    add_run(session, "Q04", D, text="aomiapp.com")                             # 没提澳觅，不进分母
    add_run(session, "Q05", D, channel="api-plugin", text="澳觅 aomiapp.com", **AOMI)   # 别的渠道
    a = attribution_daily(session, D, "api-custom", 1)
    assert a.configured and a.version == 1 and a.text == Ratio(1, 3) and a.source == Ratio(1, 3)
    hits = {h.qid: h for h in a.hits}
    assert set(hits) == {"Q01", "Q02", "Q03"}
    assert hits["Q01"].marks == ["aomiapp.com"] and not hits["Q01"].owned_source
    assert hits["Q03"].owned_source and hits["Q03"].marks == []


def test_attribution_unconfigured(session):
    add_run(session, "Q01", D, mention={"aomi": True}, order={"aomi": 1}, text="澳觅 aomiapp.com")
    a = attribution_daily(session, D, "api-custom", 1)   # brand_mark_version = "0"
    assert a.configured is False and a.text == Ratio(0, 1)
