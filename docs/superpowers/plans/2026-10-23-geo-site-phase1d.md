# 1d 实施计划：事实一致性检测（2026-10-23）

spec §4.11 + §6.5：清单没到之前只做**抽取**和**「清单里没有」列表**。用户确认清单后再补判定逻辑。

## 目标
1. 建立事实清单（设置页可维护，带版本）
2. 对每条提及澳觅的 valid 回答，用 LLM 抽出「关于澳觅的事实陈述」
3. 抽取结果落库，按「清单里有 / 清单里没有」分开列出
4. **不做**自动判定（等清单确认后再加）

## 不在本期范围
- 自动判一致 / 矛盾（清单没确认，判了也不可信）
- Cohen's κ 校准、看板指标（spec 要求人工确认后才能上指标）
- GEO 文章联动（§4.9，第二阶段）

---

## Task 1：数据模型（fact_items + fact_claims）

**新增 `app/models.py`：**

```python
class FactItem(Base):
    """事实清单（spec §4.11），整表按版本保存。"""
    __tablename__ = "fact_items"
    __table_args__ = (UniqueConstraint("version", "code"), UTF8MB4)
    id: int (PK)
    version: int (indexed)
    code: str(32)          # A1, A2, B1, C1… 草稿编号
    category: str(32)      # identity / registration / service / other
    subject: str(128)      # "与 mFood 的关系"
    correct_claim: str(1000)  # 正确说法
    source_ref: str(500)   # 出处
    status: str(16)        # active / retired

class FactClaim(Base):
    """从回答里抽出的事实断言。"""
    __tablename__ = "fact_claims"
    __table_args__ = UTF8MB4
    id: int (PK)
    run_id: str(128) (FK runs.run_id, indexed)
    extract_version: int   # 抽取 prompt + 模型的版本
    seq: int               # 该回答内的顺序
    sentence: str(2000)    # 原句（必须在 answer_text 里找得到）
    fact_code: str(32) | null  # 对应清单编号，null = "清单里没有"
    raw_label: str(32)     # LLM 原始分类："known" / "unknown" / "unrelated"
    reviewer_decision: str(16) | null  # pending / confirmed / rejected / new_item
    reviewed_at: datetime | null
    reviewed_by: str(64) | null
    note: str(500)         # 复核备注
```

**Alembic 迁移**：新建两张表，无外键依赖（fact_claims.run_id → runs 已有）。

---

## Task 2：抽取 prompt 设计

**核心设计**：给 LLM 一份「已知事实清单」+ 回答原文，让它挑出「关于澳觅的事实陈述」，每条标注：
- 原句（回答里实际出现的连续文本）
- 对应清单编号（或「清单里没有」）

**不用 LLM 做对错判定**（清单没确认，判了没意义）。只让它做分类：
- `known`：清单里有对应项（给编号）
- `unknown`：是关于澳觅的事实，但清单里没有
- `unrelated`：不是关于澳觅的事实（评价、泛指、说 mFood 等）→ 丢弃

**Prompt 草稿**（v1，中文）：

```
你是一个事实抽取器。下面是一条关于澳门外卖平台的回答。
请从中挑出所有"关于澳觅（AOMI）的事实陈述"，每条给出：
1. sentence：原句，必须是回答里能找到的连续文本
2. code：对应已知事实清单的编号，没有对应的写 null

已知事实清单：
{fact_items 渲染}

规则：
- 只抽"事实"，不抽评价（"很好用""推荐"不算）
- 只抽"关于澳觅"的，mFood / 闪蜂的不算，泛指的（"澳门外卖平台"）不算
- 同一事实重复出现只抽一次
- 找不到原句的不要输出

输出 JSON 数组：[{"sentence": "...", "code": "A2" | null}, ...]
```

**版本管理**：`extract_version` 在 Setting 里存 `fact_extract_version`，prompt 或模型 ID 改了手动升。

---

## Task 3：抽取服务（app/factcheck.py）

```python
def extract_claims(answer_text: str, items: list[FactItem], client: ArkClient, model: str) -> list[dict]
    """返回 [{"sentence": str, "code": str|None, "raw_label": str}, ...]"""

def verify_sentence(sentence: str, answer_text: str) -> bool
    """sentence 必须在 answer_text 里原样找到（spec §4.11 强制要求）"""

def extract_and_store(session, run: Run, items: list[FactItem], client: ArkClient, version: int) -> int
    """对单条回答抽取并落库，返回新增条数。已抽过的（同 run_id + version）跳过。"""
```

**实现要点**：
- 用 `app/ark.py` 的 `HttpArkClient`，构造一个不带 web_search 的简单请求体（纯对话）
- 模型用 `doubao-seed-2-1-pro-260915`（和采集一样，省钱）
- JSON 解析失败 → 记错误日志，该条跳过，不重试（prompt 问题修了再重抽）
- 原句验证失败 → 丢弃该条（spec 要求）

---

## Task 4：批量抽取脚本（scripts/fact_extract.py）

```bash
python -m scripts.fact_extract [--date 2026-10-23] [--channel api-custom] [--reextract]
```

- 默认跑当天全部 mention_aomi=True 的 valid 回答
- `--reextract` 清空该条件下的旧 claims 再重抽
- 进度打印：处理 N/M 条，新增 X 条，跳过 Y 条

---

## Task 5：API 路由

**新增 `app/api/routes_factcheck.py`：**

```
GET  /api/factcheck/claims?date=&channel=&filter=known|unknown|pending
     返回抽取结果列表，带回答原文摘要和跳转 run_id
GET  /api/factcheck/claims/stats
     返回：总条数、known 条数、unknown 条数、待复核条数
POST /api/factcheck/claims/{id}/review
     body: {"decision": "confirmed"|"rejected"|"new_item", "note": "..."}
     人工复核

GET  /api/settings/fact-items?version=latest
     返回当前版本清单
PUT  /api/settings/fact-items
     body: [{code, category, subject, correct_claim, source_ref, status}, ...]
     整表替换，升版本（和 BrandMark 同模式）
```

---

## Task 6：前端

**设置页新增「事实清单」标签**（`/settings?tab=facts`）：
- 表格：编号、分类、主题、正确说法、出处、状态
- 增删改行，保存时整表提交

**新页面「事实问题」**（左侧导航，在「优化建议」下面）：
- 两个标签：「清单匹配」（known）/ 「清单里没有」（unknown）
- 每行：原句、对应编号（或「无」）、回答链接（run_id）
- 复核按钮：确认 / 驳回 / 加入清单（unknown 专用）
- 「加入清单」→ 跳到设置页预填该行

---

## Task 7：集成测试

- `tests/test_factcheck.py`：
  - `extract_claims` 用 mock ArkClient 测 JSON 解析 + 原句验证
  - `extract_and_store` 测去重（同 run_id + version 不重复抽）
  - API 路由测 CRUD + 复核

---

## Task 8：跑一次真实数据

- 本地 `data/geo.db` 现有 ~28 条 mention_aomi 的回答
- 用真实 `ARK_API_KEY` 跑 `scripts/fact_extract.py`
- 结果写进 scratchpad（不进仓库）
- 检查抽取质量：原句是否真的在回答里、分类是否合理、有没有漏抽

---

## 执行顺序
T1 → T2 → T3 → T7（先写测试保证抽取逻辑对）→ T4 → T5 → T6 → T8

## 依赖
- `ARK_API_KEY` 环境变量（已有）
- 现有 `runs` 数据（本地库有 ~28 条）
- 不需要 RDS（本地先跑通，RDS 迁移等用户确认再合）
