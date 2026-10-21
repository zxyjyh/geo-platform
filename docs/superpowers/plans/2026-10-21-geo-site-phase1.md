# 豆包 GEO 内部网站 · 第一阶段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 每天 06:00（北京时间）用豆包搜索 Custom 版 API 跑 v3 的 15 题，把回答、信源、编码结果存进 MySQL，并在需要登录的网站上展示当日指标、回答记录、信源分析和平台推荐，用 Docker 部署到公司服务器。

**Architecture：** 后端用 Python 包 `app/`（FastAPI + SQLAlchemy 2 + Alembic），同一个镜像跑两个进程：`api`（uvicorn）和 `worker`（APScheduler 定时采集，同时轮询"手动补跑"请求）。前端是 `web/`（React + Vite + Ant Design + ECharts）构建出的静态文件，由 Caddy 提供并反向代理 `/api`。所有指标从 `runs` / `sources` / `codings` 三张表实时算出，不存聚合结果，这样别名表一改，重算后数字就一致。

**Tech Stack：** Python 3.12、uv、FastAPI、SQLAlchemy 2、Alembic、PyMySQL、APScheduler 3、bcrypt、itsdangerous（Starlette SessionMiddleware）、pytest；Node 20、React 18、Vite 5、TypeScript、antd 5、echarts 5、vitest；MySQL 8.4、Caddy 2、Docker Compose（本机用 colima）。

**Spec：** `docs/superpowers/specs/2026-10-21-geo-site-design.md`（实现范围：§6.5 第 1 项；**不含** 1b 网页采集、第二阶段知识库和文章、第三阶段 App 手测）。数据口径的上游是 `docs/schema-v1.md`。

## Global Constraints

- 时区：所有"哪一天"一律按 `Asia/Shanghai` 计算；`collected_at` 存带时区的 ISO 时间。
- 采集渠道：`channel="api-custom"`，请求体 `tools=[{"type":"web_search","sources":["doubao"]}]`，模型 `doubao-seed-2-1-pro-260915`，端点 `https://ark.cn-beijing.volces.com/api/v3/responses`（沿用 `collect/doubao_api.py`）。渠道名存在 settings 里，可以改，但第一阶段只实现 `api-custom` 和 `api-plugin` 两种请求体。
- run_id：`daily-doubao-{channel}-{qid}-{YYYYMMDD}`，例如 `daily-doubao-api-custom-Q01-20261022`；round 固定为 `daily`。
- 题库：`data/questions/questions-v3-15.csv`，question_version=`v3`。带品牌名的题（branded=Y）是 Q03、Q12、Q13、Q14、Q15，**不计入**提及率、三家中首位率、提及份额。
- 只追踪三家：`aomi`（澳觅）、`mfood`（mFood）、`shanfeng`（闪蜂）。排位只在这三家之间比；页面上的指标名必须写成"三家中首位率"，不能写成"首位率"。
- 别名表 v1（照搬 `analysis/quick_scan.py`）：aomi = 澳觅、澳覓、Aomi、aomi、AOMI；mfood = mFood、MFood、mfood、澳門Food、澳门Food；shanfeng = 闪蜂、閃蜂。
- 比率一律显示成"分子/分母（百分比）"，例如 `8/10（80%）`；分母为 0 时显示"无数据"，不显示 0%。
- 采集失败：重试 2 次（共 3 次），仍失败就写一条 `status="failed"` 的 run 并带上错误信息；**绝不补数，也不拿前一天的数据顶替**。回答文本为空记 `status="void"`。
- 计费搜索次数取 `usage.tool_usage.web_search`，存为 `billed_searches`；搜索轮数（`web_search_call` 的个数）存为 `search_rounds`。两者分开存。
- 7 个平台的初始映射：smzdm 什么值得买 `smzdm.com`；toutiao 头条号 `toutiao.com`；baijiahao 百家号 `baijiahao.baidu.com`；sohu 搜狐 `sohu.com`；bilibili B站 `bilibili.com`；netease 网易号 `163.com`；zhihu 知乎 `zhihu.com`。按"域名等于后缀或以 `.后缀` 结尾"匹配，多个后缀都能匹配时取最长的。
- 密钥：`ARK_API_KEY`、`SECRET_KEY`、`MYSQL_PASSWORD` 只从环境变量或 `.env` 读，不进仓库、不进数据库、页面上不显示。
- 依赖版本：用 `uv lock` 和 `package-lock.json` 锁定精确版本，不手写 latest。

## Review Focus

1. **服务器时区是 UTC 时，06:00 北京时间是 UTC 前一天 22:00。** 这时 `collect_date` 和 run_id 里的日期必须是北京时间的当天。测试放在 Task 4、Task 10。
2. **当天采集只跑了一半就崩了**（比如进程被杀，10 题里只有 6 题入库）。看板要显示 `x/6` 并列出缺的 4 题，不能显示 `x/10`，也不能空白。测试放在 Task 6。
3. **同一天重复触发采集**（定时任务加手动补跑）时，已经成功的题不能重复调用、不能写出重复的行；只重试之前失败的题。测试放在 Task 4。
4. **同一篇文章的 URL 有多种写法**（`m.` / `www.`、带 `utm_*` / `spm` / `from` 参数）。按"参照文章"去重计数时要算成一篇。测试放在 Task 3、Task 7。
5. **改了别名表**（比如给 mFood 加一个别名"澳门mFood"）。所有历史 run 都要按新版本重新编码，看板只读最新版本的编码，新旧版本不能混在一起。测试放在 Task 9。

---

## 文件结构

```
pyproject.toml / uv.lock / .gitignore / .env.example
app/
  config.py            # Settings：从环境变量读配置
  db.py                # engine、SessionLocal、Base、get_session
  models.py            # 全部 ORM 表
  seed.py              # 题库、别名 v1、平台、默认 settings
  ark.py               # 方舟请求体构造、响应解析、HTTP 调用（从 collect/doubao_api.py 搬过来）
  coding.py            # 别名匹配 → 提及与排位
  urls.py              # URL 规范化、平台映射
  collector.py         # run_daily：采集 + 落库 + 编码
  importer.py          # 导入 trial 的 CSV 和原始响应
  metrics.py           # 当日指标、趋势、自检
  analysis.py          # 域名排行、平台统计、短板题、参照文章
  auth.py              # 密码哈希、登录限流、current_user 依赖
  timeutil.py          # 北京时间的 today()、now()
  worker.py            # APScheduler 入口
  cli.py               # create-user、import-trial、run-daily、recode
  api/__init__.py      # create_app()
  api/routes_*.py      # auth / dashboard / runs / questions / sources / suggestions / settings
migrations/            # alembic
collect/doubao_api.py  # 改成从 app.ark 导入（保留 trial 的 CLI 用法）
tests/                 # pytest；fixtures 直接读 data/raw/trial/*.json
web/                   # Vite React TS
deploy/docker-compose.yml, deploy/Dockerfile, deploy/Caddyfile
scripts/compare_rounds.py
```

---

### Task 1：仓库初始化 + 数据库模型 + 种子数据

**Files：**
- Create：`.gitignore`、`pyproject.toml`、`.env.example`、`app/config.py`、`app/db.py`、`app/models.py`、`app/seed.py`、`app/timeutil.py`、`migrations/`（alembic init，第一个 revision 由 models 自动生成）
- Test：`tests/conftest.py`、`tests/test_seed.py`

**Interfaces：**
- Produces：
  - `app.db.Base`、`app.db.make_engine(url: str)`、`app.db.SessionLocal`、`app.db.get_session()`（FastAPI 依赖，yield Session）
  - `app.timeutil.CST`（ZoneInfo("Asia/Shanghai")）、`now_cst() -> datetime`、`today_cst() -> date`
  - `app.seed.seed_all(session) -> None`（幂等，可以重复执行）
  - ORM 表（列名就是后续任务用的属性名）：
    - `Question`：qid、version、text、branded(bool)、scene、intent、status；主键 (qid, version)
    - `Run`：run_id（主键）、round、qid、question_version、platform、channel、channel_detail、mode、collected_at(DateTime tz)、collect_date(Date，建索引)、collector、account_ref、location、new_session、answer_text(Text)、raw_path、sources_visible(bool)、sources_count、status（valid/void/failed）、error(Text, nullable)、search_queries(Text)、search_rounds、billed_searches(nullable)、input_tokens、output_tokens
    - `Source`：id、run_id(FK)、rank、title、url、url_norm（建索引）、domain、site_name、publish_time_raw、publish_time(DateTime, nullable)、platform_key(nullable)、is_owned(bool)
    - `Coding`：run_id(FK)、alias_version(int)、mention_aomi/mention_mfood/mention_shanfeng(bool)、order_aomi/order_mfood/order_shanfeng(int, nullable)；主键 (run_id, alias_version)
    - `Alias`：id、version(int)、entity、alias
    - `Platform`：key（主键）、name、domain_suffix、publishable(bool)
    - `OwnedPrefix`：id、name、url_prefix
    - `SourceTag`：url_norm（主键）、tag（`external_geo`）、note
    - `JobRun`：id、job（`daily_collect`）、run_date、channel、status（requested/running/done/failed）、requested_by(nullable)、started_at、finished_at、n_ok、n_failed、message
    - `User`：id、username（唯一）、password_hash、is_active、created_at
    - `Setting`：key（主键）、value(Text)。默认值：`api_channel=api-custom`、`alias_version=1`、`weak_recent_n=7`、`weak_mention_ratio=0.5`、`platform_window_days=30`、`price_per_search_yuan`、`price_input_per_1k_yuan`、`price_output_per_1k_yuan`（后三项默认为空）
- 测试用 SQLite 内存库（`conftest.py` 提供 `session` fixture）；MySQL 只在 Task 13 的冒烟测试里用。所有字符串列在 MySQL 下必须用 utf8mb4（迁移里设表级 charset）。

- [ ] **Step 1：`git init`，写 `.gitignore`**（忽略 `.env`、`.venv/`、`__pycache__/`、`web/node_modules/`、`web/dist/`、`data/raw/daily/`、`graphify-out/`），然后 `uv init --python 3.12` 生成 pyproject 并加依赖。
- [ ] **Step 2：写失败的测试 `tests/test_seed.py`**

```python
def test_seed_questions_v3(session):
    seed_all(session); seed_all(session)              # 跑两次，验证幂等
    qs = session.scalars(select(Question).where(Question.version == "v3")).all()
    assert len(qs) == 15
    assert {q.qid for q in qs if q.branded} == {"Q03", "Q12", "Q13", "Q14", "Q15"}

def test_seed_aliases_platforms_settings(session):
    seed_all(session)
    assert {a.alias for a in session.scalars(select(Alias).where(Alias.entity == "shanfeng"))} == {"闪蜂", "閃蜂"}
    assert session.get(Platform, "baijiahao").domain_suffix == "baijiahao.baidu.com"
    assert len(session.scalars(select(Platform)).all()) == 7
    assert session.get(Setting, "api_channel").value == "api-custom"

def test_today_cst_when_utc_is_previous_day():
    assert today_cst(datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)) == date(2026, 10, 22)
```
（为了能测，`today_cst` 接收一个可选的 `at: datetime | None` 参数。）

- [ ] **Step 3：运行 `uv run pytest tests/test_seed.py -v`**，预期 FAIL（ImportError）
- [ ] **Step 4：实现 models / seed / timeutil / config**。题库从 `data/questions/questions-v3-15.csv` 读取（utf-8-sig），列名照抄 CSV（qid、scene、question、branded、intent、status）。
- [ ] **Step 5：运行测试**，预期 PASS；再运行 `uv run alembic revision --autogenerate -m init`，生成的迁移文件里能看到 11 张表
- [ ] **Step 6：Commit** `feat: db models, seed data, alembic init`

---

### Task 2：方舟客户端模块

**Files：**
- Create：`app/ark.py`
- Modify：`collect/doubao_api.py`（删掉 `build_body` / `parse_response` / `search_queries` / `call_api` 这几个定义，改为 `from app.ark import ...`；CLI 参数和行为不变）
- Test：`tests/test_ark.py`

**Interfaces：**
- Produces：
  - `build_body(question: str, channel: str, model: str = DEFAULT_MODEL, location: tuple[str,str,str] | None = ("中国","广东","深圳"), limit: int = 10, max_tool_calls: int = 3) -> dict`，channel 取 `"api-custom"` 或 `"api-plugin"`（custom 不带 user_location）
  - `@dataclass ArkResult: text: str; citations: list[dict]; search_queries: list[str]; billed_searches: int | None; input_tokens: int | None; output_tokens: int | None`
  - `parse(resp: dict) -> ArkResult`（citations 的去重规则沿用原来的 `parse_response`：同一个 url 只算一次）
  - `parse_publish_time(raw: str) -> datetime | None`：同时支持 ISO 格式和"2026年10月15"（后者按北京时间 00:00）；解析不了返回 None
  - `class ArkClient(Protocol): def create(self, body: dict) -> dict`；`HttpArkClient(api_key: str, timeout: int = 180)` 实现它，HTTP 错误抛 `ArkError(str)`

- [ ] **Step 1：写失败的测试**，fixture 直接读 `data/raw/trial/*.json` 里的 `response` 字段

```python
def test_parse_custom_trial_totals():
    rs = [parse(load(f)) for f in glob("data/raw/trial/trial-doubao-api-custom-*.json")]
    assert len(rs) == 15
    assert sum(r.billed_searches for r in rs) == 42
    assert sum(len(r.citations) for r in rs) == 69          # 和 sources-trial.csv 里 custom 的行数一致

def test_parse_plugin_billed_vs_rounds():
    rs = [parse(load(f)) for f in glob("data/raw/trial/trial-doubao-api-plugin-*.json")]
    assert sum(r.billed_searches for r in rs) == 83
    assert sum(len(r.search_queries) for r in rs) == 27

def test_build_body_custom_has_no_location():
    tool = build_body("q", "api-custom")["tools"][0]
    assert tool == {"type": "web_search", "sources": ["doubao"]}

def test_parse_publish_time_both_formats():
    assert parse_publish_time("2026-09-11T19:14:05+08:00").day == 11
    assert parse_publish_time("2026年10月15").date() == date(2026, 10, 15)
    assert parse_publish_time("") is None
```

- [ ] **Step 2：运行 `uv run pytest tests/test_ark.py -v`**，预期 FAIL
- [ ] **Step 3：实现 `app/ark.py`，修改 `collect/doubao_api.py` 改为导入**（`billed_searches` 读 `usage.tool_usage.web_search`）
- [ ] **Step 4：运行测试**，预期 PASS；再运行 `uv run python collect/doubao_api.py --round trial --rep 1 --variant custom --qids Q01 --dry-run`，确认请求体输出和改动前一致
- [ ] **Step 5：Commit** `refactor: move ark client into app.ark`

---

### Task 3：编码（别名匹配）+ URL 规范化 + 平台映射

**Files：**
- Create：`app/coding.py`、`app/urls.py`
- Test：`tests/test_coding.py`、`tests/test_urls.py`

**Interfaces：**
- Produces：
  - `ENTITIES = ("aomi", "mfood", "shanfeng")`
  - `@dataclass CodingResult: mention: dict[str, bool]; order: dict[str, int | None]`
  - `code_answer(text: str, aliases: dict[str, list[str]]) -> CodingResult`：每家取所有别名里**最早出现的位置**；排位是被提及的几家按这个位置从小到大排，从 1 开始；没提到的那家排位为 None
  - `load_aliases(session, version: int) -> dict[str, list[str]]`
  - `normalize_url(url: str) -> str`：scheme 统一成 https，host 转小写并去掉开头的 `www.` 和 `m.`，删掉 `utm_*`、`spm`、`from`、`share_token`、`source` 这几种查询参数，去掉 fragment 和末尾的 `/`
  - `platform_for(domain: str, platforms: list[Platform]) -> str | None`（最长后缀优先）
  - `is_owned(url: str, prefixes: list[OwnedPrefix]) -> bool`

- [ ] **Step 1：写失败的测试**

```python
A = {"aomi": ["澳觅", "澳覓", "Aomi", "aomi", "AOMI"], "mfood": ["mFood", "MFood", "mfood", "澳門Food", "澳门Food"], "shanfeng": ["闪蜂", "閃蜂"]}

def test_order_among_three_only():
    r = code_answer("推荐 Klook、mFood，其次澳覓；閃蜂也行", A)
    assert r.order == {"mfood": 1, "aomi": 2, "shanfeng": 3}

def test_not_mentioned_is_none():
    r = code_answer("用美团吧", A)
    assert r.mention == {"aomi": False, "mfood": False, "shanfeng": False} and r.order["aomi"] is None

def test_trial_custom_regression(trial_custom_texts):     # fixture：10 道不带品牌名的题的 answer_text
    rs = [code_answer(t, A) for t in trial_custom_texts]
    assert sum(r.mention["aomi"] for r in rs) == 8
    assert sum(r.mention["mfood"] for r in rs) == 7
    assert sum(r.mention["shanfeng"] for r in rs) == 5
    assert sum(r.order["aomi"] == 1 for r in rs) == 4   # 和 analysis/quick_scan.py 的结果一致

def test_normalize_url_variants_equal():
    a = normalize_url("https://m.sohu.com/a/123?utm_source=x&spm=1#top")
    assert a == normalize_url("http://www.sohu.com/a/123/") == "https://sohu.com/a/123"

def test_platform_longest_suffix(platforms):
    assert platform_for("baijiahao.baidu.com", platforms) == "baijiahao"
    assert platform_for("www.baidu.com", platforms) is None
    assert platform_for("post.m.smzdm.com", platforms) == "smzdm"
    assert platform_for("notsohu.com", platforms) is None
```

- [ ] **Step 2：运行测试**，预期 FAIL
- [ ] **Step 3：实现**
- [ ] **Step 4：运行测试**，预期 PASS
- [ ] **Step 5：Commit** `feat: alias coding, url normalization, platform mapping`

---

### Task 4：每日采集 `run_daily`

**Files：**
- Create：`app/collector.py`、`tests/fakes.py`（`FakeClient`：`from_trial(variant)` 按 qid 回放 trial 的响应；`failing_for(qids, times)` 让指定题前 times 次抛 `ArkError`、之后回放；提供 `calls_for(qid)` 和 `total_calls`。Task 7、9、10 的测试都复用它）
- Test：`tests/test_collector.py`

**Interfaces：**
- Consumes：`ArkClient`、`build_body`、`parse`、`parse_publish_time`（Task 2）；`code_answer`、`load_aliases`、`normalize_url`、`platform_for`、`is_owned`（Task 3）；`today_cst`、`now_cst`（Task 1）
- Produces：
  - `@dataclass JobSummary: run_date: date; channel: str; n_ok: int; n_failed: int; n_skipped: int; failed_qids: list[str]`
  - `run_daily(session, client: ArkClient, run_date: date, channel: str, raw_dir: Path, sleep_s: float = 1.0, retries: int = 2) -> JobSummary`
  - `store_run(session, run: Run, result: ArkResult, raw: dict) -> None`：写 Source 行和当前 alias_version 的 Coding，`collector` 和 `importer` 共用
- 行为：
  - 题目取 settings 里的题库版本 v3，按 qid 顺序逐题跑。
  - 已有 `status` 为 valid 或 void 的 run 直接跳过，计入 n_skipped。已有 failed 的 run 先删掉再重跑。
  - 每次调用的原始响应写到 `raw_dir/{run_id}.json`，内容是 `{request, response, collected_at}`，和 trial 的格式相同。
  - 回答文本为空时，记 `status="void"`。
  - 每题提交一次事务，这样中途崩溃时已经完成的题不会丢。

- [ ] **Step 1：写失败的测试**（`FakeClient` 依次回放 trial 的响应，或者按配置抛出 `ArkError`）

```python
def test_run_daily_writes_runs_sources_codings(session, tmp_path):
    s = run_daily(session, FakeClient.from_trial("custom"), date(2026, 10, 22), "api-custom", tmp_path, sleep_s=0)
    assert (s.n_ok, s.n_failed) == (15, 0)
    r = session.get(Run, "daily-doubao-api-custom-Q01-20261022")
    assert r.collect_date == date(2026, 10, 22) and r.round == "daily" and r.question_version == "v3"
    assert session.query(Source).count() == 69
    assert session.query(Coding).filter_by(alias_version=1).count() == 15

def test_failure_after_retries_records_failed_no_fabrication(session, tmp_path):
    c = FakeClient.failing_for({"Q05"}, times=3)
    s = run_daily(session, c, date(2026, 10, 22), "api-custom", tmp_path, sleep_s=0)
    r = session.get(Run, "daily-doubao-api-custom-Q05-20261022")
    assert r.status == "failed" and r.error and r.answer_text == ""
    assert s.failed_qids == ["Q05"] and c.calls_for("Q05") == 3
    assert session.query(Coding).filter_by(run_id=r.run_id).count() == 0

def test_rerun_same_day_only_retries_failed(session, tmp_path):
    run_daily(session, FakeClient.failing_for({"Q05"}, times=3), D, "api-custom", tmp_path, sleep_s=0)
    c2 = FakeClient.from_trial("custom")
    s2 = run_daily(session, c2, D, "api-custom", tmp_path, sleep_s=0)
    assert c2.total_calls == 1 and s2.n_skipped == 14
    assert session.query(Run).filter_by(collect_date=D).count() == 15

def test_empty_answer_is_void(session, tmp_path): ...       # Fake 返回不含 message 的响应 → status == "void"

def test_collect_date_is_cst(session, tmp_path, freeze_utc_2026_10_21_2200): ...  # run_date 用 today_cst() 算出 → run_id 结尾是 20261022
```

- [ ] **Step 2：运行测试**，预期 FAIL
- [ ] **Step 3：实现 `run_daily` 和 `store_run`**（`publish_time_raw` 保存原文，`publish_time` 存解析后的值；`domain` 取 `urlparse(url).netloc`；`search_queries` 用 ` | ` 拼接）
- [ ] **Step 4：运行测试**，预期 PASS
- [ ] **Step 5：Commit** `feat: daily collector with retry and idempotency`

---

### Task 5：导入 trial 数据 + CLI

**Files：**
- Create：`app/importer.py`、`app/cli.py`
- Test：`tests/test_importer.py`

**Interfaces：**
- Consumes：`parse`（Task 2）、`store_run`（Task 4）
- Produces：
  - `import_trial(session, raw_dir: Path = Path("data/raw/trial")) -> int`：从原始 JSON 重新解析，**不读 CSV 里的 answer_text**，保证和日常采集走同一套解析。run_id 沿用原文件名（例如 `trial-doubao-api-custom-Q01-1`），`round="trial"`，`question_version="v3"`，`collect_date` 取 `collected_at` 的日期。重复导入时跳过已存在的 run。
  - CLI（`uv run python -m app.cli <cmd>`）：`import-trial`、`run-daily [--date YYYY-MM-DD] [--channel api-custom]`、`create-user <username>`（交互输入密码，Task 8 实现）、`recode`（Task 9 实现）

- [ ] **Step 1：写失败的测试**

```python
def test_import_trial(session):
    assert import_trial(session) == 30 and import_trial(session) == 0
    assert session.query(Run).filter_by(round="trial").count() == 30
    assert session.query(Source).count() == 165
    assert {r.question_version for r in session.query(Run)} == {"v3"}
```

- [ ] **Step 2：运行**，预期 FAIL；**Step 3：实现**；**Step 4：运行**，预期 PASS
- [ ] **Step 5：Commit** `feat: trial importer and cli`

---

### Task 6：当日指标、趋势和自检

**Files：**
- Create：`app/metrics.py`
- Test：`tests/test_metrics.py`

**Interfaces：**
- Consumes：Run、Coding、Question（Task 1）
- Produces：
  - `@dataclass Ratio: num: int; den: int`，提供 `def pct(self) -> float | None`（den 为 0 时返回 None）
  - `@dataclass DailyMetrics: date: date; channel: str; n_expected: int; n_valid: int; missing_qids: list[str]; mention: dict[str, Ratio]; first: dict[str, Ratio]; share: dict[str, Ratio]; selfcheck_failures: list[str]`
  - `daily_metrics(session, d: date, channel: str, alias_version: int) -> DailyMetrics`
  - `trend(session, start: date, end: date, channel: str, alias_version: int) -> list[DailyMetrics]`：每天一条，**没有数据的日期也输出**（n_valid 为 0），前端据此显示"缺数据"
- 口径（来自 spec §4.5）：
  - 题目范围：v3 里不带品牌名的 10 题；只取 `round="daily"` 并且 `channel` 等于参数的 run。
  - 分母：当天 status 为 valid 的 run 数。void、failed 和缺失的题都列进 `missing_qids`，`n_expected` 固定为 10。
  - `mention[e] = Ratio(提到 e 的 run 数, 分母)`
  - `first[e] = Ratio(e 排第 1 的 run 数, 分母)`
  - `share[e] = Ratio(提到 e 的 run 数, 三家提及次数之和)`
- 自检（任何一条不通过，就把对应的指标名写进 `selfcheck_failures`）：
  - 每一家都满足 `first.num ≤ mention.num`
  - 三家的 share 分子之和等于分母
  - 查询结果里只有一个 channel
  - n_valid ≤ 10

- [ ] **Step 1：写失败的测试**（用构造的 Run 和 Coding 数据）

```python
def test_mention_8_of_10(session, day_with_codings):          # 10 题都有效，其中 8 题提到澳觅
    m = daily_metrics(session, D, "api-custom", 1)
    assert (m.mention["aomi"].num, m.mention["aomi"].den) == (8, 10)

def test_branded_and_other_channel_excluded(session): ...    # Q03 提到澳觅、api-plugin 的数据都不计入
def test_partial_day_denominator_and_missing(session):      # 只有 6 题有效，Q05 failed，另外 3 题完全没有
    m = daily_metrics(session, D, "api-custom", 1)
    assert m.n_valid == 6 and m.mention["aomi"].den == 6 and len(m.missing_qids) == 4

def test_no_data_day_is_none_not_zero(session):
    m = daily_metrics(session, D, "api-custom", 1)
    assert m.n_valid == 0 and m.mention["aomi"].pct() is None

def test_share(session, day_with_codings): ...              # 澳觅 8、mFood 7、闪蜂 5 → share aomi == Ratio(8, 20)
def test_selfcheck_flags_first_gt_mention(session): ...     # 构造一条 order_aomi=1 但 mention_aomi=False 的坏数据 → 报 "first_aomi"
def test_trend_includes_empty_days(session): ...            # 3 天里只有 1 天有数据 → 输出 3 条
```

- [ ] **Step 2：运行**，预期 FAIL；**Step 3：实现**（只读 `Coding.alias_version == alias_version` 的编码）；**Step 4：运行**，预期 PASS
- [ ] **Step 5：Commit** `feat: daily metrics, trend and self-checks`

---

### Task 7：信源分析和优化建议

**Files：**
- Create：`app/analysis.py`
- Test：`tests/test_analysis.py`

**Interfaces：**
- Consumes：Source、Run、Coding、Platform、SourceTag、Question
- Produces：
  - `domain_ranking(session, channel: str, start: date, end: date, limit: int = 50) -> list[tuple[str, int]]`
  - `@dataclass PlatformCount: key: str; name: str; count: int; verified: bool`（count 为 0 时 verified=False，前端显示"未验证"）
  - `platform_counts(session, channel: str, start: date, end: date, qids: list[str] | None = None) -> list[PlatformCount]`：固定返回 7 个平台（publishable=True 的那些），按 count 从高到低排；count 为 0 的平台也要出现
  - `@dataclass WeakQuestion: qid: str; text: str; n_runs: int; aomi_mentions: int; aomi_first: int; competitor_first: int; reasons: list[str]`
  - `weak_questions(session, channel: str, today: date, recent_n: int = 7, mention_ratio: float = 0.5, alias_version: int = 1) -> list[WeakQuestion]`：每道不带品牌名的题取最近 `recent_n` 条 valid 的 daily run。满足 `aomi_mentions < mention_ratio * n_runs` 时，reasons 加 `"mention_low"`；满足 `competitor_first > aomi_first` 时（competitor_first = 三家里排第 1 的是 mfood 或 shanfeng 的 run 数），reasons 加 `"competitor_ahead"`。n_runs 为 0 的题不返回。
  - `@dataclass RefArticle: url_norm: str; url: str; title: str; domain: str; platform_key: str | None; count: int; external_geo: bool`
  - `reference_articles(session, qid: str, channel: str, end: date, days: int = 30, limit: int = 5) -> list[RefArticle]`：按 url_norm 分组计数；`url` 和 `title` 取最近一次出现时的值
  - `owned_citations(session, channel: str, start: date, end: date) -> list[Source]`（is_owned=True 的明细）

- [ ] **Step 1：写失败的测试**

```python
def test_platform_counts_include_zero(session, daily_from_trial):   # fixture：run_daily(FakeClient.from_trial("custom"), D0)
    pc = {p.key: p for p in platform_counts(session, "api-custom", D0, D1)}
    assert len(pc) == 7 and pc["zhihu"].count == 0 and pc["zhihu"].verified is False

def test_weak_mention_low(session): ...         # 某题 7 条 run 里只有 3 条提到澳觅 → reasons == ["mention_low"]
def test_weak_competitor_ahead(session): ...    # 7 条 run 都提到澳觅，但其中 4 条 mFood 排第一、澳觅排第一的只有 2 条 → ["competitor_ahead"]
def test_ref_articles_dedupe_url_variants(session):   # 同一篇文章以 m.sohu.com?utm=… 和 www.sohu.com 两种写法出现 → 一条记录，count == 2
    ...
def test_external_geo_flag(session): ...        # 给 SourceTag 加一条 external_geo → RefArticle.external_geo is True
```

- [ ] **Step 2：运行**，预期 FAIL；**Step 3：实现**；**Step 4：运行**，预期 PASS
- [ ] **Step 5：Commit** `feat: source analysis, weak questions, platform ranking`

---

### Task 8：登录与鉴权

**Files：**
- Create：`app/auth.py`、`app/api/__init__.py`、`app/api/routes_auth.py`
- Modify：`app/cli.py`（`create-user`）
- Test：`tests/test_auth.py`

**Interfaces：**
- Produces：
  - `hash_password(p: str) -> str`、`verify_password(p: str, h: str) -> bool`（bcrypt）
  - `create_app(session_factory=None) -> FastAPI`：挂 `SessionMiddleware(secret_key=SECRET_KEY, https_only=settings.cookie_secure, same_site="lax")`，所有路由都放在 `/api` 下
  - `current_user(request, session) -> User`：FastAPI 依赖，没登录抛 401。除 `POST /api/auth/login` 和 `GET /api/health` 外，所有路由都要依赖它
  - 路由：`POST /api/auth/login {username, password}` 返回 200 `{username}` 或 401；`POST /api/auth/logout`；`GET /api/auth/me`
  - 登录限流：同一个 (username, client_ip) 在 15 分钟内失败 5 次后，返回 429，持续到窗口结束。计数存在进程内存里（单实例部署，够用）
  - CLI：`create-user <username>` 用 getpass 读两次密码，两次一致才创建

- [ ] **Step 1：写失败的测试**（用 FastAPI TestClient）

```python
def test_protected_requires_login(client): assert client.get("/api/auth/me").status_code == 401
def test_login_ok_then_me(client, user_alice): ...          # 登录 200 → /me 返回 alice
def test_wrong_password_401_and_rate_limit(client, user_alice):
    for _ in range(5): assert login(client, "alice", "bad").status_code == 401
    assert login(client, "alice", "correct").status_code == 429
def test_inactive_user_cannot_login(client, user_inactive): ...
```

- [ ] **Step 2：运行**，预期 FAIL；**Step 3：实现**；**Step 4：运行**，预期 PASS
- [ ] **Step 5：Commit** `feat: session auth with rate limiting`

---

### Task 9：业务 API

**Files：**
- Create：`app/api/routes_dashboard.py`、`routes_runs.py`、`routes_questions.py`、`routes_sources.py`、`routes_suggestions.py`、`routes_settings.py`
- Modify：`app/cli.py`（`recode`）、`app/coding.py`（加 `recode_all`）
- Test：`tests/test_api.py`

**Interfaces：**
- Consumes：Task 6 的 `daily_metrics` / `trend`；Task 7 的全部函数；Task 3 的 `code_answer`；Task 8 的 `current_user`
- Produces（JSON 字段名就是前端要用的名字。Ratio 序列化为 `{num, den}`，日期用 ISO 格式）：
  - `GET /api/dashboard?date=&channel=` → `{date, channel, latest_date, metrics: DailyMetrics, job: {status, n_ok, n_failed, message} | null, usage: {billed_searches, input_tokens, output_tokens, est_cost_yuan | null}}`。`date` 不传时取最近一个有 valid run 的日期；`channel` 不传时取 settings 里的 `api_channel`
  - `GET /api/dashboard/trend?start=&end=&channel=` → `list[DailyMetrics]`
  - `GET /api/runs?date_from=&date_to=&qid=&channel=&aomi_mentioned=&status=&page=&size=` → `{total, items:[{run_id, collect_date, qid, question, channel, status, mention:{...}, order:{...}, sources_count}]}`
  - `GET /api/runs/{run_id}` → run 的全部字段、当前 alias_version 下的 coding、sources 列表（每条带 platform_key、is_owned、external_geo）
  - `GET /api/questions` → 15 题（只读）
  - `GET /api/sources/domains`、`GET /api/sources/platforms`、`GET /api/sources/owned`，参数都是 `start, end, channel`；`POST /api/sources/tags {url, tag:"external_geo", note}`（服务端先做 normalize_url）；`DELETE /api/sources/tags?url=`
  - `GET /api/suggestions?channel=` → `[{weak: WeakQuestion, platforms: list[PlatformCount], references: list[RefArticle]}]`，外加一个固定字段 `notice: "排序来自 {channel} 渠道的信源，App 可能不同。"`
  - Settings：`GET/PUT /api/settings`（只允许修改白名单内的 key）；`GET /api/settings/aliases`；`PUT /api/settings/aliases {entity: [alias…]}` → 新建 `version = 当前 + 1` 的完整别名表，调用 `recode_all(session, new_version)`，最后把 settings 里的 `alias_version` 更新为新版本；`GET/PUT /api/settings/platforms`；`GET/POST/DELETE /api/settings/owned-prefixes`（改动后重算所有 Source 的 is_owned）；`GET /api/settings/jobs?limit=30`；`POST /api/settings/jobs/rerun {date}` → 插入一条 `JobRun(status="requested")`；`GET/POST /api/settings/users`、`PATCH /api/settings/users/{id} {is_active}`
  - `recode_all(session, alias_version: int) -> int`：对所有 status=valid 的 run 用指定版本的别名表重新编码，写入新版本的 Coding 行，旧版本的保留；返回编码的条数

- [ ] **Step 1：写失败的测试**

```python
def test_all_business_routes_require_auth(client):
    for p in ["/api/dashboard", "/api/runs", "/api/sources/platforms", "/api/suggestions", "/api/settings"]:
        assert client.get(p).status_code == 401

def test_dashboard_defaults_to_latest_day(authed, seeded_daily_two_days): ...   # 不传 date → latest_date 是第二天

def test_alias_change_recodes_and_dashboard_uses_new(authed, seeded_one_day):
    before = authed.get("/api/dashboard").json()["metrics"]["mention"]["mfood"]["num"]
    aliases = authed.get("/api/settings/aliases").json()
    aliases["mfood"].append("M Food")                             # fixture 里有 1 题只用"M Food"这个写法（不含已有别名的子串）
    assert authed.put("/api/settings/aliases", json=aliases).status_code == 200
    after = authed.get("/api/dashboard").json()["metrics"]["mention"]["mfood"]["num"]
    assert after == before + 1
    assert authed.get("/api/settings").json()["alias_version"] == "2"

def test_rerun_creates_requested_job(authed): ...
def test_settings_rejects_unknown_key(authed): ...           # PUT {"ARK_API_KEY": "x"} → 422
def test_run_detail_includes_sources_and_coding(authed, seeded_one_day): ...
```

- [ ] **Step 2：运行**，预期 FAIL；**Step 3：实现**（每个路由文件一个 APIRouter，在 `create_app` 里注册）；**Step 4：运行**，预期 PASS
- [ ] **Step 5：Commit** `feat: business api routes`

---

### Task 10：Worker（定时采集 + 手动补跑）

**Files：**
- Create：`app/worker.py`
- Test：`tests/test_worker.py`

**Interfaces：**
- Consumes：`run_daily`（Task 4）、`today_cst`（Task 1）、JobRun
- Produces：
  - `daily_job(session_factory, client: ArkClient, raw_dir: Path, at: datetime | None = None) -> JobRun`：算出 `today_cst(at)`，写一条 JobRun（running → done/failed），调用 `run_daily`，把 n_ok、n_failed 和失败题号写进 message
  - `process_requested(session_factory, client, raw_dir) -> int`：把 `status="requested"` 的 JobRun 逐条按它的 run_date 执行，返回处理的条数
  - `main()`：BlockingScheduler(timezone="Asia/Shanghai")，配置 `cron hour=6 minute=0` 跑 `daily_job`，每 60 秒跑一次 `process_requested`；`coalesce=True`，`misfire_grace_time=3600`
  - 进程启动时，如果已经过了今天 06:00，并且今天还没有 done 的 daily_collect，就立即补跑一次（spec：不补数是指不伪造数据，不是指不重跑）

- [ ] **Step 1：写失败的测试**

```python
def test_daily_job_uses_cst_date(session_factory, tmp_path):
    jr = daily_job(session_factory, FakeClient.from_trial("custom"), tmp_path, at=datetime(2026,10,21,22,0,tzinfo=timezone.utc))
    assert jr.run_date == date(2026, 10, 22) and jr.status == "done" and jr.n_ok == 15

def test_process_requested_runs_and_marks_done(session_factory, tmp_path): ...
def test_job_failed_status_when_all_fail(session_factory, tmp_path): ...   # 15 题全部失败 → status == "failed"，message 里列出全部题号
```

- [ ] **Step 2：运行**，预期 FAIL；**Step 3：实现**；**Step 4：运行**，预期 PASS
- [ ] **Step 5：Commit** `feat: scheduler worker`

---

### Task 11：前端骨架、登录和看板

**Files：**
- Create：`web/`（`npm create vite@5 web -- --template react-ts`）、`web/src/api.ts`、`web/src/format.ts`、`web/src/App.tsx`（路由和左侧导航）、`web/src/pages/Login.tsx`、`web/src/pages/Dashboard.tsx`
- Test：`web/src/format.test.ts`

**Interfaces：**
- Consumes：Task 8、Task 9 的接口
- Produces：
  - `formatRatio(r: {num:number, den:number}): string`：`{8,10}` → `"8/10（80%）"`，den 为 0 → `"无数据"`，百分比四舍五入取整
  - `api.ts`：所有请求带 `credentials: "include"`，遇到 401 跳转到 `/login`
  - 布局：antd `Layout` 左侧 `Sider` 导航，菜单顺序为 看板 / 回答记录 / 题目 / 信源分析 / 优化建议 / 设置，风格参考 Answerbit 的数据密集型后台
  - 看板：
    - 日期选择，默认最近一天
    - 渠道标签，显示当前 API 渠道
    - 三家对比的指标卡：提及率、**三家中首位率**、提及份额，全部用 formatRatio 显示
    - 今日采集状态卡：done / failed / 缺数据，以及失败的题号
    - 缺题提示："今天只采到 6/10 题，缺：Q05、…"
    - 自检未通过的指标显示"自检未通过：原因"，不显示数字
    - ECharts 趋势折线：三家提及率，没有数据的日期断开（值为 null），不连线
    - 今日消耗：计费搜索次数、token、估算费用（没配置单价时显示"未配置单价"）

- [ ] **Step 1：写失败的测试 `format.test.ts`**

```ts
expect(formatRatio({num: 8, den: 10})).toBe("8/10（80%）");
expect(formatRatio({num: 0, den: 0})).toBe("无数据");
expect(formatRatio({num: 2, den: 3})).toBe("2/3（67%）");
```

- [ ] **Step 2：运行 `npm --prefix web run test`**，预期 FAIL；**Step 3：实现 format 和各页面**；**Step 4：运行 test**，预期 PASS，并且 `npm --prefix web run build` 无报错
- [ ] **Step 5：手工验收**：本地起 `uv run uvicorn app.api:create_app --factory` 和 `npm --prefix web run dev`（vite 把 `/api` 代理到 8000），导入 trial 数据后，再执行一次 `run-daily`（不想调用真实 API 时，可以把 trial 导入成某一天的 daily 数据）。登录后，在看板上确认看到的是 `8/10（80%）` 这种格式，并且有"三家中首位率"这个名称
- [ ] **Step 6：Commit** `feat: web shell, login, dashboard`

---

### Task 12：前端其余页面

**Files：**
- Create：`web/src/pages/Runs.tsx`、`Questions.tsx`、`Sources.tsx`、`Suggestions.tsx`、`Settings.tsx`
- Test：`web/src/format.test.ts`（补测 `platformLabel`）

**Interfaces：**
- Consumes：Task 9 的接口
- Produces：
  - `platformLabel(p: PlatformCount): string`：count 为 0 时 → `"知乎 0（未验证）"`
  - **回答记录**：左边是列表，带筛选条件（日期范围、题目、渠道、是否提到澳觅、状态）；右边是详情，显示回答原文（三家的名字高亮）、信源表（排名、标题链接、站点、平台、是否自有、外部 GEO 标签开关）和搜索词
  - **题目**：只读表格，显示 qid、题目、是否带品牌名、场景、版本
  - **信源分析**：日期范围；域名排行表；7 个平台的柱状图（0 次的平台要显示，并标"未验证"）；自有内容被引用的明细
  - **优化建议**：短板题卡片，显示原因（"提及不足：3/7"、"被竞品压住：mFood 排第一 4 次 vs 澳觅 2 次"）、平台推荐和参照文章（外部 GEO 文章带标签）；页面顶部固定显示 `notice` 文案；"写文章"按钮置灰，提示"第二阶段"
  - **设置**：别名表编辑（保存时弹窗确认"会生成新版本并重算全部历史数据"）、平台映射、自有渠道前缀、短板阈值、单价、采集任务列表和"补跑某天"、账号管理（新建、停用）

- [ ] **Step 1：写失败的测试** `expect(platformLabel({key:"zhihu",name:"知乎",count:0,verified:false})).toBe("知乎 0（未验证）")`
- [ ] **Step 2：运行**，预期 FAIL；**Step 3：实现**；**Step 4：运行 test 和 build**，预期 PASS
- [ ] **Step 5：手工验收**：逐页点一遍；在设置里给 mFood 加一个别名，回到看板确认数字跟着变了；在回答记录里给一条搜狐信源打上外部 GEO 标签，到优化建议页确认能看到这个标签
- [ ] **Step 6：Commit** `feat: runs, questions, sources, suggestions, settings pages`

---

### Task 13：Docker 部署 + MySQL 冒烟 + 服务器对照试跑

**Files：**
- Create：`deploy/Dockerfile`（多阶段构建：node:20 构建 web → python:3.12-slim 安装 uv 依赖；同一个镜像，用不同 command 启动 api 和 worker）、`deploy/docker-compose.yml`、`deploy/Caddyfile`、`.env.example`、`scripts/compare_rounds.py`、`docs/deploy.md`
- Test：`tests/test_mysql_smoke.py`（标记为 `@pytest.mark.mysql`，默认跳过，`MYSQL_TEST_URL` 存在时才跑）

**Interfaces：**
- compose 服务：
  - `mysql`：mysql:8.4，`--character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci`，数据卷 `mysql_data`
  - `api`：`alembic upgrade head && uvicorn app.api:create_app --factory --host 0.0.0.0 --port 8000`
  - `worker`：`python -m app.worker`
  - `caddy`：提供 `/srv/web`（构建产物），`/api/*` 反向代理到 `api:8000`；站点地址来自 `${SITE_DOMAIN}`，自动申请 HTTPS
  - 所有服务设置 `TZ=Asia/Shanghai`；`api` 和 `worker` 共享卷 `raw_data` 挂载到 `/app/data/raw/daily`
- `.env.example` 的键：`SITE_DOMAIN`、`MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`、`DATABASE_URL`、`ARK_API_KEY`、`SECRET_KEY`、`COOKIE_SECURE=true`
- `scripts/compare_rounds.py --a-round trial --b-date YYYY-MM-DD --channel api-custom`：拿 trial 那一轮和某一天的 daily 数据，逐题打印信源域名的 Jaccard、均值，以及澳觅是否被提及的一致情况

- [ ] **Step 1：写 `tests/test_mysql_smoke.py`**：在 MySQL 上执行 `alembic upgrade head`，然后 `seed_all`、`import_trial`，断言 30 runs / 165 sources，并且中文 `answer_text` 读回来与原文一致（验证 utf8mb4）
- [ ] **Step 2：本机执行 `colima start`、`docker compose -f deploy/docker-compose.yml up -d mysql`，再运行 `MYSQL_TEST_URL=... uv run pytest -m mysql -v`**，预期 PASS
- [ ] **Step 3：执行 `docker compose up -d --build`**，然后 `docker compose exec api python -m app.cli create-user admin`。本机访问 `https://localhost`（Caddy 用内部证书）能登录；`docker compose exec api python -m app.cli import-trial` 之后，回答记录里能看到 trial 数据，看板不受影响（trial 不进看板）
- [ ] **Step 4：写 `docs/deploy.md`**，内容包括：
  - 服务器上的步骤（拷贝 `.env`、`up -d`、建账号）
  - 上线前清单：
    - ① **轮换** ARK_API_KEY（旧 Key 在对话里出现过）
    - ② 运维确认子域名已 ICP 备案，且接入商和服务器所在云厂商一致
    - ③ 服务器能访问 `ark.cn-beijing.volces.com`
  - **上线后第一件事（spec §4.3）**：在服务器上执行 `python -m app.cli run-daily --channel api-custom`，再执行 `python scripts/compare_rounds.py --a-round trial --b-date <当天> --channel api-custom`，对比本机 trial 和服务器跑出来的信源。如果 Jaccard 明显偏低，或者澳觅提及情况不一致，就在看板的渠道标签旁注明"api-custom 的地区取决于服务器所在地"（spec 的要求，由用户判断是否需要）
- [ ] **Step 5：Commit** `feat: docker deployment and smoke test`
