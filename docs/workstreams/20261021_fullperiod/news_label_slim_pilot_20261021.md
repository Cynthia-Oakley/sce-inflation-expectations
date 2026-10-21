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

## 决定性对照：换回原打标模型 deepseek-flash（用户提议，2026-10-22）

用户指出：打标模型无需与模拟模型相同，旧标签本来就是 deepseek-flash（DeepSeek 官方端点）标的。用 **flash + 精简 4 字段 prompt v2.1** 复测同 300 篇（$0.0294 保守计价，38/38 批成功，outputs/sce_news_labels_flash_pilot_20261022_v1/）：

| 指标 | v3.2+v2.1 | **flash+v2.1** |
|---|---|---|
| decision 一致率 | 0.747 | **0.877（过 85% 阈值）** |
| topics Jaccard | 0.677 | **0.868** |
| scope 一致率 | 0.580 | **0.807** |

→ **74% 的漂移主要来自换模型而非砍字段**。错例核查：英国央行加息 flash 判 keep（policy/economic_outlook/living_prices，与旧标签一致）；欧盟核能天然气仍 exclude（两个模型一致排除，属旧标签偏宽的边界案例）。

**结论（待用户批准执行）**：全量补标 43,512 篇缺口用 deepseek-flash 官方端点 + 精简 4 字段 prompt v2.1，temperature 0、thinking 关闭、8 篇/批；旧 7,157 篇保留不重标（一致性已验证）。预估费用按保守价 ≤$4.5（flash 实际价更低，约 $1.5–2），5,439 批约 1.5 小时。

## 待决

- **推荐方案**：只标新增缺口 43,512 篇，用 deepseek-flash（与旧标签同模型，一致性已验证 87.7%），旧 7,157 篇保留不重标、字段差异在 README 明示。预估 ≤$4.5 保守价（实际约 $1.5–2），待用户批准。
- ~~是否全量重标 50,669 篇统一 vintage~~：flash 一致性验证通过后已无必要。
