"""URL 规范化（同一篇文章的不同写法算一篇）和平台映射。"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DROP_PARAMS = {"spm", "from", "share_token", "source"}


def _host(netloc: str) -> str:
    host = netloc.lower()
    # scheme 统一成 https 之后，:80 / :443 都是默认端口
    for port in (":80", ":443"):
        if host.endswith(port):
            host = host[: -len(port)]
    while True:
        for p in ("www.", "m."):
            if host.startswith(p):
                host = host[len(p):]
                break
        else:
            return host


def normalize_url(url: str) -> str:
    """scheme 统一 https；host 小写并去掉开头的 www. / m.；删掉追踪参数（utm_*、spm、from、share_token、source），
    其余参数按名字排序；去掉 fragment 和末尾的 /。路径大小写保留。"""
    url = url.strip()
    if "://" not in url and not url.startswith("//"):
        url = "//" + url  # 不带 scheme 的「sohu.com/a/1」，否则 urlsplit 会把 host 当成路径
    parts = urlsplit(url)
    params = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                    if not (k.lower().startswith("utm_") or k.lower() in DROP_PARAMS))
    return urlunsplit(("https", _host(parts.netloc), parts.path.rstrip("/"), urlencode(params), ""))


def platform_for(domain: str, platforms) -> str | None:
    """域名等于后缀或以 .后缀 结尾就算匹配；多个都能匹配时取最长的后缀。"""
    d = domain.lower().split(":")[0]
    best = None
    for p in platforms:
        s = p.domain_suffix.lower()
        if (d == s or d.endswith("." + s)) and (best is None or len(s) > len(best.domain_suffix)):
            best = p
    return best.key if best else None


def is_owned(url: str, prefixes) -> bool:
    u = normalize_url(url)
    for p in prefixes:
        pre = normalize_url(p.url_prefix)
        if u == pre or u.startswith(pre + "/") or u.startswith(pre + "?"):
            return True
    return False
