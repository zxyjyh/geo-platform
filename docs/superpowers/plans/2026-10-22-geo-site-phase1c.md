# 1c 阶段（每题次数 / 品牌归因 / 引用周期 / 平台属性）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已上线的第一阶段之上，只用现有数据加四项：每题次数设置项、品牌归因两个比例、文章引用周期表、平台属性人工列。

**Architecture:** 后端沿用现有分层：模型 `app/models.py` + 手写 alembic 迁移；纯计算放 `app/metrics.py` / `app/analysis.py` / 新文件 `app/attribution.py`；路由放 `app/api/routes_*.py`。前端在现有页面上加卡片和设置项，不加新页面。

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2 / alembic / pytest（`uv run pytest`）；React + Ant Design + ECharts / vitest（`cd web && npm test`，类型检查 `npm run build`）。

**Spec:** `docs/superpowers/specs/2026-10-21-geo-site-design.md` §4.3（每题次数）、§4.4.1（品牌归因）、§4.6.1（引用周期）、§4.6.2（平台属性，只做人工列；"实测时延"列随第二阶段）。

**前置条件（开工前必须处理）：** 工作区里有其它会话留下的未提交改动，正好落在本计划要改的文件上（`app/metrics.py`、`app/api/routes_*.py`、`web/src/pages/*.tsx` 等）。先让用户决定提交或暂存这些改动，再开始 Task 1；否则每个 Task 的 commit 会把别人的改动一起带进去。

## Global Constraints

- 任何数字都要能追溯到具体 run；每个比率同时显示分子和分母（spec 反目标 1、4）。
- 渠道分开统计，不合并（spec §4.5）。只看 `round == "daily"`、`status == "valid"` 的 run。
- 没配置的东西显示"未配置"，不拿 0 顶替（同 dashboard 里单价的处理）。
- run_id：第 1 次不变 `daily-doubao-{channel}-{qid}-{YYYYMMDD}`，第 2 次起加 `-r2`、`-r3`（spec §4.3）。
- 品牌归因题目范围 = 全部题（含带品牌名的）；网址和名称不区分大小写；电话只比数字，数字间允许空格、短横线、括号（spec §4.4.1）。
- 引用周期不做"频率"列；首次被引日期等于窗口内第一个可观测日时标"监测开始前可能已被引用"，不算首次被引耗时（spec §4.6.1）。
- 平台属性不参与平台推荐排序（spec §4.6.2）。
- 每个 schema 改动一个 alembic 迁移，新列必须带 `server_default`，老数据不用回填脚本。
- 注释、页面文案用中文，风格照现有代码。

## Review Focus

1. 官方标识清单为空时，归因率显示成 `0/n`（看起来像"从不给官方入口"）→ 应显示"未配置官方标识"。测试：Task 3 `test_attribution_unconfigured`。
2. 每题次数从 2 改回 1 之后，以前 2 次的那几天自检报错 → 自检只看当天数据本身，不看当前设置。测试：Task 1 `test_metrics_reps_check_ignores_current_setting`。
3. 同一天 Q01 第 1 次成功、第 2 次失败：Q01 不该进 `missing_qids`，但分母要少 1。测试：Task 1 `test_metrics_partial_rep`。
4. 文章在所选窗口开始之前就被引用过，却被算成"窗口第一天首次被引、耗时 N 天"→ 应标左删失。测试：Task 5 `test_lifecycle_window_start_censors`。
5. 电话号码是更长数字串的一部分（订单号、价格）时误判为命中。测试：Task 3 `test_match_phone_not_inside_longer_number`。

---

### Task 1: 每题次数（后端）

**Files:**
- Modify: `app/models.py`（`Run` 加 `rep`）
- Create: `migrations/versions/<rev>_run_rep.py`（用 `uv run alembic revision -m "run rep"` 生成后手填）
- Modify: `app/collector.py`（`daily_run_id`、`new_run`、`run_daily`）
- Modify: `app/metrics.py`（`DailyMetrics.n_reps`、自检）
- Modify: `app/seed.py`、`app/api/routes_settings.py`
- Modify: `tests/builders.py`（`add_run` 加 `rep`）
- Test: `tests/test_collector.py`、`tests/test_metrics.py`、`tests/test_api.py`、`tests/test_migrations.py`

**Interfaces:**
- Produces:
  - `Run.rep: Mapped[int]`，`Integer`，`default=1`，`server_default="1"`
  - `daily_run_id(channel: str, qid: str, d: date, rep: int = 1) -> str`
  - `new_run(..., rep: int = 1) -> Run`（新增关键字参数，写入 `Run.rep`）
  - `run_daily(session, client, run_date, channel, raw_dir, sleep_s=1.0, retries=2, repeats: int | None = None) -> JobSummary`；`repeats=None` 时读设置 `repeats_per_question_api`（默认 `"1"`）。`JobSummary.failed_qids` 里第 2 次起的失败记成 `"Q01-r2"`。
  - `DailyMetrics.n_reps: int` = 当天 valid run 里 `rep` 的最大值，没有 valid 时为 0
  - 设置 `repeats_per_question_api`：默认 `"1"`，`EDITABLE` 校验 `v.isdigit() and 1 <= int(v) <= 5`
  - `tests/builders.add_run(..., rep: int = 1)`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_collector.py
def test_run_id_rep_suffix():
    d = date(2026, 10, 22)
    assert daily_run_id("api-custom", "Q01", d) == "daily-doubao-api-custom-Q01-20261022"
    assert daily_run_id("api-custom", "Q01", d, 2) == "daily-doubao-api-custom-Q01-20261022-r2"

def test_run_daily_repeats_two(session, tmp_path):
    seed_all(session)
    c = FakeClient.from_trial("custom")
    s = run_daily(session, c, D, "api-custom", tmp_path, sleep_s=0, repeats=2)
    assert (s.n_ok, c.total_calls, c.calls_for("Q01")) == (30, 30, 2)
    r2 = session.get(Run, "daily-doubao-api-custom-Q01-20261022-r2")
    assert r2.rep == 2 and r2.status == "valid"

def test_run_daily_reads_setting_and_keeps_existing_r2(session, tmp_path):
    seed_all(session)
    session.get(Setting, "repeats_per_question_api").value = "2"; session.commit()
    run_daily(session, FakeClient.from_trial("custom"), D, "api-custom", tmp_path, sleep_s=0)
    session.get(Setting, "repeats_per_question_api").value = "1"; session.commit()
    c = FakeClient.from_trial("custom")
    run_daily(session, c, D, "api-custom", tmp_path, sleep_s=0)
    assert c.total_calls == 0 and session.query(Run).count() == 30   # 改回 1 不删已采到的 r2

# tests/test_metrics.py
def test_metrics_two_reps_denominator(session):
    for i, qid in enumerate(UNBRANDED):
        add_run(session, qid, D, mention={"aomi": True}, order={"aomi": 1})
        add_run(session, qid, D, rep=2, mention={"aomi": i < 5}, order={"aomi": 1 if i < 5 else None})
    m = daily_metrics(session, D, "api-custom", 1)
    assert m.mention["aomi"] == Ratio(15, 20) and m.n_reps == 2 and m.selfcheck_failures == []

def test_metrics_partial_rep(session):
    add_run(session, "Q01", D)
    add_run(session, "Q01", D, rep=2, status="failed")
    m = daily_metrics(session, D, "api-custom", 1)
    assert m.n_valid == 1 and "Q01" not in m.missing_qids

def test_metrics_reps_check_ignores_current_setting(session):
    add_run(session, "Q01", D); add_run(session, "Q01", D, rep=2)
    session.get(Setting, "repeats_per_question_api").value = "1"; session.commit()
    assert daily_metrics(session, D, "api-custom", 1).selfcheck_failures == []

# tests/test_api.py
def test_settings_repeats_validation(authed):
    for bad in ("0", "6", "x"):
        assert authed.put("/api/settings", json={"repeats_per_question_api": bad}).status_code == 422
    assert authed.put("/api/settings", json={"repeats_per_question_api": "2"}).json()["repeats_per_question_api"] == "2"

# tests/test_migrations.py：在 upgrade head 的测试里加
#   assert "rep" in {c["name"] for c in inspect(engine).get_columns("runs")}
```

- [ ] **Step 2: 运行，确认失败**

Run: `uv run pytest tests/test_collector.py tests/test_metrics.py tests/test_api.py tests/test_migrations.py -q`
Expected: 新测试 FAIL（`daily_run_id()` 不接受第 4 个参数、`Run` 没有 `rep` 等）

- [ ] **Step 3: 实现**

- 迁移：`op.add_column("runs", sa.Column("rep", sa.Integer(), nullable=False, server_default="1"))`；downgrade 删列。
- `run_daily`：外层按题、内层 `for rep in range(1, k + 1)`，每个 run_id 照现有逻辑处理（已 valid/void 跳过、failed 删掉重跑）。
- `daily_metrics` 自检：`duplicate_qid` 的含义改成"同一 `(qid, rep)` 有两条 valid"（代码名不变，前端文案已经有了）；`n_valid` 检查改成 `n_valid > len(qids) * max(n_reps, 1)`。模块 docstring 里分母那一句改成"当天 valid 的回答数（每题可能有多次）"。`missing_qids` 仍是"一条 valid 都没有的题"。
- `weak_questions` 不改：它取"最近 N 条 run"，每题 2 次时覆盖的天数会减半，在 docstring 里写一句。

- [ ] **Step 4: 运行，确认全部通过**

Run: `uv run pytest -q`
Expected: 全部 PASS（`test_mysql_smoke` 若因无 MySQL 被跳过属正常）

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/collector.py app/metrics.py app/seed.py app/api/routes_settings.py migrations/versions/*_run_rep.py tests/
git commit -m "feat: repeats_per_question setting (default 1), run.rep and -rN run ids"
```

---

### Task 2: 每题次数（前端）

**Files:**
- Modify: `web/src/types.ts`（`DailyMetrics.n_reps: number`）
- Modify: `web/src/format.ts`、`web/src/format.test.ts`
- Modify: `web/src/pages/Settings.tsx`、`web/src/pages/Dashboard.tsx`

**Interfaces:**
- Consumes: Task 1 的 `n_reps`、设置 `repeats_per_question_api`
- Produces: `repsChanges(trend: DailyMetrics[]): { date: string; reps: number }[]`（`format.ts`）

- [ ] **Step 1: 写失败的测试**

```ts
describe("repsChanges", () => {
  it("只在有数据的相邻两天 n_reps 不同时返回，空数据日跳过", () => {
    const t = [day({ date: "2026-10-20", n_reps: 1 }), day({ date: "2026-10-21", n_reps: 0 }),
               day({ date: "2026-10-22", n_reps: 2 }), day({ date: "2026-10-23", n_reps: 2 })];
    expect(repsChanges(t)).toEqual([{ date: "2026-10-22", reps: 2 }]);
  });
  it("第一天不算变化", () => expect(repsChanges([day({ n_reps: 2 })])).toEqual([]));
});
```
（`day()` 是 `format.test.ts` 里现成的构造函数，给它的默认值加 `n_reps: 1`。）

- [ ] **Step 2:** Run `cd web && npm test` → `repsChanges` 未定义，FAIL
- [ ] **Step 3: 实现**
  - `repsChanges` 写在 `format.ts`。
  - Dashboard 趋势图：给第一个 series 加 `markLine`，`data` 为每个变化点 `{ xAxis: date.slice(5), label: { formatter: "每题次数改为 " + reps } }`，虚线。
  - Settings 表单：`repeats_per_question_api` → `InputNumber min={1} max={5}`，label「每题次数（API，每天每题问几次；改动即改口径）」。
- [ ] **Step 4:** Run `cd web && npm test && npm run build` → PASS，构建无类型错误
- [ ] **Step 5: Commit** `git add web/src && git commit -m "feat(web): repeats setting and trend marker"`

---

### Task 3: 品牌归因（后端）

**Files:**
- Modify: `app/models.py`（新表 `BrandMark`）
- Create: `migrations/versions/<rev>_brand_marks.py`
- Create: `app/attribution.py`
- Modify: `app/seed.py`（设置 `brand_mark_version` 默认 `"0"`）
- Modify: `app/api/routes_settings.py`（`GET/PUT /settings/brand-marks`）
- Modify: `app/api/routes_dashboard.py`（`GET /dashboard/attribution`）
- Modify: `tests/builders.py`（`add_source` 已有 `is_owned`，不用改）
- Test: `tests/test_attribution.py`（新）、`tests/test_api.py`、`tests/test_migrations.py`

**Interfaces:**
- Produces:
  - `BrandMark`：表 `brand_marks`，列 `id`（PK 自增）、`version: int`（index）、`kind: String(16)`、`value: BinString(128)`；`UniqueConstraint("version", "kind", "value")`；`__table_args__` 带 `UTF8MB4`
  - `MARK_KINDS = ("website", "phone", "app_store", "mini_program", "official_account", "other")`（`app/attribution.py`）
  - `match_marks(text: str, marks: list[BrandMark]) -> list[BrandMark]`
  - `@dataclass AttributionHit: run_id: str; qid: str; marks: list[str]; owned_source: bool`
  - `@dataclass AttributionDay: date: date; channel: str; version: int; configured: bool; text: Ratio; source: Ratio; hits: list[AttributionHit]`
  - `attribution_daily(session, d: date, channel: str, alias_version: int, platform: str = "doubao") -> AttributionDay`
  - `GET /api/settings/brand-marks` → `{"version": int, "marks": [{"kind", "value"}]}`
  - `PUT /api/settings/brand-marks`，body `[{"kind", "value"}]` → 新版本号 + 清单；写 `settings.brand_mark_version`
  - `GET /api/dashboard/attribution?date&channel&platform` → `to_json(AttributionDay)`；`date` 缺省 = `latest_date`

- [ ] **Step 1: 写失败的测试**

```python
def mk(kind, value): return BrandMark(version=1, kind=kind, value=value)

def test_match_website_case_insensitive():
    assert [m.value for m in match_marks("官网 AomiApp.com 下载", [mk("website", "aomiapp.com")])] == ["aomiapp.com"]

def test_match_phone_separators():
    m = [mk("phone", "28888888")]
    for t in ("客服 2888-8888", "致电 (2888) 8888", "+853 2888 8888"):
        assert match_marks(t, m), t

def test_match_phone_not_inside_longer_number():
    assert match_marks("订单号 1288888888 99", [mk("phone", "28888888")]) == []

def test_attribution_counts(session):
    # Q01 提到澳觅且正文有官网；Q03（品牌题）提到澳觅、信源有自有 URL；Q02 提到澳觅、什么都没有；Q04 没提澳觅（不进分母）
    ... 用 add_run(mention={"aomi": True}, text=...) 和 add_source(is_owned=True) 构造，
        BrandMark(version=1, kind="website", value="aomiapp.com")，settings brand_mark_version = "1"
    a = attribution_daily(session, D, "api-custom", 1)
    assert a.configured and a.text == Ratio(1, 3) and a.source == Ratio(1, 3)
    assert {h.qid for h in a.hits} == {"Q01", "Q02", "Q03"}

def test_attribution_unconfigured(session):
    add_run(session, "Q01", D, mention={"aomi": True}, order={"aomi": 1}, text="澳觅 aomiapp.com")
    a = attribution_daily(session, D, "api-custom", 1)   # brand_mark_version = "0"
    assert a.configured is False and a.text == Ratio(0, 1)

# tests/test_api.py
def test_brand_marks_put_creates_version(authed):
    r = authed.put("/api/settings/brand-marks", json=[{"kind": "website", "value": " aomiapp.com "},
                                                     {"kind": "website", "value": "aomiapp.com"}]).json()
    assert r["version"] == 1 and r["marks"] == [{"kind": "website", "value": "aomiapp.com"}]   # 去空格、去重
    assert authed.put("/api/settings/brand-marks", json=[{"kind": "fax", "value": "x"}]).status_code == 422
    assert authed.put("/api/settings/brand-marks", json=[{"kind": "phone", "value": "12"}]).status_code == 422
# test_all_business_routes_require_auth 的列表里加 "/api/settings/brand-marks"、"/api/dashboard/attribution"
```

- [ ] **Step 2:** Run `uv run pytest tests/test_attribution.py tests/test_api.py -q` → FAIL（模块不存在）
- [ ] **Step 3: 实现**
  - 电话匹配：`digits = re.sub(r"\D", "", value)`，正则 `(?<!\d)` + `r"[\s\-()]*".join(digits)` + `(?!\d)`。其余类型用 `value.lower() in text.lower()`。
  - PUT 校验：`kind` 必须在 `MARK_KINDS`；`value` 去空格后 1–128 字；`phone` 去掉非数字后 6–15 位；按 `(kind, value)` 去重保序。允许空列表（新版本里没有标识 → `configured=False`）。版本号 = 现有最大版本 + 1，旧版本保留。
  - `attribution_daily`：取当天该渠道全部题（**不按 unbranded 过滤**）的 valid run，join 当前 `alias_version` 的 `Coding`，`mention_aomi` 为真的进分母；`configured` = 当前版本至少一条标识；`owned_source` = 该 run 有任一 `Source.is_owned`。
- [ ] **Step 4:** Run `uv run pytest -q` → 全部 PASS
- [ ] **Step 5: Commit** `git commit -m "feat: brand attribution (official marks in answer text / owned sources)"`（add 上面列出的文件）

---

### Task 4: 品牌归因（前端）

**Files:**
- Modify: `web/src/types.ts`（`AttributionDay`、`AttributionHit`、`BrandMark`、`MARK_KIND_LABEL`）
- Modify: `web/src/pages/Dashboard.tsx`、`web/src/pages/Settings.tsx`

**Interfaces:**
- Consumes: Task 3 的三个接口
- Produces: `MARK_KIND_LABEL: Record<string, string>` = 官网 / 客服电话 / 应用商店名 / 小程序名 / 公众号名 / 其他

- [ ] **Step 1:** Dashboard 加一张卡片「品牌归因（全部题中提到澳觅的回答）」：两行「正文给出官方入口 n/den」「信源含自有内容 n/den」，用现有 `formatRatio`。`configured=false` 时第一行显示「未配置官方标识」+ 跳到设置页的链接，不显示数字。卡片可展开命中明细：qid、命中的标识、是否有自有信源，点 qid 跳回答记录（沿用 Dashboard 里已有的跳转写法）。
- [ ] **Step 2:** Settings 加标签页「官方标识」：可编辑表格（类型 Select、内容 Input、删除），保存调用 PUT，成功提示「已保存为第 N 版」。电话一栏 placeholder「不带区号，例如 2888 8888」。
- [ ] **Step 3:** Run `cd web && npm test && npm run build` → PASS
- [ ] **Step 4:** 手动验证：`uv run` 起后端 + `npm run dev`，清单为空时卡片显示「未配置官方标识」；加一条 `aomiapp.com` 后显示分子/分母。
- [ ] **Step 5: Commit** `git commit -m "feat(web): brand attribution card and official marks settings"`

---

### Task 5: 引用周期（后端）

**Files:**
- Modify: `app/analysis.py`
- Modify: `app/api/routes_sources.py`（`GET /sources/lifecycle`）
- Modify: `tests/builders.py`（`add_source` 加 `publish_time: datetime | None = None`）
- Test: `tests/test_analysis.py`、`tests/test_api.py`

**Interfaces:**
- Produces:
  - `@dataclass CitationLife: url_norm: str; url: str; title: str; domain: str; platform_key: str | None; n_citations: int; first_date: date; last_date: date; active_days: int; span_days: int; persistence: float; energy: float; publish_time: datetime | None; lag_days: int | None; left_censored: bool; publish_suspect: bool; external_geo: bool; is_owned: bool`
  - `citation_lifecycle(session, channel: str, start: date, end: date, platform: str = "doubao") -> list[CitationLife]`，按 `n_citations` 降序、`first_date` 升序、`url_norm` 升序
  - `GET /api/sources/lifecycle?start&end&channel&platform`：`end` 缺省今天；`start` 缺省 = `max(该渠道 first_date, end − 365 天)`，没有数据时 `end − 29 天`

- [ ] **Step 1: 写失败的测试**（D0 = 渠道第一天，D1 = D0+1 …）

```python
def test_lifecycle_basic(session):
    # 渠道 D0 就有数据；A 在 D1 被 2 条 run 引用（一条用 m.sohu.com、一条用 www.sohu.com），D3 被 1 条 run 引用，
    # 其中一条 run 里 A 出现两次；A 的 publish_time = D1 − 5 天
    rows = {l.url_norm: l for l in citation_lifecycle(session, "api-custom", D0, D3)}
    a = rows[normalize_url(A)]
    assert (a.n_citations, a.first_date, a.last_date, a.active_days, a.span_days) == (3, D1, D3, 2, 3)
    assert a.persistence == pytest.approx(2 / 3) and a.energy == pytest.approx(1.5)
    assert (a.lag_days, a.left_censored, a.publish_suspect) == (5, False, False)

def test_lifecycle_first_day_is_censored(session):     # B 在渠道第一天 D0 就被引用
    b = ...; assert b.left_censored and b.lag_days is None

def test_lifecycle_window_start_censors(session):      # C 在 D1、D3 被引；窗口从 D1 开始 → D1 是窗口第一个可观测日
    c = ... citation_lifecycle(session, "api-custom", D1, D3) ...
    assert c.left_censored and c.first_date == D1

def test_lifecycle_publish_after_first_citation(session):   # publish_time 晚于首次被引
    assert x.lag_days is None and x.publish_suspect

def test_lifecycle_excludes_other_channel_and_trial(session): ...
```

- [ ] **Step 2:** Run `uv run pytest tests/test_analysis.py -q` → FAIL
- [ ] **Step 3: 实现**
  - 复用 `_daily_sources(channel, start, end, platform)`，带上 `Run.collect_date`；按 `url_norm` 归并，被引次数按不同 `run_id` 计。
  - 窗口第一个可观测日 = `max(start, 该渠道全部历史里 valid daily run 的最早 collect_date)`；`first_date` 等于它就 `left_censored=True`。
  - `publish_time` 取所有出现里非空的最早值；`lag = (first_date − publish_time.date()).days`；`lag < 0` 时 `lag_days=None, publish_suspect=True`；左删失时 `lag_days=None`。
  - `url/title/domain/platform_key` 取最近一次出现的值（同 `reference_articles` 的取法）；`is_owned` = 任一次出现为真；`external_geo` 查 `SourceTag`。
- [ ] **Step 4:** Run `uv run pytest -q` → PASS
- [ ] **Step 5: Commit** `git commit -m "feat: citation lifecycle per article (left-censoring aware)"`

---

### Task 6: 引用周期（前端）

**Files:**
- Modify: `web/src/types.ts`（`CitationLife`）、`web/src/pages/Sources.tsx`

- [ ] **Step 1:** Sources 页加卡片「引用周期」，用页面现有的日期范围和渠道参数请求 `/sources/lifecycle`。表格列：标题（外链）、平台/域名、被引次数、首次 → 末次、活跃天数/跨度、持续度（百分比）、日均被引（1 位小数）、首次被引耗时。耗时列：`left_censored` 显示 Tag「监测开始前可能已被引用」；`publish_suspect` 显示 Tag「发布时间晚于首次被引」；`publish_time` 为空显示「—」。另加 Tag：外部 GEO 文章、自有。被引次数、持续度、耗时三列可排序。卡片底部固定一行小字：「发布时间来自接口返回，未核实；被引次数 = 引用过它的回答数。」
- [ ] **Step 2:** Run `cd web && npm test && npm run build` → PASS
- [ ] **Step 3:** 手动验证：用本地已有的 daily 数据打开信源分析页，确认表格有数据，并且第一天就出现的文章带左删失标记。
- [ ] **Step 4: Commit** `git commit -m "feat(web): citation lifecycle table"`

---

### Task 7: 平台属性（人工列）

**Files:**
- Modify: `app/models.py`（`Platform` 加三列）
- Create: `migrations/versions/<rev>_platform_attrs.py`
- Modify: `app/api/routes_settings.py`（`PlatformBody`、`put_platforms`、`_platform_json`）
- Modify: `app/analysis.py`（`PlatformCount` 加三个字段）
- Modify: `web/src/types.ts`、`web/src/pages/Settings.tsx`、`web/src/pages/Suggestions.tsx`
- Test: `tests/test_api.py`、`tests/test_analysis.py`、`tests/test_migrations.py`

**Interfaces:**
- Produces:
  - `Platform.review_strictness: String(16)`，server_default `"unknown"`，取值 `loose / medium / strict / unknown`
  - `Platform.allows_links: String(16)`，server_default `"unknown"`，取值 `yes / no / unknown`
  - `Platform.notes: String(500)`，server_default `""`
  - `PlatformBody` 对应字段用 `Literal[...]`，默认 `"unknown"` / `""`
  - `PlatformCount` 增加 `review_strictness: str; allows_links: str; notes: str`

- [ ] **Step 1: 写失败的测试**

```python
def test_platform_attrs_roundtrip_and_default(authed):
    body = authed.get("/api/settings/platforms").json()
    assert body[0]["review_strictness"] == "unknown" and body[0]["notes"] == ""
    body[0].update(review_strictness="strict", allows_links="no", notes="需白名单")
    assert authed.put("/api/settings/platforms", json=body).json()[0]["review_strictness"] == "strict"
    body[0]["review_strictness"] = "harsh"
    assert authed.put("/api/settings/platforms", json=body).status_code == 422

def test_platform_counts_attrs_do_not_affect_order(session):
    # sohu 被引 2 次（审核 strict），zhihu 被引 1 次（审核 loose）→ 顺序仍是 sohu、zhihu，且带上属性
```

- [ ] **Step 2:** Run `uv run pytest tests/test_api.py tests/test_analysis.py -q` → FAIL
- [ ] **Step 3: 实现** 后端按 Interfaces 加列和字段。前端：Settings 平台映射表加「审核宽严」「能否带外链」两个 Select 和「发布注意事项」Input；Suggestions 的平台列表每个平台后面显示两个小 Tag（「审核：严」「可带链接」，`unknown` 显示「未知」）+ 注意事项 Tooltip。中文标签映射放 `types.ts`。
- [ ] **Step 4:** Run `uv run pytest -q && cd web && npm test && npm run build` → PASS
- [ ] **Step 5: Commit** `git commit -m "feat: platform attributes (manual: review strictness, links, notes)"`

---

### Task 8: 收尾验证

- [ ] **Step 1:** `uv run pytest -q`、`cd web && npm test && npm run build` 全部通过，贴输出。
- [ ] **Step 2:** 对本地 MySQL 或 RDS 跑一遍 `uv run alembic upgrade head`，确认三个迁移都能在 MySQL 上执行（`test_mysql_ddl_*` 只检查 DDL 文本）。**连 RDS 前先问用户**：本地调试数据也写在那个库里，见 `.claude/tasks/2026-10-22-本地连RDS.md`。
- [ ] **Step 3:** 更新 `.claude/tasks/2026-10-22-竞品GEO平台分析.md`：已完成项、迁移版本号、下一步（1d 事实一致性检测，等用户确认事实清单草稿）。
