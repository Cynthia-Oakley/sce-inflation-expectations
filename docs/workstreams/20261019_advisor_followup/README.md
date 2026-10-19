# 下一阶段：同类家庭差距诊断

先完成零API诊断，再按用户本批授权完成Q8单改384次调用。参考配置和旧实验保持不变。

1. [结果与结论](diagnostic_results.md)：十二期九格诊断、旧Q8独立复算与平台免费能力。
2. [图文阅读章节](../20261013_behavior/codex_expansion_diagnostic_20261014.html#household-grid-q8-20261019)：四图、逐格支持、基线和边界。
3. [Q8单改结果](q8_delta_results_20261019.md)：384调用、估$0.432，全合法；Q8分布改善，Q9中心未过保护门槛，不改默认。[执行前对照](next_trial_design.md)保留。
4. [执行前固定口径](diagnostic_plan.md)及[原反馈衔接](plan.md)。

补充：[网格维度与十类变量关系](../20261013_behavior/codex_expansion_diagnostic_20261014.html#grid-variable-priority-20261019)、[排名聚合](population_factor_priority_20261019.json)。年龄×学历只是初诊；ConsumerSim扩展维度已核，真人水平与个人不确定性的变量侧重不同。

最新：[六格人口草案](stratification_draft.md)、[Q8准备收据](q8_delta_ready_v1/readiness.json)、[阅读章节](../20261013_behavior/codex_expansion_diagnostic_20261014.html#six-cell-q8-ready-20261019)。两项分开：网格只设计，格式实验沿用旧四期24人。

公共聚合与图在[diagnostic_readout_v1](diagnostic_readout_v1/)。权威私有输出为`outputs/sce_advisor_diagnostic_20261019_v2/`；v1是已标记失效的草稿。原始回包与逐人输入不进Git。

## 复算入口

```text
python scripts/analyze_sce_advisor_diagnostics.py --out outputs/<fresh_output>
python -m pytest tests/test_sce_advisor_diagnostics.py -q
```

分析直接复用已计分轨迹，不重新拟合Q9。平台工具仅核免费目录/能力，没有付费模型问卷。`scripts/report_sce_advisor_diagnostics.py --source outputs/<fresh_output>`负责聚合图文；同名公共目录/章节已存在时拒绝覆盖，重做应使用新版本标识。

其余当前任务统一在[任务板](../../NEXT_ACTIONS.md)：采购角色—价格菜单、候选独立时期/种子、最终研究包持续推进，本轮没有把所有后续工作标为完成。

## 已完成：温度对照

[三组方案](temperature_trial_plan.md)、[配置](temperature_config_v1.json)、[48单元离线收据](temperature_readiness_v1.json)。0.5/0.8/1.0×四旧开发月×24人×4遍，1152请求已完成，全合法，估$1.2875/$6；主比较未过筛选，保留0.5参考。[结果与复算](temperature_results_20261019.md)。只改变API温度，不改变网格、先验或回答格式。

## 当前下一步：固定模型与两层评价

[最新安排](next_stage_model_and_evaluation.md)：官方同输入能力优先核；条件不足则单一固定备选。微观W1/分组/更新与宏观冻结组合分别验证，不改旧试验结果。现阶段只有免费核查与计划，无新模型真实调用。
