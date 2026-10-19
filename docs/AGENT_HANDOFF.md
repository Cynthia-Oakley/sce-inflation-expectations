# SCE 项目当前交接

更新：2026-10-19。先读[DESIGN](DESIGN.md)和[NEXT_ACTIONS](NEXT_ACTIONS.md)。本页只维护当前现场；旧运行中/待授权描述见[原文快照](reviews/20261019_repository_cleanup/README.md)，不能据其重启任务。

## 1. 当前状态

- 用户已提交开题提案，最终交付按10月31日组委会要求。时间安排只见ROADMAP；10月16—23用户繁忙的背景不改变已授权本地研究。
- 本地官方SocioVerse2引擎、真实DeepSeek回答、冻结近似Q9计分和评价链已实际运行。当前是A线回访者条件重建，使用本人真实上期信念，不是严格B自主预测。
- 12期×192×两遍主MAE 0.459/照抄0.239；分布仍过窄。全国完整波次成绩另报，不混入同支持成绩。详[配置](CURRENT_SIMULATION_CONFIGURATION.md)和[台账](EXPERIMENT_STATUS_20261018.md)。
- 最新六期新闻量试验完成3456请求，估$3.859845/$16，3454有效/2无效保留，0接口错误/重试。固定8/匹配/随机中心MAE为0.389/0.354/0.339，照抄0.369；随机相对照抄优势受月份影响，不升级默认。
- 本对话没有在跑模拟、没有待执行的新付费授权。已完成授权不得当成新实验通行证。

## 2. 有效运行包与复算入口

- 最新有效运行包：`outputs/sce_news_breadth_trial_20261019_v2/`；v1是准备失败存档，勿复用。
- 评价：`outputs/sce_news_breadth_evaluation_20261019_v1/`；汇总：`outputs/sce_news_breadth_readout_20261019_v1/`。
- 公共聚合与图：[news_breadth_results_v1](workstreams/20261018_targeted_mechanisms/news_breadth_results_v1/)，[结果说明](workstreams/20261018_targeted_mechanisms/news_breadth_results_20261019.md)。完整提示、人月、回复只在本地忽略目录。
- 共用入口：`scripts/run_sce_frozen_trial.py`；机制特定准备入口见[scripts索引](../scripts/README.md)与该批运行计划。新增机制不是自动支持，须明确适配。
- 最新汇总/作图：`scripts/report_sce_news_breadth.py`、`scripts/plot_sce_news_breadth.py`，复用已计分结果。仅需解释结果时不重复拟合Q9、不再发API。准备/评价/报告均用新输出目录，禁止覆盖。
- Python：`/Users/wushuyue/anaconda3/envs/socioverse/bin/python`。官方宿主`../socioverse2_repo/`；源码单向导出，核心只读。运行协议与版本要求见[EXPERIMENT_PIPELINE](EXPERIMENT_PIPELINE.md)。

## 3. 下一步研究及现有材料

先核采购角色对应的可见价格信息；新闻量与购物价格分开实验，避免完整宏观表让个体菜单变化失去含义。ATUS/SCE匹配、三种子菜单已备，尚未接新真实模拟。详[匹配结果](workstreams/20261018_targeted_mechanisms/atus_sce_matching_results_20261019.md)。

已有ATUS 2016/2022/2023文件和字典在`data/raw/behavior_references/2026-10-19_atus_roles_v2/`及同日supplement目录；不要重复下载。2022→2023采购角色预测支持不等于SCE预测收益；whole-residence人数、未知儿童/搬家/信息年龄按原规则保留。金融决策者不等于购物者，CE汽油支出不等于本人驾车。

先查本地食品/日用品新闻路由、候选覆盖及历史BLS细分类表，再审定菜单、完整提示、时间与主题/文字量平衡、干跑及预登记；有新付费批次再报具体范围预算。新闻随机分配保留另一次独立验证候选，不按六期真值调篇数或挑分配种子。

[财经关注文献](literature/sce/information_exposure/news_attention_demographics_20261019.md)已核8项一手材料，人口关联不能直接当个体数量定律。Kimi新[六项更新事实](workstreams/20261019_updating_facts/README.md)已交付但本线未做完整独立复核，不直接据此设置回摆系数。

## 4. 协作与保护

- 开工看git status，保留用户及其他Agent改动。`docs/sources/sol_handoff_protected_files_20261010.json`记录15项保护文件；其中DECISIONS、提案、P/计分等仍有原未审改动。**不得改写、提交、还原或混入本次提交。**未提交A/B契约亦属保护范围。
- 不动其他线`20261019_updating_facts`的代码和文档。公共页一次由一位Agent整合，不跨线程自行发消息或重复审计。
- scoped add、每批本地提交；推送另按用户授权。Git状态和本地提交不等于远端已备份。
- 源数据/历史输入/源码/冻结manifest不因整理而改写。只更新当前页对应条目，不再每轮在交接页前面堆多段“最新”快照。

本轮已完成总纲/索引、任务/交接收束及37份历史文档归档；保护及扫描到的冻结路径未变，没有新增API调用。治理记录见[整理记录](reviews/20261019_repository_cleanup/README.md)；历史资料见[归档索引](archive/2026-10/README.md)。
