# Codex任务：概率表达与报告机制

2026-10-13。状态：任务已准备，尚未执行新分析。此任务可以与Kimi的信念更新线独立推进。

## 问题

真实居民的概率取整、零概率和稀疏档，哪些表现为跨期相对稳定的习惯，哪些也可能是信念与不确定性变化？它们改变了多少项目近似Q9计分？模型与真人的差距中，哪些可归于报告层，哪些在Q8或更新后的中心已经出现？

## 输入

只读`age_reporting_audit.py`、原`age_reporting_summary_20261012.json`、`confidence_response_diagnostic_20261012.md`、真实缓存及最新本人先验轨迹；原始行只在本地。已有5%/10%取整敏感性保留，不能把人工情景当真人风格比例；HRS文献不能直接给SCE十档题定参数。

## 交付

1. 先检查既有诊断覆盖，补同人跨期及年龄/教育/numeracy的概率模式稳定性，避免重复已完成的全量取整计算。
2. 区分个人中心、人际分歧、个人不确定性与报告精度；用Q8及映射前后中心定位差距，不把非零档少等同于习惯取整。
3. 仅用历史训练期估计候选模式、保留支持不足与分配不确定性，另留时期复核。先做零API敏感性，保存未改变的原问卷与映射结果。
4. 提出少量可比较的提示/程序方案，保持官方题意/档位/合计100约束；不硬指定通缩为0、非零档数或当期真值。
5. 写`codex_progress.md`、`codex_results.md`、无个人行`codex_summary.json`，附可复算代码和必要验证；没有支持也记录。

预留源码范围：`studies/sce_inflation_expectations/reporting_behavior/`、`scripts/analyze_sce_reporting_behavior.py`、`tests/test_sce_reporting_behavior*.py`；目前未建立可运行的新模块。Kimi的belief_dynamics目录、正式输入/运行/计分与15份保护改动只读。

Codex负责两个任务的公共状态整合，不能在Kimi未开始或未交付时替其打完成勾。两方首次结果后再收敛实验，真实API范围和预算另确认。
