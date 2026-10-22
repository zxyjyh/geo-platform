"""种子数据：题库 v3、别名表 v1、7 个平台、默认设置。可以重复执行，已有的行不覆盖。"""
import csv

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ROOT
from app.models import Alias, Platform, Question, Setting

QUESTIONS_CSV = ROOT / "data" / "questions" / "questions-v3-15.csv"
QUESTION_VERSION = "v3"

ALIASES_V1 = {
    "aomi": ["澳觅", "澳覓", "Aomi", "aomi", "AOMI"],
    "mfood": ["mFood", "MFood", "mfood", "澳門Food", "澳门Food"],
    "shanfeng": ["闪蜂", "閃蜂"],
}

PLATFORMS = [
    ("smzdm", "什么值得买", "smzdm.com"),
    ("toutiao", "头条号", "toutiao.com"),
    ("baijiahao", "百家号", "baijiahao.baidu.com"),
    ("sohu", "搜狐", "sohu.com"),
    ("bilibili", "B站", "bilibili.com"),
    ("netease", "网易号", "163.com"),
    ("zhihu", "知乎", "zhihu.com"),
]

DEFAULT_SETTINGS = {
    "api_channel": "api-custom",
    "question_version": QUESTION_VERSION,
    "alias_version": "1",
    "repeats_per_question_api": "1",
    "brand_mark_version": "0",
    "weak_recent_n": "7",
    "weak_mention_ratio": "0.5",
    "platform_window_days": "30",
    "price_per_search_yuan": "",
    "price_input_per_1k_yuan": "",
    "price_output_per_1k_yuan": "",
}


def seed_questions(session: Session) -> None:
    with open(QUESTIONS_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if session.get(Question, (row["qid"], QUESTION_VERSION)) is None:
                session.add(Question(qid=row["qid"], version=QUESTION_VERSION, text=row["question"],
                                     branded=row["branded"] == "Y", scene=row["scene"],
                                     intent=row["intent"], status=row["status"]))


def seed_aliases(session: Session) -> None:
    if session.scalars(select(Alias).where(Alias.version == 1)).first() is None:
        session.add_all(Alias(version=1, entity=e, alias=a) for e, names in ALIASES_V1.items() for a in names)


def seed_platforms(session: Session) -> None:
    for key, name, suffix in PLATFORMS:
        if session.get(Platform, key) is None:
            session.add(Platform(key=key, name=name, domain_suffix=suffix, publishable=True))


def seed_settings(session: Session) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        if session.get(Setting, key) is None:
            session.add(Setting(key=key, value=value))


def seed_all(session: Session) -> None:
    seed_questions(session)
    seed_aliases(session)
    seed_platforms(session)
    seed_settings(session)
    session.commit()
