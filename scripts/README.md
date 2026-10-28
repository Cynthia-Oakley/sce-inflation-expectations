# 脚本入口索引

- `analyze_sce_downstream_regression.py --panel <月度面板> --a <A全国序列> --b <B全国序列> --protocol <冻结协议> --out outputs/<新目录>`：按 ConsumerSim Appendix B 的适配方案，对工资、耐用品、循环信贷和 MICH 做未来 1—3 个月回归；包含持续性、历史均值、AR(1)、领域 ARX、官方/模拟/组合 SCE 对照，导出全部逐月预测、样本内外指标、配对对照、图和 HTML。A 仅用当时已形成标签扩展训练，B 冻结 A 系数；0 Simulation/LLM，不插值、不覆盖输出。结果与复算见[下游工作目录](../docs/workstreams/20261026_downstream/README.md)。

- `prepare_sce_downstream_data.py --raw-root outputs/sce_downstream_data_20261026_v1 --out outputs/sce_downstream_data_20261026_v1/derived_replay`：只读核验下游第一阶段公开原始文件哈希并合并月度面板；不联网、不插补、不调用 LLM，拒绝覆盖非空输出目录。范围与证据见[下游工作目录](../docs/workstreams/20261026_downstream/README.md)。

- `evaluate_sce_recent_b_core_normal.py --prediction outputs/<sealed_B_expansion> --out outputs/<fresh>`：在封存1300代理/τ8预测之后，仅计算全国MAE/RMSE/bias及同权组合/固定宏观模型迁移敏感性；不重新拟参、API或Q9拟合，不评价缺失的近期真人微观W1/IQR。

- `expand_sce_recent_b_core_normal.py --target-n 1300 --out outputs/<fresh>`：仅离线消费新版B实际Core，按固定A τ8扩至声明的1300代理（也支持1200）；Core保留旧源原始质量，Normal只积分余量，统一缩放不改变CDF。0API/0新Q9拟合、不读近期真人目标、不做准确性评价。产物含精确原子分布及检查用Normal人口行，见[方法](../docs/workstreams/20261026_b_core_normal/README.md)。

- `run_sce_recent_b_sampled.py prepare/review/run/watch`：消费已通过完整11期Core的冻结个人日期B提示；复用full-A容错队列、独立后台、一次技术补跑及隔离全国/固定组合评价。主补总帽$8，实际启动须有新包明确授权；`--resume`只续从未尝试位置，已生成完成不再调用。见[运行说明](../docs/workstreams/20261026_response_dates/B_TERMINAL_RUNBOOK_20261026.md)。

更新：2026-10-19。按用途导航，**不表示所有入口都适用于当前配置**。以下根据现有文件名及原docstring整理；日期和实验参数以对应workstream/冻结运行包为准，不能凭脚本名直接启动付费调用。

## 优先使用的入口

- `analyze_sce_dynamic_fair_benchmark.py --out outputs/<新目录>`：在旧结果外另加月末可得SCE/CPI宏观对照，固定早24月选参规则并更新到2025-10，检查匹配模拟增量；不改正式as_of或原预测。`report_sce_dynamic_model_presentation.py --source <分析目录> --out docs/workstreams/<新目录>`说明ARX/MA/差分边界与主辅呈现，另列48/34简单组合的时点敏感性。
- `analyze_sce_observable_inflation_trigger.py --out outputs/<新目录>`：同一月末对照下验证相邻锚、形成真正差分，用23期初始历史确定价格触发器，完整比较8家族的固定/按公布日更新预测；不按2021调阈值。`report_sce_observable_inflation_trigger.py --source <分析目录> --out docs/workstreams/<新目录>`生成信号、预测与配对增量三图；详见[本轮说明](../docs/workstreams/20261026_observable_trigger/README.md)。
- `prepare_sce_recent_b_review.py --out outputs/<新目录>`：只读核验B新版新闻候选，输出逐月人口/历史锚/先验/已发布CPI清单和A数据固定的组合、宏观配对参数，不解析B目标值、不创建授权或发送器。`report_sce_recent_b_review.py --source <材料目录> --out docs/workstreams/<新目录>`生成运行前配置审阅页；它们都不是付费运行入口。
- `analyze_sce_response_date_distribution.py --out outputs/<新目录>`：只用日期/权重元数据比较均匀、前一年同月、可得6月和最多3年同月；按B滞后规则限定历史来源，另查11期新闻档的每日范围与基础标签缺口。`report_sce_response_date_distribution.py --source <分析目录> --out docs/workstreams/<新目录>`生成日期分布、日期误差与CPI可见比例图；0API，不改B的D或提示。
- `prepare_sce_recent_b_sampled_dates.py dates --lag-months 12 --out outputs/<新目录>`：用户已确认的前一年同月日期映射，固定种子并封顶原全局D；`assemble --date-plan <日期目录> --repair-manifest <修复manifest> --out outputs/<新目录>`按个人日期重建E和冻结消息，原文覆盖缺口先阻断。可用`--months`做明确标记的工程子集；无paid run子命令。
- `inventory_sce_recent_b_news_repairs.py --out outputs/<新目录> [--repair-manifest <新修复清单>]`：只读查Jan/Feb/Sep三个窗口并导出公开去重待分类JSONL；输出原文覆盖与主题标签缺口，不下载/分类/模拟。修复overlay结构见[接口schema](../docs/workstreams/20261026_response_dates/news_repair_manifest.schema.json)。
- `repair_sce_recent_b_news.py fetch-january`：重新核查后按日分页补抓2026-01 NYT官方原文，逐页保存并支持续跑；另存转换合并快照，不覆盖canonical月档。`run_sce_recent_b_news_labels.py prepare/execute`只处理明确导出的增量公开候选，沿用slim4与DeepSeek Flash；execute需显式确认，不是Simulation入口。`finalize_sce_recent_b_news_repair.py source-audit/write-manifest/accept`分别做来源对账、绑定overlay和最终库存验收。详[修复说明](../docs/workstreams/20261026_response_dates/NEWS_REPAIR_IMPLEMENTATION_20261026.md)。

- `analyze_sce_scoring_measurement_bridge.py --out outputs/<新目录>`：同人同权重分离官方个人密度、本地冻结评分、支持样本、chart/首发，另验Cox聚合候选；0API/0新拟合。`analyze_sce_anomaly_year_calibration.py --out outputs/<新目录>`：2020年底前18/6选参、全年固定与按实际公布标签逐月更新的2021对照。`report_sce_measurement_anomaly.py --measurement <对账目录> --anomaly <2021目录> --out docs/workstreams/<新报告目录>`生成三图。

- `analyze_sce_full_a_macro_calibration.py --out outputs/<新目录>`：核官方全国目标/共同计分桥接，复算Core和τ8扩展凸组合，按36/12/34时间安排探索CPI/状态/交叉项岭回归，保留不含模拟对照；0API，不改原预测。`report_sce_full_a_macro_calibration.py --source <分析目录> --out docs/workstreams/<新目录>`生成解释与图表。

- `analyze_sce_full_a_core_normal_tau.py --out outputs/<新目录>`：只读已有T0人口/模型缓存，扩大τ搜索并按早48月全国Q9 MAE监督校准，封存选择后检查后34月；0API/0密度重拟，不替换原τ8结果。`report_sce_full_a_core_normal_tau.py --source <分析目录> --out docs/workstreams/<新报告目录>`生成训练曲线与时期对照。

- `readout_sce_recent_b.py --run-dir <已完成B运行> --catalog <评价专用首发目录> --score-cache <精确向量缓存> --out outputs/<新目录>`：先查目标月份与账本哈希，再离线评价全国及描述性分组；不创建发送器、不读密钥、不调用模型。`report_sce_recent_b.py --source <分析目录> --out docs/reports/<新目录>`生成图文、CSV与Canvas，私有答卷不进入阅读页。详[近期B结果与复算](../docs/workstreams/20261025_recent_b/results.md)。

- `analyze_sce_2021_environment_blend.py --out outputs/<新目录>`：核对2021年实际请求与原模板、食品原始来源与登记日期，分析真实相邻回访者，并重算全期/后期事后凸组合、核对冻结48/34月评价；0API、0密度拟合，不改变主配置。详[2021专项](../docs/workstreams/20261024_fullperiod_analysis/2021_environment_and_blend.md)。

- `analyze_sce_fullperiod_run.py --out outputs/<新目录>`：按冻结A82来源重用已计分回答，核对逐月指标、统计时期/分组/更新/54格方差、描述性历史/模拟增量回归；0API、0密度重拟合。`report_sce_fullperiod_run.py --source <分析目录> --out docs/reports/<新目录>`生成六图与HTML，并复核组合与剩余缺失中位数包络；不调整配置。详[结果与复算](../docs/workstreams/20261024_fullperiod_analysis/results.md)。

- `run_sce_monthly_repair_followup.py prepare/run/watch`：首轮补齐后残余6份的一次后续补跑，复用既有监督/队列/评价，保留成功字段和三轮raw来源；6新调用上限$0.04计入原$40，用户Terminal确认启动，旧源码/结果不改。详[命令](../docs/workstreams/20261023_main_run/technical_repair_20261024.md#六份残余的一次后续补跑)。

- `run_sce_monthly_repair.py prepare/run/watch`：完整主运行后的361份技术失败一次人工补齐；精确复用提示，保留成功字段，原/新raw账本分开，逐字段覆盖后独立评价。`run --confirm-one-time-repair`由用户Terminal启动，额外费用计入原总上限；不是重跑整批或重复加权人口。详[补跑说明](../docs/workstreams/20261023_main_run/technical_repair_20261024.md)。

- `render_sce_mechanism_guide.py`：从现有冻结候选与说明内容生成`docs/project_guide.html`、分章节JSON和Canvas源；仅说明机制，不重拟合Q9或调用模型，用户审阅后再决定运行。

- `prepare_sce_monthly_fine_inputs.py`、`prepare_sce_monthly_fine_pipeline.py`：54格512人、近期初始化、既有完整提示与官方Core离线验线；支持复用完整提示，不调用API。
- `run_sce_monthly_main_pipeline.py`：默认预览；精确授权后才`--execute`，一命令逐月生成→独立进程微观评价→完整波次/全国组合；停止不自动重启。
- `manage_sce_monthly_main.py prepare/start/status`：原生Terminal后台管理上述管线，10秒本地进度、独立会话及Mac防空闲睡眠；prepare/status零API、start需已有精确授权；不自动续跑或重发，详[夜间说明](../docs/workstreams/20261023_main_run/overnight_runbook.md)。
- `evaluate_sce_monthly_reconstruction.py prepare-truth --score-cache <旧兼容真值目录>`：隔离投影当前真值，只补缺少的冻结Q9向量；`readout_sce_monthly_main.py`复用共同指标/凸组合算法，后期真值不拟合早期权重。当前配置见[全量前说明](../docs/workstreams/20261023_main_run/README.md)。
- 以下Core＋Normal入口保留为未来扩展工具，按10月23日晚用户共识不用于本次缺失先验或新人代答。
- `expand_sce_core_normal.py --population <P> --core <名册> --answers <已计分Core> --tau <强度> --out outputs/<新目录>`：有限人口Core保留＋Normal联合答卷经验收缩与概率积分；无API/真值读取/Q9新拟合，不等于已接入全量主运行。
- `validate_sce_core_normal.py`、`validate_sce_core_normal_cached.py`：82月真人Core统计参照与旧V3.2小框架留出，均零API；两种分数不可混称LLM最终拟合成绩。
- `prepare_sce_core_normal_pilot.py`、`report_sce_core_normal.py`：准备三期256Core＋64审计名册、生成冻结聚合图文；尚需完整历史/P/E提示、预算和新授权。
- `prepare_sce_core_normal_scale_pilot.py`、`report_sce_core_normal_scale.py`：准备三期256/384/512共用Core＋共同留出审计名册，读取既有82月结果生成成本—精度图文；不调用API，不将理想真人Core误差当LLM拟合成绩。最终规模未定。
- `analyze_sce_grid_dimensions.py`：八类人口特征的关联/GVIF/MCA、三/四维126候选和受访者/时间检查，评价层零API，不改模拟配置。
- `analyze_sce_grid_joint_holdout.py`、`analyze_sce_grid_sensitivity.py`：同一真人Core的联合格留出、覆盖门槛及Q8保护敏感性；不是新的LLM实验或生产Bayes扩展。
- `analyze_sce_grid_oversampling.py --out outputs/<新目录>`：仅从人口/权重比较12/36/54细格的保底过采样、实际抽中概率和比例校准；不读取问卷答案、不新增API，尚未接生产Normal。
- `report_sce_grid_dimensions.py --source <选择目录> --joint <联合目录> --sensitivity <敏感性目录> --out <新报告目录>`：读取聚合生成图文；不重拟合问卷或调用API。
- `materialize_sce_fullperiod.py --out outputs/<新目录> --stage all`：复用现有缓存补全93月P/E，可用`--months`限定；无LLM调用，近期合成不自动取得严格B资格。
- `complete_sce_policy_sources.py --delivery outputs/<物化目录>`：补公开美联储/Gallup材料并记录原文、日期和哈希，无付费API。
- `prepare_sce_monthly_reconstruction.py` → `assemble_sce_monthly_reconstruction.py` → `run_sce_monthly_reconstruction.py prepare`：正常月度六格/近期信念/完整提示/官方Core干跑/执行封存；付费运行必须另有明确授权。

- [run_sce_frozen_trial.py](run_sce_frozen_trial.py)：共用prepare / dry-run / run / worker / evaluate。已接Q8单改、温度三组及单一Qwen/OpenRouter迁移适配（固定供应商、复用旧对照），另支持采购角色的仅工程验收包（禁付费/研究计分）；旧协议仍用原标量温度。新增机制须有适配器及冻结配置，真实调用另需有效授权。
- [prepare_sce_news_breadth_trial.py](prepare_sce_news_breadth_trial.py)：最新已完成新闻量三组试验的准备入口；不要重启旧包。
- [prepare_sce_state_continuity_inputs.py](prepare_sce_state_continuity_inputs.py)：复用现有构建器组装本地E、过去信念及家庭字段，零API，新目录保存。
- [prepare_sce_state_continuity_prompts.py](prepare_sce_state_continuity_prompts.py)：组装动态状态模板并作确定性接续回放，不生成模型结果。
- [check_sce_state_continuity_core.py](check_sce_state_continuity_core.py)：复用frozen_batch.worker执行官方Core零API验收，独立记录检查与源码副本。
- [prepare_sce_state_continuity.py](prepare_sce_state_continuity.py)：从物化P和历史信念准备三月固定名单/状态依赖，不读取本期真值，不调用API；产物明确尚未prompt-ready。
- [run_sce_state_continuity.py](run_sce_state_continuity.py)：冻结/授权/单次启动三月动态状态队列，复用SCEOpenAILLM，按月接续、逐槽日志及在途费用预占；不会自动重试或重启。
- [evaluate_sce_state_continuity.py](evaluate_sce_state_continuity.py)：独立真值投影与缓存评价，复用冻结Q9/分位数/W1，Q8/Q9独立、基线覆盖单列。
- [continue_sce_state_continuity.py](continue_sce_state_continuity.py)：仅在人工确认后续跑从未发送的状态位置，保留全部旧尝试及失败；源差异和不可改写的两段账本单独登记，原总预算不变。
- [report_sce_state_continuity.py](report_sce_state_continuity.py)：读取完成缓存生成既有风格的三月接续图文，不调用API或重拟合密度。
- [prepare_sce_news_matching.py](prepare_sce_news_matching.py)：V3.2八期数量/主题四组离线准备与精确旧答复用；逐人提示相同则引用同一次调用，不重复发送。配置、预算和授权须按新批冻结。
- [prepare_sce_news_matching_truth.py](prepare_sce_news_matching_truth.py)、[evaluate_sce_news_matching.py](evaluate_sce_news_matching.py)：独立真值投影、共享计分及固定人群上期后备评价；不是新模拟器。自动流程登记`news_matching`，旧批默认不变。
- [finalize_sce_news_matching_evaluation.py](finalize_sce_news_matching_evaluation.py)：本轮缓存导出恢复，过去Q8缺失时另作合法上期的Q8照抄对照；保留原Q9计分和所有有效模型Q8，0API/0密度重拟合。
- [read_sce_news_matching.py](read_sce_news_matching.py)、[report_sce_news_matching.py](report_sce_news_matching.py)：从八期四组完成缓存生成加权/分组/时期/每遍读数和既有风格HTML；链式汇总断网前后唯一调用与费用，禁止重启旧付费包。
- [prepare_sce_media_mechanism_v3.py](prepare_sce_media_mechanism_v3.py)、[run_sce_media_mechanism_v3.py](run_sce_media_mechanism_v3.py)、[evaluate_sce_media_mechanism_v3.py](evaluate_sce_media_mechanism_v3.py)、[audit_sce_media_mechanism_v3.py](audit_sce_media_mechanism_v3.py)：七个月新闻路由/四档容量/警示/Fox/CPI五组对照的准备、官方Core干跑、授权运行、只续未启动任务、哈希验收及A82评价；真实模拟必须另行批准，不沿用补标授权。
- [prepare_sce_fox_news.py](prepare_sce_fox_news.py)、[prepare_sce_fox_mechanism_labels.py](prepare_sce_fox_mechanism_labels.py)、[refresh_sce_fox_english.py](refresh_sce_fox_english.py)：Fox公开sitemap/Wayback与旧样本英文原文准备、六字段补标包；不生成理由或证据摘录，补标和模拟分别授权。
- [prepare_sce_news_mechanism_labels.py](prepare_sce_news_mechanism_labels.py)、[run_sce_news_mechanism_labels.py](run_sce_news_mechanism_labels.py)：公开新闻tone/persistence或slim4+机制字段补标与累计预算账本；失败不自动重试，resume只续从未请求的批次。
- [report_sce_news_breadth.py](report_sce_news_breadth.py)、[plot_sce_news_breadth.py](plot_sce_news_breadth.py)：基于已有评价缓存汇总/作图，不再发API。
- [prepare_sce_personal_information.py](prepare_sce_personal_information.py)、[prepare_sce_personal_information_views.py](prepare_sce_personal_information_views.py)：ATUS/SCE角色与菜单的离线准备，不等于真实模拟入口已接通。
- [prepare_sce_procurement_views.py](prepare_sce_procurement_views.py)：六期食品采购角色—价格视图离线准备，复用首发PDF、匹配/打乱及完整提示；不发API，不是付费运行入口。
- [evaluate_sce_outputs.py](evaluate_sce_outputs.py)：统一规范包评价，旧批次须遵守其计分版本和支持定义。
- [run_sce_automatic_pipeline.py](run_sce_automatic_pipeline.py)：一次运行已经明确授权的冻结队列，完成后自动评价；不创建授权、不重试或重启。已注册新四期2025的同支持基线/方差评价配置，真实状态以唯一账本为准。
- [read_sce_post2025_validation.py](read_sce_post2025_validation.py)、[analyze_sce_post2025_support.py](analyze_sce_post2025_support.py)、[report_sce_post2025_validation.py](report_sce_post2025_validation.py)：从新四期既有计分缓存读取设计加权指标、检查缺失支持敏感性并生成图文，不调用API或重新拟合Q9。正式本批读数见readout v2，不将通用评价器等权字段与加权基线混比。
- [prepare_sce_post2025_validation.py](prepare_sce_post2025_validation.py)、[evaluate_sce_post2025_validation.py](evaluate_sce_post2025_validation.py)：新增2025月P/新闻离线准备与实际回答评价；完整提示仍走共用`run_sce_frozen_trial.py prepare`的明确协议适配。
- [render_current_todo.py](render_current_todo.py)：从当前任务板生成固定路径`docs/current_todo.html`。
- [prepare_sce_entry_initialization.py](prepare_sce_entry_initialization.py)：近期供体、联合Q8/Q9、上期中位数软约束的零API预检；82期数量覆盖与三月96/512支持检查，不是模型重跑。输出必须为新目录。
- [prepare_sce_entry_pilot.py](prepare_sce_entry_pilot.py)：从已封存全期输入准备三期24新人＋24真实回访者、两遍288请求的小试；逐字复用提示并完成官方Core离线检查，真实调用需单独授权。
- [evaluate_sce_entry_pilot.py](evaluate_sce_entry_pilot.py)：隔离抽取已有真值/计分缓存，分别评价新人和回访者的中心、分布及两遍敏感性；不把两组差额解释为初始化因果效果。
- [prepare_sce_entry_pilot_continuation.py](prepare_sce_entry_pilot_continuation.py)：仅针对15有效回包＋1连接失败的明确人工例外，封存272个未发送位置；复用既有续跑队列，失败和成功均不重发。
- [report_sce_entry_pilot.py](report_sce_entry_pilot.py)：从已完成评价缓存生成既有风格的新人/回访者图文，Q8、共同支持、失败和成本分开说明，不产生API调用。
- [analyze_sce_entry_share.py](analyze_sce_entry_share.py)：复用82月人口权重及新人小试缓存，计算实际新人占比和仅评价用理想替换敏感性；不拟合新模型、不改P/E，不把混合小样本误差称全国成绩。
- [prepare_sce_monthly_reconstruction.py](prepare_sce_monthly_reconstruction.py)：沿已登记512/24六格抽样，准备独立月份的近期初始化、实际权重与基线；不读本期通胀答案，不递推模型历史。
- [assemble_sce_monthly_reconstruction.py](assemble_sce_monthly_reconstruction.py)：复用既有P/E提示和官方worker，一次完成提示、离线回放、Core检查及机器可读评价配置；无live模式、无调用授权。
- [report_sce_entry_initialization.py](report_sce_entry_initialization.py)：读取上述聚合缓存，在既有三月阅读页增加初始化图文，不修改原模拟统计与图。
- [render_sce_progress_report_20261019.py](render_sce_progress_report_20261019.py)：从已有聚合证据更新20页阶段汇报，PDF和单文件HTML保存至`docs/reports/20261019/`；不发API、不重拟合Q9。

共享算法优先从`studies/sce_inflation_expectations/evaluation/`、`experiments/`导入，基础分位数/W1/权重先查[metrics.py](../studies/sce_inflation_expectations/evaluation/metrics.py)。不同按人/按月重抽样设计不能自动互换。旧冻结脚本不在本轮重构或移动；部分report脚本仍被模块导入。

运行、预算、失败和新输出目录要求见[共用流程](../docs/EXPERIMENT_PIPELINE.md)。当前任务见[任务板](../docs/NEXT_ACTIONS.md)；每轮证据见[workstreams](../docs/workstreams/)。

- [analyze_sce_advisor_diagnostics.py](analyze_sce_advisor_diagnostics.py)：复用十二期缓存诊断年龄×学历九格，并从旧原回包单独恢复Q8；不重拟合Q9。
- [report_sce_advisor_diagnostics.py](report_sce_advisor_diagnostics.py)：将上述聚合结果作图并接入既有阅读页；同名输出存在时拒绝覆盖。
- [report_sce_q8_delta.py](report_sce_q8_delta.py)：从共用评价缓存生成Q8单改对照图文与费用收据，不发API或重拟合Q9。
- [check_sce_simulation_capabilities.py](check_sce_simulation_capabilities.py)：仅核免费Simulation能力与受支持参数，不执行付费问卷。
- [evaluate_sce_model_migration.py](evaluate_sce_model_migration.py)：连接中断后仅评价全部重复完整的月份，生成只读派生manifest，不补API或改原答。
- [report_sce_model_migration.py](report_sce_model_migration.py)：模型迁移的公共图文、分组、重复分解与去重费用收据，读取已计分缓存。

Q8单改已用共用runner完成384调用；结果见`docs/workstreams/20261019_advisor_followup/q8_delta_results_20261019.md`，不重复运行旧包。人口六格只做设计，不随格式实验更换。温度批次复算用`evaluate_sce_temperature.py`的四遍真值索引适配，再用`report_sce_temperature.py`作图；不重跑已完成API。

## 按用途查找全部入口

下列英文简介保留自原文件，帮助识别；不是新的方法或有效性认定。


### 运行与导出（37）

- [export_sce_confidence_analysis.py](export_sce_confidence_analysis.py) — Recompute frozen analysis with a strict missing-value JSON export adapter.
- [export_sce_u1_answers.py](export_sce_u1_answers.py) — Export completed U1 state/guided runs to the registered comparison schema.
- [export_study_runtime.py](export_study_runtime.py) — One-way export of the SCE study from the research repo to a runtime studies root.
- [run_approved_sce_expanded_news.py](run_approved_sce_expanded_news.py) — Dispatch only never-started, frozen public-news packages under the approved cap.
- [run_nyt_label_quote_adapter.py](run_nyt_label_quote_adapter.py) — Thin entry for source-verified quote restoration and unattempted continuation.
- [run_nyt_label_trial.py](run_nyt_label_trial.py) — Classification runner; offline validation unless --execute is explicit.
- [run_sce_anchor_baselines.py](run_sce_anchor_baselines.py) — Run the preregistered personal-anchor update rules (belief dynamics, round 2).
- [run_sce_anchor_role_trial.py](run_sce_anchor_role_trial.py) — Isolated prior-role trial; no auto-resume/retry and explicit authorization gate.
- [run_sce_annual_model_comparison.py](run_sce_annual_model_comparison.py) — Budgeted exact-message annual questionnaire replay; offline unless confirmed.
- [run_sce_baselines.py](run_sce_baselines.py) — Run the frozen offline benchmark protocol and retain per-month predictions.
- [run_sce_belief_baselines.py](run_sce_belief_baselines.py) — SCE preregistered empirical update baselines (B0-B4), train 201702-202112 /
- [run_sce_cognition_trial.py](run_sce_cognition_trial.py) — Historical cognition input pilot; no auto-resume/retry and explicit authorization gate.
- [run_sce_confidence_trial.py](run_sce_confidence_trial.py) — Offline preparation and budget-gated paired confidence experiment.
- [run_sce_event_probe.py](run_sce_event_probe.py) — Execute a protocol-bound, approved Event data probe once, with no retries.
- [run_sce_expanded_trial.py](run_sce_expanded_trial.py) — Prepare/dry-run/execute the approved expanded experiment in SocioVerse2.
- [run_sce_experience_trial.py](run_sce_experience_trial.py) — Freeze and run the authorized 20-person, two-month, five-arm SCE trial.
- [run_sce_finance_validation_trial.py](run_sce_finance_validation_trial.py) — Separate cross-month finance entry; inherit the audited no-resume runner.
- [run_sce_frozen_trial.py](run_sce_frozen_trial.py) — Shared frozen-prompt trials: prepare, dry-run, gated run, worker, evaluate.
- [run_sce_household_finance_trial.py](run_sce_household_finance_trial.py) — Household financial-circumstances pilot; no auto-resume/retry and explicit authorization gate.
- [run_sce_household_state_trial.py](run_sce_household_state_trial.py) — Prepare a Q1-only paired pilot offline; execute only after fresh approval.
- [run_sce_information_exposure_trial.py](run_sce_information_exposure_trial.py) — Prepare an isolated E/P routing trial; paid execution needs explicit approval.
- [run_sce_information_update_trial.py](run_sce_information_update_trial.py) — Information-time follow-up; reuse old A, run only new B/C; no auto-resume/retry and explicit authorization gate.
- [run_sce_lifetime_text_trial.py](run_sce_lifetime_text_trial.py) — Budget-gated qualitative history comparison, no change to old configurations.
- [run_sce_lifetime_trial.py](run_sce_lifetime_trial.py) — Run the isolated, budget-gated Lifetime Inflation Experience trial.
- [run_sce_local.py](run_sce_local.py) — Local SCE run entry — export the study one-way, run it in the official clone, audit fully.
- [run_sce_model_counterfactual.py](run_sce_model_counterfactual.py) — Replay prepared model-only messages; default is offline validation, not spending.
- [run_sce_model_followup.py](run_sce_model_followup.py) — Continue fixed model comparison without resetting prior spend; default is offline.
- [run_sce_native_spending_trial.py](run_sce_native_spending_trial.py) — Prepare, then explicitly execute the isolated native SCE basket trial.
- [run_sce_news_exposure_trial.py](run_sce_news_exposure_trial.py) — Prepare/dry-run news exposure; real execution needs fresh complete-label approval.
- [run_sce_price_contact_trial.py](run_sce_price_contact_trial.py) — Thin entry for the isolated price-contact experiment.
- [run_sce_prior_trial.py](run_sce_prior_trial.py) — Prepare/dry-run/run the isolated observed-prior trial, with explicit budget.
- [run_sce_purchase_frequency_trial.py](run_sce_purchase_frequency_trial.py) — Purchase-frequency instruction contrast; same data in both arms; no auto-resume/retry and explicit authorization gate.
- [run_sce_reference_news.py](run_sce_reference_news.py) — Budget-bound dispatch of frozen public news, no automatic retry or resume.
- [run_sce_reference_validation_trial.py](run_sce_reference_validation_trial.py) — Reference scale-up; isolated worker plus the existing gated fail-stop dispatch.
- [run_sce_reuse_probe.py](run_sce_reuse_probe.py) — One-model, $0.50 capped archived-message replay; defaults to no network.
- [run_sce_revision_format_trial.py](run_sce_revision_format_trial.py) — Direct-versus-revision response-format pilot; no auto-resume/retry and explicit authorization gate.
- [run_sce_u1_trial.py](run_sce_u1_trial.py) — Entry point for the U1 explicit-state trial: prepare, dry-run or execute.


### 准备与构建（40）

- [build_nyt_events.py](build_nyt_events.py) — Build the NYT salient-event ledger (E v2 event layer, D049d).
- [build_sce_available_environment.py](build_sce_available_environment.py) — Build isolated B month-start input drafts from verified local release archives.
- [build_sce_baseline_inputs.py](build_sce_baseline_inputs.py) — Prepare release-audited aggregate inputs and evaluation-only micro reference cache.
- [build_sce_baseline_review.py](build_sce_baseline_review.py) — Add rolling diagnostics and a portable, offline HTML view of completed runs.
- [build_sce_environment.py](build_sce_environment.py) — Materialize the BLS information environment (E) for sce_inflation_expectations.
- [build_sce_environment_v2.py](build_sce_environment_v2.py) — Build the E v2 information environment for sce_inflation_expectations.
- [build_sce_evaluation_truth.py](build_sce_evaluation_truth.py) — Extract evaluation-layer truth for the SCE main window from the microdata.
- [build_sce_population.py](build_sce_population.py) — Build a real-population Persona bundle by sampling U.S. respondents from the
- [build_sce_price_experience.py](build_sce_price_experience.py) — Build an A-line CE basket sidecar and preview all mechanism arms, fully offline.
- [build_sce_psychological_profiles.py](build_sce_psychological_profiles.py) — Build offline candidate sidecars, not runtime population or new answers.
- [prepare_ce_category_frequency.py](prepare_ce_category_frequency.py) — 专题入口；运行前读文件说明与对应批次记录。
- [prepare_ce_diary.py](prepare_ce_diary.py) — Prepare weekly 2020 CE Diary experience records offline; this script never calls an LLM.
- [prepare_nyt_selection_trial.py](prepare_nyt_selection_trial.py) — Offline entry point; import the study without optional simulation packages.
- [prepare_sce_annual_model_comparison.py](prepare_sce_annual_model_comparison.py) — Prepare fixed 2021 model comparisons offline; never read keys or call APIs.
- [prepare_sce_baseline_sources.py](prepare_sce_baseline_sources.py) — Archive public release evidence for offline SCE benchmarks. No credentials.
- [prepare_sce_belief_trial.py](prepare_sce_belief_trial.py) — Prepare local-only belief inputs; this entry point cannot request a model.
- [prepare_sce_coverage.py](prepare_sce_coverage.py) — Thin entry point for offline multi-period preparation.
- [prepare_sce_expansion_preflight.py](prepare_sce_expansion_preflight.py) — Offline candidate coverage and budgeting only; no execution option.
- [prepare_sce_frequency_candidate.py](prepare_sce_frequency_candidate.py) — Prepare the source-limited offline matching prototype. No network or API.
- [prepare_sce_information_exposure.py](prepare_sce_information_exposure.py) — Prepare six-month news/statistics view inventory; cannot start paid calls.
- [prepare_sce_macro_profile_sources.py](prepare_sce_macro_profile_sources.py) — Free public archive downloads and deterministic aggregate macro extraction.
- [prepare_sce_mechanism_pilot.py](prepare_sce_mechanism_pilot.py) — Create a small, fixed within-month comparison panel without reading answers.
- [prepare_sce_model_counterfactual.py](prepare_sce_model_counterfactual.py) — Offline matched model inputs from completed DeepSeek runs; no API/key access.
- [prepare_sce_monthly_inputs.py](prepare_sce_monthly_inputs.py) — Prepare A-line monthly P/E/simulation packages without model calls.
- [prepare_sce_news_breadth_trial.py](prepare_sce_news_breadth_trial.py) — Freeze varied news-count inputs for the shared engine; no API calls.
- [prepare_sce_news_exposure_demo.py](prepare_sce_news_exposure_demo.py) — Thin, offline entry point for the news exposure demonstration.
- [prepare_sce_news_extension_labels.py](prepare_sce_news_extension_labels.py) — Thin offline entry for new-period public news classification preparation.
- [prepare_sce_news_label_completion.py](prepare_sce_news_label_completion.py) — Thin offline entry; never resends a request.
- [prepare_sce_news_pool.py](prepare_sce_news_pool.py) — Thin offline entry for completing the existing news candidate pool.
- [prepare_sce_persistence_probe.py](prepare_sce_persistence_probe.py) — Prepare local-only previews; there is deliberately no execute mode.
- [prepare_sce_personal_information.py](prepare_sce_personal_information.py) — Prepare local ATUS/SCE role probabilities and quantity-balanced allocations.
- [prepare_sce_personal_information_views.py](prepare_sce_personal_information_views.py) — Create news/price fragments from a prepared ATUS/SCE bridge, without APIs.
- [prepare_sce_prior_trial.py](prepare_sce_prior_trial.py) — Zero-API SCE prior inventory and conditional-update input preparation.
- [prepare_sce_progress_report.py](prepare_sce_progress_report.py) — Create aggregate-only figures for the 2026-10-15 progress briefing.
- [prepare_sce_purchase_frequency.py](prepare_sce_purchase_frequency.py) — Offline matched contact/price materials; previews only, no live provider/API.
- [prepare_sce_reference_news.py](prepare_sce_reference_news.py) — Prepare only unlabeled public articles for reference scaleup; never call API.
- [prepare_sce_reuse_probe.py](prepare_sce_reuse_probe.py) — Prepare an outcome-blind, 20-person annual Qwen replay. Offline only.
- [prepare_sce_revision_draft.py](prepare_sce_revision_draft.py) — Offline prompt drafts, not a runnable/authorized experiment batch.
- [prepare_sce_shared_environment.py](prepare_sce_shared_environment.py) — Export the exact existing Agent public E for baselines; no downloads or LLM.
- [prepare_sce_u1a_state.py](prepare_sce_u1a_state.py) — Prepare the U1 explicit personal-state arms (offline, zero API calls).


### 评价与报告（16）

- [evaluate_sce_model_migration.py](evaluate_sce_model_migration.py) — Evaluate only fully completed repeated months from a stopped model-migration batch, without reruns.
- [report_sce_model_migration.py](report_sce_model_migration.py) — Plot cached model comparisons and publish aggregate execution/cost evidence only.
- [report_sce_advisor_diagnostics.py](report_sce_advisor_diagnostics.py) — Plot cached household-grid and recovered Q8 diagnostics in the existing reader.
- [report_sce_q8_delta.py](report_sce_q8_delta.py) — Render the completed Q8-only pilot from cached evaluation; no API or refit.
- [evaluate_sce_temperature.py](evaluate_sce_temperature.py) — Reuse invariant person-month truth across four temperature repeats; no source or answer rewriting.
- [report_sce_temperature.py](report_sce_temperature.py) — Publish temperature accuracy, repeat-noise decomposition and cost from cached outputs.

- [evaluate_sce_dev_run.py](evaluate_sce_dev_run.py) — Same-person development analysis: actual answers are read only after the run.
- [evaluate_sce_outputs.py](evaluate_sce_outputs.py) — Evaluate normalized SCE bundles without loading inputs into the simulation engine.
- [report_sce_frozen_trial.py](report_sce_frozen_trial.py) — Make an aggregate report from already scored frozen-prompt trial answers.
- [report_sce_information_exposure.py](report_sce_information_exposure.py) — Report all preregistered six-arm contrasts from already-scored answers.
- [report_sce_news_breadth.py](report_sce_news_breadth.py) — Read out matched/random/uniform news exposure using shared scored outputs.
- [report_sce_reference_validation.py](report_sce_reference_validation.py) — Write aggregate Chinese findings and update the existing project reading page.
- [summarize_midus_local.py](summarize_midus_local.py) — User-run MIDUS statistics. Do not execute on real data through an AI agent.
- [summarize_sce_cognition_diagnostics.py](summarize_sce_cognition_diagnostics.py) — Recompute explicitly exploratory response variation and past-only context, with no API.
- [summarize_sce_psychological_waves.py](summarize_sce_psychological_waves.py) — Compare completed wave trial to cached 2018 answers using existing metrics.
- [summarize_sce_retention_predictability.py](summarize_sce_retention_predictability.py) — Small public readout and capacity check; no refit, API, or model selection.


### 分析（58）

- [analyze_sce_stratification_support.py](analyze_sce_stratification_support.py) — Outcome-free six-cell support and minimum-plus-proportional Core allocation draft.

- [analyze_sce_population_factor_priority.py](analyze_sce_population_factor_priority.py) — Compare ten cached trait blocks on identical monthly support; descriptive R2 only.

- [analyze_sce_advisor_diagnostics.py](analyze_sce_advisor_diagnostics.py) — Cached nine-cell household comparisons and independent Q8 recovery.

- [analyze_nyt_selection_trial.py](analyze_nyt_selection_trial.py) — Offline verification of news trial; no classifier or simulation calls.
- [analyze_sce_aggregate_blend.py](analyze_sce_aggregate_blend.py) — Fit MAE/MSE convex weights on existing aggregate trajectories; zero APIs.
- [analyze_sce_anchor_direction.py](analyze_sce_anchor_direction.py) — Compare alignment with older personal answers and common references, offline.
- [analyze_sce_anchor_role_trial.py](analyze_sce_anchor_role_trial.py) — 专题入口；运行前读文件说明与对应批次记录。
- [analyze_sce_attention_support.py](analyze_sce_attention_support.py) — Check external attention/channel predictive support without paid calls.
- [analyze_sce_atus_roles.py](analyze_sce_atus_roles.py) — Audit public ATUS roles and external attention without simulation calls.
- [analyze_sce_behavior_comparison.py](analyze_sce_behavior_comparison.py) — Compare saved SCE responses and same-cohort baselines; never call an API.
- [analyze_sce_belief_dynamics.py](analyze_sce_belief_dynamics.py) — SCE belief dynamics: task A (real panel update facts) + task A' (LLM same-
- [analyze_sce_cognition_low_only.py](analyze_sce_cognition_low_only.py) — Post-hoc Low-only cognition policy using frozen, independent household replies.
- [analyze_sce_cognition_trial.py](analyze_sce_cognition_trial.py) — Offline analysis of a completed SCE cognition presentation trial.
- [analyze_sce_confidence_trial.py](analyze_sce_confidence_trial.py) — Extract evaluation truth or analyze paired confidence trial, no API calls.
- [analyze_sce_event_probe.py](analyze_sce_event_probe.py) — Audit a completed fixed Event probe and hash-linked official source archive.
- [analyze_sce_expanded_trial.py](analyze_sce_expanded_trial.py) — Freeze the development weight, or evaluate held-out months offline.
- [analyze_sce_expansion_diagnostic.py](analyze_sce_expansion_diagnostic.py) — Offline entry point; fresh output folder required.
- [analyze_sce_experience_trial.py](analyze_sce_experience_trial.py) — Analyze the two-month, five-arm SCE price-experience pilot without API calls.
- [analyze_sce_finance_validation.py](analyze_sce_finance_validation.py) — Offline evaluation of completed Q1 cross-month validation runs.
- [analyze_sce_forecast_population.py](analyze_sce_forecast_population.py) — Profile-only monthly drift and B donor diagnostics, no model/network calls.
- [analyze_sce_frequency_controls.py](analyze_sce_frequency_controls.py) — Offline controlled associations in the completed frequency experiment.
- [analyze_sce_heterogeneous_news.py](analyze_sce_heterogeneous_news.py) — Reuse archived news-count replies for a fixed external-attention allocation.
- [analyze_sce_history_forward.py](analyze_sce_history_forward.py) — Time-ordered personal-history checks on cached scores; no network or API.
- [analyze_sce_history_mechanism.py](analyze_sce_history_mechanism.py) — Offline follow-up: personal history coefficients, Sim-only R2 and SCE proxies.
- [analyze_sce_household_finance_associations.py](analyze_sce_household_finance_associations.py) — Zero-API, aggregate-only analysis entry point.
- [analyze_sce_household_finance_trial.py](analyze_sce_household_finance_trial.py) — Offline analysis of a completed SCE household-finance three-arm trial.
- [analyze_sce_household_state_trial.py](analyze_sce_household_state_trial.py) — Evaluate a completed Q1 paired trial offline; no network or new simulation.
- [analyze_sce_inertia_calibration.py](analyze_sce_inertia_calibration.py) — Fixed-weight ConsumerSim-style aggregate sensitivity; zero network or LLM calls.
- [analyze_sce_information_exposure_trial.py](analyze_sce_information_exposure_trial.py) — Evaluate completed E/P routing LLM trial; no network, no new simulation.
- [analyze_sce_information_update_trial.py](analyze_sce_information_update_trial.py) — 专题入口；运行前读文件说明与对应批次记录。
- [analyze_sce_lifetime_trial.py](analyze_sce_lifetime_trial.py) — Offline analysis only; no simulation or model calls.
- [analyze_sce_model_costs_groups.py](analyze_sce_model_costs_groups.py) — Offline cost normalization and group diagnostics for the frozen model pilot.
- [analyze_sce_model_counterfactual.py](analyze_sce_model_counterfactual.py) — Analyze completed model probes offline, with true answers only in this script.
- [analyze_sce_native_spending_trial.py](analyze_sce_native_spending_trial.py) — 专题入口；运行前读文件说明与对应批次记录。
- [analyze_sce_news_exposure_trial.py](analyze_sce_news_exposure_trial.py) — Analyze a completed news trial offline, without new API calls.
- [analyze_sce_news_extension_labels.py](analyze_sce_news_extension_labels.py) — Thin offline entry for new-period news-label acceptance and libraries.
- [analyze_sce_outlook_forward.py](analyze_sce_outlook_forward.py) — Check previous Q2 using validated caches; no original workbooks or API.
- [analyze_sce_past_exposure_gate.py](analyze_sce_past_exposure_gate.py) — Select already-generated information views using frozen past-only predictions.
- [analyze_sce_population_associations.py](analyze_sce_population_associations.py) — 专题入口；运行前读文件说明与对应批次记录。
- [analyze_sce_prior_trial.py](analyze_sce_prior_trial.py) — Offline observed-prior evaluation; never launches an API request.
- [analyze_sce_purchase_frequency_trial.py](analyze_sce_purchase_frequency_trial.py) — Offline evaluation entry point; never calls the simulation API.
- [analyze_sce_reference_validation.py](analyze_sce_reference_validation.py) — Offline evaluation of the 12-month reference scale-up.
- [analyze_sce_reporting_behavior.py](analyze_sce_reporting_behavior.py) — Offline SCE probability-reporting analysis; no API or simulation calls.
- [analyze_sce_reporting_mapping.py](analyze_sce_reporting_mapping.py) — Run the registered personal reporting mapping into a fresh local directory.
- [analyze_sce_response_gap.py](analyze_sce_response_gap.py) — Describe archived human/model gaps without APIs or refitting probabilities.
- [analyze_sce_response_gap_controls.py](analyze_sce_response_gap_controls.py) — Describe conditional response gaps without API calls or density refitting.
- [analyze_sce_retention_predictability.py](analyze_sce_retention_predictability.py) — Predict reported stability from past-only records; zero paid calls.
- [analyze_sce_reuse_probe.py](analyze_sce_reuse_probe.py) — Score archived annual DeepSeek and optional exact-input Qwen offline.
- [analyze_sce_revision_format_trial.py](analyze_sce_revision_format_trial.py) — Offline evaluation, no API calls.
- [analyze_sce_update_direction.py](analyze_sce_update_direction.py) — Run the fixed past-only update-direction diagnostic, without network access.
- [analyze_sce_update_mismatch_profiles.py](analyze_sce_update_mismatch_profiles.py) — Locate observed human/model update mismatches using verified cached inputs.
- [analyze_sce_updating_facts.py](analyze_sce_updating_facts.py) — SCE updating micro facts F1-F6: inaction, lumpy revisions, information
- [analyze_sce_wave_stats.py](analyze_sce_wave_stats.py) — Wave-by-wave descriptive statistics on FRBNY SCE public micro data
- [diagnose_sce_beta.py](diagnose_sce_beta.py) — Independent diagnostic experiments; NEVER imported by the production scorer.
- [diagnose_sce_center_shift.py](diagnose_sce_center_shift.py) — 专题入口；运行前读文件说明与对应批次记录。
- [diagnose_sce_confidence_responses.py](diagnose_sce_confidence_responses.py) — Describe existing answers offline; this entry never starts a simulation.
- [diagnose_sce_reference_regression.py](diagnose_sce_reference_regression.py) — Exploratory regressions on frozen fitted responses; never refits Q9 or calls APIs.
- [diagnose_sce_reference_update.py](diagnose_sce_reference_update.py) — Post-hoc slope diagnostic from existing fitted cases; zero new model calls.


### 审计与验证（42）

- [check_sce_simulation_capabilities.py](check_sce_simulation_capabilities.py) — Free registry/schema verification only; never runs a paid questionnaire.

- [audit_cloud_v2_environment.py](audit_cloud_v2_environment.py) — Verify the pasted v2 cloud environment against the archived local inputs.
- [audit_cloud_v2_model.py](audit_cloud_v2_model.py) — Replay the archived v2 scripted formula against local P/E and raw answers.
- [audit_cloud_v2_raw.py](audit_cloud_v2_raw.py) — Independently audit the v2 scripted pilot's pasted raw JSONL answers.
- [audit_cloud_v3_audit.py](audit_cloud_v3_audit.py) — Independently audit the v3 scripted audit-run artifacts retrieved from the platform.
- [audit_local_scripted_replay.py](audit_local_scripted_replay.py) — Replay audit: local scripted run vs the cloud v3 archive (2026-10-01).
- [audit_nyt_inventory.py](audit_nyt_inventory.py) — Thin entry point for the local-only NYT inventory audit.
- [audit_population_proposal.py](audit_population_proposal.py) — Read-only independent checks of the October 3 population proposal; no API calls.
- [audit_sce_basket_population.py](audit_sce_basket_population.py) — Audit a complete SCE population's synthetic CE baskets, fully offline.
- [audit_sce_behavior_mechanisms.py](audit_sce_behavior_mechanisms.py) — Zero-API audit of official conditional associations and existing LLM compression.
- [audit_sce_coverage_and_age.py](audit_sce_coverage_and_age.py) — 专题入口；运行前读文件说明与对应批次记录。
- [audit_sce_deepseek_reuse.py](audit_sce_deepseek_reuse.py) — Audit archived DeepSeek responses offline; never reads keys or calls APIs.
- [audit_sce_environment_candidate.py](audit_sce_environment_candidate.py) — Offline acceptance of an isolated E candidate; no simulation or API calls.
- [audit_sce_factual_mechanisms.py](audit_sce_factual_mechanisms.py) — Prepare factual mechanism evidence offline; never executes simulation.
- [audit_sce_frequency_quarters.py](audit_sce_frequency_quarters.py) — Existing-data CE quarter/matching audit; never starts simulation or an API.
- [audit_sce_household_state.py](audit_sce_household_state.py) — Audit development months and GSS2018 donor support; no model calls.
- [audit_sce_monthly_run.py](audit_sce_monthly_run.py) — Audit a monthly P/E run and form weighted diagnostic summaries, no APIs.
- [audit_sce_news_responses.py](audit_sce_news_responses.py) — Offline audit of existing inputs/replies; does not call any API.
- [audit_sce_numeracy.py](audit_sce_numeracy.py) — Offline numeracy validation on existing real and simulated SCE answers.
- [audit_sce_pe_diagnostic.py](audit_sce_pe_diagnostic.py) — Read archived P/E/B messages and answers; no network, no providers.
- [audit_sce_psychological_waves.py](audit_sce_psychological_waves.py) — Audit downloaded public GSS waves; never calls a model.
- [audit_sce_q9_scoring.py](audit_sce_q9_scoring.py) — Compare local Q9 density scores with public SCE derived fields and chart data.
- [audit_sce_replies_20261018.py](audit_sce_replies_20261018.py) — Audit archived SCE reply text without API calls, fitting, or source mutation.
- [audit_sce_reuse_run.py](audit_sce_reuse_run.py) — Offline audit of identities, original payloads, retries and cumulative fees.
- [audit_sce_scaleup_coverage.py](audit_sce_scaleup_coverage.py) — Local-only availability audit for a proposed expanded A-line validation.
- [audit_sce_sources.py](audit_sce_sources.py) — Read-only feasibility audit of downloaded SCE workbooks; no model fitting.
- [audit_sce_spending.py](audit_sce_spending.py) — Link real SCE spending baskets and run a fixed offline structural probe.
- [audit_sce_u1_execution.py](audit_sce_u1_execution.py) — Verify U1 real run records and exports without making new API requests.
- [audit_sce_u1_preparation.py](audit_sce_u1_preparation.py) — Read-only audit of prepared U1 messages; no real simulation or API calls.
- [audit_sce_vintage_examples.py](audit_sce_vintage_examples.py) — Offline, bounded CES revision example using verified local BLS PDFs.
- [check_mcp_free_capabilities.py](check_mcp_free_capabilities.py) — Verify connectivity and FREE catalog/field capabilities of the configured MCP services.
- [check_sce_cognition_population_weights.py](check_sce_cognition_population_weights.py) — Post-hoc High/Low population-margin sensitivity; never changes model answers.
- [check_sce_core_normal.py](check_sce_core_normal.py) — Offline expansion diagnostic with real Core answers as oracle response atoms.
- [check_sce_core_size.py](check_sce_core_size.py) — Offline Core-size study: nested samples of observed responses, never an LLM run.
- [check_sce_macro_population.py](check_sce_macro_population.py) — No API: compare macro profile forecasts against lagged SCE distributions.
- [check_sce_population_precision.py](check_sce_population_precision.py) — Offline development-month sampling check; no providers or simulation inputs.
- [check_sce_reference_history_information.py](check_sce_reference_history_information.py) — Check unused regression information already present in the frozen prompts.
- [check_sce_reference_validation.py](check_sce_reference_validation.py) — Small independent aggregate check; reuse scored cases, never refit or call API.
- [validate_sce_scorer_holdout.py](validate_sce_scorer_holdout.py) — One preregistered comparison; imports frozen algorithms without modifying them.
- [verify_bls_pit_e.py](verify_bls_pit_e.py) — Verify the two-month BLS E snapshot against its archived release PDFs.
- [verify_sce_prior_preparation.py](verify_sce_prior_preparation.py) — Verify offline SCE prior input preparation; reuse existing answers only.
- [verify_sce_purchase_frequency_trial.py](verify_sce_purchase_frequency_trial.py) — Focused saved-run verification: actual inputs/parameters/cost and SciPy metrics.


### 下载与数据获取（5）

- [download_sce_atus_reference.py](download_sce_atus_reference.py) — Download public BLS ATUS files through an already connected browser.
- [fetch_ce_diary_public.py](fetch_ce_diary_public.py) — Download explicit public BLS CE Diary CSV archives; no credentials/API.
- [fetch_eia_gasoline.py](fetch_eia_gasoline.py) — Fetch U.S. retail gasoline prices (E v2 data layer, D049c).
- [fetch_gss2018.py](fetch_gss2018.py) — Archive official current public GSS2018 data; no historical-vintage claim.
- [probe_sce_event_sources.py](probe_sce_event_sources.py) — Read the free Event MCP catalog without fetching metered source data.


### 作图与阅读页（37）

- [plot_sce_anchor_role_results.py](plot_sce_anchor_role_results.py) — Plot aggregate prior-role experiment results; no API or private rows read.
- [plot_sce_baselines.py](plot_sce_baselines.py) — Render a standalone scientific figure from a completed baseline run (offline).
- [plot_sce_cognition_results.py](plot_sce_cognition_results.py) — Create static figures from an aggregated SCE cognition evaluation summary.
- [plot_sce_coverage_age_audit.py](plot_sce_coverage_age_audit.py) — Static figures from aggregate coverage/age analysis, no API.
- [plot_sce_experience_trial.py](plot_sce_experience_trial.py) — Plot equal-person medians and interquartile ranges from a completed pilot.
- [plot_sce_finance_validation_results.py](plot_sce_finance_validation_results.py) — Render aggregate-only charts from a completed frozen cross-month evaluation.
- [plot_sce_frequency_controls.py](plot_sce_frequency_controls.py) — Scientific figures from aggregate offline diagnostics; no API or private records.
- [plot_sce_frequency_quarter_audit.py](plot_sce_frequency_quarter_audit.py) — Figures for existing-data CE quarter/matching checks; no private rows/API.
- [plot_sce_history_mechanism.py](plot_sce_history_mechanism.py) — Plot aggregate results for the existing personal-history reading page.
- [plot_sce_household_finance_results.py](plot_sce_household_finance_results.py) — Draw aggregate-only household-finance pilot figures in a fresh directory.
- [plot_sce_household_state_trial.py](plot_sce_household_state_trial.py) — Export a paper-ready Q1 group comparison from completed paired evaluation.
- [plot_sce_information_exposure.py](plot_sce_information_exposure.py) — Scientific figures from the six-arm aggregate readout; no private records.
- [plot_sce_information_update_results.py](plot_sce_information_update_results.py) — Plot aggregate information-time follow-up results; no API or private rows read.
- [plot_sce_news_breadth.py](plot_sce_news_breadth.py) — Figures from aggregate news-allocation results; no personal data or APIs.
- [plot_sce_psychological_wave_results.py](plot_sce_psychological_wave_results.py) — Render the saved aggregate comparison; no data fitting or model calls.
- [plot_sce_purchase_frequency_results.py](plot_sce_purchase_frequency_results.py) — Plot aggregate purchase-frequency contrast results; no API or private rows read.
- [plot_sce_reference_validation.py](plot_sce_reference_validation.py) — Scientific figures from the frozen 12-wave evaluation; aggregate outputs only.
- [plot_sce_regression_contributions.py](plot_sce_regression_contributions.py) — Scientific figure for the existing regression-diagnostic reading page.
- [plot_sce_revision_format_results.py](plot_sce_revision_format_results.py) — Aggregate figures for the revision-format pilot; no API or individual rows.
- [plot_sce_spending.py](plot_sce_spending.py) — 专题入口；运行前读文件说明与对应批次记录。
- [plot_sce_targeted_profiles.py](plot_sce_targeted_profiles.py) — Plot aggregate profile differences; no fitting or API access.
- [render_current_todo.py](render_current_todo.py) — Render the current NEXT_ACTIONS checklist as a small local reading page.
- [render_sce_anchor_direction.py](render_sce_anchor_direction.py) — Render aggregate anchor-alignment diagnostics, without accessing person rows.
- [render_sce_behavior_comparison.py](render_sce_behavior_comparison.py) — Render a frozen public comparison summary as a local, offline reading page.
- [render_sce_confidence_report.py](render_sce_confidence_report.py) — Aggregate-only figures and result update in the existing news reading page.
- [render_sce_expanded_results.py](render_sce_expanded_results.py) — Render frozen aggregate results into the existing project reading page.
- [render_sce_inertia_calibration.py](render_sce_inertia_calibration.py) — Render fixed-weight offline diagnostics into the existing SCE reading page.
- [render_sce_mechanism_evidence.py](render_sce_mechanism_evidence.py) — Render aggregate, zero-API mechanism evidence into the existing reading page.
- [render_sce_news_exposure_report.py](render_sce_news_exposure_report.py) — Append actual aggregate results to the existing news reading HTML.
- [render_sce_news_response_diagnostic.py](render_sce_news_response_diagnostic.py) — Add reviewed diagnostic aggregates to the existing HTML; no browser or network.
- [render_sce_pe_diagnostic.py](render_sce_pe_diagnostic.py) — Render an offline audit into static scientific plots and a browser report.
- [render_sce_population_associations.py](render_sce_population_associations.py) — Render aggregate-only real-data results; no modelling or API in this step.
- [render_sce_population_guide.py](render_sce_population_guide.py) — Render the requested fixed reading handout, not simulation code or inputs.
- [render_sce_prior_report.py](render_sce_prior_report.py) — Render aggregate scientific figures and append results to the existing reading page.
- [render_sce_progress_report.py](render_sce_progress_report.py) — Render the agreed progress briefing as PDF and a matching local HTML reader.
- [render_sce_progress_report_20261019.py](render_sce_progress_report_20261019.py) — Refresh the existing 16:9 PDF/HTML briefing from frozen aggregate evidence.
- [render_sce_response_gap.py](render_sce_response_gap.py) — Render the existing reading-page supplement from cached aggregate results.


### 其他入口（23）

- [archive_sce_expanded_public_policy.py](archive_sce_expanded_public_policy.py) — Archive public Fed statements and a Gallup topline; no model API or credentials.
- [archive_sce_gasoline_support.py](archive_sce_gasoline_support.py) — Archive missing weekly FRED GASREGW history separately; preserve original cache.
- [archive_sce_public_brief_sources.py](archive_sce_public_brief_sources.py) — Archive a fixed small list of free official evidence; never calls an MCP/LLM.
- [backtest_sce_macro_profile_extension.py](backtest_sce_macro_profile_extension.py) — Offline rolling population-margin comparisons; no simulation calls.
- [decompose_sce_reference_regression.py](decompose_sce_reference_regression.py) — Attribute existing response-regression R2 and diagnose overlapping predictors.
- [derive_sce_expanded_program.py](derive_sce_expanded_program.py) — Materialize every program prediction WITHOUT reading current real answers.
- [expand_sce_core_normal.py](expand_sce_core_normal.py) — Expand a completed single-month Core run; reads NO actual questionnaire truth.
- [extend_sce_baseline_inputs.py](extend_sce_baseline_inputs.py) — Compile a new latest-data baseline version without rewriting the 60-month sources.
- [extend_sce_environment_sources.py](extend_sce_environment_sources.py) — Append E source caches and prepare an isolated candidate, never run simulation.
- [extract_cpi_components.py](extract_cpi_components.py) — Extract household-perceivable CPI component 12-month changes from the
- [freeze_sce_information_exposure.py](freeze_sce_information_exposure.py) — Freeze prepared information views for the existing executor; no API calls.
- [inspect_sce_beta_reference_support.py](inspect_sce_beta_reference_support.py) — Evaluation-only inverse diagnostic, NEVER an Agent input or scoring rule.
- [inventory_sce_matching_fields.py](inventory_sce_matching_fields.py) — 专题入口；运行前读文件说明与对应批次记录。
- [inventory_sce_population_mechanisms.py](inventory_sce_population_mechanisms.py) — Local public-field inventory only: no model/API/runtime changes.
- [inventory_sce_subjective_models_reference.py](inventory_sce_subjective_models_reference.py) — Inspect public replication data locally; save aggregate inventory only.
- [preflight_sce_run.py](preflight_sce_run.py) — Render/inspect a planned SCE run without instantiating an LLM client.
- [preview_sce_dated_environment.py](preview_sce_dated_environment.py) — Render actual EnvironmentProvider observations offline; never invokes B/API.
- [record_sce_matched_progress.py](record_sce_matched_progress.py) — Describe existing stages on identical person-generation support; no API.
- [replay_sce_core_size.py](replay_sce_core_size.py) — Subsample completed LLM Core responses. No new answers, calls or actual truth.
- [sce_cpi_layout.py](sce_cpi_layout.py) — Deterministically read annual CPI component changes from BLS release PDFs.
- [sce_llm_probe.py](sce_llm_probe.py) — SCE LLM probe — explicit, counted, tiny paid interactions with the configured endpoint.
- [sce_release_available.py](sce_release_available.py) — Parse available first-release CPI fields without inventing missing months.
- [split_sce_basket_population.py](split_sce_basket_population.py) — Split one already-built full basket population into Core/Normal, offline.
# 2026-10-24主运行续跑入口

`run_sce_resilient_main.py`：最新有界容错控制台。原单次队列临时停止后自动冷却、降并发、仅继续未发送位置；不重发失败、不改科学输入/累计预算。prepare/run/watch/status，用户Terminal明确确认后启动。策略与命令见[续跑说明第7节](../docs/workstreams/20261023_main_run/resume_runbook_20261024.md)。

`run_sce_monthly_main_console.py`：用户本地Terminal的run/watch控制台；手动`--confirm-continuation`后才发送准备包中的未发送请求，每10秒显示聚合进度/费用/阶段，watch零API。最新手动包与复制命令见[续跑说明第6节](../docs/workstreams/20261023_main_run/resume_runbook_20261024.md)。

`continue_sce_monthly_main.py`：按不可改写旧账本，仅续从未发送位置；prepare/authorize/start/status，停止不自动重启。旧成功/失败均保留，费用从原累计额接算，完成后独立评价。具体已执行命令见[续跑说明](../docs/workstreams/20261023_main_run/resume_runbook_20261024.md)。算法位于`studies/sce_inflation_expectations/experiments/monthly_main_continuation.py`；不要直接重启旧主包。


- [render_sce_research_report.py](render_sce_research_report.py)：从单一正文源排版8页参赛报告PDF、HTML和文字稿，读取既有汇总与图；不需API密钥，不调用模拟或计分。


### 2026-10-25近期B离线准备

- `prepare_sce_recent_b.py`：核实公开旧快照、54格代理P与截止前全国锚；禁止新目录覆盖，无API发送器。
- `prepare_sce_recent_b_rolling.py`：按明确九个月发布滞后假设逐月选择微观源波次，构造54格代理P/同源就业收入/家庭结构，登记历史版本限制；不调用API。
- `prepare_sce_recent_b_priors.py`：同一合法旧库的联合供体起点、已公开历史Q9约束与有限样本分配，保留原Q8/Q9，不称本人实际上月答卷。
- 运行命令、边界及仍未完成项见 `docs/workstreams/20261025_recent_b/README.md`；两入口仅离线候选，不启动近期11月真实模型。

- `prepare_sce_recent_b_run.py`：从公开旧P/联合先验和现有E机制生成B提示，执行官方Core离线检查。
- `prepare_sce_recent_b_news_refresh.py`：从完成的B11版本复制P/先验/购物/政策，离线准备四档新闻＋CPI1.5候选与11个Core单元；保持B共同截止，无发送器。当前候选sce_recent_b_news_refresh_20261025_v3。
- `check_sce_recent_b_news_refresh.py`：只读核查候选的源/产物哈希、非新闻字节不变、5632提示再现及分档CPI暴露；输出独立readiness，不写授权或调用API。
- `prepare_sce_recent_b_continuity_pe.py`：只准备连续递推的固定首月512人、权重/角色/新闻档和逐月公开E；唯一首月合成种子＋同人上月依赖图，无最终提示/发送器。当前底包sce_recent_b_continuity_pe_20261026_v2。
- `check_sce_recent_b_continuity_pe.py`：独立核查固定身份与权重、唯一种子、各月新闻/价格/政策截止和依赖图；输出readiness，不调用LLM或评分。
- `build_sce_submission_experiment_logs.py`：按显式canonical收据来源生成公开/私有实验JSON/CSV；去重累计账本，分开API实报、token估费、未知预留和运行快照，不读取模型回答。
- `build_sce_research_package.py`：按版本白名单构建研究包ZIP；v06补真实模型输出、有效答卷和微观复算，不移动原日志或改冻结源。run.py区分工程例、聚合、微观复算和显式授权的付费生成。
- `run_sce_recent_b.py`：freeze仅离线，review只读核查且不读取密钥；run明确确认后独立后台执行，网络有界等待、一次技术失败自动补跑、独立全国评价；watch只读。当前夜间包为sce_recent_b_overnight_20261025_v3，不运行旧A或旧B包。
# 新闻机制 V3：本地逐请求启动补充（2026-10-25）

`run_sce_media_mechanism_terminal.py`：`prepare/review/watch`无API；`run --confirm-scope-and-budget`由用户本人终端启动独立后台，`resume`只继续未发送位置，`evaluate`离线复算。复用Kimi冻结提示、70个官方Core验收及共享指标，额外提供持久意图、费用/在途预留、有界冷却和进程锁；输出同支持照抄上期基线。研究算法不改，具体命令和预算见[执行附录](../docs/workstreams/20261024_media_mechanism/TERMINAL_EXECUTION_ADDENDUM_20261025.md)。当前未真实启动；不要与旧 `run_sce_media_mechanism_v3.py run` 混用。

### A个人日期×警示（2026-10-25）

- `prepare_sce_media_timing.py`：只投影完成日期元数据、建立个人截止与实际可见E提示，输出补标缺口；不读取本期答案，不发送API。
- `assemble_sce_media_timing.py`：594篇新标签齐备后生成四组提示、精确复用映射和56个官方Core离线单元；只准备，不启动Simulation。
- 科学包、复用语义、预算与授权状态见[本轮说明](../docs/workstreams/20261024_media_mechanism/TIMING_FACTORIAL_RUN_PLAN_20261025.md)。

- `analyze_sce_media_timing.py`：只读已完成Terminal评价缓存，按各自共同支持输出七期/2021/分月/两遍/删月/早晚日期分组，0API、0Q9新拟合。
- `analyze_sce_media_timing_conditions.py`：在同四臂支持上复算20个人口/真实上期水平条件组，记录最小单元N/ESS；不把稀疏组当因果证据。
- `report_sce_media_timing.py`：从上述聚合生成七期日期×警示图文/折线/Canvas，不重新调用模型或Q9拟合。

### 新全A个人截止T0（2026-10-25晚）

- `prepare_sce_full_a_personal_inputs.py`：82月原名单的个人日期、同步E与权重适配；按月检查点，0API、不读当期答案。
- `run_sce_full_a_personal.py`：prepare/review/watch均离线；用户确认后run/resume，单组单遍、182个精确历史回包导入、逐请求容错和一次技术补跑；主补共用$50帽。
- `analyze_sce_full_a_personal.py`：仅生成完成后在隔离进程评价，复用旧真值/缓存、统一Q8/Q9与权重口径，分同名单/完整波次/全国及48/34组合。
- 完整命令、审批和状态见[正式运行说明](../docs/workstreams/20261024_media_mechanism/FULL_A_T0_TERMINAL_RUNBOOK_20261025.md)。用户已批准，本人Terminal启动；Codex未启动Simulation，B未更改。

- `report_sce_full_a_refresh.py`：完成新版A隔离评价后，只读比较新旧全国/逐年（重点2021）、同名单微观及48/34组合；生成聚合CSV与图文，不调用API、不重拟Q9。

### 已有A82 Core＋Normal离线接入（2026-10-26）

- `export_sce_full_a_model_scores.py`：评价侧将旧混合评分缓存投影为模型专用向量表，校验原始main/repair字段，不新增拟合或API。
- `run_sce_full_a_core_normal.py`：prepare/predict，仅人口权重白名单和封存模型答卷；早48模型遮蔽选参，按原人口质量扩展98,382行，旧结果不改。
- `evaluate_sce_full_a_core_normal.py`：预测封存后打开冻结真人真值；统一全波次比较MAE/W1/IQR，另报全国headline和48/34组合。
- `report_sce_full_a_core_normal.py`：读取正式评价v3生成独立图文，不改报告v05。入口和版本见`docs/workstreams/20261026_core_normal_full_a/README.md`。
- `run_sce_recent_b_recursion.py prepare/review/replay/authorize/run/watch`：固定首月512家庭，精确复用根月，后10月只读取本人上一模拟checkpoint。复用容错队列、月屏障、每位置最多一次技术补跑、共享预算及独立后台；需本批明确授权，不能沿用旧B批准。完成后单独进程评价全国误差及模拟漂移，不按近期真值拟参。见[月度递推说明](../docs/workstreams/20261026_belief_recursion/MONTHLY_RUNBOOK_20261026.md)。

- `inspect_sce_weekly_readiness.py --out outputs/<fresh>`：零API清点候选周五日历、旧月度选稿截断数量、价格/政策/信心最后可得快照与月度先验可得日；不是周度执行包，不修改冻结月度运行。默认核202601/04/09，细节见周度设计工作流。

- `prepare_sce_weekly_release_plan.py --out outputs/<fresh>`：零API生成周度公开SCE校准时钟与每月/7、14、21日提前期评分时钟。不是LLM执行包，方向/异常阈值尚未冻结；周度个人状态执行器仍待接。
- `prepare_sce_weekly_preflight.py --out outputs/<fresh>`：零API按54格从512户根框架抽固定300户并恢复格质量，核对全47周候选新闻/基础标签、价格/信心快照与政策缺口；输出候选名单和逐周清单，不读取模型回答，不生成付费请求或最终执行授权。
# 已完成月度递推的离线漂移分析

`analyze_sce_recent_b_recursion.py --run <completed_run> --out <fresh_outputs> --report <fresh_workstream_report>`：验证冻结来源、同人前驱及实际提示，复用Q9评分缓存，生成全国误差／组合／分歧／条件轨迹。仅离线、0 API、不拟权、不改原结果。当前交付：`docs/workstreams/20261026_belief_recursion/monthly_results_v1/index.html`；计算实现位于`studies/sce_inflation_expectations/reports/monthly_b_recursion.py`。

- `prepare_sce_weekly_inputs.py --out outputs/<fresh>`：固定300户、按公开发布周期联合先验校准、47周有限阅读/完整日期E及官方Core离线验收；0付费调用。
- `run_sce_weekly.py prepare/authorize/run/watch/replay/evaluate`：独立周屏障、同人状态、主补共享预算、一次技术补跑和独立评价；实际运行必须匹配本批授权，已完成任务拒绝重新生成。见周度运行说明。
- `analyze_sce_weekly_partial.py --run-dir <run> --out-dir <fresh>`：禁网读取已封存周点；主指标只取完整月份最后预定周，保留部分月曲线，不将停机日改为月末。另输出费用/错误对账、同周期先验对照和图文读数。
- `evaluate_sce_weekly_compat.py --run-dir <run>`：完整47周后离线评价实际紧凑执行schema；只补可推导日期元数据，不改冻结输入、运行器或评分函数；不启动/续跑API。
- `resume_sce_weekly_key_limit.py inspect/prepare/run --run-dir <run>`：用户提高key限额后接续原周度批，只有附录绑定的旧403可补一次；其余新403仍停，旧35周与账本不改，最终自动接离线评价兼容入口。`run`须显式`--key-limit-raised --confirm-live`。
- `analyze_sce_weekly_final.py --run-dir <complete> --out-dir <fresh>`：完整47周后禁网核查账本/同人前驱/费用/加权统计，输出11个月主误差、提前期、转折、模拟分组和月度方案描述性对照；0API、0拟参。

## 2026-10-27 研究包更新

- `build_sce_paper_materials.py --out docs/workstreams/20261027_final_delivery/<全新目录>`：从当前已验收研究包聚合与冻结A/网格证据构建作者审阅材料册（HTML/Markdown、数字CSV、图表、来源哈希），核对指标和固定组合；不拟参、不重跑API、不重写论文。当前入口见[材料册](../docs/workstreams/20261027_final_delivery/materials_v1/index.html)。

- `build_sce_research_package.py --draft-version v06 --out <新目录> --public-log-registry <公开索引.json> --a-refresh-readout <新版A目录> --micro-data <冻结微观投影data目录>`：当前v06按职责导出，新增四个最终任务原文/答卷、A微观及A/B Normal重算。完整命令见[统一交付入口](../deliverables/README.md)。旧v05保留，不能只改ZIP名称升级。
- `verify_sce_research_package.py --archive <zip> --out <新目录>`：独立解压、隔离Python/异地cwd、源码导入审计、工程/聚合/微观复算及包内测试。v06通过独立无system-site-packages环境验收；原文/答卷范围见micro导读。

- `catalog_sce_study.py --out <新目录>`：分类开发study文件，按当前入口计算静态依赖与补充归档，不执行实验。v04为此前的依赖筛选布局；当前交付使用构建器v06和`submission_tools/release_layout.py`，按组件/运行/评价实际归位源码。以[统一交付入口](../deliverables/README.md)和`submission/latest_package.json`选包，包内`DIRECTORY_GUIDE.md`及study的`FILE_GUIDE.md`解释读法。

## 正式逐答卷与模型原文（2026-10-29）

- `export_sce_micro_reproduction.py --out <新outputs目录>`：只读正式账本，投影A/B/月度/周度答卷、原文、评价字段及Normal；私人键表不进data，不调用模型。
- `replay_sce_micro_reproduction.py --data <data目录> --out <新目录> [--refit-density]`：禁网络，检验主补字段/归一化，重算全国、A微观及Normal后验。默认精确向量缓存，选项重做数值拟合，不重新询问LLM。
- 数据范围与验收：[v06微观复现](../docs/workstreams/20261029_micro_reproduction/README.md)。
