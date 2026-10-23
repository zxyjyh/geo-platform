"""火山方舟多模态向量化：一次请求一个切片（接口会把多段输入合成一个向量），不传 dimensions（默认 2048）。"""
import time
from typing import Protocol

from app.ark import ArkError, post_json

EMBED_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"
EMBED_MODEL = "doubao-embedding-vision-251215"
RETRY_DELAYS = (1, 3)  # 失败后重试 2 次，间隔 1s、3s


class Embedder(Protocol):
    model: str

    def embed(self, text: str) -> list[float]: ...


def build_embed_body(text: str, model: str = EMBED_MODEL) -> dict:
    return {"model": model, "encoding_format": "float", "input": [{"type": "text", "text": text}]}


def parse_embedding(resp: dict) -> list[float]:
    """响应里 data 是单个对象（不是列表）：{"data": {"embedding": [...], "object": "embedding"}}。"""
    data = resp.get("data")
    vec = data.get("embedding") if isinstance(data, dict) else None
    if (not isinstance(vec, list) or not vec
            or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in vec)):
        raise ArkError("向量化响应缺少 data.embedding 或格式不对")
    return [float(x) for x in vec]


def _is_retryable(err: ArkError) -> bool:
    """429（限流）、5xx（服务端错误）、网络/超时可重试；400/401/403 等 4xx 不可重试。"""
    code = err.status_code
    if code is None:
        return True  # 网络错误、超时、JSON 解析错误等非 HTTP 错误
    return code == 429 or code >= 500


class HttpArkEmbedder:
    def __init__(self, api_key: str, model: str = EMBED_MODEL, timeout: int = 60):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def embed(self, text: str) -> list[float]:
        body = build_embed_body(text, self.model)
        for delay in (*RETRY_DELAYS, None):
            try:
                resp = post_json(EMBED_ENDPOINT, self.api_key, body, self.timeout)
            except ArkError as e:
                if delay is None or not _is_retryable(e):
                    raise
                time.sleep(delay)
                continue
            return parse_embedding(resp)
