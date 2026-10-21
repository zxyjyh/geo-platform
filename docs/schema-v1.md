# T-9 数据模型与指标口径 v1（2026-10-20）

本文件一经用于基线采集即冻结。改动只能升版本（v2…），并在「变更记录」写明原因；**不得为了让指标好看去改口径**。

## 1. 基本单位

- **一次采集（run）** = 一道题在一个平台、一个渠道里，**新开对话**问一次得到的完整回答。
- 每题每轮测 3 次，分布在不同日期。轮次：`pairing`（对照测试）/ `baseline` / `R1` / `R2` / 之后的 `R3…`。
- **App 和 API 的数据永不合并计算。** 所有指标都按 `platform × channel` 分开报。

## 2. 表结构

### 2.1 questions（题库）
来源文件：`data/questions/questions-v4-50.csv`。主键 `qid`，再加 `question_version`（例如 v4），保证复测问的是同一道题。
关键字段：`category`（A–G）、`persona`、`branded`（Y/N）、`intent`、`fact_check`、`arm`（覆盖题 / 对照题 / TBD）。

### 2.2 runs（每次采集一行）
| 字段 | 说明 |
|---|---|
| run_id | `{round}-{platform}-{channel}-{qid}-{n}`，例如 `baseline-doubao-app-Q01-2` |
| round | pairing / baseline / R1 / R2 … |
| qid, question_version | 题目和题库版本 |
| platform | doubao / yuanbao / kimi / … |
| channel | app / web / api-plugin（联网内容插件）/ api-custom（豆包搜索 Custom 版）/ api-assistant（豆包助手 API） |
| channel_detail | App 版本号，或 API 的模型 ID + 功能模式（如 `doubao-seed-2-1-pro-260915 / ai_search`） |
| mode | 快速回答 / 深度思考 / 联网（按界面实际选项记录） |
| collected_at | 带时区的时间，例如 `2026-10-27T14:05+08:00` |
| collector | 手测人姓名或脚本名 |
| account_ref | 测试账号代号（不记手机号） |
| location | App 填设备所在城市或 IP 归属地；API 填 user_location 的值 |
| new_session | 必须为 Y，否则这条作废 |
| answer_text | 回答全文原文，不做删改 |
| answer_capture | 截图或录屏的文件路径（App 必填） |
| sources_visible | Y/N：界面或返回结果里有没有展示信源 |
| sources_count | 信源条数 |
| status | valid / void（作废要写原因） |
| search_queries | 仅 API：模型实际发出的搜索词，多个用 ` \| ` 分隔（取自 web_search_call.action.query） |
| search_calls | 仅 API：搜索次数 |
| input_tokens, output_tokens | 仅 API：token 用量，用来核算成本 |

### 2.3 sources（每条信源一行）
`run_id, rank, title, url, domain, site_name, publish_time, source_type, is_owned`
- source_type 取值：自有 / 字节系 / 新闻媒体 / UGC 平台 / 竞品 / 政府机构 / 其他
- is_owned：url 属于下面「自有渠道清单」中的任意一项时记为 Y

### 2.4 coding（每次采集 × 每位编码者一行）
| 字段 | 取值 | 判定规则 |
|---|---|---|
| coder | `human:姓名` / `llm:模型ID@prompt版本` | |
| mention_{aomi,mfood,shanfeng} | 0/1 | 正文出现该实体或其别名（见 2.6）。只出现在信源标题里、正文没提的，不算 |
| order_{aomi,mfood,shanfeng} | 1,2,3… / 空 | 在回答提到的所有平台中，按首次出现的先后排位；没提到就留空 |
| recommend_aomi | 0/1 | 提到澳觅，并且把它当作可选方案正面呈现（推荐、可以用、适合）。只是列出名字、或者伴随否定（「不建议」「不支持」）的，记 0 |
| cite_owned | 0/1 | 这条采集的信源里至少有一条 is_owned=Y |
| aomi_claims | 整数 | 回答里关于澳觅、可以核对的事实陈述条数 |
| aomi_errors_major | 整数 | 与事实卡冲突、并且会影响用户决策的陈述条数（业务范围、支付、注册、配送范围、价格） |
| aomi_errors_minor | 整数 | 其他与事实卡冲突的陈述 |
| sentiment_aomi | -1/0/1/空 | 对澳觅的整体倾向；没提到澳觅就留空 |
| fact_status | judged / pending | 事实卡签字之前一律填 pending |

### 2.5 fact_errors（每条错误陈述一行）
`run_id, coder, fact_id, claim_text, severity(major/minor), note`，其中 fact_id 对应事实卡条目。

### 2.6 entities（别名表）
| entity | 别名（待补全） |
|---|---|
| aomi | 澳觅、澳覓、Aomi |
| mfood | mFood |
| shanfeng | 闪蜂、閃蜂 |
别名表要和编码 prompt 一起加版本号。新增别名后，已经编过码的数据要用新别名表重跑一遍。

### 2.7 content_units（S4 使用）
`unit_id, type(服务页/FAQ/专题文章), channel, url, qids(覆盖的题号), published_at, fact_ids`

### 2.8 自有渠道清单（待用户补全）
官网域名、头条号、抖音号、小红书号、公众号……每项写明 URL 前缀。**基线开始前要定稿**，否则 is_owned 无法判定。

## 3. 指标口径

聚合方式：**每道题先算 3 次采集的平均值，再对题目取平均**（每题权重相同）。这样某道题少测一次，也不会让结果偏向测得多的题。

| 指标 | 分子 | 分母 | 题目范围 |
|---|---|---|---|
| 提及率 | mention_aomi=1 的采集 | 全部有效采集 | **只算不带品牌名的 35 题** |
| 推荐率 | recommend_aomi=1 的采集 | 全部有效采集 | 不带品牌名的 35 题 |
| 首位率 | order_aomi=1 的采集 | 全部有效采集 | 不带品牌名的 35 题 |
| 提及份额 | 澳觅被提及次数 | 澳觅 + mFood + 闪蜂的提及次数之和 | 不带品牌名的 35 题 |
| 引用率 | cite_owned=1 的采集 | 全部有效采集 | 全部 50 题；另外拆成带品牌名 / 不带品牌名两组分别报 |
| 信源可见率 | sources_visible=Y 的采集 | 全部有效采集 | 全部 50 题 |
| 事实错误率 | aomi_errors_major≥1 的采集 | mention_aomi=1 的采集 | 全部 50 题；fact_status=pending 的不计入 |
| 事实陈述错误率（辅助） | major+minor 错误条数之和 | aomi_claims 之和 | 同上 |

说明：
- 带品牌名的题里，AI 几乎必然会提到澳觅，所以这 15 题不进提及率、推荐率、首位率的分母，只用来测事实错误和引用。
- 某次采集信源不可见，引用率记 0，但要同时报信源可见率。这样「引用率低」可以拆开看：是平台没展示信源，还是展示了但里面没有澳觅自有内容。

### 3.1 自检规则（每次出报表都自动跑，任何一条不通过就不出报表）
1. 推荐率 ≤ 提及率；首位率 ≤ 提及率
2. 引用率 ≤ 信源可见率
3. 每道题每轮有效采集数等于 3；不等于 3 的题单独列出
4. 每次采集都有且只有一条主编码（基线阶段要求人工和 LLM 各一条）
5. 没有任何一张表把不同 `platform × channel` 的数据混在一起
6. 报表里每个数字都附上 n_questions、n_runs 和 95% 区间
7. fact_status=pending 的采集数单独列出，并在报表里写明「事实错误率未覆盖 X 次采集」

### 3.2 置信区间
按题目做 cluster bootstrap：每次有放回地抽题（抽中一题就带上它的全部采集），重复 2000 次，取 2.5% 和 97.5% 分位数。同一题的 3 次回答彼此不独立，直接用 Wilson 区间会算得过窄。

### 3.3 编码一致性（S3）
- 基线这一轮人工和 LLM 都编码，逐个字段计算 Cohen's κ
- 门槛（**提议值，等用户确认**）：客观字段（mention、order、cite_owned）κ ≥ 0.80；主观字段（recommend、sentiment、errors）κ ≥ 0.70
- 某个字段的阳性率低于 10% 时，κ 会不稳定 → 同时报原始一致率和分歧条数，分歧逐条人工复核
- 字段过了门槛，复测时才可以只用 LLM 编码；每轮再抽 10% 让人工复核

### 3.4 前后对照
- 同一题库版本、同一渠道、同一种账号设置、同一测量地点、同样每题 3 次
- 变化量 = 复测值 − 基线值，用 bootstrap 计算差值的区间
- 效果估计 = 覆盖题的变化量 − 对照题的变化量（双重差分）。arm 在 S4 做内容之前，按类别分层随机分配，并记录随机种子

## 4. 采集规则（App 手测）
- 使用专用测试账号；关闭记忆和个性化（如有此设置）；每题都新开对话
- 测量地点固定为**广东深圳**（2026-10-20 用户确定），记录在 location 字段。App 手测的设备要在深圳，或者 IP 归属地是深圳；API 的 user_location 填深圳（只有 api-plugin 生效）
- 回答生成完再截图；信源展开后再截一张
- 不追问、不点「重新生成」；如果点了，这条记为作废

## 5. 待定项
- 自有渠道清单（2.8）
- κ 门槛（3.3）
- 别名表补全（2.6）
- 豆包助手 API 是否返回信源：要等拿到 beta 资格、实际调用后才能确认，决定 API 渠道能不能算引用率

## 变更记录
- v1 2026-10-20 初版；同日补充：测量地点定为深圳，channel 拆出三种 API 渠道
- v1.1 2026-10-21 runs 表新增 search_queries / search_calls / input_tokens / output_tokens（只对 API 渠道），不影响已有字段
