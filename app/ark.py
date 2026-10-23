"""火山方舟 Responses API：请求体构造、响应解析、HTTP 调用（从 collect/doubao_api.py 搬来）。

两种联网方式（火山方舟文档「联网搜索工具」，2026-10-20 读取）：
  api-plugin  联网内容插件：默认全网，user_location 生效
  api-custom  豆包搜索 Custom 版：sources 只能是 ["doubao"]，user_location 会被忽略
"""
import http.client
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.timeutil import CST

ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/responses"
DEFAULT_MODEL = "doubao-seed-2-1-pro-260915"
CHANNELS = ("api-custom", "api-plugin")


class ArkError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def build_body(question: str, channel: str, model: str = DEFAULT_MODEL,
               location: tuple[str, str, str] | None = ("中国", "广东", "深圳"),
               limit: int = 10, max_tool_calls: int = 3) -> dict:
    if channel == "api-custom":
        tool = {"type": "web_search", "sources": ["doubao"]}
    elif channel == "api-plugin":
        tool = {"type": "web_search", "limit": limit}
        if location:
            # 字段名来自文档；country/region 填中文名，2026-10-21 实测请求被接受
            tool["user_location"] = {"type": "approximate", "country": location[0],
                                     "region": location[1], "city": location[2]}
    else:
        raise ValueError(f"不支持的渠道：{channel}")
    return {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": question}]}],
        "tools": [tool],
        "max_tool_calls": max_tool_calls,
    }


@dataclass
class ArkResult:
    text: str
    citations: list[dict]
    search_queries: list[str]
    billed_searches: int | None
    input_tokens: int | None
    output_tokens: int | None


def parse(resp: dict) -> ArkResult:
    """citations 按出现顺序去重（同一 url 只记一次）。"""
    texts, citations, seen = [], [], set()
    for item in resp.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") != "output_text":
                continue
            texts.append(part.get("text", ""))
            for ann in part.get("annotations", []) or []:
                if ann.get("type") != "url_citation" or ann.get("url") in seen:
                    continue
                seen.add(ann.get("url"))
                citations.append(ann)
    # 模型实际发出的搜索词（web_search_call.action.query，文档未写，2026-10-21 实测发现）
    queries = [(item.get("action") or {}).get("query", "") for item in resp.get("output", [])
               if item.get("type") == "web_search_call"]
    usage = resp.get("usage") or {}
    return ArkResult(text="".join(texts), citations=citations, search_queries=queries,
                     billed_searches=(usage.get("tool_usage") or {}).get("web_search"),
                     input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"))


_CN_DATE = re.compile(r"^\s*(\d{4})年(\d{1,2})月(\d{1,2})日?\s*$")


def parse_publish_time(raw: str) -> datetime | None:
    """custom 返回 ISO 格式，plugin 返回「2026年10月15」（按北京时间 00:00）。解析不了返回 None。"""
    if not raw:
        return None
    m = _CN_DATE.match(raw)
    try:
        if m:
            return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=CST)
        dt = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=CST)


class ArkClient(Protocol):
    def create(self, body: dict) -> dict: ...


def post_json(url: str, api_key: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:500]
        except OSError:
            detail = ""
        raise ArkError(f"HTTP {e.code}: {detail}", status_code=e.code) from e
    # urllib 只把建连阶段的 OSError 包成 URLError；getresponse / read 阶段的断连、
    # 不完整响应会原样抛出。ValueError 覆盖 JSON 和 UTF-8 解码错误。
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise ArkError(f"{type(e).__name__}: {e}") from e
    if not isinstance(data, dict):
        raise ArkError(f"响应不是 JSON 对象：{type(data).__name__}")
    return data


class HttpArkClient:
    def __init__(self, api_key: str, timeout: int = 180):
        self.api_key = api_key
        self.timeout = timeout

    def create(self, body: dict) -> dict:
        return post_json(ENDPOINT, self.api_key, body, self.timeout)
