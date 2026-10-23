"""文本归一化、分词、BM25 与 RRF：纯函数，入库和检索共用同一套 normalize / tokenize。"""
import logging
import math
import re
import unicodedata
from collections import Counter

import jieba
from opencc import OpenCC

# 自定义词典（spec §4.8），按 normalize 后的形式登记
_CUSTOM_WORDS = ["澳觅", "mFood", "闪蜂", "+86", "支付宝", "微信支付", "澳门通", "MPay"]

# 不用 \b：后面紧跟汉字（「5,700家」）时 \b 不成立
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
# 只含空白或标点 / 符号的词不要（"+86" 含数字，不受影响）
_NOISE = re.compile(r"^[\s\W_]+$")

_cc: OpenCC | None = None
_jieba_ready = False


def normalize(text: str) -> str:
    """NFKC → 繁转简 → 小写 → 去数字千分位逗号。"""
    global _cc
    if _cc is None:
        _cc = OpenCC("t2s")
    s = unicodedata.normalize("NFKC", text)
    s = _cc.convert(s).lower()
    return _THOUSANDS.sub("", s)


def _init_jieba() -> None:
    global _jieba_ready
    if _jieba_ready:
        return
    jieba.setLogLevel(logging.WARNING)  # 不要在 stderr 打印 "Building prefix dict"
    for w in _CUSTOM_WORDS:
        jieba.add_word(normalize(w))
    _jieba_ready = True


def tokenize(text: str) -> list[str]:
    """normalize 后用搜索引擎模式分词，丢掉纯空白 / 纯标点的词。"""
    _init_jieba()
    return [t for t in jieba.cut_for_search(normalize(text)) if not _NOISE.match(t)]


def bm25_scores(
    query: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75
) -> list[float]:
    """标准 Okapi BM25；idf = log((N - df + 0.5) / (df + 0.5) + 1)。"""
    n = len(docs)
    if n == 0:
        return []
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df = Counter(t for d in docs for t in set(d))
    tfs = [Counter(d) for d in docs]
    scores = []
    for d, tf in zip(docs, tfs):
        s = 0.0
        for t in set(query):
            f = tf.get(t, 0)
            if not f:
                continue
            idf = math.log((n - df[t] + 0.5) / (df[t] + 0.5) + 1)
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / avgdl))
        scores.append(s)
    return scores


def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """倒数排名融合：每个 ranking 是按相关度排好的下标；分数降序，同分按下标升序。"""
    acc: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            acc[idx] = acc.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(acc.items(), key=lambda x: (-x[1], x[0]))
