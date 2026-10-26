# 新闻来源与曝光机制：材料审计交接

2026-10-24，Kimi 旁线。依据 `docs/workstreams/20261024_fullperiod_analysis/media_sources_literature_20261024.md` 第 6 节。

**状态：材料审计与离线提示准备完成，未开展模拟。**本轮 new_api_calls=0、new_llm_calls=0；未修改 A82 冻结输入、运行配置或既有结果。工作区大量已有改动均保留。**早期离线准备回执见 `PREPARATION_RESULTS.md`；当前拟实施方案以 `NEWS_MECHANISM_PLAN_V3.md` 为准，尚未成为可启动执行包。**

## 1. 先给结论

两个原假设都应保留为候选，但审计发现了更直接的输入缺口：

1. **负面新闻权重不是目前最先能确认的问题。**生活成本类文章在候选池和实际展示中的占比接近；2022-06 实际展示也是警示文章多于安抚文章，不能概括为“NYT 输入整体太安抚”。
2. **A1 头版路由造成了确定的重要新闻缺口。**A1 文章只能参加共同 3 篇的均匀抽签，不能进入个人新闻流。2021-06 和 2022-06 最重要的 CPI 发布报道均未抽中，因此实际曝光为 0。
3. **媒体来源效应仍未被检验。**Fox/NYPost 材料提供了实际工资、家庭月度额外支出、街头生活经历和政治归因等补充叙事，但并非一律更警示；只有同人口、同数量、同信息截止的对照才能估计其增量。
4. 因此建议顺序是：**先修重要新闻路由，再分别检验来源混合和负面权重；不要同时改完后把收益归给某一个因素。**小对照设计见 `next_trial_design.md`。

这只是输入侧审计，尚未定量证明哪个缺口造成了多少模拟误差。

## 2. 当前 NYT 选择器实际怎样工作

复算入口：

- `studies/sce_inflation_expectations/experiments/state_continuity_prompts.py:136-197`
- `studies/sce_inflation_expectations/news_exposure_demo.py`
- `studies/sce_inflation_expectations/news_exposure.py`
- `studies/sce_inflation_expectations/news_quantity.py`

实际机制：

- 新闻窗口为上月 1 日至目标月 `as_of`；经关键词召回、语义标签和去重后形成候选池。
- 所有 A1 文章仅参与共同 3 篇的均匀无放回抽签；个人池只含非 A1 且 `keep` 的文章。
- 每人先抽 17 篇个人候选，权重为 `0.5×均匀 + 0.5×兴趣加权`；兴趣命中文章的分数为 2，其余为 1。
- 全量身份框按 48:28:20 分配 3/8/20 篇总量；3 篇档没有个人新闻，8 篇档看到 5 篇个人新闻，20 篇档看到 17 篇个人新闻。
- 提示中实际保留在线发布日期、标题和摘要，不是只给标题。

两月均逐人复算出共同 3/3 和个人 512/512 的文章集合，与冻结提示一致。

## 3. 两个月实际曝光

实际输入：

- `outputs/sce_monthly_fine_full_assembly_20261023_v3/prompts/<month>/timing_context_private.json`
- `outputs/sce_monthly_fine_full_assembly_20261023_v3/prompts/<month>/templates_private.json`
- 候选标签：`outputs/sce_fullperiod_materialized_20261022_v2/<month>/news_label_index.json`

| 指标 | 2021-06 | 2022-06 |
|---|---:|---:|
| Core 人数 | 512 | 512 |
| 个人合格池 | 201 | 219 |
| 实际至少出现一次的个人文章 | 201 | 219 |
| 个人文章总曝光（不含共同新闻） | 2,563 | 2,534 |
| 单篇个人曝光范围 | 4–24 | 4–21 |
| 生活成本类在 keep 池占比 | 12.6% | 19.5% |
| 生活成本类在实际展示篇目占比 | 12.3% | 18.5% |

生活成本类没有在展示环节被系统性压低。兴趣权重改变了文章被谁看到的概率，但没有造成合格文章整篇消失。

### 共同新闻没有覆盖当月核心通胀事件

- 2021-06 共同 3 篇：难民上限、中国出生率、清洁能源。
- 2022-06 共同 3 篇：魁北克水电争端、婴儿配方奶粉、红旗法。

以下 A1 通胀文章均在候选资料中，但因未抽中共同新闻且不能进入个人流，**曝光为 0**：

| 月份 | 日期 | 文章 |
|---|---|---|
| 2021-06 | 2021-05-03 | Widespread Commodity Shortages Raise Inflation Fears |
| 2021-06 | 2021-05-12 | Jump in Consumer Prices Raises Stakes in Inflation Debate |
| 2021-06 | 2021-06-10 | Prices Jumped 5% in May From Year Earlier |
| 2022-06 | 2022-05-04 | Fed Makes Biggest Interest Rate Increase Since 2000 |
| 2022-06 | 2022-05-11 | Consumer Prices Are Still Climbing Rapidly |
| 2022-06 | 2022-06-10 | Inflation Sped Up Again in May, Dashing Hopes for Relief |

这比“媒体是否保守”更直接地说明：**模型可能根本没有看到当月最重要的公开通胀信号。**

### 不能忽略但不建议本轮改动的边界

现有 `as_of` 均为目标月 10 日结束，因此当月后续报道不在输入中；2022-06 也包括 6 月 15 日美联储加息 75bp。此现象属于已冻结的信息截止规则，不是新闻选择器错误。本轮不借此事后扩展 `as_of`，避免把更多信息误称为同一机制修复。

## 4. 外部媒体材料补到了什么

文件：

- 候选数据：`outputs/sce_media_mechanism_20261024_v1/external_candidates.json`
- 检索与逐月重点：`docs/workstreams/20261024_media_mechanism/external_source_notes.md`

每月 15 篇，共 30 篇：

| 窗口 | Fox Business | Fox News | NYPost |
|---|---:|---:|---:|
| 2021-06 | 13 | 2 | 0 |
| 2022-06 | 9 | 2 | 4 |

有补充性的内容：

- 2021-06：实际工资被侵蚀、条件式持续通胀判断、预算/能源政策归因。
- 2022-06：NYPost 街头生活成本访谈、“每月额外支出约 $460”的可记忆数字、名义工资与实际工资差异。
- 反向证据：Fox 也有安抚或中性报道；2021-06 外部材料并非统一警示，不能给整个媒体预设方向。

**当前还不能直接用于对照运行：**

1. 30 篇只覆盖 6 月 1—10 日，未覆盖现有输入窗口中的 5 月；如开跑必须按同一完整窗口补齐。
2. 文章是 2026-10-24 获取的当前在线版本，尚未完成历史文本快照核验；`published_at` 与 `observed_at` 已分开，但发布日正确不等于正文版本已认证。
3. NYPost 2021-06-01..10 未检出合格通胀专门报道，已保留真实缺口，没有用后月文章凑数。
4. 许可未核验；只保存 URL、标题和短导言，未把全文入库。

## 5. Watson 社交分享数据不能直接作为新闻输入库

核查对象：<https://github.com/JoeMarkWatson/negative_news_sharing>；论文开放全文：<https://pmc.ncbi.nlm.nih.gov/articles/PMC11405697/>。

已核实：

- 数据含 NYT、NYPost、Daily Mail、Guardian 的文章级 URL、日期、标题/正文情感派生特征和社交分享计数。
- **不含标题文本或正文文本**，不能直接组装提示。
- 仓库样本实际止于 2021-09-30，不能覆盖 2022-06。
- 仓库没有 LICENSE 文件；论文 CC BY 4.0 不等于仓库数据或出版商正文获得同样授权。
- 可免费下载派生特征作研究参照，但“负面文章分享约 1.91 倍”不能挪用为本项目通胀新闻权重。

## 6. 对最终研究的建议定位

- A82 原结果、原配置和原误差全部保留；这次审计用于解释输入机制，不回写主成绩。
- 新实验属于看过 2021/2022 结果后的探索性机制实验，不能当作独立验证。
- 若只做最后一次小对照，优先回答三个可分的问题：重要新闻路由是否有增量、来源混合是否有增量、负面权重是否有增量。
- 具体分组、固定规则和运行前缺口见 `next_trial_design.md`；真实调用须另行冻结并授权。
