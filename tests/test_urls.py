from app.models import OwnedPrefix, Platform
from app.urls import is_owned, normalize_url, platform_for


def test_normalize_url_variants_equal():
    a = normalize_url("https://m.sohu.com/a/123?utm_source=x&spm=1#top")
    assert a == normalize_url("http://www.sohu.com/a/123/") == "https://sohu.com/a/123"


def test_normalize_url_keeps_other_params_and_path_case():
    assert normalize_url("https://WWW.Zhihu.com/question/A1?id=5&from=timeline&share_token=z") == "https://zhihu.com/question/A1?id=5"


def test_normalize_url_param_order_irrelevant():
    assert normalize_url("https://x.com/p?b=2&a=1") == normalize_url("https://x.com/p?a=1&b=2")


def test_platform_longest_suffix(platforms):
    assert platform_for("post.m.smzdm.com", platforms) == "smzdm"
    assert platform_for("notsohu.com", platforms) is None
    assert platform_for("www.baidu.com", platforms) is None


def test_platform_longest_suffix_takes_longest_match():
    # 后缀嵌套时取最长的：platform_for 是纯函数，用合成平台验证（种子平台后缀互不嵌套）
    nested = [Platform(key="outer", name="外", domain_suffix="example.com", publishable=True),
              Platform(key="inner", name="内", domain_suffix="sub.example.com", publishable=True)]
    assert platform_for("www.sub.example.com", nested) == "inner"
    assert platform_for("example.com", nested) == "outer"


def test_is_owned_respects_boundary():
    prefixes = [OwnedPrefix(name="官网", url_prefix="https://www.aomi.mo")]
    assert is_owned("http://aomi.mo/about?utm_source=x", prefixes)
    assert is_owned("https://aomi.mo", prefixes)
    assert not is_owned("https://aomi.mo.evil.com/x", prefixes)
    assert not is_owned("https://sohu.com/a/1", [])


def test_normalize_url_without_scheme():
    # 设置页里录入的自有前缀、外部 GEO 标签，常常不带 scheme
    assert normalize_url("sohu.com/a/1") == normalize_url("www.sohu.com/a/1/") == "https://sohu.com/a/1"
    assert normalize_url("//m.sohu.com/a/1") == "https://sohu.com/a/1"


def test_normalize_url_drops_default_ports():
    assert normalize_url("https://www.sohu.com:443/a") == "https://sohu.com/a"
    assert normalize_url("http://m.sohu.com:80/a") == "https://sohu.com/a"
    assert normalize_url("https://sohu.com:8443/a") == "https://sohu.com:8443/a"


def test_is_owned_with_schemeless_prefix():
    assert is_owned("https://www.aomi.mo/about", [OwnedPrefix(name="官网", url_prefix="aomi.mo")])
