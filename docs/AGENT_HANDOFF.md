# SCE 项目当前交接

更新：2026-10-20。先读[DESIGN](DESIGN.md)和[NEXT_ACTIONS](NEXT_ACTIONS.md)。本页只维护当前现场；旧运行中/待授权描述见[原文快照](reviews/20261019_repository_cleanup/README.md)，不能据其重启任务。

## 1. 当前状态

- 用户已提交开题提案，最终交付按10月31日组委会要求。时间安排只见ROADMAP；10月16—23用户繁忙的背景不改变已授权本地研究。
- 本地官方SocioVerse2引擎、真实DeepSeek回答、冻结近似Q9计分和评价链已实际运行。当前是A线回访者条件重建，使用本人真实上期信念，不是严格B自主预测。
- 12期×192×两遍主MAE 0.459/照抄0.239；分布仍过窄。全国完整波次成绩另报，不混入同支持成绩。详[配置](CURRENT_SIMULATION_CONFIGURATION.md)和[台账](EXPERIMENT_STATUS_20261018.md)。
- 最新六期新闻量试验完成3456请求，估$3.859845/$16，3454有效/2无效保留，0接口错误/重试。固定8/匹配/随机中心MAE为0.389/0.354/0.339，照抄0.369；随机相对照抄优势受月份影响，不升级默认。
- Q8单改384请求完成，全合法、估$0.4323/$2、0错误/重试；Q8分布改善，Q9中心保护门槛未过，不改默认。温度三组1152请求已完成，全合法、估$1.2875/$6、0错误/重试；Qwen迁移及一次补齐均按再次失败停止，150请求、三期已描述评价，保守估$0.201/$1，无运行中任务，详下节；此前已完成授权不得当成其他新实验通行证。

## 2. 有效运行包与复算入口

- 最新Q8有效包：`outputs/sce_q8_only_trial_20261019_v3/`；评价`outputs/sce_q8_only_evaluation_20261019_v1/`，聚合见[结果](workstreams/20261019_advisor_followup/q8_delta_results_20261019.md)。Q8完整96人月、照抄95人月、Q9为94人月；两遍不增加真人数。
- 新闻量有效运行包：`outputs/sce_news_breadth_trial_20261019_v2/`；v1是准备失败存档，勿复用。
- 评价：`outputs/sce_news_breadth_evaluation_20261019_v1/`；汇总：`outputs/sce_news_breadth_readout_20261019_v1/`。
- 公共聚合与图：[news_breadth_results_v1](workstreams/20261018_targeted_mechanisms/news_breadth_results_v1/)，[结果说明](workstreams/20261018_targeted_mechanisms/news_breadth_results_20261019.md)。完整提示、人月、回复只在本地忽略目录。
- 共用入口：`scripts/run_sce_frozen_trial.py`；机制特定准备入口见[scripts索引](../scripts/README.md)与该批运行计划。新增机制不是自动支持，须明确适配。
- 最新汇总/作图：`scripts/report_sce_news_breadth.py`、`scripts/plot_sce_news_breadth.py`，复用已计分结果。仅需解释结果时不重复拟合Q9、不再发API。准备/评价/报告均用新输出目录，禁止覆盖。
- Python：`/Users/wushuyue/anaconda3/envs/socioverse/bin/python`。官方宿主`../socioverse2_repo/`；源码单向导出，核心只读。运行协议与版本要求见[EXPERIMENT_PIPELINE](EXPERIMENT_PIPELINE.md)。

## 3. 下一步研究及现有材料

用户10月19日新方向：微观结构优先看W1/人际差异/更新，宏观组合另冻结拟权与验证；暂停默认新增DeepSeek。Qwen同输入迁移及一次人工补齐已停止并完成可评价三期：150请求/148回包/2连接错误，费用保守估$0.201/$1；三期144份中139份Q9合法。Q9中心MAE DeepSeek1.563/Qwen1.644，W1 2.748/2.868，IQR 1.866/1.651（真人5.791），未显示整体改善。2022-03未完成排除，无任务运行、不再补发，不升级默认。 详[本批结果](workstreams/20261019_advisor_followup/qwen_migration_results.md)。

原始包`outputs/sce_qwen_migration_trial_20261019_v1/`及一次人工补齐`outputs/sce_qwen_completion_trial_20261019_v2/`均为停止现场。用户明确授权一次补齐后又遇连接错误；不再请求/触发自动补发。原75＋补齐75=150请求；完整202004/202105/202111共72人月×2，202203部分原答保留、整月不入评价。144回答5份Q9和不合法（105三份、99两份），共同Q9为65人月、Q8为72，不归一化。供应商报告$0.191888，失败计费未知，保守使用量估$0.200809。无运行中任务或待执行授权。

只读评价范围`outputs/sce_qwen_partial_scope_20261019_v1/`，评价`outputs/sce_qwen_migration_evaluation_20261019_v1/`；共享评价器按完整月份复用原收据，不改旧manifest。复算用`evaluate_sce_model_migration.py --folder ... --scope outputs/<fresh_scope> --out outputs/<fresh_eval>`。`report_sce_model_migration.py`只读缓存，公开两图/分组/费用在workstream的`qwen_migration_results_v1/`，阅读页#qwen-migration-results-20261019。原授权前readiness是历史状态。

最新官方免费证据`data/raw/mcp_checks/2026-10-19_qwen_migration_v1/`仍只登记gpt-4o-mini，未确认同输入接口；不发付费问卷。Qwen完整知识截止和托管权重修订未核实。冻结源码副本在`outputs/sce_shared_runtime_snapshot_20261019_qwen_v1/`、`outputs/sce_shared_runtime_snapshot_20261019_qwen_before_completion_v1/`。补齐v1是prepare残留0调用，勿复用。当前没有一项模型替换被升级默认，后续回到采购角色—可见价格离线准备。

温度对照完成，运行包`outputs/sce_temperature_trial_20261019_v1/`，评价`outputs/sce_temperature_evaluation_20261019_v1/`。四旧开发月24人、三组×4遍，共1152请求，全合法，估$1.2875/$6，0错误/重试，调用398.1秒。Q9中心0.5/0.8/1.0为1.037/1.032/1.047、W1 2.665/2.420/2.505；照抄0.730/1.784。主1.0比较区间跨0、未过预定筛选；0.8仅保留辅助W1信号，参考温度仍0.5。Q9人内重复方差0.315→0.915，修正跨人方差2.567→2.801，未解决同质化。[结果](workstreams/20261019_advisor_followup/temperature_results_20261019.md)。

本批复算须用`evaluate_sce_temperature.py --folder ... --out outputs/<fresh>`：旧真人缓存只有两遍索引，新增评价层适配先核同人同月192个缓存键一致，再映射到4遍384键；96个真人事实数不变，没有修改真值、原答、源码pin或manifest，没有新API。适配收据与哈希在评价目录及公共费用收据。原共用evaluate缺此索引适配；不要为修复重跑模拟。`report_sce_temperature.py`只读缓存作图。共用三入口修改前副本见`outputs/sce_shared_runtime_snapshot_20261019_temperature_v1/`，旧Q8复算用对应冻结版本。

10月19日[网格/Q8预检](workstreams/20261019_advisor_followup/diagnostic_results.md)已完成。权威输出为`outputs/sce_advisor_diagnostic_20261019_v2/`，v1是分位数/旧运行精度对齐前草稿，勿引用。公开聚合与四图见同workstream的`diagnostic_readout_v1/`；复算入口`analyze_sce_advisor_diagnostics.py`，9项测试通过。十二期主结果对账一致；九格中五格全期有支持，约89%方差缺口在格内。旧Q9失败的74份Q8全部恢复，两臂Q8均192/192合法；两遍中心排序反转，不升级参考配置。

平台仅完成免费元数据回查，证据`data/raw/mcp_checks/2026-10-19_advisor_free_v1/`；仍登记gpt-4o-mini，未确认自带逐人P/E/先验或模型选择，不运行问卷。

[Q8单改](workstreams/20261019_advisor_followup/q8_delta_results_20261019.md)已完成真实批次。四旧开发月各24人、直接/q8_delta两臂各两遍，384请求；Q9都填绝对概率。估算$0.4323、上限$2，全有效、0错误/重试；调用跨度129.5秒、评价12.4秒。Q8等人中心0.788→0.613、W1 4.392→3.126（差区间低于0），IQR 1.488→2.850／真人4.500；Q9调查权重敏感性中心1.012→1.037、W1 2.162→1.940，中心点值门槛未过，不升级。原16干跑/384转换/23测试仍保留。v1/v2为未调用准备残留，禁止复用；旧manifest未改。共享三入口修改前副本在`outputs/sce_shared_runtime_snapshot_20261019_q8_v1/`，旧批次需用原冻结源码，不能改manifest绕过。图文脚本`report_sce_q8_delta.py`只读缓存，不重新调用。

[人口六格草案](workstreams/20261019_advisor_followup/stratification_draft.md)为学历×是否在职，63/72格月达到初步支持；未知独立池。支持与192人分配示例在`outputs/sce_stratification_support_20261019_v1/`。尚未实际抽样、改旧P或接新Normal，年龄/收入边际与财务/数理另作诊断。本轮Q8用旧样本，不同时换网格。相关指标扩展仍先评估Q2。

采购角色—可见价格本轮已落实为[六期完整离线提示](workstreams/20261020_procurement/README.md)：有效包`outputs/sce_procurement_price_views_20261020_v3/`，576个人月×三组×三种子共5184提示；v1因平衡失败停止，v2是共享加载格式对齐前草稿，均0调用。解析6份已有首发PDF共60项，食品6类用于角色视图，清洁/纸品/护理仅储备。原固定8新闻/先验/问卷不变，三组共同移除完整统计表；新共同背景不能复用旧回答。匹配/打乱交换整套角色/类别，接收者时间标签重算；权重排序约12人块内受限随机，18项平衡均通过，不能说无限制随机。共享加载54文件及8测试通过，尚未引擎干跑或付费。脚本`prepare_sce_procurement_views.py`，模块`procurement_price_views.py`。没有改旧源文件/manifest、默认模型或配置。

今日官方免费回查成功，证据`data/raw/mcp_checks/2026-10-20_procurement_free_v1/evidence.json`，user_pool_mcp1.27.0，实际gpt-4o-mini，别名GPT=gpt-4o-2024-08-06不能等同执行模型；逐人同输入/模型选择仍未明确。要求与未发送询问草稿见[GPT接入](workstreams/20261020_procurement/platform_gpt_requirements.md)。无新付费调用或运行任务；下一步先确认通道，再引擎干跑/冻结一批种子和预算。新增全部study文件没有改旧在册入口；旧运行继续用原冻结源。

已有ATUS 2016/2022/2023文件和字典在`data/raw/behavior_references/2026-10-19_atus_roles_v2/`及同日supplement目录；不要重复下载。2022→2023采购角色预测支持不等于SCE预测收益；whole-residence人数、未知儿童/搬家/信息年龄按原规则保留。金融决策者不等于购物者，CE汽油支出不等于本人驾车。

本地路由补查与BLS分类表解析已完成，不重复抓取。食品角色只说明采购分工，不识别本人价格；0/1/3/6/6可见条数是实验假设，不能按结果反选。六期仍是开发期，尚未登记独立验证月份。新闻随机分配保留独立验证候选，不按六期真值调篇数或挑分配种子。

[财经关注文献](literature/sce/information_exposure/news_attention_demographics_20261019.md)已核8项一手材料，人口关联不能直接当个体数量定律。Kimi新[六项更新事实](workstreams/20261019_updating_facts/README.md)已交付但本线未做完整独立复核，不直接据此设置回摆系数。

## 4. 协作与保护

- 开工看git status，保留用户及其他Agent改动。`docs/sources/sol_handoff_protected_files_20261010.json`记录15项保护文件；其中DECISIONS、提案、P/计分等仍有原未审改动。**不得改写、提交、还原或混入本次提交。**未提交A/B契约亦属保护范围。
- 不动其他线`20261019_updating_facts`的代码和文档。公共页一次由一位Agent整合，不跨线程自行发消息或重复审计。
- scoped add、每批本地提交；推送另按用户授权。Git状态和本地提交不等于远端已备份。
- 源数据/历史输入/源码/冻结manifest不因整理而改写。只更新当前页对应条目，不再每轮在交接页前面堆多段“最新”快照。

本轮已完成总纲/索引、任务/交接收束及37份历史文档归档；保护及扫描到的冻结路径未变，没有新增API调用。治理记录见[整理记录](reviews/20261019_repository_cleanup/README.md)；历史资料见[归档索引](archive/2026-10/README.md)。
