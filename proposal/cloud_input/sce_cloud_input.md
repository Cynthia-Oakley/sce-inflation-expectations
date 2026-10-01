# 水上挽月｜SocioVerse2 SCE 云端首试输入

版本：2026-09-29 v2。用途：赛道 A 的**小规模流程实验**。本文件与 `sce_20_synthetic_personas.csv`、`persona_fixture_dictionary.md`、`sce_2021_05_06_bls_release_e.json` 配套。Event MCP 的 FRED 回包若缺历史发布时间/版本，先用 BLS 官方首发新闻稿构造的真实 E；`sce_2_month_synthetic_environment.json` 仅作为文件导入故障排查。真实数据与合成情景必须在产物中明确区分。

## 1. 研究任务

研究对象是纽约联储 Survey of Consumer Expectations（SCE）的**美国居民一年期通胀预期**。主目标拟为每位受访者 Q9 十区间主观概率所拟合密度的均值，再在受访者之间取加权中位数；副目标为 Q8 直接点预测的插值加权中位数。真实目标月 SCE 答案和官方月度值只能进入评价，不进入模拟家庭的 P/E/B 输入。今天先验证云端 study 结构、人口文件导入、Event 查询、问卷结构、40 条逐人输出及导出；暂不声称具有预测效果。

建议 study ID：`sce_inflation_expectations`。两个相邻**开发期**目标月：`2021-05` 与 `2021-06`。各自信息截止：`2021-04-30 23:59:59 America/New_York`、`2021-05-31 23:59:59 America/New_York`。按前月末预测该月调查统计值。两个目标月使用同一批 20 个 Agent。

## 2. P：合成测试人口与真实人口的下一步

本轮上传的 `sce_20_synthetic_personas.csv` 有 20 条、8 列：`agent_id,weight,age_group,education_group,household_income_band,region,housing_tenure,employment_status`。均为人为编排的 household-head 风格标签；每人 `weight=1`，原始总权重 20，归一后 0.05。`p_source_type=synthetic`，`p_version=p_pilot_20260929_v1`。请实际读取文件，报告行数、列名、缺失、唯一 ID、权重总和和至少 3 条画像样例，然后将其**物化成 study population**。不得只把 CSV 当附件而在研究里重新生成另一批人物。详细值域见配套字典。

真实 P 的后续候选依次是：有可得日证据的**历史已公布 SCE 微观画像**；2019 ACS 1-year PUMS 等在目标 `as_of` 前已公布的人口记录/边际；确有额外机制时再查 CPS、SIPP、CE。若确需 MCP 辅助，`census_acs`、`cps_basic`、`cps_asec`、`sipp` 是 Event 服务中的 population 来源，应**逐个单源**请求并验调查年份、人口单位、字段联合结构、权重、实际发布日期、版本和许可；它们不是 Population MCP 的 SCE 画像池。SCE 面向 household heads，不是所有成年人。SCE 官方问卷有年龄、教育、过去 12 个月家庭收入、就业、住房、地区等字段。当前官方微观文件的下载日不等于它在 2021 年的历史可得日；目标月同期 SCE 画像、真实权重、Q8/Q9 及派生值不得进入 P。首试无需人格/Big Five 赋值，也无需 Population MCP。

## 3. E：只查询精确 Event 来源并先验收

先查看 Event MCP 的 `list_sources()` 和本账号是否可用 `fred`。两个查询对应上面两个 `as_of`，每次只指定 `source="fred"`，并尝试 `series="CPIAUCSL,UNRATE"`：

```text
get_source_detail(source="fred", year=2021, month=4, series="CPIAUCSL,UNRATE", use_cache=true)
get_source_detail(source="fred", year=2021, month=5, series="CPIAUCSL,UNRATE", use_cache=true)
```

若云端只经 SocioVerse2 的公开 `materialize_external_events` 封装，传 `months=["2021-04","2021-05"]`、`sources=["fred"]`，再在返回后按 series ID 做白名单；该客户端本身不传 `series` 或精确日时 `as_of`。请展示**真实工具名、实际参数、原始返回结构**，不能由研究助手凭文字补造记录。不要调用默认/all 来源集（含 `nyfed_sce`），不要用 `search_web` 做历史新闻。

每条候选 E 信号须保留 `source/series_id/value/unit/reference_period/observation_date/published_at/vintage/source_url/fetched_at/as_of`，标记 `eligible` 或隔离原因。请求月份只约束观测截止；2021 年某月的 CPI/失业率可能在当时尚未发布或后来修订。只有**首次发布时间不晚于该 `as_of` 且历史数值版本可重建**的记录进入 Agent。缺日期或 vintage 时标 `unknown_as_of`，并输出隔离列表；不要以今天抓到的修订值假装当时已知。SCE 当期结果及复述结果的新闻始终排除。今天先不开新闻；以后单独验 `nyt_archive` 的初发日期、正文范围和修订版本。

若本账号 Event MCP 无法提供合格历史证据，**改用附件 `sce_2021_05_06_bls_release_e.json`**。它列出 BLS 在各 `as_of` 之前的当期 CPI 和就业首发新闻稿、发布时间、版本编号、数值、链接和本地 PDF 哈希。2021-05 使用 2021-03 CPI 全项目同比 2.6%（未季调）、环比 0.6%（季调）及失业率 6.0%；2021-06 使用 2021-04 CPI 同比 4.2%、环比 0.8% 及失业率 6.1%。CPI 增幅**不是** `CPIAUCSL` 指数。请先核对六条来源，再把冻结 JSON 物化为 E；FRED 当前快照留审计，不进入 B。只有这份真实 E 无法导入时，才用合成 E 诊断流程故障，并标“synthetic E / schema smoke”。

## 4. B：按 SCE 原题语义生成回答

每个 Agent 先回答 Q8：未来 12 个月为通胀还是通缩，以及该方向的非负幅度（百分比）；结构化保存 `direction,magnitude_pct,point_pct`，其中 `point_pct` 为带符号值。随后回答 Q9：**同一个人**对以下十种未来通胀/通缩结果分配百分数概率，十数之和严格为 100，顺序不能更换：

1. 通胀 ≥12%；2. 通胀 8–12%；3. 通胀 4–8%；4. 通胀 2–4%；5. 通胀 0–2%；
6. 通缩 0–2%；7. 通缩 2–4%；8. 通缩 4–8%；9. 通缩 8–12%；10. 通缩 ≥12%。

输出至少含 `agent_id,target_month,as_of,p_snapshot_id,e_snapshot_id,direction,magnitude_pct,point_pct,q9_bin1..q9_bin10,validation_status,prompt_version,model_version,seed`。概率每项在 0–100，总和 100；保存原始回答、失败/修复状态，不静默改写。两个月跨月记忆只能来自 Agent 之前**模拟**的状态。

官方 headline 的计分是 `Q9 十概率 → 个人参数化密度 → 个人密度均值 → 跨人加权中位数`，不能以十档区间中点平均代替。2017 官方方法附录 C 对 ≥3、相邻 2、单个正概率区间使用不同密度分支。我们的本地核验已能用公开文件中的个人 `Q9_mean` 复核 2020–2024 年 60 个月的跨人统计，但**尚未复现十概率到个人 Q9_mean**。因此今天请输出原始 Q9；若云端未独立验证拟合器，只能做“完整问卷/点预测流程演示”，不得把近似 Q9 结果称作官方主指标。

## 5. 今天分段操作与保存要求

1. 先回复研究方案、文件识别、Event 能力、计分/导出路径、预计 Agent/Simulation 额度，并停在平台确认点。研究对话本身可能消耗 Agent 额度。
2. 验证文件实际物化为 20 人，检查 Event 两次小样的 `published_at`/vintage；不合格的 Event 记录不喂入 B。
3. 运行 20 人×2 月的**scripted 确定性**演示；如平台会收费，先显示费用确认卡。预期 40 条逐人逐月回答。真实 LLM 试验应在能力与费用核验后另行确认。
4. 导出 study 配置、P/E 快照、脚本/prompt、40 条原始 Q8/Q9 回答、校验与失败信息、聚合/计分方法、模型和实际成本。给出 cloud study ID、导出文件列表与行数。本地将独立核查；若平台无法完整导出，明确报告缺项。

## 官方参考，优先按原文核对

- [SCE 主页面及文件入口](https://www.newyorkfed.org/microeconomics/sce)、[SCE FAQ](https://www.newyorkfed.org/microeconomics/sce/sce-faq)。
- [核心问卷 PDF：Q8/Q9 与人口题](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-survey-core-module-public-questionnaire.pdf)。
- [2017 方法论文：附录 B/C 的中位数与密度规则](https://www.newyorkfed.org/medialibrary/media/research/epr/2017/epr_2017_survey-consumer-expectations_armantier.pdf)。
- [官方图表指南 PDF：headline/point/uncertainty 口径](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/glossary/frbny-sce-chartglossary.pdf)。
- [SocioVerse Event 数据服务说明](https://socioverse.fudan-disc.com/docs/guides/data-services/)。

若平台无法读取这些外部链接，可单独上传本地同名 PDF；无需上传 SCE 原始微观工作簿或任何带真实回答的文件。
