# 知识库第一期（自建，向量存 MySQL）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在网站上上传 PDF（100MB 以上），后台解析、切块、向量化存进 MySQL；提供只查「现行」文档的混合检索（语义 + 关键词），带 PDF 页码出处；用年刊做验收。

**Architecture:** 新包 `app/kb/`，按职责拆成 PDF 解析（`pdf.py`）、文本归一化和关键词检索（`text.py`）、向量化客户端（`embed.py`）、入库流水线（`ingest.py`）、检索（`search.py`）；对外只暴露这几个函数，以后换 Qdrant 或火山只改这一层（spec §4.8）。上传走分片接口（`app/api/routes_kb.py`），文件落盘到 `KB_DIR`，入库由现有 worker 每 60 秒轮询处理。前端加一个「知识库」页面。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 / alembic / pytest（`uv run pytest`）；新依赖 `pymupdf`、`numpy`、`jieba`、`opencc-python-reimplemented`。React + Ant Design / vitest（`cd web && npm test`，类型检查 `npm run build`）。

**Spec:** `docs/superpowers/specs/2026-10-21-geo-site-design.md` §4.8（以 2026-10-23 的决定为准：自建、向量存 MySQL、不用 Qdrant）。§4.9 GEO 文章不在本计划内。

**前置条件：** 开工前 `git status` 应该是干净的。本会话已改了 spec（§4.8）、新增 `docs/fact-list-draft-2026-10-23.md`，先按主题提交这两份文档再开分支。

## Global Constraints

- 切片原文、元数据、向量都存 MySQL；不加向量库容器（spec §4.8，2026-10-23）。
- 向量化：`POST https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal`，`Authorization: Bearer $ARK_API_KEY`，模型 `doubao-embedding-vision-251215`，`input=[{"type":"text","text":...}]`，**一次请求一个切片**（接口把多段输入合成一个向量），不传 `dimensions`（默认 2048）。
- 检索只用「现行」（`status == "active"`）且已处理完（`process_status == "ready"`）的文档。
- 不做 OCR。整页没有文字的页面记为「无文字层，未入库」，详情页列出；详情页显示每页提取到的字数。
- 出处 = 文档标题 + PDF 页码（对开页再标左 / 右半页）。印刷页码不另存。
- 关键词检索前，文档和查询都要转成简体（年刊是繁体，豆包回答和查询是简体）。
- jieba 自定义词典：澳觅、mFood、闪蜂、+86、支付宝、微信支付、澳门通、MPay（spec §4.8）。
- 每个 schema 改动一个 alembic 迁移，新列带 `server_default`。
- 注释、页面文案用中文，风格照现有代码。

## Review Focus

1. 用户用简体查「澳觅合作商家多少」，年刊里写的是繁体「澳覓合作商家」→ 关键词检索也要命中。测试：Task 3 `test_tokenize_folds_traditional`、Task 6 `test_search_keyword_matches_traditional_doc`。
2. 上传 100MB 文件到一半断网，重试时应从服务器已收到的位置续传，不能从头再传、也不能把同一段写两遍。测试：Task 7 `test_upload_offset_mismatch_returns_received`、Task 8 `upload resumes from server offset`。
3. 向量化处理到第 37 个切片时方舟接口报错 → 文档标「失败」并写原因，已写入的切片清掉，不能出现「检索得到一半文档」。测试：Task 5 `test_process_doc_embed_failure_leaves_no_chunks`。
4. worker 在处理文档时重启 → 文档永远卡在「处理中」。启动时应改回「排队」重新处理。测试：Task 5 `test_recover_stale_requeues_processing_docs`。
5. 把文档改成「失效」后，检索马上查不到它，但文档列表里还在。测试：Task 6 `test_search_excludes_inactive_and_unready`。

---

### Task 1: 数据表、配置和依赖

**Files:**
- Modify: `pyproject.toml`（`uv add pymupdf numpy jieba opencc-python-reimplemented`）
- Modify: `app/config.py`（`Settings.kb_dir`）
- Modify: `app/models.py`（`KbDoc`、`KbPage`、`KbChunk`）
- Create: `migrations/versions/<rev>_knowledge_base.py`（`uv run alembic revision -m "knowledge base"` 生成后手填）
- Modify: `deploy/docker-compose.yml`（api、worker 都挂 `kb_data:/app/data/kb`，`KB_DIR: /app/data/kb`）
- Modify: `.gitignore`（忽略 `data/kb/`）
- Test: `tests/test_migrations.py`、`tests/test_kb_models.py`

**Interfaces:**
- Produces:
  - `Settings.kb_dir: Path`，环境变量 `KB_DIR`，默认 `ROOT / "data" / "kb"`
  - `KbDoc`（表 `kb_docs`）：`id: int` 自增主键；`title: String(256)`；`filename: String(256)`；`size_bytes: BigInteger`；`received_bytes: BigInteger`（server_default `"0"`）；`sha256: String(64)`（server_default `""`，上传完成时写入）；`effective_date: Date`；`status: String(16)`（`active` 现行 / `inactive` 失效）；`process_status: String(16)`（`uploading` / `queued` / `processing` / `ready` / `failed`）；`n_pages / n_chunks / n_embedded: Integer`（server_default `"0"`）；`embed_model: String(64)`（server_default `""`）；`message: Text`；`uploaded_by: String(64)`；`created_at: CSTDateTime`；`processed_at: CSTDateTime | None`
  - `KbPage`（表 `kb_pages`）：主键 (`doc_id` FK→kb_docs.id ON DELETE CASCADE, `page_no: Integer` 从 1 开始)；`n_chars: Integer`；`n_images: Integer`
  - `KbChunk`（表 `kb_chunks`）：`id` 自增主键；`doc_id` FK（CASCADE，带索引）；`seq: Integer`（文档内顺序）；`page_no: Integer`；`half: String(1)`（`L` / `R` / `""`）；`text: LongText`；`tokens: LongText`（归一化后的分词，空格分隔）；`embedding: LargeBinary`（float32 小端字节，MySQL 上用 `mysql.MEDIUMBLOB` variant）；`dim: Integer`
  - 文件路径约定：`kb_dir / f"{doc.id}.pdf"`

- [ ] **Step 1: 写失败的测试**

`tests/test_kb_models.py::test_kb_tables_roundtrip`：建一个 `KbDoc`、两个 `KbPage`、一个 `KbChunk`（`embedding=np.arange(4, dtype="<f4").tobytes()`），读回来字节相等；删除 `KbDoc` 后（SQLite 需 `PRAGMA foreign_keys=ON`，或在测试里显式验证 ORM 级联）`KbPage`、`KbChunk` 都没了。
`tests/test_migrations.py::test_alembic_upgrade_head_creates_all_tables` 的期望表名集合加上 `kb_docs`、`kb_pages`、`kb_chunks`。

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_kb_models.py tests/test_migrations.py -v`
Expected: FAIL（`ImportError: cannot import name 'KbDoc'`；迁移测试缺表）

- [ ] **Step 3: 实现**

模型照 `JobRun` 的写法（`UTF8MB4`、`CSTDateTime`）。ORM 关系上 `KbDoc.pages`、`KbDoc.chunks` 设 `cascade="all, delete-orphan"`，外键同时写 `ondelete="CASCADE"`。迁移的 `downgrade` 按 chunks → pages → docs 顺序删表。

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest -q`
Expected: 全部 PASS（含原有 141 个）

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml uv.lock app/config.py app/models.py migrations/versions/*_knowledge_base.py deploy/docker-compose.yml .gitignore tests/test_kb_models.py tests/test_migrations.py
git commit -m "feat(kb): knowledge base tables and config"
```

---

### Task 2: PDF 解析和切块

**Files:**
- Create: `app/kb/__init__.py`（空）
- Create: `app/kb/pdf.py`
- Modify: `tests/builders.py`（生成测试 PDF 的工具，后面的任务都用它）
- Test: `tests/test_kb_pdf.py`

**Interfaces:**
- Produces:
  - `tests.builders.make_pdf(directory: Path, pages: list[str | None], landscape: bool = False, name: str = "doc.pdf") -> Path`：写到 `directory / name` 并返回路径；每个字符串一页（`page.insert_textbox`，中文用内置字体 `fontname="china-s"`），`None` 表示这页只画一个矩形、没有文字；`make_pdf_bytes(tmp_path, pages) -> bytes` 读回字节。分栏、折行、多块这类特殊版面在 `tests/test_kb_pdf.py` 里单独构造。
  - `@dataclass PageStat: page_no: int; n_chars: int; n_images: int`（`n_chars` = 去掉所有空白后的字符数）
  - `@dataclass ChunkDraft: seq: int; page_no: int; half: str; text: str`
  - `@dataclass ParsedPdf: pages: list[PageStat]; chunks: list[ChunkDraft]`
  - `parse_pdf(path: Path, max_chars: int = 1200) -> ParsedPdf`
  - 打不开 / 不是 PDF 时抛 `PdfError(Exception)`

切块算法（测试决定不了的部分，写死在这里）：
1. 宽 > 高的页面视为对开页，按页面中线切成左右两个半页，`half` 记 `L` / `R`；否则整页一个单元，`half=""`。
2. 每个单元取 `page.get_text("blocks", clip=单元矩形)` 里的文字块（`block[6] == 0`，去掉空块），按 `(列, y0, x0)` 排序，列 = `0 if x0 < 单元中线 else 1`。这样左右两栏的时间线不会交错（已在年刊第 5 页验证：「2025」后面紧跟「註冊用戶超300萬」「合作商家超5,700家」）。
3. 块内换行：两侧都是 CJK 字符时直接拼接，否则用空格拼接；块之间用 `\n` 分隔。
4. 一个单元的文字 ≤ `max_chars` 就是一个切片；超过就按块边界贪心切，每片不超过 `max_chars`（单个块本身超长时按句号「。！？」再切）。切片不跨单元、不跨页。
5. 单元里没有文字就不出切片。`seq` 在整份文档内从 0 递增。

- [ ] **Step 1: 写失败的测试**

```python
def test_spread_page_orders_columns_within_each_half(tmp_path):
    # 横版页面（宽 1200 高 800）；右半页左栏写「2024」「商家5500」，右栏写「2025」「商家5700」，
    # 右栏的块 y 坐标比左栏下面的块更靠上
    parsed = parse_pdf(make_spread_pdf(tmp_path))
    right = [c for c in parsed.chunks if c.half == "R"][0].text
    assert right.index("2025") < right.index("商家5700")
    assert right.index("商家5500") < right.index("2025")

def test_page_without_text_has_zero_chars_and_no_chunk(tmp_path):
    parsed = parse_pdf(make_pdf(tmp_path, pages=["澳觅上线", None]))   # None = 只画一个矩形
    assert [p.n_chars for p in parsed.pages] == [4, 0]
    assert [c.page_no for c in parsed.chunks] == [1]

def test_long_unit_split_at_block_boundaries(tmp_path):
    # 竖版单页，5 个块，每块 400 字
    parsed = parse_pdf(make_pdf_blocks(tmp_path, n_blocks=5, chars=400), max_chars=1200)
    assert [len(c.text.replace("\n", "")) for c in parsed.chunks] == [1200, 800]
    assert all(c.page_no == 1 and c.half == "" for c in parsed.chunks)

def test_cjk_line_wrap_joined_without_space(tmp_path):
    # 一个块里文字被折成两行：「團購」「業務啟動」
    assert "團購業務啟動" in parse_pdf(make_wrapped_pdf(tmp_path)).chunks[0].text

def test_not_a_pdf_raises(tmp_path):
    p = tmp_path / "x.pdf"; p.write_bytes(b"hello")
    with pytest.raises(PdfError):
        parse_pdf(p)

@pytest.mark.skipif(not os.environ.get("KB_SAMPLE_PDF"), reason="本机年刊路径，不进仓库")
def test_yearbook_timeline_page():
    parsed = parse_pdf(Path(os.environ["KB_SAMPLE_PDF"]))
    assert len(parsed.pages) == 88
    p5r = " ".join(c.text for c in parsed.chunks if c.page_no == 5 and c.half == "R")
    assert p5r.index("2025") < p5r.index("5,700")
```

（`make_pdf` 来自 `tests/builders.py`；`make_spread_pdf`、`make_pdf_blocks`、`make_wrapped_pdf` 是本测试文件里的小工具，用 `fitz.open()` + `page.insert_textbox` 在指定矩形里写字。）

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_kb_pdf.py -v`
Expected: FAIL（`ModuleNotFoundError: app.kb.pdf`）

- [ ] **Step 3: 实现 `parse_pdf`**（按上面的算法）

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/test_kb_pdf.py -v`，再跑一次 `KB_SAMPLE_PDF=/Users/xufeifeng/Downloads/十週年年刊.pdf uv run pytest tests/test_kb_pdf.py::test_yearbook_timeline_page -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/kb/__init__.py app/kb/pdf.py tests/test_kb_pdf.py
git commit -m "feat(kb): pdf parsing and layout-aware chunking"
```

---

### Task 3: 文本归一化、分词、BM25、RRF

**Files:**
- Create: `app/kb/text.py`
- Test: `tests/test_kb_text.py`

**Interfaces:**
- Produces:
  - `normalize(text: str) -> str`：`unicodedata.normalize("NFKC")` → OpenCC `t2s` 繁转简 → 小写 → 去掉数字里的千分位逗号（`re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)`，「5,700」→「5700」；jieba 会把「5,700」切成「5 / , / 700」，已实测）。OpenCC 用 `opencc-python-reimplemented`（0.1.7 实测：「澳覓…註冊用戶超300萬…閃蜂、澳門通」→「澳觅…注册用户超300万…闪蜂、澳门通」）
  - `tokenize(text: str) -> list[str]`：`normalize` 后用 `jieba.cut_for_search`，丢掉纯空白和纯标点的词；首次调用时 `jieba.add_word` 加载自定义词典（Global Constraints 里那 8 个词，都按 `normalize` 后的形式加）
  - `bm25_scores(query: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]`：标准 Okapi BM25，idf 用 `log((N - df + 0.5) / (df + 0.5) + 1)`
  - `rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]`：每个 ranking 是按相关度排好的下标列表；返回 (下标, 分数) 按分数降序，分数相同按下标升序

- [ ] **Step 1: 写失败的测试**

```python
def test_tokenize_folds_traditional():
    assert "澳觅" in tokenize("澳覓合作商家超5,700家")
    assert "注册" in tokenize("註冊用戶")

def test_custom_words_not_split():
    toks = tokenize("用+86手机号注册mFood，再用澳门通付款")
    assert {"+86", "mfood", "澳门通"} <= set(toks)

def test_tokenize_drops_punctuation():
    assert not any(t.strip("，。、：；！？（）,.:;!?() ") == "" for t in tokenize("澳觅，外卖。"))

def test_bm25_prefers_doc_with_query_terms():
    docs = [tokenize("澳觅合作商家超过5700家"), tokenize("葡挞和猪扒包很好吃")]
    s = bm25_scores(tokenize("澳觅商家"), docs)
    assert s[0] > 0 and s[1] == 0

def test_normalize_drops_thousands_separator():
    assert normalize("合作商家超5,700家") == "合作商家超5700家"
    assert "5700" in tokenize("澳覓合作商家超5,700家")

def test_rrf_fuses_and_breaks_ties_by_index():
    # 0 和 2 的分数都是 1/61 + 1/62，相同 → 下标小的在前；1 只有 1/63
    assert [i for i, _ in rrf([[2, 0, 1], [0, 2]])] == [0, 2, 1]
    assert [i for i, _ in rrf([[1], [0]])] == [0, 1]
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_kb_text.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/test_kb_text.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/kb/text.py tests/test_kb_text.py
git commit -m "feat(kb): text normalization, tokenizer, bm25 and rrf"
```

---

### Task 4: 向量化客户端

**Files:**
- Modify: `app/ark.py`（把 `HttpArkClient.create` 里的 HTTP 调用和错误处理抽成 `post_json`，`create` 改为调用它）
- Create: `app/kb/embed.py`
- Modify: `tests/fakes.py`（`FakeEmbedder`）
- Test: `tests/test_kb_embed.py`、`tests/test_ark.py`（原有测试保持通过）

**Interfaces:**
- Produces:
  - `app.ark.post_json(url: str, api_key: str, body: dict, timeout: int) -> dict`：错误统一抛 `ArkError`（行为和现在的 `create` 一样）
  - `EMBED_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"`，`EMBED_MODEL = "doubao-embedding-vision-251215"`
  - `class Embedder(Protocol): model: str; def embed(self, text: str) -> list[float]: ...`
  - `build_embed_body(text: str, model: str = EMBED_MODEL) -> dict` → `{"model": model, "encoding_format": "float", "input": [{"type": "text", "text": text}]}`
  - `parse_embedding(resp: dict) -> list[float]`：取 `resp["data"]["embedding"]`；缺字段或不是非空数字列表时抛 `ArkError`
  - `class HttpArkEmbedder: __init__(self, api_key: str, model: str = EMBED_MODEL, timeout: int = 60)`；`embed` 失败重试 2 次（间隔 1s、3s），仍失败抛 `ArkError`
  - `tests.fakes.FakeEmbedder(dim: int = 64, fail_after: int | None = None)`：`model = "fake"`；向量 = 对 `tokenize(text)` 每个词做 `zlib.crc32(词.encode()) % dim` 计数后 L2 归一化（不用内置 `hash`，它每个进程随机）（同词的文本相似度高）；第 `fail_after + 1` 次调用起抛 `ArkError`；记录 `calls: int`

- [ ] **Step 1: 写失败的测试**

```python
def test_build_embed_body_text_only():
    assert build_embed_body("澳觅") == {"model": "doubao-embedding-vision-251215", "encoding_format": "float",
                                        "input": [{"type": "text", "text": "澳觅"}]}

def test_parse_embedding_reads_data_object():
    assert parse_embedding({"data": {"embedding": [0.1, -0.2], "object": "embedding"}}) == [0.1, -0.2]

@pytest.mark.parametrize("resp", [{}, {"data": {}}, {"data": {"embedding": []}}, {"data": [{"embedding": [1.0]}]}])
def test_parse_embedding_rejects_bad_shapes(resp):
    with pytest.raises(ArkError):
        parse_embedding(resp)

def test_http_embedder_retries_then_raises(monkeypatch):
    calls = []
    monkeypatch.setattr("app.kb.embed.post_json", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(ArkError("x")))
    monkeypatch.setattr("app.kb.embed.time.sleep", lambda s: None)
    with pytest.raises(ArkError):
        HttpArkEmbedder("k").embed("a")
    assert len(calls) == 3
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_kb_embed.py tests/test_ark.py -v`
Expected: `test_kb_embed.py` FAIL（`ModuleNotFoundError`），`test_ark.py` PASS

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/test_kb_embed.py tests/test_ark.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/ark.py app/kb/embed.py tests/fakes.py tests/test_kb_embed.py
git commit -m "feat(kb): ark multimodal embedding client"
```

---

### Task 5: 入库流水线 + worker 接入

**Files:**
- Create: `app/kb/ingest.py`
- Modify: `app/worker.py`（加轮询任务、启动时收回卡住的文档、`main` 里构造 `HttpArkEmbedder`）
- Test: `tests/test_kb_ingest.py`、`tests/test_worker.py`

**Interfaces:**
- Consumes: `parse_pdf`（Task 2）、`tokenize`（Task 3）、`Embedder`（Task 4）、`KbDoc / KbPage / KbChunk`、`Settings.kb_dir`（Task 1）
- Produces:
  - `process_doc(session: Session, doc: KbDoc, embedder: Embedder, kb_dir: Path) -> None`
  - `process_queued(session_factory: sessionmaker, embedder: Embedder, kb_dir: Path) -> int`：按 id 顺序处理所有 `queued`，返回处理个数
  - `recover_stale_docs(session_factory: sessionmaker) -> int`：把 `processing` 改回 `queued`
  - worker：`build_scheduler(session_factory, client, raw_dir, embedder=None, kb_dir=None)`；两个参数都给了才加 `process_queued` 任务（interval 60 秒，id `kb_process`，和采集共用同一个单线程执行器，保证不并发）

`process_doc` 流程：`process_status="processing"`、清空 `message`、提交 → 删除这份文档已有的 pages / chunks → `parse_pdf` → 写 `KbPage`，`n_pages` = 页数，`n_chunks` = 切片数，`n_embedded=0`，提交 → 逐个切片 `embed`，写 `KbChunk`（`tokens=" ".join(tokenize(text))`，`embedding` 存 `np.asarray(v, dtype="<f4").tobytes()`，`dim=len(v)`），每 10 个提交一次并更新 `n_embedded`（前端显示进度）→ 全部完成：`process_status="ready"`、`embed_model=embedder.model`、`processed_at=now_cst()`。任何异常：回滚，删掉这份文档的所有 chunks（pages 保留，方便看每页字数），`process_status="failed"`，`message=f"{type(e).__name__}: {e}"`，提交；不再往外抛。

- [ ] **Step 1: 写失败的测试**

```python
def test_process_doc_happy_path(session, tmp_path):
    doc = add_doc(session, tmp_path, pages=["澳覓合作商家超5,700家", None, "註冊用戶超300萬"], process_status="queued")
    process_doc(session, doc, FakeEmbedder(), tmp_path)
    assert doc.process_status == "ready" and doc.embed_model == "fake"
    assert (doc.n_pages, doc.n_chunks, doc.n_embedded) == (3, 2, 2)
    chunks = session.scalars(select(KbChunk).order_by(KbChunk.seq)).all()
    assert [c.page_no for c in chunks] == [1, 3] and "澳觅" in chunks[0].tokens.split()
    assert len(np.frombuffer(chunks[0].embedding, dtype="<f4")) == chunks[0].dim == 64

def test_process_doc_embed_failure_leaves_no_chunks(session, tmp_path):
    doc = add_doc(session, tmp_path, pages=[f"第{i}页澳觅" for i in range(25)], process_status="queued")
    process_doc(session, doc, FakeEmbedder(fail_after=12), tmp_path)
    assert doc.process_status == "failed" and "ArkError" in doc.message
    assert session.scalar(select(func.count()).select_from(KbChunk)) == 0
    assert session.scalar(select(func.count()).select_from(KbPage)) == 25

def test_process_doc_reprocess_replaces_old_rows(session, tmp_path):
    doc = add_doc(session, tmp_path, pages=["澳觅"], process_status="queued")
    process_doc(session, doc, FakeEmbedder(), tmp_path)
    process_doc(session, doc, FakeEmbedder(), tmp_path)
    assert session.scalar(select(func.count()).select_from(KbChunk)) == 1

def test_recover_stale_requeues_processing_docs(session_factory, tmp_path):
    with session_factory() as s:
        add_doc(s, tmp_path, pages=["x"], process_status="processing")
    assert recover_stale_docs(session_factory) == 1
    with session_factory() as s:
        assert s.scalar(select(KbDoc.process_status)) == "queued"

def test_process_queued_skips_other_states(session_factory, tmp_path):
    # uploading / ready / failed 各一份，queued 一份 → 只处理 1 份
```

（`add_doc` 是 `tests/builders.py` 里新增的工具：生成 PDF 写到 `tmp_path / f"{id}.pdf"`，建 `KbDoc`，`status="active"`。）

`tests/test_worker.py` 加：`build_scheduler` 传了 embedder 和 kb_dir 时有 `kb_process` 任务，不传时没有。

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_kb_ingest.py tests/test_worker.py -v`
Expected: FAIL（`ModuleNotFoundError: app.kb.ingest`）

- [ ] **Step 3: 实现 `ingest.py` 和 worker 改动**

worker `main`：`recover_stale` 之后调 `recover_stale_docs`；`embedder = HttpArkEmbedder(cfg.ark_api_key)`，`cfg.kb_dir.mkdir(parents=True, exist_ok=True)`。

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/kb/ingest.py app/worker.py tests/builders.py tests/test_kb_ingest.py tests/test_worker.py
git commit -m "feat(kb): ingest pipeline and worker polling"
```

---

### Task 6: 混合检索

**Files:**
- Create: `app/kb/search.py`
- Test: `tests/test_kb_search.py`

**Interfaces:**
- Consumes: `tokenize`、`bm25_scores`、`rrf`（Task 3）；`Embedder`（Task 4）；Task 5 写入的表
- Produces:
  - `@dataclass Hit: chunk_id: int; doc_id: int; doc_title: str; effective_date: date; page_no: int; half: str; text: str; score: float; semantic_rank: int | None; keyword_rank: int | None`（rank 从 1 开始，没进该路前 `candidates` 名时为 None）
  - `search(session: Session, query: str, embedder: Embedder, limit: int = 5, candidates: int = 50) -> list[Hit]`

做法：读出所有 `status=="active"` 且 `process_status=="ready"` 的文档的切片（id、tokens、embedding、dim）；只保留 `dim` 等于查询向量长度的切片（换过模型的旧切片不参与）。语义：numpy 余弦相似度降序取前 `candidates`；关键词：`bm25_scores` 降序取前 `candidates`，只保留分数 > 0 的；`rrf` 融合后取前 `limit`。`query` 去掉首尾空白后为空时直接返回 `[]`，不调 embedder。

- [ ] **Step 1: 写失败的测试**

```python
def test_search_returns_page_and_title(session, tmp_path):
    ready_doc(session, tmp_path, "年刊", ["葡挞好吃", "澳覓合作商家超5,700家"])
    hits = search(session, "澳觅合作商家有多少", FakeEmbedder())
    assert hits[0].doc_title == "年刊" and hits[0].page_no == 2

def test_search_keyword_matches_traditional_doc(session, tmp_path):
    ready_doc(session, tmp_path, "年刊", ["註冊用戶超300萬", "葡挞好吃"])
    hits = search(session, "注册用户", FakeEmbedder())
    assert hits[0].page_no == 1 and hits[0].keyword_rank == 1

def test_search_excludes_inactive_and_unready(session, tmp_path):
    ready_doc(session, tmp_path, "旧版", ["澳觅商家5500"], status="inactive")
    ready_doc(session, tmp_path, "处理失败", ["澳觅商家5600"], process_status="failed")
    ready_doc(session, tmp_path, "现行", ["澳觅商家5700"])
    assert {h.doc_title for h in search(session, "澳觅商家", FakeEmbedder())} == {"现行"}

def test_search_skips_chunks_with_other_dim(session, tmp_path):
    ready_doc(session, tmp_path, "旧模型", ["澳觅"], embedder=FakeEmbedder(dim=32))
    assert search(session, "澳觅", FakeEmbedder(dim=64)) == []

def test_search_blank_query_does_not_call_embedder(session):
    e = FakeEmbedder()
    assert search(session, "   ", e) == [] and e.calls == 0

def test_search_empty_kb(session):
    assert search(session, "澳觅", FakeEmbedder()) == []
```

（`ready_doc` = `add_doc` + `process_doc`，放 `tests/builders.py`。）

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_kb_search.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/test_kb_search.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/kb/search.py tests/builders.py tests/test_kb_search.py
git commit -m "feat(kb): hybrid search over active documents"
```

---

### Task 7: 知识库接口（分片上传、管理、检索）

**Files:**
- Create: `app/api/routes_kb.py`
- Modify: `app/api/__init__.py`（挂路由；`create_app(session_factory=None, embedder=None)`，没传时 `ARK_API_KEY` 有值就建 `HttpArkEmbedder`，存 `app.state.embedder`）
- Test: `tests/test_kb_api.py`、`tests/test_api.py`（鉴权列表加上新路由）

**Interfaces:**
- Consumes: Task 1 模型、`Settings.kb_dir`；Task 6 `search`；Task 4 `Embedder`
- Produces（前缀 `/api/kb`，全部要登录）：
  - `POST /docs` body `{title, filename, size_bytes, effective_date, status}` → `{"id": int, "received_bytes": 0}`；`size_bytes` 必须在 1 到 `MAX_BYTES = 1024**3` 之间（超了 413）；`filename` 必须以 `.pdf` 结尾（不区分大小写，否则 422）；建 `process_status="uploading"`
  - `PUT /docs/{id}/content?offset=N`，请求体是原始字节（`await request.body()`）：只允许 `uploading` 状态；`offset != received_bytes` → 409，`detail={"message": "偏移量不对", "received_bytes": 已收到}`；单次超过 `MAX_PART = 16 * 1024**2` → 413；写入后超过 `size_bytes` → 422；追加写到 `kb_dir / f"{id}.pdf.part"` → `{"received_bytes": int}`
  - `POST /docs/{id}/complete`：`received_bytes == size_bytes`，文件头是 `%PDF-`（否则 422 并删掉临时文件、文档标 `failed`）；算 sha256，若已有其他文档 sha256 相同 → 409，`detail` 里给出那份文档的标题；通过后改名为 `{id}.pdf`，`process_status="queued"`
  - `GET /docs` → 列表（不含页面明细），按 `id` 倒序
  - `GET /docs/{id}` → 文档字段 + `pages: [{page_no, n_chars, n_images}]` + `empty_pages: [page_no...]`（`n_chars == 0` 的页）
  - `PATCH /docs/{id}` body 可选 `{title, effective_date, status}`
  - `POST /docs/{id}/reprocess`：只允许 `ready` / `failed` → 改 `queued`
  - `DELETE /docs/{id}`：删行（级联）+ 删 `{id}.pdf` 和 `{id}.pdf.part`（不存在不报错）
  - `GET /docs/{id}/file` → `FileResponse`，`media_type="application/pdf"`，`Content-Disposition: inline`（前端用 `#page=N` 跳页）
  - `POST /search` body `{query: str, limit: int = 5}`（`limit` 1–20）→ `[Hit 的字段 + "effective_date" ISO]`；`app.state.embedder` 为 None 时 503「没有配置 ARK_API_KEY」；embedder 抛 `ArkError` 时 502 并带原因

- [ ] **Step 1: 写失败的测试**（`client` fixture 用 `create_app(session_factory, embedder=FakeEmbedder())`，`KB_DIR` 用 monkeypatch 指到 `tmp_path`）

```python
def test_upload_in_parts_then_complete_queues_doc(authed, tmp_path):
    data = make_pdf_bytes(["澳觅"])
    doc_id = init(authed, size=len(data))
    assert put(authed, doc_id, 0, data[:100]).json() == {"received_bytes": 100}
    assert put(authed, doc_id, 100, data[100:]).status_code == 200
    r = authed.post(f"/api/kb/docs/{doc_id}/complete")
    assert r.status_code == 200 and authed.get(f"/api/kb/docs/{doc_id}").json()["process_status"] == "queued"
    assert (tmp_path / f"{doc_id}.pdf").exists() and not (tmp_path / f"{doc_id}.pdf.part").exists()

def test_upload_offset_mismatch_returns_received(authed):
    doc_id = init(authed, size=300)
    put(authed, doc_id, 0, b"%PDF-" + b"x" * 95)
    r = put(authed, doc_id, 0, b"y" * 100)          # 客户端以为没传上，重发第一段
    assert r.status_code == 409 and r.json()["detail"]["received_bytes"] == 100

def test_complete_rejects_non_pdf(authed):          # 文件头不是 %PDF- → 422，文档 failed
def test_complete_rejects_duplicate_file(authed):   # 同一份字节传两次 → 第二次 409，detail 含第一份标题
def test_init_rejects_too_large_and_non_pdf_name(authed):   # size 1024**3+1 → 413；a.docx → 422
def test_part_over_declared_size_rejected(authed):  # 声明 100，传 150 → 422
def test_patch_status_and_reprocess_rules(authed, session, tmp_path):   # uploading 状态 reprocess → 409
def test_delete_removes_rows_and_files(authed, session, tmp_path):
def test_doc_detail_lists_empty_pages(authed, session, tmp_path):       # ready_doc 第 2 页无字 → empty_pages == [2]
def test_search_endpoint(authed, session, tmp_path):                    # 返回 page_no、doc_title
def test_search_without_embedder_returns_503(...):                     # create_app(session_factory, embedder=None) 且无 ARK_API_KEY
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_kb_api.py tests/test_api.py -v`
Expected: FAIL（404 / ImportError）

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/api/routes_kb.py app/api/__init__.py tests/test_kb_api.py tests/test_api.py
git commit -m "feat(kb): upload, management and search api"
```

---

### Task 8: 「知识库」页面

**Files:**
- Create: `web/src/upload.ts`、`web/src/upload.test.ts`
- Create: `web/src/pages/Knowledge.tsx`
- Modify: `web/src/App.tsx`（菜单「工作空间」组里、「设置」之前加 `/knowledge`，图标 `BookOutlined`，标签「知识库」）
- Modify: `web/src/types.ts`（`KbDoc`、`KbDocDetail`、`KbHit`，字段同 Task 7）

**Interfaces:**
- Consumes: Task 7 全部接口
- Produces:
  - `uploadInParts(file: Blob, docId: number, opts: { partSize?: number; onProgress?: (received: number) => void; fetchImpl?: typeof fetch }): Promise<void>`：默认 `partSize = 8 * 1024 * 1024`；按 `offset` 顺序 `PUT /api/kb/docs/{id}/content?offset=`；收到 409 时用返回的 `received_bytes` 作为新 offset 继续；网络错误或 5xx 同一段最多重试 3 次（每次前先按 409 逻辑对齐 offset，即先发一次当前 offset，服务器会告诉真实位置）；全部发完后调 `POST /complete`

页面（一页三块）：
1. **上传**：标题（默认取文件名去掉 .pdf）、生效日期（默认今天）、状态（现行 / 失效，默认现行）、选文件 → 「上传」；上传中显示进度条（已传 MB / 总 MB）。
2. **文档列表**（Table）：标题、生效日期、状态（Switch，切换即 PATCH）、处理状态（上传中 / 排队 / 处理中 x/y / 已完成 / 失败（悬停看原因））、页数、切片数、无文字页数、上传时间、操作（查看、重新处理、删除，删除用 Popconfirm）。有文档处于排队或处理中时每 5 秒刷新一次。
3. **检索测试**：输入框 + 「检索」；结果列表每条显示：文档标题、生效日期、「PDF 第 N 页（左 / 右）」（点开新标签页 `/api/kb/docs/{id}/file#page=N`）、语义名次 / 关键词名次、切片原文（查询词高亮不做）。
- 「查看」打开 Drawer：每页字数表，`n_chars == 0` 的行标红「无文字层，未入库」，顶部写上「这些页面的内容不会被检索到」。

- [ ] **Step 1: 写失败的测试**（`upload.test.ts`，用假的 `fetchImpl`）

```ts
test("uploads all parts in order then completes", ...)          // 25 字节、partSize 10 → offset 0,10,20 然后 complete
test("upload resumes from server offset on 409", ...)           // 第二段返回 409 {detail:{received_bytes:20}} → 下一次从 20 发
test("retries a failed part at most 3 times", ...)              // 同一段 4 次 500 → reject
test("reports progress", ...)                                   // onProgress 收到 10, 20, 25
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd web && npm test`
Expected: FAIL（找不到 `./upload`）

- [ ] **Step 3: 实现 `upload.ts` 和页面**

- [ ] **Step 4: 运行测试和类型检查**

Run: `cd web && npm test && npm run build`
Expected: 测试 PASS，build 无报错

- [ ] **Step 5: 浏览器手动验证**（本地 SQLite + `uv run uvicorn` + `npm run dev`，worker 用真实 `ARK_API_KEY` 跑一次）：上传年刊 → 进度条走完 → 列表从排队变处理中再变已完成 → 查看页面里无文字页数为 0 → 检索「2025年合作商家有多少」第一条是 PDF 第 5 页（右）。

- [ ] **Step 6: 提交**

```bash
git add web/src/upload.ts web/src/upload.test.ts web/src/pages/Knowledge.tsx web/src/App.tsx web/src/types.ts
git commit -m "feat(web): knowledge base page"
```

---

### Task 9: 验收题和评测脚本

**Files:**
- Create: `data/kb/eval-questions.csv`（列：`qid,question,expect_page,expect_half,expect_text`；`data/kb/` 被忽略，这个文件用 `git add -f`）
- Create: `scripts/kb_eval.py`
- Test: `tests/test_kb_eval.py`

**Interfaces:**
- Consumes: Task 6 `search`
- Produces:
  - `scripts/kb_eval.py`：`evaluate(session, rows: list[dict], embedder, k: int = 5) -> list[EvalRow]`，命中 = 前 k 条里有切片满足 `page_no == expect_page`（`expect_half` 非空时也要相等）且 `normalize(expect_text)` 是 `normalize(切片原文)` 的子串；命令行 `uv run python -m scripts.kb_eval [--k 5]` 打印每题命中名次和总命中率 `x/n`

验收题（我从年刊起草，**用户确认后**再定稿；`expect_page` 执行时用 `parse_pdf` 核对）：
1. 澳觅 App 是哪天上线的？ → p5 右，「6月1日澳覓APP正式上線」
2. 澳觅外卖业务什么时候开始的？ → p5 右，「11月2日外賣業務啟動」
3. 2025 年澳觅合作商家有多少家？ → p5 右，「合作商家超5,700家」（双栏顺序验收题）
4. 澳觅注册用户有多少？ → p5 右，「註冊用戶超300萬」
5. 澳觅是哪家公司运营的？ → p5 左，「澳門網絡傳媒發展有限公司」
6. 澳觅有多少员工和配送员？ → p5 左，「超過3,800人」
7. 澳觅的充电宝业务哪年上线？ → p5 右，「澳覓充電寶業務正式上線」
8. 澳觅的研发基地在哪里？ → p5 左，「珠海、南京設立研發基地」
9—10. 由用户补两道支付方式 / 内地手机号注册相关的题（spec §4.8 的例子）；年刊里没有对应内容时，这两题预期不命中，用来检查「查不到时会不会给出不相干的段落」——只记录，不计入命中率。

- [ ] **Step 1: 写失败的测试**：`test_evaluate_counts_hits`——用 `ready_doc` 建两页，两道题一题能命中、一题不能 → 结果命中名次分别为 1 和 None
- [ ] **Step 2: 运行测试，确认失败**：`uv run pytest tests/test_kb_eval.py -v` → FAIL
- [ ] **Step 3: 实现**
- [ ] **Step 4: 运行测试，确认通过**：`uv run pytest tests/test_kb_eval.py -v` → PASS
- [ ] **Step 5: 用年刊真跑一次**（本地库已入库年刊，真实 `ARK_API_KEY`；花费：入库约 4.4 万字 + 10 次查询，按 0.70 元/百万 tokens 不到 0.1 元）：`uv run python -m scripts.kb_eval`，把输出原样贴给用户，和用户一起定及格线（spec §4.8）。**不许为了达标改题目的期望页或改命中判定**；没达标就报告实际数字和失败的题。
- [ ] **Step 6: 提交**

```bash
git add -f data/kb/eval-questions.csv
git add scripts/kb_eval.py tests/test_kb_eval.py
git commit -m "feat(kb): acceptance questions and eval script"
```
