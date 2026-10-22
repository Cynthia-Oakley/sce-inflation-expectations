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

## Codex 复审落实（2026-10-22 下午）

Codex 对管线提三点反馈，均已处理：

1. **真实缺口重算**：43,512 是旧的逐月缺口累计（含跨窗口重复，且索引漏掉近期已完成标签）。合并全部正式标签（旧 7,157 + 试点 1,868 + 一致性 300 = 8,725 篇）、按 article_id 跨月去重后：93 窗口唯一候选 38,903 篇，**真实待标 30,274 篇**（跨窗口重复 15,583 次）。预估费用约 $2（保守上限 $3）。文章跨月复用，不为重复出现重复付费。
2. **精简字段接入模拟验证**：生产链路（expanded_state_inputs / personal_information_views / reference/finance preparation / post2025_trial / news_exposure_demo）只读 `semantic_label['decision']=='keep'`，精简标签天然兼容；提示词渲染（render_news_input）只用原文 headline/abstract/snippet。硬读旧字段的仅是分析/报告/验收脚本，已做最小 .get() 修复：news_selection_analysis.py、news_extension_label_analysis.py、scripts/finalize_sce_news_parts.py（该文件为 Codex 未跟踪文件，修复留在工作区由 Codex 提交）。新增兼容层 studies/sce_inflation_expectations/news_label_compat.py（normalize_label 统一两 schema、缺失字段 None 不补造）与离线验证 scripts/verify_sce_news_label_compat.py：旧标签月 2022-03（653 标注/287 keep）与新标签月 2019-06（616 标注/185 keep）各组装一次新闻块，渲染输出与"仅原文重建"逐字节一致。测试 tests/test_news_label_compat.py 7 项。
3. **预算/断点续跑修复**（label_sce_news_pool.py）：续跑从 calls_log.jsonl 累计历史费用（prior_spend），不再从零计费；失败批持久记录于 errors.jsonl，续跑默认跳过、须显式 `--retry-failed` 才重发；每个成功批的原始 API 回复（key 已脱敏）存 responses/batch_XXXX.json 供审计；summary 增加 skipped_failed_batches 与累计口径说明。新增测试 2 项（共 22 项通过）。

⚠️ code_sha256 协议纪律：脚本已变更，旧输出目录（三个试点）不能再 execute（会报 "Script changed after prepare"）；新运行需重新 prepare。

## 待决

- **推荐方案**：只标新增缺口 **30,274 篇**（跨月去重后），用 deepseek-flash（与旧标签同模型，一致性已验证 87.7%），旧 7,157 篇保留不重标、字段差异由 news_label_compat 层吸收。预估约 $2（保守上限 $3）。
- **用户 2026-10-22 决定：暂缓执行**。管线已就绪；全量执行前需新增一个按"去重待标清单"生成的 variant（prepare 支持读预生成清单，而非逐月重建批次）。
- ~~是否全量重标 50,669 篇统一 vintage~~：flash 一致性验证通过后已无必要。

## 全量补标完成（2026-10-22，用户批准预算后执行）

- **规模**：跨月去重待标 30,274 篇全部完成（v1 串行段 2,552 篇 + v2 并发段 27,722 篇，两段目录 outputs/sce_news_labels_full_20261022_v1 与 _v2，均有 protocol/authorization/manifest 审计文件）。
- **费用**：保守计价合计 $2.8683（v1 $0.2452 + v2 $2.6231），低于 $3 硬上限；DeepSeek 实际扣费通常更低。
- **耗时**：v2 段 3,438 批 8.3 分钟（12 并发，约 8.6 批/秒；并发设计：worker 纯网络/校验、预算与文件写留主线程、在途批持预算预占）。
- **格式失败与修复**：共 33 批模型多带回声字段触发严格校验，全部经 repair 子命令从已存原始回复离线投影修复（零 API、分类内容不动、幂等）。
- **全量标签分布**（含旧 7,157 与试点）：keep 13,029（35.5%）/ background 11,754（32.0%）/ exclude 11,705（31.9%）/ uncertain 188（0.5%）。
- 验证：`pytest tests/test_label_sce_news_pool.py` 24 项 + `tests/test_news_label_compat.py` 7 项全绿；scripts/verify_sce_news_label_compat.py 新旧 schema 渲染逐字节一致。
