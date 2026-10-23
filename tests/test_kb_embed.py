import math

import pytest

from app.ark import ArkError
from app.kb.embed import HttpArkEmbedder, build_embed_body, parse_embedding
from tests.fakes import FakeEmbedder


def test_build_embed_body_text_only():
    assert build_embed_body("澳觅") == {"model": "doubao-embedding-vision-251215", "encoding_format": "float",
                                        "input": [{"type": "text", "text": "澳觅"}]}


def test_parse_embedding_reads_data_object():
    assert parse_embedding({"data": {"embedding": [0.1, -0.2], "object": "embedding"}}) == [0.1, -0.2]


@pytest.mark.parametrize("resp", [{}, {"data": {}}, {"data": {"embedding": []}}, {"data": [{"embedding": [1.0]}]},
                                  {"data": {"embedding": ["a"]}}])
def test_parse_embedding_rejects_bad_shapes(resp):
    with pytest.raises(ArkError):
        parse_embedding(resp)


def test_http_embedder_retries_then_raises(monkeypatch):
    calls = []
    monkeypatch.setattr("app.kb.embed.post_json", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(ArkError("x")))
    sleeps = []
    monkeypatch.setattr("app.kb.embed.time.sleep", sleeps.append)
    with pytest.raises(ArkError):
        HttpArkEmbedder("k").embed("a")
    assert len(calls) == 3
    assert sleeps == [1, 3]


def test_http_embedder_returns_vector_after_retry(monkeypatch):
    resps = [ArkError("x"), {"data": {"embedding": [1.0, 2.0]}}]

    def fake(*a, **k):
        r = resps.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr("app.kb.embed.post_json", fake)
    monkeypatch.setattr("app.kb.embed.time.sleep", lambda s: None)
    assert HttpArkEmbedder("k").embed("a") == [1.0, 2.0]


def test_fake_embedder_deterministic_normalized_and_similar():
    e = FakeEmbedder()
    a, b, c = e.embed("澳觅 支付宝 优惠"), e.embed("澳觅 支付宝 优惠"), e.embed("天气 预报 明天")
    assert a == b and len(a) == 64 and e.model == "fake" and e.calls == 3
    assert math.isclose(sum(x * x for x in a), 1.0)
    dot = lambda u, v: sum(x * y for x, y in zip(u, v))
    assert dot(a, e.embed("澳觅 支付宝")) > dot(a, c)


def test_fake_embedder_fail_after():
    e = FakeEmbedder(fail_after=1)
    e.embed("a")
    with pytest.raises(ArkError):
        e.embed("b")
    assert e.calls == 2
