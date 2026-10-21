from app.models import OwnedPrefix
from app.urls import is_owned, normalize_url, platform_for


def test_normalize_url_variants_equal():
    a = normalize_url("https://m.sohu.com/a/123?utm_source=x&spm=1#top")
    assert a == normalize_url("http://www.sohu.com/a/123/") == "https://sohu.com/a/123"


def test_normalize_url_keeps_other_params_and_path_case():
    assert normalize_url("https://WWW.Zhihu.com/question/A1?id=5&from=timeline&share_token=z") == "https://zhihu.com/question/A1?id=5"


def test_normalize_url_param_order_irrelevant():
    assert normalize_url("https://x.com/p?b=2&a=1") == normalize_url("https://x.com/p?a=1&b=2")


def test_platform_longest_suffix(platforms):
    assert platform_for("baijiahao.baidu.com", platforms) == "baijiahao"
    assert platform_for("www.baidu.com", platforms) is None
    assert platform_for("post.m.smzdm.com", platforms) == "smzdm"
    assert platform_for("notsohu.com", platforms) is None


def test_is_owned_respects_boundary():
    prefixes = [OwnedPrefix(name="官网", url_prefix="https://www.aomi.mo")]
    assert is_owned("http://aomi.mo/about?utm_source=x", prefixes)
    assert is_owned("https://aomi.mo", prefixes)
    assert not is_owned("https://aomi.mo.evil.com/x", prefixes)
    assert not is_owned("https://sohu.com/a/1", [])
