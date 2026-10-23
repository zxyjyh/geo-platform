"""测试用的方舟客户端：按题目回放 trial 的原始响应，或者让指定题先失败若干次。"""
import json
import math
import zlib
from collections import Counter

from app.ark import ArkError
from app.config import ROOT
from app.kb.text import tokenize

TRIAL = ROOT / "data" / "raw" / "trial"


def _trial(variant: str) -> tuple[dict[str, dict], dict[str, str]]:
    """返回 (qid → response, 题目原文 → qid)。"""
    responses, by_text = {}, {}
    for path in sorted(TRIAL.glob(f"trial-doubao-api-{variant}-*.json")):
        qid = path.stem.split("-")[-2]
        saved = json.loads(path.read_text(encoding="utf-8"))
        responses[qid] = saved["response"]
        by_text[saved["request"]["input"][0]["content"][0]["text"]] = qid
    return responses, by_text


class FakeClient:
    def __init__(self, responses: dict[str, dict], by_text: dict[str, str],
                 fail: dict[str, int] | None = None):
        self.responses = responses
        self.by_text = by_text
        self.fail = dict(fail or {})
        self.calls = Counter()

    @classmethod
    def from_trial(cls, variant: str = "custom", overrides: dict[str, dict] | None = None) -> "FakeClient":
        responses, by_text = _trial(variant)
        responses.update(overrides or {})
        return cls(responses, by_text)

    @classmethod
    def failing_for(cls, qids, times: int, variant: str = "custom") -> "FakeClient":
        responses, by_text = _trial(variant)
        return cls(responses, by_text, fail={q: times for q in qids})

    def create(self, body: dict) -> dict:
        qid = self.by_text[body["input"][0]["content"][0]["text"]]
        self.calls[qid] += 1
        if self.fail.get(qid, 0) > 0:
            self.fail[qid] -= 1
            raise ArkError(f"fake failure for {qid}")
        return self.responses[qid]

    def calls_for(self, qid: str) -> int:
        return self.calls[qid]

    @property
    def total_calls(self) -> int:
        return sum(self.calls.values())


class FakeEmbedder:
    """词袋哈希向量：同词越多越相似。用 crc32 而不是内置 hash（后者每个进程随机）。"""
    model = "fake"

    def __init__(self, dim: int = 64, fail_after: int | None = None):
        self.dim = dim
        self.fail_after = fail_after
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise ArkError("fake embedder 按设定失败")
        vec = [0.0] * self.dim
        for w in tokenize(text):
            vec[zlib.crc32(w.encode()) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
