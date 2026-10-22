import json
from datetime import date
from glob import glob

from app.ark import build_body, parse, parse_publish_time
from app.config import ROOT

TRIAL = ROOT / "data" / "raw" / "trial"


def load(path):
    return json.loads(open(path, encoding="utf-8").read())["response"]


def test_parse_custom_trial_totals():
    rs = [parse(load(f)) for f in glob(str(TRIAL / "trial-doubao-api-custom-*.json"))]
    assert len(rs) == 15
    assert sum(r.billed_searches for r in rs) == 42
    assert sum(len(r.citations) for r in rs) == 69          # 和 sources-trial.csv 里 custom 的行数一致


def test_parse_plugin_billed_vs_rounds():
    rs = [parse(load(f)) for f in glob(str(TRIAL / "trial-doubao-api-plugin-*.json"))]
    assert sum(r.billed_searches for r in rs) == 83
    assert sum(len(r.search_queries) for r in rs) == 27


def test_build_body_custom_has_no_location():
    tool = build_body("q", "api-custom")["tools"][0]
    assert tool == {"type": "web_search", "sources": ["doubao"]}


def test_build_body_plugin_has_location_and_limit():
    tool = build_body("q", "api-plugin")["tools"][0]
    assert tool["limit"] == 10
    assert tool["user_location"] == {"type": "approximate", "country": "中国", "region": "广东", "city": "深圳"}


def test_parse_publish_time_both_formats():
    assert parse_publish_time("2026-09-11T19:14:05+08:00").day == 11
    assert parse_publish_time("2026年10月15").date() == date(2026, 10, 15)
    assert parse_publish_time("") is None


def test_parse_message_missing_gives_empty_text():
    r = parse({"output": [{"type": "web_search_call", "action": {"query": "x"}}], "usage": {}})
    assert r.text == "" and r.citations == [] and r.search_queries == ["x"] and r.billed_searches is None


import http.client  # noqa: E402
import io  # noqa: E402
import urllib.error  # noqa: E402

import pytest  # noqa: E402

from app.ark import ArkError, HttpArkClient  # noqa: E402


class _Resp:
    def __init__(self, read):
        self.read = read

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _boom(exc):
    def f(*a, **k):
        raise exc
    return f


@pytest.mark.parametrize("urlopen", [
    _boom(urllib.error.HTTPError("u", 500, "x", {}, io.BytesIO(b"server error"))),
    _boom(http.client.RemoteDisconnected("closed")),                      # getresponse 阶段，urllib 不会包成 URLError
    lambda *a, **k: _Resp(_boom(ConnectionResetError("reset"))),          # 读响应体时连接被重置
    lambda *a, **k: _Resp(lambda: b"\xff\xfe not json"),                  # 响应不是 UTF-8 JSON
    lambda *a, **k: _Resp(lambda: b"[1, 2]"),                             # JSON 但不是对象
])
def test_http_client_wraps_transport_errors_as_ark_error(monkeypatch, urlopen):
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    with pytest.raises(ArkError):
        HttpArkClient("k").create({})
