from app.kb.text import bm25_scores, normalize, rrf, tokenize


def test_tokenize_folds_traditional():
    assert "澳觅" in tokenize("澳覓合作商家超5,700家")
    assert "注册" in tokenize("註冊用戶")


def test_custom_words_not_split():
    toks = tokenize("用+86手机号注册mFood，再用澳门通付款")
    assert {"+86", "mfood", "澳门通"} <= set(toks)


def test_tokenize_drops_punctuation():
    assert not any(t.strip("，。、：；！？（）,.:;!?() ") == "" for t in tokenize("澳觅，外卖。"))


def test_bm25_prefers_doc_with_query_terms():
    docs = [tokenize("澳觅合作商家超过5700家"), tokenize("葡挞和猪扒包很好吃")]
    s = bm25_scores(tokenize("澳觅商家"), docs)
    assert s[0] > 0 and s[1] == 0


def test_normalize_drops_thousands_separator():
    assert normalize("合作商家超5,700家") == "合作商家超5700家"
    assert "5700" in tokenize("澳覓合作商家超5,700家")


def test_rrf_fuses_and_breaks_ties_by_index():
    # 0 和 2 的分数都是 1/61 + 1/62，相同 → 下标小的在前；1 只有 1/63
    assert [i for i, _ in rrf([[2, 0, 1], [0, 2]])] == [0, 2, 1]
    assert [i for i, _ in rrf([[1], [0]])] == [0, 1]
