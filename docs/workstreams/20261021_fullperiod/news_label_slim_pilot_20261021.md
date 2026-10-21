# 新闻精简标签口径与试点记录（Kimi，2026-10-21/22）

背景：全时段 coverage 实测新闻 LLM 标签缺口 **43,512 篇**（召回池口径，非原始缓存）。用户决定保留标签体系并冻结精简口径。

## 冻结口径（用户 2026-10-21 确认）

- `decision`：keep / background / exclude / uncertain
- `topics`：旧 6 值封闭集，多选可为空：living_prices / supply_costs / employment_income_consumption / policy / economic_outlook / other_economic（与已有 7,157 篇旧标签完全兼容）
- `scope`：旧 7 值：us_national / us_local / us_unspecified / us_and_global / global / non_us / unspecified
- **删除** claim_type / reason_zh / evidence_snippet（用户判断：消耗 token 且下游用不到）
- 语义定义沿用 `docs/literature/sce/news_selection/llm_label_prompt_v1_2.md` 的 decision/topics/scope 段原文；v2.1 另加两条澄清（见下）

## 管线

`scripts/label_sce_news_pool.py`（commit 340b739）：OpenRouter deepseek/deepseek-v3.2、DeepInfra 锁定、temperature 0、8 篇/批、JSON 模式、零自动重试、断点续跑、key redact、prepare→authorization→execute 三段式预算纪律。候选池 = build_news_pool 同口径（含跨缓存重复容错），逐月 as_of 取自 coverage.json。

## 试点（$0.1028，1,868 篇全齐，outputs/sce_news_labels_slim_pilot_20261021_v1/）

- 新标组：2019-06（616 篇：keep 185/background 210/exclude 220/uncertain 1）、2025-05（952 篇：keep 418/background 241/exclude 290/uncertain 3）
- 一致性组（2022-03 同种子 300 篇 vs 旧标签）：decision 一致率 **0.740（标红）**、topics Jaccard 0.678、scope 0.560
- 混淆因素说明：旧标签由 deepseek-flash + 完整 7 字段提示词生成；试点是 v3.2 + 精简提示词，74% 混有模型与提示词两个变量
- 主线人工审查 7 个分歧案例：v2 版存在**不合理过严**——"英国央行加息抗通胀""欧盟核能天然气可持续投资"等被 exclude，按分类标准应保留；us_and_global 被错降为 global/non_us

## v2.1 修正（两条澄清，仍 4 字段输出）

1. 主要经济体央行货币政策、国际能源/贸易/供应链政策与事件，不得仅因发生在国外而 exclude；内容弱降 background，相关保 keep。
2. 外国事件涉及对全球/美国经济背景影响（制裁、央行政策、能源贸易）标 us_and_global；纯外国国内事务标 non_us。

一致性复测结果（同种子 300 篇，$0.0175，38/38 批成功）：decision 一致率 **0.747**（v2 为 0.740）、topics Jaccard 0.677、scope 0.580——**两条澄清基本未改变判定**。两个错例"英国央行加息抗通胀"(1a70338b89d627593a5d8ccb) 与"欧盟核能天然气可持续投资"(221e355cfad0f43538f1e683) 在 v2.1 下仍为 exclude/non_us。结论：DeepSeek V3.2 的过严是系统性模型行为，提示词澄清穿不透；继续措辞迭代预期收益低。

注：74% 不是错误率——旧标签是 deepseek-flash 的判断，双方都不是金标准；分歧集中在国际宏观内容的 keep/background/exclude 边界。

## 待决

- 全量标注约 50,669 篇（含已标 7,157 篇按统一口径重标）≈ **$5**，需用户批准后执行。
- 若用户选择只标新增 43,512 篇，则数据集会混两个标签 vintages（旧 7k 完整 7 字段、新 43.5k 精简 4 字段），需在 README 明示。
