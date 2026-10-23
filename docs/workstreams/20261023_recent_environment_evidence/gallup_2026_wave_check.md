# Gallup 2026 年"confidence in Federal Reserve chair"波次核查

- 核查日期：2026-10-23（ET）
- 核查方式：仅免费公开来源（Gallup 官网 PDF/文章、Wayback Machine CDX 与存档、Michigan SCE 公开报告、新闻媒体）；未使用任何付费 API 或 LLM 调用
- 任务边界：只读核查 + 新增证据文件与本报告；未修改任何已有注册表或配置文件
- 参考 schema：`docs/workstreams/20261017_reference_scaleup/confidence_sources.json`、`data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json`

## 结论（TL;DR）

**未找到 2026 年波次。** Gallup 已于 2026-02-11 宣布停止测量总统工作认可度及"其他 national leadership ratings"（见 FAIR 2026-03-06 及 The Hill 2026-02-11 报道）；2026 年 4 月 Economy and Personal Finance（EPF）调查（field 2026-04-01..15，n=1,001，2026-04-28 发布）的 topline 中**已无任何 economic leaders / Fed chair 题目**（连 Trump approval 都一并移除——2025 年同期 topline 的文件名就叫 "Trump Approval and Economic Leaders"）。2026 年 6 月 Confidence in Institutions 调查（17 个机构）与 2026 年 9 月 Governance 调查（联邦机构评分）中也不存在 Fed chair 题。Wayback 2026-04-01 至 2026-10-23 之间归档的全部 110 个 Gallup topline PDF 中没有任何 "Economic Leaders" 文件。

**2025-04 之后、2026-04 之前，五档 confidence 题也未在任何 Gallup 调查中复现**（该题历史上仅每年 4 月的 EPF 调查询问，Binder et al. NBER w33684 / AEA 2025："Gallup only asks about confidence in the Federal Reserve chair in April"）。但 Gallup 2025 年 12 月 Governance 调查问了**另一道题**——对 "Federal Reserve Chairman, Jerome Powell" 的 job approval（approve 44 / disapprove 47 / no opinion 9，n=1,016），这是缺口期内唯一的 Gallup 全国 Fed-chair 观测，可作备选 stopgap（量表不同，不能直接进五档注册表，见下文）。

**Powell→Warsh 交接注记**：若 2026 年 4 月波次存在，field dates（4/1–15）仍在 Powell 任内（Powell 任期 2026-05-15 结束，Kevin Warsh 同日就任），问的应是 Powell。本次核查的全部 2026 年 Gallup topline 中 grep "Warsh" 命中数为 0——2026 年内 Gallup 没有发布过任何以 Warsh 为对象的题目。模拟环境 2026-05 之后月份若继续使用 confidence wave，其问题对象在真实世界已没有对应数据支撑。

## 关键证据与哈希

| 文件（存于 `outputs/sce_recent_environment_evidence_20261023_v1/sources/`） | 说明 | sha256 |
|---|---|---|
| `gallup_20260428_epf_topline_GAL070.pdf` | 2026-04 EPF FINAL TOPLINE（GAL 070，field 2026-04-01..15，n=1,001，±4pp）。**负面证据**：仅含 Q7/Q8/Q10/Q15 个人财务题组 + 人口交叉表，无 leaders 模块 | `6877efa7aaf5da08a94940a18efa5b7a3dbaf48843f1e9eaa59bca47002b05ec` |
| `gallup_20251222_us_political_climate_topline_GAL053.pdf` | 2025-12 Governance FINAL TOPLINE（GAL 053，field 2025-12-01..15，n=1,016，±4pp）。Q20G：Powell job approval 44/47/9 | `f8ffd4970cd8a221644e430627eec281ba9677b4eeddf55e082b6c0bb66382b2` |
| `gallup_20260601_confidence_institutions_topline_GAL073.pdf` | 2026-06 Confidence in Institutions（GAL 073，field 2026-06-01..15，n=1,001）。**负面证据**：17 机构列表不含 Federal Reserve/Fed chair | `77ee0158784208068416cdee1dd416b911c4b5027c74617f3ad63c23075daeea` |
| `gallup_20261015_governance_agencies_topline_GAL076.pdf` | 2026-09 Governance（GAL 076，field 2026-09-01..17，n=1,000，2026-10-15 发布）。**负面证据**：无 leaders 模块、无 chair 题、无 "Warsh"；含 "The Federal Reserve Board" 机构评分（35/33/28，good/fair/poor） | `0376ed80a9d27169b935b7c274476d637ee952278894cca169b0001da65e6dd4` |

四份 PDF 均从 Gallup 官网直接下载（HTTP 200），并与 Wayback Machine 最早存档逐字节比对一致（sha256 相同）。

相关官方页面（核查日 2026-10-23 均可访问）：

- 2026-04-28 EPF 文章 "Affordability Still Dominates Americans' Financial Worries"（poll/708905）：确认 2026 年 EPF 发布与 field dates，全文未提 economic leaders / Fed chair — https://news.gallup.com/poll/708905/affordability-dominates-americans-financial-worries.aspx
- 2025-12-22 文章 "Americans End Year in Gloomy Mood"（poll/700241）：确认 Powell 44% approval 为全国最高领导人评分 — https://news.gallup.com/poll/700241/americans-end-year-gloomy-mood.aspx
- 2023-05 历史文章 "Americans Lack Confidence in Major Economic Leaders"（poll/505478）：该五档题的历史载体与问法（"great deal/fair amount of confidence … to do or recommend the right thing for the economy"，自 2001 年起每年 4 月 EPF）— https://news.gallup.com/poll/505478/americans-lack-confidence-major-economic-leaders.aspx
- FAIR（2026-03-06）：Gallup 宣布停止总统认可度与 national leadership ratings（引 The Hill/NYT/WaPo 2026-02-11 报道）— https://fair.org/home/why-gallup-ended-presidential-approval-polling-after-88-years/
- The Hill（2025-12-23）：2025-12-01..15 Gallup 调查 13 位领导人认可度，Powell 44%（46% Dem / 34% Rep / 49% ind）— https://thehill.com/business/5661417-jerome-powell-most-popular/
- Michigan SCE 特别报告 "Confidence in Financial Institutions"（2026-05-08，2026-02-16 起采集）：含 Federal Reserve System 信心题 — https://data.sca.isr.umich.edu/fetchdoc.php?docid=81063

## 详情

### 1. 2026 年 4 月 EPF：题目已被移除（不是改题、不是延期）

- `20260428PersonalFinancesInflation.pdf`（poll/708947，GAL 070，Princeton Job 26-04-004）是 2026 年 EPF 调查的完整 FINAL TOPLINE（18 页）。全文字符串检索：`Federal Reserve` / `Powell` / `Warsh` / `Treasury` / `leaders` / `Secretary` 命中数均为 0；`confidence` 仅出现 1 次（抽样误差方法论页 "95% confidence level"）。题组仅为：Q7 个人财务状况评级、Q8 财务展望、Q10 最重要家庭财务问题（开放式）、Q15 财务担忧系列 + 人口交叉表。
- 对比：2025 年 4 月 EPF topline（已在注册表，poll/659537）文件名即为 "Trump Approval and Economic Leaders Topline and Tabs"，即 leaders 模块与 Trump approval 绑定在同一模块；2026 年版本中两者一起消失。
- 背景：Gallup 于 2026-02-11（The Hill 报道，"reflects an evolution in how Gallup focuses its public research and thought leadership"）宣布停测 presidential approval 及 national leadership ratings。EPF 的 economic leaders 题属于 leadership ratings，随之停测。未发现 Gallup 就 Fed-chair 题单独发布停测说明。
- Wayback 2026-04 文章索引中不存在任何 "economic leaders" 文章（4 月文章仅 708905 EPF、708995 购房意向、709004、709055）。

### 2. 2025 下半年：五档题未再问，但 12 月 Governance 有 Powell job approval

- 五档 confidence 题历史上只在每年 4 月 EPF 询问（Binder et al. NBER WP 33684 / AEA 2025 论文明确记载），2025 年 4 月波次已在注册表；2025-04 至 2026-04 之间没有任何其他月份复现该题（Wayback 2025-05 至 2026-03 全部 topline 文件已核对，无 "Economic Leaders" 命名文件）。
- 但 2025 年 12 月 Governance 调查（GAL 053，field 2025-12-01..15，n=1,016，2025-12-22 发布，poll/700247）Q20 问了 13 位领导人的 job approval，其中 **G. Federal Reserve Chairman, Jerome Powell：Approve 44 / Disapprove 47 / No opinion 9**。该题此前问过 2021-12（53/40/7）与 2023-12（43/50/6），是 12 月 Governance 的既有项目。题面为 "do you approve or disapprove of the way each of the following is handling their job"，**与注册表五档 confidence 题（"how much confidence … to do or recommend the right thing for the economy"）是不同题目、不同量表（3 桶 vs 5 桶）、不同构念（对人 vs 对经济决策的信心）**。

### 3. 2026 年 6 月 / 9 月调查：均无 Fed chair 题

- 2026-06 Confidence in Institutions（poll/712667）：17 个机构（small business、military、police、higher education、…、Congress）中无 Federal Reserve / Fed chair（该列表历史上也从未包含 Fed 主席；Fed Board 于 2008 年后移出）。
- 2026-09 Governance（poll/715910，2026-10-15 发布）：无 leaders approval 模块（Q20 型题目整体消失），含 "The Federal Reserve Board" 机构表现评分（good 35 / fair 33 / poor 28，n=1,000）——机构题而非主席题，且全文无 "Warsh"。

### 4. Powell/Warsh 交接

- 2026-04 EPF field（4/1–15）在 Powell 任内；其继任者 Kevin Warsh 于 2026-05-15 就任（参议院 2026-05-12 确认；LiveNOW 2026-05-28、雪球 2026-05-15 等公开报道）。
- 所有已核对的 2026 年 Gallup topline 中 "Warsh" 命中数为 0。因此即使 Gallup 未来复题，2026 年 4 月波次问的也是 Powell；注册表整合时 wave_id 命名与问题对象备注应按此记录。

## Wave JSON 片段

**2026 年五档波次不存在，无可注册片段。** 以下为缺口期内唯一 Gallup Fed-chair 全国观测的可选 stopgap 片段——**注意：非 schema 兼容**（3 桶 approval 量表 + 不同题面），是否注册由注册表整合人决策；若注册，建议作为独立 series，不与 gallup_*_april 五档波次混用：

```json
{
  "wave_id": "gallup_2025_december_leaders_approval",
  "field_dates": ["2025-12-01", "2025-12-15"],
  "published_date": "2025-12-22",
  "published_at_conservative": "2025-12-22T23:59:59-05:00",
  "question_text": "Next, do you approve or disapprove of the way each of the following is handling their job-- [ITEMS READ IN RANDOM ORDER]? (Item G: Federal Reserve Chairman, Jerome Powell)",
  "scale": ["approve", "disapprove", "no_opinion"],
  "national_source_percent": [44, 47, 9],
  "national_sum": 100,
  "candidate_probabilities": [0.44, 0.47, 0.09],
  "sample_size": 1016,
  "survey_vehicle": "Gallup Poll Social Series: Governance (December Wave), GAL 053, Princeton Job 25-12-014, telephone",
  "source_url": "https://news.gallup.com/file/poll/700247/2025_12_22_US%20Political%20Climate%20Topline%20and%20Tabs.pdf",
  "local_file": "outputs/sce_recent_environment_evidence_20261023_v1/sources/gallup_20251222_us_political_climate_topline_GAL053.pdf",
  "sha256": "f8ffd4970cd8a221644e430627eec281ba9677b4eeddf55e082b6c0bb66382b2",
  "source_location": "PDF page 20 (Q20 summary table, sorted by approve); Q.20G detailed trend block (with 2021 Dec 53/40/7 and 2023 Dec 43/50/6); party cross-tabs in public release data pages",
  "schema_conformance": "NON_CONFORMING: 3-bucket job-approval scale, different question wording and construct than the registered 5-bucket 'confidence to do or recommend the right thing' series; do NOT blend with gallup_*_april waves without an explicit mapping decision",
  "prior_readings": {"2021-12": [53, 40, 7], "2023-12": [43, 50, 6]},
  "checked_on": "2026-10-23"
}
```

## 替代建议

1. **维持现状（推荐默认）**：2026 模拟月份（2026-01..09）继续沿用 `gallup_2025_april`，并在模拟配置/文档中显式注明：该 Gallup 系列已于 2026-02 随 Gallup 停测 national leadership ratings 中断，2026 年 4 月起无新波次，属"最后可得波次"而非"17 个月旧数据的可更新失败"。监测 2027 年 4 月 EPF 是否复题（鉴于停测决定，可能性低）。
2. **可选 stopgap**：将 `gallup_2025_december_leaders_approval`（44/47/9）作为独立的三档 approval series 注册，覆盖 2025-12 之后的模拟月份。优点：同为 Gallup 全国电话调查、同一人群（美国成人）、有历史可比读数（2021/2023-12）及党派交叉表；缺点：题面与构念不同（对人的 job approval vs 对经济决策的 confidence），且 2026 年内（Warsh 就任后）没有对应波次，2026 模拟月份仍无真实数据。
3. **学术替补**：University of Michigan Surveys of Consumers 的 "Confidence in Financial Institutions" 模块（含 Federal Reserve System）。2026-05-08 特别报告（data 2026-02-16 起采集）提供 2026 年读数；另有 2023、2025Q1、2025-08/09 读数。Binder et al.（NBER w33684）已将其 trust-in-Fed 与 Gallup 题并用。注意构念是"与五年前相比的信心净变化"（balance score），非信心水平；且为不定期特别模块，非月度。
4. **背景参考（不建议注册）**：Gallup 2026-09 Governance 的 "The Federal Reserve Board" 机构评分（good 35 / fair 33 / poor 28，n=1,000，2026-10-15 发布）是 2026 年内最新的 Fed 相关 Gallup 全国数据，但评的是机构不是主席，与注册表构念差异最大。
5. 若未来需要 Warsh 时期数据：可关注 Michigan SCE 特别模块是否继续、AP-NORC / Pew / YouGov 的 Fed 信任/认可度题，以及 Gallup 是否在领导人体系复测后恢复 economic leaders 题。

## 检索足迹（全部于 2026-10-23 完成）

- Web 检索（多组关键词）：Gallup April 2026 EPF confidence Fed chair topline；gallup.com 2026 "Economic Leaders"/"Personal Finance" PDF；Gallup Fed chair confidence 趋势页；Gallup 2025-12 leaders approval（定位到 The Hill 2025-12-23 与 Gallup poll/700241）；Michigan SCE trust/confidence in Federal Reserve；Binder AEA/NBER 文献确认该题仅 4 月询问。
- Wayback Machine CDX：
  - `news.gallup.com/file/poll/*`，from=2026-04-01 to=2026-10-23，110 条 capture 全量核对（含 2026-03-05 Foreign Policy、2026-04-14 Environmental、2026-04-22 Congress Approval、2026-04-23 ECI、2026-04-28 EPF、2026-05-06 Retirement、2026-06-01 Confidence in Institutions、2026-06-10 Moral、2026-07-09 Immigration、2026-08 Lifestyle、2026-09-14 Job Worries、2026-09-23 Economic Concepts、2026-10-15 Govt Agencies 等全部 2026 年 topline）；无 "Economic Leaders" 文件。
  - 文章页 prefix 查询 poll/6973*–6992*（2025-10..12）、poll/7002*–7005*（定位 2025-12-22 政治气候 topline 700247 与圣诞活动 700301）、poll/7089*–7159*（2026-04..10 全部文章页）；2026 年 4 月无 economic leaders 文章。
  - 历史前缀抽查（file/poll 2010–2024）确认 CDX 索引行为正常，排除"索引缺失导致漏检"的可能。
- Gallup 官网直读：poll/708905（2026-04-28 EPF 文章）、poll/700241（2025-12-22 文章）、poll/505478（2023 economic leaders 历史文章，"PDF download" 链接即对应年份 topline）；下载 4 份 topline PDF（HTTP 200）。
- Gallup 站内搜索路径 `news.gallup.com/search?q=...` 与 `topic/federal_reserve.aspx` 均返回 404（路径不存在/已改版），故改用 CDX 全量枚举，覆盖更完整。
- PDF 全文字符串核查（pypdf）：四份 2026/2025 topline 中对 `Federal Reserve` / `Powell` / `Warsh` / `right thing` / `confidence` 的逐词命中统计见上文各节。
- 存档一致性：4 份 PDF 的官网版与 Wayback 最早存档 sha256 逐字节一致。
- 工具说明：Kimi 内置浏览器在本环境返回 BROWSER_UNAVAILABLE，全程改用 curl / FetchURL / WebSearch；未调用任何付费 API 或 LLM。下载与解析（pypdf）均为本地确定性操作。

## 局限

- 结论"2026 年未问该题"基于：(a) 2026 年 EPF 完整 FINAL TOPLINE 无该题；(b) Wayback 对 2026-04..10 Gallup 全部 topline 文件与文章页的枚举无遗漏迹象；(c) Gallup 官方停测 leadership ratings 的公告。不能完全排除 Gallup 以未公开/未归档形式问过该题，但可能性极低（历年该题均随 topline 公开）。
- 2026 年 10 月 15 日之后的 Gallup 发布未纳入（超出 CDX 检索窗口的部分），如需可在 2026-11 复核 10 月下旬发布。
