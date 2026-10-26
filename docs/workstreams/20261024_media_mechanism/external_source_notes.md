# 外部媒体候选文章检索说明（Fox Business / Fox News / NYPost）

2026-10-24。依据 `docs/workstreams/20261024_fullperiod_analysis/media_sources_literature_20261024.md` 第6节执行的 Kimi 旁线任务。
数据文件：`outputs/sce_media_mechanism_20261024_v1/external_candidates.json`。

## 窗口与 as_of

- 2021-06：`as_of = 2021-06-10T23:59:59-04:00`
- 2022-06：`as_of = 2022-06-10T23:59:59-04:00`

as_of 均取自 `outputs/sce_fullperiod_materialized_20261022_v2/<month>/environment_receipt.json`。仅收录发布日不晚于 as_of 的文章，逐篇以脚本断言校验通过。

## 检索方法（零付费 API、零模拟）

1. **Fox Business / Fox News**：两站均公开 `sitemap.xml?type=articles&page=N`（每页5000条，含 `lastmod`）。按页定位到覆盖目标旬的页码（Fox Business：2021-06 在 page 9、2022-06 在 page 7；Fox News：2021-06 在 page 63、2022-06 在 page 50–51），抽出 2021-06-01..10（399条）与 2022-06-01..10（320+248条）的全部 URL，按 slug 关键词初筛后逐篇抓取原站正文，人工判定三轴。发布日期取自原页 `datePublished` 结构化数据（与 sitemap lastmod 一致）。
2. **NYPost**：无公开 sitemap。用 Kimi Code 内置浏览器在 Google 做日期限定检索（`site:nypost.com inflation`，自定义区间 6/1–6/10），逐条点击结果跳转原站确认真实 URL 与标题，再用脚本抓取原页 `datePublished` 与导言。
3. 摘要为导言级短摘录或一句话转述，未复制全文；原站正文仅用于本轮人工判断，未入库。

**覆盖边界：**当前 30 篇候选只覆盖 6 月 1—10 日，而现有 NYT 输入窗口还包括上月 1 日至月底。因此它们足以判断“有哪些新叙事”，但**还不是可直接替换原新闻池的完整对照输入**；若开展模拟，须按同一完整窗口补齐 5 月候选，不能把这 30 篇当作全窗口媒体对比。

## 每月候选数与来源组合

| 窗口 | 篇数 | Fox Business | Fox News | NYPost |
|---|---|---|---|---|
| 2021-06 | 15 | 13 | 2 | 0（缺口，见下） |
| 2022-06 | 15 | 9 | 2 | 4 |

## 来源缺口（如实记录）

- **NYPost 2021-06 为零**。Google 日期限定检索（inflation / gas prices / cost of living / consumer prices 多组词）未检出该旬通胀专门报道；其通胀密集报道始于 2021年7月（如 7/22 `biden-again-rejects-inflation-concerns-claims-its-temporary`，已在文献核查文件中登记，但超出本窗口）。不凑数、不预支后续月份文章。
- Fox 系 sitemap 覆盖文章页；视频/电视节目文字稿部分页面抓取失败（如 foxnews Charles Payne transcript 5/31 发布、属5月窗），未计入。
- 剔除项：foxbusiness `inflation-economy-top-mind-americans-heading-midterms-poll` 原站 404（以 foxnews 的 Quinnipiac 民调报道替代）；foxnews `biden-gas-prices-crisis-worsens-for-americans` 为晨间新闻信非独立报道。

## 每月最具补充性的候选（3–5篇）

### 2021-06（对当前 NYT 池最可能缺失的内容）

1. **Fox Business, 6/9, "Real wages decreasing since Biden took office"** — 实际工资被通胀侵蚀的量化表述（五个月连续下降），是"家庭经历×宏观数据"交叉轴的直接素材，NYT 同旬较少以此框架出现。
2. **Fox Business, 6/10, "Consumer prices surge 5% annually, most since August 2008"** — 5% CPI 当日的标杆报道；保留"base effects"解释与美联储"暂时论"语境，可与 NYT 同日稿件逐段对照语气差异。
3. **Fox Business, 6/10, Kudlow 评论 "Biden's plan will lead to much more inflation"** — 条件式持续性判断（政策通过→永久；不通过→暂时），是"持续性=混合/不确定"判断的清晰样本，也是归因轴（支出/税收/能源政策）的代表。
4. **Fox Business, 6/6, "Yellen says higher interest rates would be 'plus'"** — 罕见的安抚端素材：官方主动淡化通胀风险。证明 Fox 系窗口内并非单一警示语气，避免把来源整体标签化。
5. **Fox News, 6/1, "House conservatives slam 'Pathway to Bankruptcy' budget"** — 把通胀嵌入预算/支出政治框架的报道，体现归因轴上"赤字支出"叙事的早期形态。

### 2022-06（CPI 8.6% 发布旬）

1. **NYPost, 6/10, "Inflation hammers New Yorkers as consumer prices surge to 40-year high"** — 街头采访合集（$300两袋食物、$103加油、$120早餐），生活成本轴的最强素材，叙事方式与通讯社/大报明显不同。
2. **NYPost, 6/10, "Inflation costing Americans an extra $460 per month"** — 家庭月度额外支出估计值（Moody's 测算），典型的"可记忆数字"小报框架，可检验此类数字是否比百分比统计更易进入家庭预期。
3. **Fox Business, 6/10, "Scorching-hot inflation wiped out most Americans' wage gains"** — 名义工资 vs 实际工资框架，与2021年同框架稿件（Goodspeed）构成跨窗口对照，直接服务持续性判断。
4. **Fox Business, 6/5, "Sperling credits American Rescue Plan 'resilience'"** — 语气=混合的样本：白宫安抚叙事与"经济学家指认救助计划"并列，归因分歧在单篇内可见。
5. **Fox News, 6/2, "Why Biden's inflation blitz is falling flat"** — 把"暂时论"转向回溯性追责的元叙事样本，显示2022年6月窗口叙事已带有事后归因色彩（对 agent 输入需谨慎）。

## 三轴判断要点

- **价格内容**：2021-06 以宏观统计/政策解释为主，生活成本类（网约车、二手车、Chipotle）刚出现；2022-06 生活成本类占主导（房租、油价、杂货、缩水式通胀）。
- **语气**：2021-06 中性8、警示6、安抚1；2022-06 中性6、警示8、混合1。负面语气不等于失实：如 CPI 报道数据全部准确。
- **持续性**：2021-06 多为"暂时/不确定"（含官方暂时论语境）；2022-06 转向"持续/不确定"。
- **归因**：共和党归因（支出、能源政策）贯穿两窗；2022-06 新增"普京/俄乌"归因（拜登框架）与"供应商借机涨价"（行业归因）。逐篇记入 JSON 的 `attribution_note`，未做统一标签。

## 重要声明：尚不能称为历史版本认证

- 所有文章均为 **2026-10-24 抓取的原站当前在线版本**，未与 Wayback Machine 等历史存档比对；页面可能在发布后经过编辑（标题、导语、数据图均有可能变动）。
- `published_at` 取自原页结构化数据或站点地图，为历史发布时点；`observed_at=2026-10-24` 为抓取时点，两者未混淆。
- 版权与再利用许可未核验；以上候选仅为机制小样的候选输入，未下载全文入库，不代表可直接进入正式环境配置。
- 下一步（如继续）：用存档服务比对至少各窗口 3–5 篇的关键句，核验当前版本与原始版本差异；确认 NYPost 2021-06 缺口是否可用其印刷版/数据库补齐。
