# SCE 项目当前交接

更新：2026-10-19。先读[DESIGN](DESIGN.md)和[NEXT_ACTIONS](NEXT_ACTIONS.md)。本页只维护当前现场；旧运行中/待授权描述见[原文快照](reviews/20261019_repository_cleanup/README.md)，不能据其重启任务。

## 1. 当前状态

- 用户已提交开题提案，最终交付按10月31日组委会要求。时间安排只见ROADMAP；10月16—23用户繁忙的背景不改变已授权本地研究。
- 本地官方SocioVerse2引擎、真实DeepSeek回答、冻结近似Q9计分和评价链已实际运行。当前是A线回访者条件重建，使用本人真实上期信念，不是严格B自主预测。
- 12期×192×两遍主MAE 0.459/照抄0.239；分布仍过窄。全国完整波次成绩另报，不混入同支持成绩。详[配置](CURRENT_SIMULATION_CONFIGURATION.md)和[台账](EXPERIMENT_STATUS_20261018.md)。
- 最新六期新闻量试验完成3456请求，估$3.859845/$16，3454有效/2无效保留，0接口错误/重试。固定8/匹配/随机中心MAE为0.389/0.354/0.339，照抄0.369；随机相对照抄优势受月份影响，不升级默认。
- Q8单改384请求完成，全合法、估$0.4323/$2、0错误/重试；Q8分布改善，Q9中心保护门槛未过，不改默认。温度三组1152请求已完成，全合法、估$1.2875/$6、0错误/重试；当前无运行中任务或待执行付费批次。已完成授权不得当成新实验通行证。

## 2. 有效运行包与复算入口

- 最新Q8有效包：`outputs/sce_q8_only_trial_20261019_v3/`；评价`outputs/sce_q8_only_evaluation_20261019_v1/`，聚合见[结果](workstreams/20261019_advisor_followup/q8_delta_results_20261019.md)。Q8完整96人月、照抄95人月、Q9为94人月；两遍不增加真人数。
- 新闻量有效运行包：`outputs/sce_news_breadth_trial_20261019_v2/`；v1是准备失败存档，勿复用。
- 评价：`outputs/sce_news_breadth_evaluation_20261019_v1/`；汇总：`outputs/sce_news_breadth_readout_20261019_v1/`。
- 公共聚合与图：[news_breadth_results_v1](workstreams/20261018_targeted_mechanisms/news_breadth_results_v1/)，[结果说明](workstreams/20261018_targeted_mechanisms/news_breadth_results_20261019.md)。完整提示、人月、回复只在本地忽略目录。
- 共用入口：`scripts/run_sce_frozen_trial.py`；机制特定准备入口见[scripts索引](../scripts/README.md)与该批运行计划。新增机制不是自动支持，须明确适配。
- 最新汇总/作图：`scripts/report_sce_news_breadth.py`、`scripts/plot_sce_news_breadth.py`，复用已计分结果。仅需解释结果时不重复拟合Q9、不再发API。准备/评价/报告均用新输出目录，禁止覆盖。
- Python：`/Users/wushuyue/anaconda3/envs/socioverse/bin/python`。官方宿主`../socioverse2_repo/`；源码单向导出，核心只读。运行协议与版本要求见[EXPERIMENT_PIPELINE](EXPERIMENT_PIPELINE.md)。

## 3. 下一步研究及现有材料

温度对照完成，运行包`outputs/sce_temperature_trial_20261019_v1/`，评价`outputs/sce_temperature_evaluation_20261019_v1/`。四旧开发月24人、三组×4遍，共1152请求，全合法，估$1.2875/$6，0错误/重试，调用398.1秒。Q9中心0.5/0.8/1.0为1.037/1.032/1.047、W1 2.665/2.420/2.505；照抄0.730/1.784。主1.0比较区间跨0、未过预定筛选；0.8仅保留辅助W1信号，参考温度仍0.5。Q9人内重复方差0.315→0.915，修正跨人方差2.567→2.801，未解决同质化。[结果](workstreams/20261019_advisor_followup/temperature_results_20261019.md)。

本批复算须用`evaluate_sce_temperature.py --folder ... --out outputs/<fresh>`：旧真人缓存只有两遍索引，新增评价层适配先核同人同月192个缓存键一致，再映射到4遍384键；96个真人事实数不变，没有修改真值、原答、源码pin或manifest，没有新API。适配收据与哈希在评价目录及公共费用收据。原共用evaluate缺此索引适配；不要为修复重跑模拟。`report_sce_temperature.py`只读缓存作图。共用三入口修改前副本见`outputs/sce_shared_runtime_snapshot_20261019_temperature_v1/`，旧Q8复算用对应冻结版本。

10月19日[网格/Q8预检](workstreams/20261019_advisor_followup/diagnostic_results.md)已完成。权威输出为`outputs/sce_advisor_diagnostic_20261019_v2/`，v1是分位数/旧运行精度对齐前草稿，勿引用。公开聚合与四图见同workstream的`diagnostic_readout_v1/`；复算入口`analyze_sce_advisor_diagnostics.py`，9项测试通过。十二期主结果对账一致；九格中五格全期有支持，约89%方差缺口在格内。旧Q9失败的74份Q8全部恢复，两臂Q8均192/192合法；两遍中心排序反转，不升级参考配置。

平台仅完成免费元数据回查，证据`data/raw/mcp_checks/2026-10-19_advisor_free_v1/`；仍登记gpt-4o-mini，未确认自带逐人P/E/先验或模型选择，不运行问卷。

[Q8单改](workstreams/20261019_advisor_followup/q8_delta_results_20261019.md)已完成真实批次。四旧开发月各24人、直接/q8_delta两臂各两遍，384请求；Q9都填绝对概率。估算$0.4323、上限$2，全有效、0错误/重试；调用跨度129.5秒、评价12.4秒。Q8等人中心0.788→0.613、W1 4.392→3.126（差区间低于0），IQR 1.488→2.850／真人4.500；Q9调查权重敏感性中心1.012→1.037、W1 2.162→1.940，中心点值门槛未过，不升级。原16干跑/384转换/23测试仍保留。v1/v2为未调用准备残留，禁止复用；旧manifest未改。共享三入口修改前副本在`outputs/sce_shared_runtime_snapshot_20261019_q8_v1/`，旧批次需用原冻结源码，不能改manifest绕过。图文脚本`report_sce_q8_delta.py`只读缓存，不重新调用。

[人口六格草案](workstreams/20261019_advisor_followup/stratification_draft.md)为学历×是否在职，63/72格月达到初步支持；未知独立池。支持与192人分配示例在`outputs/sce_stratification_support_20261019_v1/`。尚未实际抽样、改旧P或接新Normal，年龄/收入边际与财务/数理另作诊断。本轮Q8用旧样本，不同时换网格。相关指标扩展仍先评估Q2。

采购角色对应的可见价格信息保留为已准备方向；新闻量与购物价格分开实验，避免完整宏观表让个体菜单变化失去含义。ATUS/SCE匹配、三种子菜单已备，尚未接新真实模拟。详[匹配结果](workstreams/20261018_targeted_mechanisms/atus_sce_matching_results_20261019.md)。

已有ATUS 2016/2022/2023文件和字典在`data/raw/behavior_references/2026-10-19_atus_roles_v2/`及同日supplement目录；不要重复下载。2022→2023采购角色预测支持不等于SCE预测收益；whole-residence人数、未知儿童/搬家/信息年龄按原规则保留。金融决策者不等于购物者，CE汽油支出不等于本人驾车。

先查本地食品/日用品新闻路由、候选覆盖及历史BLS细分类表，再审定菜单、完整提示、时间与主题/文字量平衡、干跑及预登记；有新付费批次再报具体范围预算。新闻随机分配保留另一次独立验证候选，不按六期真值调篇数或挑分配种子。

[财经关注文献](literature/sce/information_exposure/news_attention_demographics_20261019.md)已核8项一手材料，人口关联不能直接当个体数量定律。Kimi新[六项更新事实](workstreams/20261019_updating_facts/README.md)已交付但本线未做完整独立复核，不直接据此设置回摆系数。

## 4. 协作与保护

- 开工看git status，保留用户及其他Agent改动。`docs/sources/sol_handoff_protected_files_20261010.json`记录15项保护文件；其中DECISIONS、提案、P/计分等仍有原未审改动。**不得改写、提交、还原或混入本次提交。**未提交A/B契约亦属保护范围。
- 不动其他线`20261019_updating_facts`的代码和文档。公共页一次由一位Agent整合，不跨线程自行发消息或重复审计。
- scoped add、每批本地提交；推送另按用户授权。Git状态和本地提交不等于远端已备份。
- 源数据/历史输入/源码/冻结manifest不因整理而改写。只更新当前页对应条目，不再每轮在交接页前面堆多段“最新”快照。

本轮已完成总纲/索引、任务/交接收束及37份历史文档归档；保护及扫描到的冻结路径未变，没有新增API调用。治理记录见[整理记录](reviews/20261019_repository_cleanup/README.md)；历史资料见[归档索引](archive/2026-10/README.md)。
