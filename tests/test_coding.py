from app.coding import code_answer, load_aliases
from app.seed import seed_all

A = {"aomi": ["澳觅", "澳覓", "Aomi", "aomi", "AOMI"], "mfood": ["mFood", "MFood", "mfood", "澳門Food", "澳门Food"], "shanfeng": ["闪蜂", "閃蜂"]}


def test_order_among_three_only():
    r = code_answer("推荐 Klook、mFood，其次澳覓；閃蜂也行", A)
    assert r.order == {"mfood": 1, "aomi": 2, "shanfeng": 3}


def test_not_mentioned_is_none():
    r = code_answer("用美团吧", A)
    assert r.mention == {"aomi": False, "mfood": False, "shanfeng": False} and r.order["aomi"] is None


def test_earliest_alias_wins():
    # 闪蜂 的第一个别名出现得晚，但 閃蜂 出现得早 → 取最早位置
    r = code_answer("閃蜂、澳觅、再说一次闪蜂", A)
    assert r.order == {"shanfeng": 1, "aomi": 2, "mfood": None}


def test_trial_custom_regression(trial_custom_texts):     # fixture：10 道不带品牌名的题的 answer_text
    rs = [code_answer(t, A) for t in trial_custom_texts]
    assert sum(r.mention["aomi"] for r in rs) == 8
    assert sum(r.mention["mfood"] for r in rs) == 7
    assert sum(r.mention["shanfeng"] for r in rs) == 5
    assert sum(r.order["aomi"] == 1 for r in rs) == 4   # 和 analysis/quick_scan.py 的结果一致


def test_load_aliases_v1(session):
    seed_all(session)
    got = load_aliases(session, 1)
    assert {k: sorted(v) for k, v in got.items()} == {k: sorted(v) for k, v in A.items()}


def test_mention_snippet_first_occurrence_sentence():
    from app.coding import mention_snippet
    text = "澳门外卖有几个选择。\n首推 mFood，覆盖广。其次是澳覓，游客友好！闪蜂也行"
    assert mention_snippet(text, A["aomi"]) == "其次是澳覓，游客友好！"
    assert mention_snippet(text, ["美团"]) is None
    long = "很长的铺垫" * 20 + "澳觅" + "很长的后文" * 20
    s = mention_snippet(long, ["澳觅"], width=30)
    assert "澳觅" in s and len(s) <= 32 and s.startswith("…") and s.endswith("…")
