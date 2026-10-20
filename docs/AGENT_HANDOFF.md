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

采购角色—可见价格本轮已落实为[六期完整离线提示](workstreams/20261020_procurement/README.md)：有效包`outputs/sce_procurement_price_views_20261020_v3/`，576个人月×三组×三种子共5184提示；v1因平衡失败停止，v2是共享加载格式对齐前草稿，均0调用。解析6份已有首发PDF共60项，食品6类用于角色视图，清洁/纸品/护理仅储备。原固定8新闻/先验/问卷不变，三组共同移除完整统计表；新共同背景不能复用旧回答。匹配/打乱交换整套角色/类别，接收者时间标签重算；权重排序约12人块内受限随机，18项平衡均通过，不能说无限制随机。共享加载54文件及8项价格测试通过；后续引擎验收见下段，仍未付费。脚本`prepare_sce_procurement_views.py`，模块`procurement_price_views.py`。没有改旧源文件/manifest、默认模型或配置。

后续[共用管线验收](workstreams/20261020_procurement/engineering_and_validation.md)已完成：`outputs/sce_procurement_engineering_20261020_v1/`，一个分配种子20261019、六期×三组18单元、1728脚本动作、0模型请求/费用。新增`procurement_price_engineering`准备适配和`engineering_only`模式，run与研究evaluate明确拒绝该包；没有真人真值输入。共用worker/评价器/CLI做小范围改动前206份Python源已保全在`outputs/sce_shared_runtime_snapshot_20261020_before_procurement_engineering_v1/`；旧manifest未改，旧结果须用冻结源。原5,184提示包与三种子加载事实不变，其他两种子未引擎验收。

今日官方免费证据仍为`data/raw/mcp_checks/2026-10-20_procurement_free_v1/evidence.json`，user_pool_mcp1.27.0，实际gpt-4o-mini，别名不等同执行模型。用户提供参考文档库后，通过浏览器核六份在线正文并保全在`data/raw/mcp_checks/2026-10-20_official_model_docs_v1/`：框架确实支持文件P和逐人信息，LLM读自配凭据；平台Sim覆盖模拟/MCP，但未说明本地额度网关；在线FAQ明确界面暂无数据上传/研究包下载。外接GPT通道或团队导入study仍须确认。已收窄[待平台确认项与未发送草稿](workstreams/20261020_procurement/platform_gpt_requirements.md)，不再泛问框架能否自带P/E。无新付费、账号操作、平台消息或运行任务，不重复MCP目录请求。浏览器标签组“SocioVerse接口核查”只打开官方公开文档，未关闭（等用户要求）。

用户随后批准[10人技术试测](workstreams/20261020_procurement/official_pool_pilot.md)及$0.10上限。v1免费能力查询连接中断、0模拟请求；免费恢复后原协议/输入/批准复制至`outputs/sce_platform_survey_pilot_20261020_v2/`，唯一一次模拟工具请求返回`status:error`、`ValueError: questionnaire[0].options must contain at least two options.`。外层`isError=false`不能视为成功。返回逐人回答0，不能评价GPT准确度；实际扣费未知，$0.04只是原计划估算。无付费重发、无扩样/换模型，当前任务已停止、没有运行进程。原始回包与`inspection.json`本地保存；公开技术摘要`official_pool_pilot_result_v1.json`。数值开放题/Q9概率分配及本地同输入仍须官方确认，不能靠添加无意义选项或以单选代替十档概率“跑通”。不发送真实SCE个人资料，不用平台Chat。已有批准为这一笔已执行尝试，不继续复用。

用户质疑后已补查[使用规范及候选](workstreams/20261020_procurement/platform_gpt_requirements.md)：免费MCP资源/提示目录均为空，旧官方经济问卷17题均choice但字段属旧版，不能推定新接口只支持单选。原失败仅验证options为空被拒绝；Q9可以把真实十档放入options并在正文要求概率，候选`native_questionnaire_candidates_v1.json`已准备、未执行。建议下一次先1人Q9检查实际回包形态，再谈Q8数值幅度与逐人同输入；新增付费调用需另确认。不要将未测试的候选写成兼容成功或直接判死，也没有改变旧试测协议和结果。

上述候选随后按用户“尝试另一候选”明确授权完成：`outputs/sce_platform_native_q9_pilot_20261020_v1/`，1人/1次Q9请求，十个真实区间作options。接口status=ok，输出1行、服务模型gpt-4o-mini、耗时15.956s；答案仅`answer:A`＋reason，无十档概率。公开摘要`native_q9_pilot_result_v1.json`。新增估$0.004，和旧请求保守预留合计$0.044，原$0.10累计上限不变，实际扣费未知。无自动重试、Q8/扩样/换模型，当前无运行任务。8项定向检查通过。修改共用MCP试测适配前旧源码保全在`outputs/sce_platform_survey_pilot_source_snapshot_20261020_v1/`；旧协议/回包未改。尚不能区分服务提示/模型响应/解析层原因，不能称GPT不能分配概率；下一步需概率/数值题型及原始模型文本或本地同输入路径，不再盲目调选项。

用户再要求试OpenRouter Qwen/LLaMA，已执行独立公开格式检查1次：`outputs/sce_openrouter_q9_format_20261020_v1/`，Qwen2.5-72B/DeepInfra-fp8、温度0.5、JSON模式、max_tokens1024、无重试/供应商回退。收到十概率[15,25,30,15,8,4,2,0,0,1]、合计100，模型/供应商匹配，6.632s、API报告$0.00015372。题目写q9.bin1，模型用平铺键；原读取器预期嵌套报KeyError，原inspection保留；零API确定性字段嵌套后共用校验通过，未改概率或归一化。新读数`offline_key_readout.json`，公开`openrouter_q9_format_result_v1.json`。新入口`check_sce_openrouter_q9_format.py`复用原路由/预算/Q9检查；不重启旧批。沿用旧OpenRouter$1累计上限、此前估$0.200809，本次$0.01子上限；不与MCP$0.10混账。本次仅格式可行，不证明拟合更好、99%稳定或MCP限制原因。无任务运行，下一步可将本地官方引擎＋Qwen作为采购角色机制候选，另冻结新批次。

用户要求的无答案数值结构示例已实现于`output_format_example.py`，完整Q8/Q9及仅Q9模板见[阅读版](workstreams/20261020_procurement/output_structure_example_v1.md)。十个bin全展开、不含概率答案；追加时不改变原消息，3项定向检查通过。新Qwen公开prepare已接入：`outputs/sce_openrouter_q9_structure_preparation_20261020_v1/`，未授权/执行、0新增API；只确认格式准备，不称实际遵循率提高。修改已执行探针脚本前保存旧源至`outputs/sce_openrouter_format_source_snapshot_20261020_before_template_v1/`，旧协议/答卷未改。当前原采购输入仍冻结不覆盖，下一批需三组统一追加同版模板并另封存，避免混淆机制效应。

该新模板包随后按用户“用新的提示词再尝试”明确授权已执行一次：`outputs/sce_openrouter_q9_structure_preparation_20261020_v1/`，直接嵌套q9下bin1..10、概率[10,20,30,20,10,5,2,1,1,1]合计100，严格读取器通过，0字段转换/概率修补/归一化/重试。Qwen2.5-72B/DeepInfra-fp8、温度0.5、JSON模式及1024上限与前试相同；原问题完整保留，只追加855字节结构说明。9.667s、522/97 token、API报告$0.00022672；沿用OpenRouter累计$1及$0.01子上限，不扣平台额度。前述“未执行”是准备时状态，以本段和`format_readout.json`为准；公开`output_structure_result_v1.json`。只证明本次格式可行，不能估计稳定率或拟合效果。当前无任务运行，不再调用该已执行包。

采购角色Qwen新批已按用户“开始”推进至待预算确认：`outputs/sce_procurement_qwen_trial_20261020_v1/`，六期96人×三组×两遍=3,456请求。已统一追加完整无数值模板，固定OpenRouter→DeepInfra/fp8 Qwen2.5、温度0.5/1024上限/无重试。202206/202503各12人三组两遍共144次技术段，从原96人按固定哈希选取；仅完整且>=99%严格合法时进入其余3,312次，前段计入全样本、不重复调用，不按拟合成绩选配置。48个分段引擎单元/3,456脚本动作、23项定向检查通过，实际输入哈希一致、真实调用0。估$3.3254、保守预留$14.332412、拟上限$16，授权文件仍false；不沿用旧$1授权。源码修改前208文件保存在`outputs/sce_shared_runtime_snapshot_20261020_before_qwen_procurement_v1/`，旧manifest不改。新可选分段维持旧协议默认路径，main直接worker也不能绕过技术门槛；评价合并互斥分段并固定匹配减打乱。详[本轮计划](workstreams/20261020_procurement/qwen_trial_plan_v1.md)。用户随后明确批准完整范围和$16；授权已登记。144次技术段运行中：首次调度一个免费目录GET重置、0该单元模型调用，36份已完成回答保留，仅继续尚未发送的108份（`unused_gate_continuation_v1.json`），不是重发或旧Qwen批续跑。main尚未启动，必须等完整技术段并达到99%。

**上述本批现已结束：**144请求全部完成、0模型接口错误/付费重试，嵌套十档/数字Q8/正常结束均144/144；概率和合法140/144=97.22%，未过99%，技术门槛false、main 0单元/剩余3,312未启动。共同背景48/48、匹配44/48、打乱48/48；4份均在匹配组，3份95/1份105，仅技术描述不作机制因果。API报告$0.12921944，首末模型调用跨度356.5s；一个免费目录GET错误发生在0该单元模型请求之前，36份原答保留，只继续未发送108，不是付费重试。报告`outputs/sce_procurement_qwen_format_readout_20261020_v1/`、公开[技术结果](workstreams/20261020_procurement/qwen_format_gate_results_v1.md)；`stopped_after_technical_gate.json`已保存，没有运行任务。原批准仍是历史收据，不能绕过门槛自动开main；如要反馈纠错需另明确设计及调用，不能把4份直接归一化后称原始合法。尚未读取本期真值/计算机制拟合。

**用户后续已明确修正上述禁止归一化的约定**：概率加总偏差等比例归一化，不因其卡流程。新包`outputs/sce_procurement_qwen_trial_20261020_v2/`只复用原144份、继续未发3,312，原提示/参数/三组/总3456及$16不变。纯派生层`q9_normalization.py`仅对齐全/有限非负/正合计计算100*p/s，保留原答、原状态、零值/比例/Q8；缺档/负数/零和不构造。新技术口径144可用/140原始合法，原v1门槛失败不改。36新引擎单元+12原收据、31测试通过，组合保守$13.86081，授权按原明确范围预算+此次直接指令登记。修改前210源码在`outputs/sce_shared_runtime_snapshot_20261020_before_normalization_v1/`，旧manifest不改。新协议最多16单元并发；本批开始前免费目录统一封存、worker不重复GET，锁路由价格不变。尚未新调用；接下来run --phase main --workers16，完成后新evaluate及归一化/原答敏感性，详[规则](workstreams/20261020_procurement/qwen_normalization_amendment_v2.md)。此前“不得归一化/不得开main”仅属原v1历史，不可忽略用户本次修正。

已有ATUS 2016/2022/2023文件和字典在`data/raw/behavior_references/2026-10-19_atus_roles_v2/`及同日supplement目录；不要重复下载。2022→2023采购角色预测支持不等于SCE预测收益；whole-residence人数、未知儿童/搬家/信息年龄按原规则保留。金融决策者不等于购物者，CE汽油支出不等于本人驾车。

本地路由补查与BLS分类表解析已完成，不重复抓取。食品角色只说明采购分工，不识别本人价格；0/1/3/6/6可见条数是实验假设，不能按结果反选。六期仍是开发期，尚未登记独立验证月份。新闻随机分配保留独立验证候选，不按六期真值调篇数或挑分配种子。

[财经关注文献](literature/sce/information_exposure/news_attention_demographics_20261019.md)已核8项一手材料，人口关联不能直接当个体数量定律。Kimi新[六项更新事实](workstreams/20261019_updating_facts/README.md)已交付但本线未做完整独立复核，不直接据此设置回摆系数。

## 4. 协作与保护

- 开工看git status，保留用户及其他Agent改动。`docs/sources/sol_handoff_protected_files_20261010.json`记录15项保护文件；其中DECISIONS、提案、P/计分等仍有原未审改动。**不得改写、提交、还原或混入本次提交。**未提交A/B契约亦属保护范围。
- 不动其他线`20261019_updating_facts`的代码和文档。公共页一次由一位Agent整合，不跨线程自行发消息或重复审计。
- scoped add、每批本地提交；推送另按用户授权。Git状态和本地提交不等于远端已备份。
- 源数据/历史输入/源码/冻结manifest不因整理而改写。只更新当前页对应条目，不再每轮在交接页前面堆多段“最新”快照。

本轮已完成总纲/索引、任务/交接收束及37份历史文档归档；保护及扫描到的冻结路径未变，没有新增API调用。治理记录见[整理记录](reviews/20261019_repository_cleanup/README.md)；历史资料见[归档索引](archive/2026-10/README.md)。
