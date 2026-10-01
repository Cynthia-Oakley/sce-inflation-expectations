# E｜Event MCP 首试规格与历史可得性验收

核查日期：2026-09-29。适用范围：美国纽约联储 SCE 一年期通胀预期；本文件给云端两个月 scripted 小试定义 Event MCP 的获取与准入规则。用户随后转述平台反馈：`fred` 两次有数值，但没有发布日与 vintage，因此已标 `unknown_as_of`。真实历史 E 的补救路径现见 [BLS 首发新闻稿方案](E_PIT_RECOVERY.md)；本地没有该平台回包原件，仍待导出归档。

## 结论与证据边界

- 官方 SocioVerse2 当前文档列出 21 个 Event collector，其中 10 个默认启用；默认集合含 `nyfed_sce` 和 `nyt_archive`。Event 工具是 build-time 数据能力，不是自动按研究问题检索的 RAG 服务。`query` 只写 provenance；月度查询需要显式 `year`、`month`，历史新闻实时搜索 `search_web` 不属于 vintage 查询路径。[数据服务文档](https://socioverse.fudan-disc.com/docs/guides/data-services/)，[客户端参考](https://socioverse.fudan-disc.com/docs/reference/external-events/)（核查：2026-09-29）
- 官方文档对 as-of 的保证限于观测窗口：collector 截止到所请求月份的最后一天；修订版本取决于上游。文档要求记录 `target_date`、`fetched_at`、`from_cache`，但这三个值本身不能证明某个值当时已发布，也不能证明它是当时可见的历史版本。
- 本机只读参考仓库在 commit `fa678ff6aea0e5a6497a7ffac15459123200a150`。`ExternalEventsClient.fetch(query, months, sources)` 显式逐月逐源调用 `get_source_detail(source, year, month)`；空 `sources` 才走 `get_data(sources="default", year, month)`。客户端不传 `series`、`as_of` 或逐条发布日期筛选条件。其测试用的是模拟 transport，不是在线 Event MCP 的实测结果。
- 今日没有查询用户账号下的云端服务、没有确认服务端可用 collector/字段/历史版本/费用，也没有取得任何 Event 响应。下文分为“官方文档说明”“本地代码显示”“项目准入约定”“待平台验证”，不把前三者写成服务实测。

## 首次两个月小试：固定建议月份与精确查询

取两个相邻开发目标月 **2021-05、2021-06**。它们均落在项目候选开发期 2020–2021；本选择只用于今天的小试，不冻结正式实验窗口。按 `RESEARCH_PROTOCOL.md` 的月初预测信息边界，每个目标月使用前一个月最后一秒（`America/New_York`）。Event MCP 的 `year/month` 指的是数据观测截止月份，因此与预测目标月相差一月：

| 模拟目标月 | `as_of`（纽约时间） | 等价 UTC | Event MCP `year/month` | 允许进入该步的信息 |
|---|---|---|---|---|
| 2021-05 | 2021-04-30 23:59:59 EDT | 2021-05-01 03:59:59Z | `2021 / 4` | 截止该时点已经公开且版本可重建的记录 |
| 2021-06 | 2021-05-31 23:59:59 EDT | 2021-06-01 03:59:59Z | `2021 / 5` | 截止该时点已经公开且版本可重建的记录 |

**最小来源：只请求 `fred`，试查两个序列 `CPIAUCSL`（美国 CPI 总项季调指数）与 `UNRATE`（失业率）。** 价格和劳动力各留一个可解释的宏观信号，足以检查两个月、两种序列的时间映射；暂不拉政策利率、其他市场指标或新闻。它们没有必要作为 scripted 流程验收的先决条件。

先运行一次只读目录查询 `list_sources()`，记录返回中 `fred` 的 `category`、`default_enabled`、`requires_api_key` 和 `api_key_env_var`。再按官方数据服务工具签名发出两次单源请求：

```text
get_source_detail(
  source="fred", year=2021, month=4,
  series="CPIAUCSL,UNRATE", use_cache=true
)

get_source_detail(
  source="fred", year=2021, month=5,
  series="CPIAUCSL,UNRATE", use_cache=true
)
```

上述 `series` 是官方 `get_source_detail` 的可选子序列参数；官方文档称 `fred` 和 `bls` 等指定 collector 实现此过滤。它不是历史发布时间过滤，也没有传入精确的日时 `as_of`。如平台只通过本地公开封装获取，等价入口是：

```python
path, bundle = materialize_external_events(
    study_dir,
    query="SCE E smoke check; query is provenance only",
    months=["2021-04", "2021-05"],  # as-of observation months, not target months
    sources=["fred"],
)
```

公开客户端不会把 `series` 传给远端，故必须在本地按 `data` 中的 series ID 做白名单过滤；如果返回负载无法区分 CPI 与失业率，标为接口待扩展或只作 connectivity smoke check，不能把整个 `fred` 回包不加检查地馈入家庭 Agent。两种调用路径的实际服务工具是否暴露相同参数，均待云端核验。

不要调用 `get_data(sources="default")` 或 `get_data(sources="all")`：它们会扩大来源集合，默认集明确包含 `nyfed_sce`。也不要用 `query` 字符串假设服务会理解目标月、检索关键词或过滤发布时间。

## 数据契约：五种时间不能合并

每一条宏观值或新闻版本，在本项目 E 快照中至少应有以下字段；无法从服务返回时由后处理补充有证据的字段，证据缺失则隔离：

| 字段 | 含义与准入规则 |
|---|---|
| `signal_id`, `source`, `series_id` | 稳定的项目内 ID、collector 名和原始序列代码。series 不明的聚合数字不进入 E。 |
| `value`, `unit`, `frequency`, `seasonal_adjustment` | 原始值及定义。计算同比时另记算法和所用历史观测；不把 API 已算出的变换值误写成原始值。 |
| `reference_period`, `observation_date` | 数据代表的月份或观测日期。月度 CPI 需保留类似 `2021-03` 的参考月，不把 Event 查询月份当成参考月。 |
| `observed_at` | 若是具体事件，记录事件发生时间；宏观月度统计若没有精确测量瞬间，保留 observation date/reference period，并标明 `observed_at` unknown，不伪造某月 1 日为发生时刻。 |
| `published_at` / `release_date` | 首次公开日期或时间及其时区、官方发布 URL。用它判定信息何时可见；`published_at` 不可用抓取日代替。 |
| `vintage` / `source_version` | 该数值的来源修订版本。修订型序列应有可复现的 as-of vintage（如 FRED/ALFRED 的实时区间或 vintage date、初次发布表）；仅有当前值时记录当前拉取版，但标为不满足严格历史回测。 |
| `as_of` | 项目定义的目标月截止时刻，纽约时区；它是筛选阈值，不能从响应的 `target_date` 推断。每条实际准入的信号应满足发布时间和 vintage 均不晚于它。 |
| `fetched_at` / `ingested_at` | Event 服务拉取及本项目落盘时间。用于来源审计、哈希与复现，不能冒充发布时间或 vintage。 |
| `source_url`, `availability_rule`, `eligibility` | 原始来源链接、采用的发布/日期规则和状态（`eligible`、`unknown_as_of`、`future`、`excluded`）。未知状态不进入模拟输入。 |

官方 Event 响应的共同外壳据文档/公开客户端约为 `source_name, category, description, target_date, fetched_at, from_cache, status, error_message, data`；`ExternalEventsBundle` 另外保存 `provider, requested_months, requested_sources, fetched_at, results, availability, errors`。本地仓库没有 Event 服务端 collector 源码，也没有对内层 `data` 的强制 schema；需要逐字段验收真实返回，不能把此“约为”当作已保证字段。

### 准入规则

1. **观测期门槛：**`observation_date/reference_period` 不得超出该目标月的 `as_of` 截止月。它只拦未来观测，不证明已发布。
2. **发布时间门槛：**准确时间与时区明确时要求 `published_at <= as_of`。只有日期、没有时刻或时区时，采用保守规则：仅当 `release_date < as_of` 的纽约本地日期才通过；同日记录设为 `unknown_as_of`，不把日期默认成午夜。
3. **版本门槛：**修订型宏观值应按 `as_of` 重建当时版本，或者能交叉核对同期首次发布文件。若只能取到今天的修订值，虽然其参考月较早也不得进入严格预测 E。
4. **缓存门槛：**`target_date="2021-04"` 是服务查询的月份标签，`from_cache=true` 说明可能读了服务缓存，`fetched_at` 是此次取数时间；三者均不能证明 2021-04-30 当时的数值 vintage。
5. **缺失/错误门槛：**区分源返回零条记录、未配置/不可用、超时、服务错误和因历史日期不明而隔离。不得将空值补成零，也不因 bundle 的 `available=true` 就认为每个必需 source-month 均通过。

FRED 官方 API 对 `series/observations` 提供 `realtime_start`、`realtime_end`、`vintage_dates` 及初次发布 `output_type=4` 等历史版本机制；官方也区分今天显示最新修订的 FRED 与记录历史版本的 ALFRED。[FRED observations API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)、[Real-Time Periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)、[FRED 与 ALFRED 说明](https://fredhelp.stlouisfed.org/fred/about/about-fred/what-is-fred/)（核查：2026-09-29）。Event MCP 的公开工具参数没有这些参数，官方服务文档对版本的说明也限定在 observation-date window。因此首试必须检查真实 payload 或单独的 ALFRED/原始发布证据；没有时这批值只能标为 **结构流程样例**，不能称为严格 point-in-time E。

## 输出验收：今天的 C2 与 C3

### C2｜Event 回包与时点样本

要求平台返回或导出：原始 MCP 工具名和参数、工具响应原文、Event bundle、拉取时间/缓存状态、两个月 × 两 series 的行数，以及逐条时间字段。判定标准：

- `list_sources` 明确返回 `fred`；两次 `get_source_detail` 的来源、月份、series 参数与上表一致；没有错误，或每个错误均保留并解释。
- 每个回包有实际的 `CPIAUCSL` 与 `UNRATE` series/value、单位、频率、季调标签、观测日/参考月和来源链接；不靠模型从自由文本猜测。
- 每一条进入 E 的值都能证明 `published_at` 与历史版本通过对应 `as_of`；缺字段的值留下隔离记录，不准无声剔除或让模型补全。
- 形成按目标月份映射的冻结快照，每条记录保留 raw response/hash 和 `as_of`；其余工具输出、错误、缺源与排除原因也归档。报告确切实际 `provider`、`sources_used`、`sources_unavailable`、`source_status`。
- 这一轮目标是获取路径与可审计结构，不是证明通胀预测能力。若服务没有历史发布/版本证据，优先用[已核对的 BLS 首发新闻稿 E](../proposal/cloud_input/sce_2021_05_06_bls_release_e.json)继续两月流程；不合格 FRED 回包只留审计。仅在真实 E 文件导入失败时，用[明确标记的合成 E fixture](../data/fixtures/sce_2_month_synthetic_environment.json)排查 schema；不得把最新修订值悄悄塞入预测输入。

### C3｜20 人 × 2 月 scripted 演示

同一套 P/B scripted 演示按 `target_month=2021-05,2021-06` 固定信息包；每个目标月的 Agent 输入只关联前月末 `as_of` 快照。输出验收至少有 40 条 agent-month 记录、稳定的 `agent_id`、各步的信息快照 ID / 哈希、目标月、回答和无效/失败状态。E 注入必须通过 allowlist：只允许已经验收的宏观记录；无真实 SCE 个体答案、同期聚合值、当期权重、`nyfed_sce` 输出或复述该结果的文章。该 scripted 演示只证明读入、时点映射、执行和导出流程，不作为预测准确性结果。

## SCE 结果隔离与新闻清洗

### 强制排除

- `nyfed_sce` 在本研究所有预测 E source list 中永久排除；不使用默认/all 集合，也不让平台助手“顺手”把 Event 默认数据写进 environment。
- E 不接收目标月的 SCE headline/微观答案、目标 Q8/Q9、由它们计算的个人/全国/群体结果、目标月权重或基于这些内容形成的描述。将 E 白名单写进 study 输入 prompt 和环境构建审计。
- 复述当前或未来目标月 SCE 数值的新闻一律剔除，包括搜索摘要、社媒转述和文章中引用的目标结果。过去已公开 SCE 值若未来需要，只能作为单独标识、带首次发布时间和历史版本的持续性基线，不默认混入新闻 E。
- `search_web(query, max_results, days, lang)` 是实时搜索，不用于历史回测；`summary` 是另一 LLM 写的 prose，不得注入 E。根据 typed `results` 或通过时间核验的文章原文人工生成固定格式广播。

### 可选新闻阶段的规则（不进入今天首试）

优先单独评估 `nyt_archive`，它是按月历史档案入口；不要同时开启 `gdelt`、`news_alt` 或默认 news 来源。NYT archive 输出是文章档案元数据接口，不能默认成文章全文、首发文本版本或文章完整覆盖。[NYT Archive API 规格](https://github.com/nytimes/public_api_specs/blob/master/archive_api/archive_api.md)（核查：2026-09-29）。正式打开新闻 E 前须在真实服务样本核实稳定文章 ID、标题、原始 `pub_date`（含时区）、`updated`/版本、URL、abstract/snippet/full text 范围、来源、语言及可复现查询条件；缺少历史正文版本时不得用今日更新版冒充当时文本。

先冻结来源、关键词/主题标签、语言和筛选规则，再按月拉取；不要根据测试月结果挑文章。对每条记录：

1. `published_at` 不晚于目标 `as_of`；若只有日期，严格早于截止日期；未来发表/更新时间的版本排除。采集月份不等于单篇文章的截止时间。
2. 保留原始 ID、标题、URL、出版方、原始发布时间、更新时点、抓取时间、返回文本类型、语言和文件哈希；区分原创、转载、重复版本和修订。去重规则写入 manifest；多篇转载不重复计权。
3. 使用初始已知文章版本；如果服务只返回后来编辑过的文本且没有历史版本，整条文章作为 `unknown_as_of` 隔离。不要以现时摘要替换当时文章。
4. 先做 SCE 结果污染过滤：检索结果或正文命中 NY Fed SCE / Survey of Consumer Expectations 等表述，且给出预期调查数值、月份结果或对结果的复述，则从 E 排除。即使它是截止日前的旧调查报道，也移入单独的历史 SCE baseline 评估，不进入首版新闻 E。
5. 其余文本也需清理模板、导航、广告、与美国通胀无关内容和无可核验来源的模型摘要。只保留经时间核验的原始元数据/文本；新闻量、失败量、排除量及原因逐月报告。若服务仅返回标题/短摘要，明确标注输入内容范围，不称为新闻全文实验。

## 后续完整 E 实验清单（逐项申请，不是今日来源集合）

| 次序 | 假设/消融 | 候选 source 与参数 | 进入正式输入前的额外门槛 |
|---|---|---|---|
| E0 核心宏观 | 家庭看到近期价格和劳动力信息 | `fred`, `series="CPIAUCSL,UNRATE"`；全窗口按每个目标月前月 `year/month` 拉取 | 逐月发布日期、ALFRED/首次发布 vintage、系列定义与频率核验；如无历史版本则改用官方首发档案或剔除该字段 |
| E1 政策信号 | 加入货币政策环境 | 单独增加 `fred`, `series="FEDFUNDS"` | 发布日/版本同样通过；政策决定公告可另做正式文本来源，不能把月均值当作公告时点 |
| E2 价格暴露 | 检查能源价格是否提供额外信息 | 单独增加 `fred`, `series="DCOILWTICO"` 或后续经来源核验的零售汽油序列 | 频率与月聚合规则冻结、发布日期/修订版核验；E1/E2 分开消融 |
| E3 新闻增量 | 固定历史报道能否改善输入 | 单独 `nyt_archive`，每个 as-of 月一请求，不调用 `search_web` | 服务字段、全文范围、发布日期/更新时间、文章 vintage、覆盖缺口和去重规则全部过 C2 新闻验收；SCE 报道过滤按上节执行 |
| E4 来源稳健性 | 检验新闻覆盖对单一档案源的依赖 | `gdelt` 或 `news_alt`，一次只加一个 collector | 逐项另验覆盖起点、原文/摘要、时间字段、去重、使用条款与服务错误；不假定官方目录注册等于账号可用 |
| E5 历史 SCE baseline（单列） | 与“最后已公布 SCE 目标值”基线比较 | NY Fed 官方已发布 chart/release 快照及明示的 `release_at`；不是 `nyfed_sce` 默认回包 | 只使用 `as_of` 以前已公布的历史值；绝不输入目标期或其复述，单列为透明基线而非普通宏观新闻 |

开展 E0–E4 时统一同一目标月与 `as_of`、同一 P/B/prompt/种子，逐项冻结源列表和数据哈希；测试期只能做覆盖和时间合规检查，不按预测成绩选新闻或宏观变量。最终来源列表与时间切分未冻结，扩展项不得冒充当前已完成配置。

## 核查来源

- 官方 SocioVerse2：[Data services: population and event](https://socioverse.fudan-disc.com/docs/guides/data-services/)；[External events API reference](https://socioverse.fudan-disc.com/docs/reference/external-events/)；[External Capabilities](https://socioverse.fudan-disc.com/docs/guides/capabilities/)（均于 2026-09-29 核查）。
- 本地只读代码：[SocioVerse2 `external_events.py`](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/socioverse/external_events.py)、[对应 mock transport 测试](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/tests/test_external_events.py)（commit `fa678ff6aea0e5a6497a7ffac15459123200a150`；本机代码审阅，不是云服务实测）。
- 数据版本与新闻：[FRED observations API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)、[FRED/ALFRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)、[NYT Archive API](https://github.com/nytimes/public_api_specs/blob/master/archive_api/archive_api.md)（2026-09-29 核查）。
- 项目边界：[研究与评测协议](RESEARCH_PROTOCOL.md)、[云端预试验方案](CLOUD_PILOT_PLAN.md)、[Event MCP/PMI 既有审计](SOCIOVERSE_MCP_AND_PMI.md)。
