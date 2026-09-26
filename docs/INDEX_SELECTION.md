# 从“指标跟踪”选目标｜初筛记录

更新：2026-09-26。**尚未选定最终指数**。来源是 `../../指标跟踪/global_index_candidates(1).csv`、`../../指标跟踪/global_economic_index_candidates(1).csv` 和相应 `methodology/<ID>/` 缓存。两个 CSV 共 551 条候选；缓存目录数不是候选总数。

## 筛选顺序

1. **属于教授提供的清单**，且统计目标能用一句话精确定义。若教授要求严格的“官方指数”，优先选名称与发布方法均明确的指数。
2. **能做 P→E→B→聚合**：目标由人的/企业或专家的回答构成，能解释“谁在回答、看见什么、如何作答”。纯文本计数、物理测量与市场价格不适合直接照搬 ConsumerSim 问卷范式。
3. **真值可回测**：连续历史值、调查期、发布日期、问卷和聚合规则可核验；公开报告不等于有可复用数值表。
4. **与既有案例区分**：避免只是把美国消费者信心换个发布机构；重视新的人群或机制，同时控制一个月内能完成的工作量。

## 四个需要审计的候选

- **ECO-0078｜ACCA–IMA Global Economic Confidence Index**：目前最值得先查的**正式指数**。来自会计师及财务专业人员季度调查，能形成专业人群 Agent 与财务信息环境；[ACCA 官方报告归档](https://www.accaglobal.com/policy-and-insights/report-archives/global-economic-conditions-archive.html)有历史各季报告。主要风险是精确数值可能只出现在图中，公开说明未完整给出单独的加权公式；先抽查 2019–2026 的连续数值和问卷口径。
- **ECO-0086｜OECD G20 Business Confidence Index**：正式月度指数，官方 [定义](https://www.oecd.org/en/data/indicators/business-confidence-index-bci.html)与数据入口较明确。主要风险是它是各地制造业调查的标准化综合指标，无法把少量企业 Agent 的回答直接等同为 G20 的 100 基准指数；需复核原始构成及是否能定义可比研究目标。
- **IDX-0100｜Ipsos What Worries the World**：确实在“指标跟踪”CSV 中，标注 `B_index_like`、`include`。因一般公众问卷和月度事件环境与 ConsumerSim 机制贴近，之前被建议为首选；但它是一组问题的比例，**不是单一官方综合指数**，且[官方页面](https://www.ipsos.com/en/what-worries-world)提示国别完整分解可索取。除非明确某国某题的连续公开序列，并确认这种调查比例符合导师的“指数”要求，否则不定题。
- **ECO-0088｜UN Tourism Confidence Index**：由旅游专家调查形成，官方 0–200 量表，领域差异性强。[官方指标说明](https://www.untourism.int/un-tourism-world-tourism-barometer-data)可查；主要风险是低频、历史数值和专家画像不易取得。

## 暂缓

- `IDX-0004` / `ECO-0089` World Sentiment Index 虽有正式月度数据，但基于 EIU 国别报告正负词评分；直接用新闻文本和 LLM 重造词频，不足以证明 Agent 调查模拟的价值。
- `IDX-0099` / `ECO-0082` Ipsos Global Consumer Confidence Index 与 ConsumerSim 的消费信心题材重合；前者在非经济清单中也被标为 `exclude_strict_economic_boundary`，不能把它当作“换领域”的优先目标。

## 9 月 30 日的选题门槛

分别对 ECO-0078、ECO-0086、IDX-0100 抽查至少 12–24 个连续观测、公开来源、调查/发布时点、口径断点和可再分发性。先用可核验性筛掉不可做的目标，再在合格目标之间比较社会科学问题与 Agent 机制。最终选择和排除理由写入 `DECISIONS.md`，避免事后按回测成绩挑题。
