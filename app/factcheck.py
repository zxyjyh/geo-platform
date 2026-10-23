"""事实抽取 prompt 与解析（1d 事实一致性检测，Task 2）。

职责边界：只负责 prompt 渲染、LLM 输出解析、原句验证。
LLM 调用本身在 Task 3（抽取服务）里做，本模块不碰网络。
"""

import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.ark import ENDPOINT, post_json, parse
from app.models import FactClaim


class FactCheckError(Exception):
    """事实抽取/解析过程中的错误（JSON 损坏、格式不符等）。"""
    pass


PROMPT_V1 = """\
你是一个事实抽取器。下面是一条关于澳门外卖平台的回答原文。

请从中挑出所有"关于澳觅（AOMI）的事实陈述"，每条给出：
1. sentence：原句，必须是回答原文里能找到的连续文本（逐字一致，不能改写）
2. code：对应已知事实清单的编号，没有对应的写 null

已知事实清单：
{fact_items}

规则：
- 只抽"事实"，不抽主观评价（"很好用""推荐""体验不错"不算）
- 只抽"关于澳觅"的事实；说 mFood、闪蜂的不算；泛指"澳门外卖平台"而没有点名澳觅的不算
- 同一事实重复出现只抽一次
- sentence 必须在回答原文里原样找到，找不到就丢弃，不要凭记忆改写或拼接

输出一个 JSON 数组，不要输出其他内容：
[{{"sentence": "原句文本", "code": "A2" | null}}, ...]

如果没有符合条件的事实陈述，输出空数组：[]

回答原文：
{answer_text}
"""


def render_prompt(items: list, answer_text: str) -> str:
    """把事实清单和回答原文渲染进 PROMPT_V1。

    items: [{"code": "A1", "subject": "...", "correct_claim": "..."}, ...]
    """
    if not items:
        lines = "（清单为空）"
    else:
        lines = "\n".join(
            f"- {it['code']}：{it['subject']}——{it['correct_claim']}"
            for it in items
        )
    return PROMPT_V1.format(fact_items=lines, answer_text=answer_text)


def parse_claims(llm_output: str) -> list[dict]:
    """解析 LLM 返回的 JSON 数组。

    返回 [{"sentence": str, "code": str|None, "raw_label": str}, ...]
    code 非 null → raw_label = "known"；code 为 null → raw_label = "unknown"

    JSON 解析失败或格式不符抛 FactCheckError。
    """
    text = llm_output.strip()
    # 部分模型会在 JSON 外包一层 ```json ... ```，尝试剥掉
    if text.startswith("```"):
        first_nl = text.find("\n")
        last_fence = text.rfind("```")
        if first_nl != -1 and last_fence > first_nl:
            text = text[first_nl + 1:last_fence].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise FactCheckError(f"JSON 解析失败：{e}") from e

    if not isinstance(data, list):
        raise FactCheckError(f"期望 JSON 数组，得到 {type(data).__name__}")

    results = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise FactCheckError(f"第 {i} 条不是对象：{type(item).__name__}")
        sentence = item.get("sentence")
        if not isinstance(sentence, str) or not sentence.strip():
            raise FactCheckError(f"第 {i} 条缺少有效的 sentence 字段")
        code = item.get("code")
        if code is not None and not isinstance(code, str):
            raise FactCheckError(f"第 {i} 条 code 应为字符串或 null，得到 {type(code).__name__}")
        results.append({
            "sentence": sentence.strip(),
            "code": code,
            "raw_label": "known" if code is not None else "unknown",
        })
    return results


def verify_sentence(sentence: str, answer_text: str) -> bool:
    """sentence 去除首尾空白后必须是 answer_text 的子串（spec §4.11 强制要求）。"""
    return sentence.strip() in answer_text


def call_llm(prompt: str, api_key: str, model: str = "doubao-seed-2-1-pro-260915") -> str:
    """调用火山方舟 Responses API（不带 web_search），返回模型输出文本。

    复用 app.ark 的 post_json 和 ENDPOINT。
    请求体格式（不带 tools）：
    {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    }
    """
    body = {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    }
    resp = post_json(ENDPOINT, api_key, body, timeout=300)
    result = parse(resp)
    return result.text


def extract_claims(answer_text: str, items: list[dict], api_key: str, model: str = "doubao-seed-2-1-pro-260915") -> list[dict]:
    """对一条回答抽取事实陈述。

    1. render_prompt(items, answer_text)
    2. call_llm(prompt, api_key, model)
    3. parse_claims(llm_output)
    4. 对每条 claim 调 verify_sentence，不通过的丢弃
    5. 返回通过验证的 claims
    """
    prompt = render_prompt(items, answer_text)
    llm_output = call_llm(prompt, api_key, model)
    claims = parse_claims(llm_output)
    verified = [c for c in claims if verify_sentence(c["sentence"], answer_text)]
    return verified


def extract_and_store(session: Session, run, items: list[dict], api_key: str, version: int, model: str = "doubao-seed-2-1-pro-260915") -> int:
    """对单条 Run 抽取并落库 FactClaim，返回新增条数。

    - 已抽过的（同 run_id + extract_version）跳过，返回 0
    - 调 extract_claims
    - 每条写入 FactClaim(run_id=run.run_id, extract_version=version, seq=i, sentence=..., fact_code=..., raw_label=...)
    """
    # Check if already extracted
    existing = session.execute(
        select(FactClaim).where(
            FactClaim.run_id == run.run_id,
            FactClaim.extract_version == version
        )
    ).first()
    if existing:
        return 0

    # Extract claims
    claims = extract_claims(run.answer_text, items, api_key, model)

    # Store to database
    for i, claim in enumerate(claims):
        fact_claim = FactClaim(
            run_id=run.run_id,
            extract_version=version,
            seq=i,
            sentence=claim["sentence"],
            fact_code=claim["code"],
            raw_label=claim["raw_label"]
        )
        session.add(fact_claim)

    session.commit()
    return len(claims)
