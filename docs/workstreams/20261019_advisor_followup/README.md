# 下一阶段：同类家庭差距诊断

本轮为零新增付费调用的开发诊断，参考配置和旧实验保持不变。

1. [结果与结论](diagnostic_results.md)：十二期九格诊断、旧Q8独立复算与平台免费能力。
2. [图文阅读章节](../20261013_behavior/codex_expansion_diagnostic_20261014.html#household-grid-q8-20261019)：四图、逐格支持、基线和边界。
3. [下一项对照草案](next_trial_design.md)：Q8变化值、Q9仍直接填概率；输入已备，尚未引擎验收或付费运行。
4. [执行前固定口径](diagnostic_plan.md)及[原反馈衔接](plan.md)。

公共聚合与图在[diagnostic_readout_v1](diagnostic_readout_v1/)。权威私有输出为`outputs/sce_advisor_diagnostic_20261019_v2/`；v1是已标记失效的草稿。原始回包与逐人输入不进Git。

## 复算入口

```text
python scripts/analyze_sce_advisor_diagnostics.py --out outputs/<fresh_output>
python -m pytest tests/test_sce_advisor_diagnostics.py -q
```

分析直接复用已计分轨迹，不重新拟合Q9。平台工具仅核免费目录/能力，没有付费模型问卷。`scripts/report_sce_advisor_diagnostics.py --source outputs/<fresh_output>`负责聚合图文；同名公共目录/章节已存在时拒绝覆盖，重做应使用新版本标识。

其余当前任务统一在[任务板](../../NEXT_ACTIONS.md)：采购角色—价格菜单、候选独立时期/种子、最终研究包持续推进，本轮没有把所有后续工作标为完成。
