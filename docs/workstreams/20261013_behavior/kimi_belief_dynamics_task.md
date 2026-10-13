# 给Kimi的任务：个人信念保留、更新与经验基线

日期：2026-10-13。当前状态：待用户转发后启动。独立负责这条线，不需要等待Codex的概率报告分析。

## 目标和当前认识

水上挽月、SocioVerse Challenge赛道A、美国SCE一年期预期。现在把B=f(P,E)中的信息处理规则作为研究重点。P/E已有基础，添加标签/资料没有稳定恢复微观分布；央行信心和本人真实t-1先验有改善线索。本人先验四期12人试验仍过度压缩差异，不能称全国预测或正确学习。

任务是回答：真实居民如何保留和调整上期预期，现有LLM哪里偏离；简单经验更新器能做到什么。不要以人为增加方差作为成功，不直接采用小样斜率作为因果更新率。

## 从哪里接手

仓库绝对路径：`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge`。按AGENTS先读`docs/AGENT_HANDOFF.md`最新段与`docs/NEXT_ACTIONS.md`顶部，不需要通读全部旧历史。再读同目录`coordination.md`和以下材料：

- `docs/reviews/20261012_mechanism_retro/behavior_reorientation_20261013.md`：最新目标、评价和A/B边界。
- `docs/literature/sce/factual_mechanisms_20261013/prior_trial_execution_20261013.md`：真实先验试验及压缩结果。
- `docs/literature/sce/factual_mechanisms_20261013/summary_public.json`：106月/103630有效Q9相邻对的既有真实统计。
- `studies/sce_inflation_expectations/factual_mechanism_audit.py`：已有严格相邻日历月匹配，读作参考。
- `studies/sce_inflation_expectations/age_reporting_audit.py`的`load_reference`：已有官方字段及缓存来源验证，只读复用。
- `outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet`及同目录`extraction_receipt.json`：真实2017-01至2025-10缓存；按现成程序验证哈希。个体资料只在本地。
- `outputs/sce_prior_analysis_20261013_v1/`和`outputs/sce_prior_transfer_diagnostic_20261013_v1/`：先检查实际schema再复用现成配对结果，不猜字段。官方Q9_mean和统一近似重算的版本不得混比。

现有Conda解释器：`/Users/wushuyue/anaconda3/envs/socioverse/bin/python`。先用已有环境，不修改系统Python。

## 顺序与交付

1. 写`kimi_progress.md`，确认输入、有效集、当前步骤和计划；先复核现成相邻匹配，不重复下载资料。
2. 用完整真人面板描述delta分布、跨期排序、先验位置/个人不确定性与更新的关系。分月份及事先确定的人口组；漏访不能当相邻一月，当前权重的条件性质、轮换与11个月预测窗口重叠要说明。现有小试只是机制诊断，不能由四个断开的时期估计模型长期个人方差。
3. 对已有真实LLM小试做同口径比较：本人先验原样延续、当前LLM，以及置换的身份对照。相关性不是因果更新率；只看中位数或排序稳定不足以识别更新有效性。
4. 提出少量低参数经验更新基线。在查看新基线结果前写出特征、训练/验证/评价月份、方法候选和主指标；按时间划分并说明过去已看过的统计/开发期，不称全项目盲测。A可用声明的真实起点；未验证发布可得性的方案只标A，不声称PIT B。本人原样延续为必要对照。
5. 先验证最简单的经验更新器，再决定是否需要复杂化；主报中心/W1、delta W1、群体关系和相邻排序，单人MAE为辅助。不要为了微观更分散而随机加噪；若研究剩余变动，须用训练资料估计并独立验证，另标机制假设。
6. 交付`kimi_results.md`、无个人记录`kimi_summary.json`、可复算代码与必要测试，说明哪些结果支持下一轮“显式本人状态/更新规则”，哪些不支持。精确个人记录仅留新outputs目录。

不要求本轮把LLM provider或模拟引擎接好。先把一条研究线做出可复核结果，公共集成后续另做。

## 可修改范围与约束

新增源码只在`studies/sce_inflation_expectations/belief_dynamics/`；入口为`scripts/analyze_sce_belief_dynamics.py`与`scripts/run_sce_belief_baselines.py`；测试为`tests/test_sce_belief_dynamics*.py`；本任务文档只写本目录`kimi_*.md/json`。新outputs以run_id命名，拒绝覆盖。

不修改公共任务板/交接/DECISIONS、现有计分、P/E、正式配置、旧provider或Codex的reporting_behavior文件。保护清单里的15份改动不得还原或提交；提交只scoped add，与另一端Git保存串行。实际实现不同于建议时在自己记录中解释，不擅自改项目目标。

本轮零付费API、不读取密钥、不发微观给新的模拟服务；MIDUS/UAS微观继续隔离。遇到需要新服务或真正运行实验的工作，先完成可审查准备，再交用户明确范围和预算。这里只启动本地分析，不沿用旧预算开展新模拟。
