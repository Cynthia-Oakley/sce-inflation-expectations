# Codex与Kimi的水平分工

2026-10-14。最新状态：Codex[U1 v2准备层验收](codex_u1_v2_readiness_20261014.md)完成，48状态/96提示独立重算保留原输入、42有指导/6关闭、35测试及192旧回答离线复放通过，API0。新协议codex_u1_comparison_protocol_v2补齐指导减状态和事前42人月附加分组；报告映射仍附加。Kimi按用户安排搭运行管线和dry run，Codex待运行入口的实际提示/配置/别名/调用数收据复核。状态组含新历史，不能叫纯措辞实验；准备通过不等于执行验收或预算授权对齐。双方文件分工保持，Codex未改Kimi模块或原配置。下文保留最初分工约定。

## 为什么这样分

以研究问题分工，每一方都完成自己那条线的证据核查、分析程序、结果与候选方案。这样Kimi可以独立推进，不必等待Codex先完成全部文献；Codex也不必等待Kimi实现后才开始复核。最终的运行配置、评价和付费调用需要一次共同收敛，这个短依赖保留。

本轮两条线是：

- **Kimi：信念保留与更新。**用同人相邻问卷分析变化，建立不依赖LLM的经验更新参照，再提出显式个人状态的候选方式。任务见[kimi_belief_dynamics_task.md](kimi_belief_dynamics_task.md)。
- **Codex：概率表达与报告。**分析取整、零概率、概率形状及跨期稳定性；查明它们改变了多少计分，再提出单独的报告机制候选。任务见[codex_reporting_task.md](codex_reporting_task.md)。

两条线共用SCE目标、冻结近似计分和真实资料，只读已有输入。任何一方的结果都不是另一方开始的必要条件。

## 共享的事实与边界

研究对象是SCE一年期通胀预期，不是预测未来实际CPI。A条件重建和B事前预测分别说明。当前本人先验来自真实t-1问卷，是A诊断；B不能逐月读未公开本人微观，需自身模拟状态或可得经验初始化。

已完成106月真实资料审计和四期12人先验试验。本人先验让样本中心MAE1.760→1.318pp、W1 3.473→3.102pp，但真人/模型人际IQR5.502/0.974pp；置换中心更近，身份价值未确认。不能将12人样本误差与全国基线混比。全国输出40/60组合MAE0.409pp，公开值延续0.400pp；未证明预测增量。详见[方向复盘](../../reviews/20261012_mechanism_retro/behavior_reorientation_20261013.md)。

15份用户/Kimi待审改动按[保护清单](../../sources/sol_handoff_protected_files_20261010.json)保持；不还原、不混入提交。新代码用各自目录，旧模块只读。现阶段两条线都是零API任务；旧实验剩余预算不自动用于新调用。MIDUS/UAS微观继续隔离，不能被任务包默认授权读入。

## 文件分工

以下新源码位置是预留，不表示已经实现：

- Kimi：`studies/sce_inflation_expectations/belief_dynamics/`、`scripts/analyze_sce_belief_dynamics.py`、`scripts/run_sce_belief_baselines.py`、`tests/test_sce_belief_dynamics*.py`，以及本目录内`kimi_*.md/json`。
- Codex：`studies/sce_inflation_expectations/reporting_behavior/`、`scripts/analyze_sce_reporting_behavior.py`、`tests/test_sce_reporting_behavior*.py`，以及本目录内`codex_*.md/json`。
- 原始/个人结果：各写新的`outputs/sce_belief_dynamics_<run_id>/`或`outputs/sce_reporting_behavior_<run_id>/`，不覆盖已有结果，不提交个体记录。
- 公共文件：`NEXT_ACTIONS.md`、`AGENT_HANDOFF.md`及任务清单阅读页由Codex整合。Kimi只更新自己的进度/结果文件。计分器、已有运行入口、P/E和正式配置均不在本轮可改范围。

各自只暂存自己的明确文件。使用同一checkout时不并发操作Git暂存/提交，不切分支、不stash/reset/pull覆盖现场；提交时发现另一方正在保存，稍后串行完成。研究分析本身不需要等待Git操作。未来若需要同时改公共代码，再改用隔离worktree并合并。

## 交付格式：传递证据，而不依赖转述全部思考

每方先写简短`*_progress.md`，包含当前步骤、已完成内容和下一步。完成写`*_results.md`与无个人行`*_summary.json`，只保留：

1. 分析要回答的问题及假设；
2. 输入路径、版本/哈希、样本有效集、时间窗口；
3. 实际方法及可复算入口；
4. 数字、比较对象和成立范围；
5. 已排除的解释、仍不确定之处、候选改进；
6. 所改文件和下一项。

不要求复制聊天历史、生成私有思考过程或把全部文献读一遍。缺少关键事实先检查材料；不确定项明确记下，不自行补造假设。一个简报不足以传递所有上下文，但证据路径与复算能降低交接损失。

## 汇合点

两方各完成第一次可复核交付后，Codex与用户合并判断：问题主要发生在信念更新还是概率报告，哪个机制先做真实对照。用相同P/E与样本构造候选，不同时任意改变两层；需要交叉设计时另登记。最后才共同冻结评价、独立时期、运行配置和新预算。

没有结果也可交付负证据及停止理由。完成任务的勾选表示交付与验收完成，不表示机制一定改善拟合。
