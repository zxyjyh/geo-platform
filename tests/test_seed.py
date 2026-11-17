from datetime import date, datetime, timezone

from sqlalchemy import select

from app.models import Alias, Platform, Question, Setting
from app.seed import seed_all
from app.timeutil import today_cst


def test_seed_questions_v3(session):
    seed_all(session); seed_all(session)              # 跑两次，验证幂等
    qs = session.scalars(select(Question).where(Question.version == "v3")).all()
    assert len(qs) == 15
    assert {q.qid for q in qs if q.branded} == {"Q03", "Q12", "Q13", "Q14", "Q15"}


def test_seed_aliases_platforms_settings(session):
    seed_all(session)
    assert {a.alias for a in session.scalars(select(Alias).where(Alias.entity == "shanfeng"))} == {"闪蜂", "閃蜂"}
    assert session.get(Platform, "smzdm").domain_suffix == "smzdm.com"
    assert len(session.scalars(select(Platform)).all()) == 3
    assert session.get(Setting, "api_channel").value == "api-custom"


def test_today_cst_when_utc_is_previous_day():
    assert today_cst(datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)) == date(2026, 10, 22)
