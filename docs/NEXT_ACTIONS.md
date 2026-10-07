# 当前任务板

- **2026-10-07 E跨年资料扩展完成（本轮主线）**：见[SCE_ENVIRONMENT_EXTENSION_20261007](SCE_ENVIRONMENT_EXTENSION_20261007.md)。2022候选包`outputs/sce_e_extension_20261007T081207Z/`，12步每步77数值/30新闻；46份BLS、115分项全部官方网页核对一致。新入口只追加原始缓存、隔离候选；旧能源匹配8项2022错误已在新入口修正，就业“remained at”解析补齐，61 tests＋9 subtests。ConsumerSim新闻方法披露不完整，用户决定暂缓高阶新闻基线，不安装句向量/情绪模型。**下一项**：补2019–2020历史支持及2023–2025-10资料，另建A/B截止包、解决汽油/新闻版本证据，再拟长跨度运行卡；资料扩展不等于冻结新测试期或预算。新LLM/付费MCP为0，未改正式模拟配置，Kimi待审批次保留。

**2026-10-07 新偏好与划分澄清**：[句向量与训练/评价说明](SCE_NEWS_EMBEDDING_AND_SPLITS_20261007.md)。用户暂不采用TF-IDF；下一项在独立项目环境验收固定本地编码器（候选MPNet），逐篇编码/长度审计/缓存，再补历史E并登记训练、验证和滚动评价日期。日期示例未冻结，不改变旧协议；新基线尚未训练，零API、未下载模型。PCA/标准化不得看评价期；既有AR/ARX当期真值未进当次拟合。

## 2026-10-07 同信息比较与长期模拟（最新）

- **已完成，零 API**：[方案与Core规模实测](SCE_FAIR_BASELINES_AND_LONG_RUN_20261007.md)、[可打开HTML](SCE_FAIR_COMPARISON_20261007.html)。共同E导出12月×77列/同新闻；全年Core网格1800组，已有两月LLM回答下采样240组。21项定向测试与独立数值核验通过。建议300 Core全年＋完整Normal，规模敏感性复用回答；未冻结预算、未新增真实调用。
- **下一优先**：补至少36个月的历史共同E训练窗及对应已发布SCE标签；汽油推定日期/未验历史版本补证或共同隔离。以原cutoff物化，再实现全宏观Ridge→宏观＋新闻Ridge→宏观SARIMAX；训练内选参数与文本词表，不用2021这12点拟合再宣传样本外。
- **随后**：全年A新运行卡/提示预览/干跑，固定300 Core、PE v2、温度0.5等候选并明确模型、评价用途与预算后授权执行；同模型直接预测作为新付费对照另卡。新版全年不能与旧73人旧E结果拼接。
- **持续保留**：共同月份与信息权限对账、A微观同计分评价；B另建截止前P/E，不混入A当期画像；Kimi10-03未审文件不提交/还原，提交 scoped add。

**2026-10-07 最新范围基线与方法解释已完成。** 读[学习方式、训练/回测与最新结果](SCE_BASELINE_METHODS_AND_LATEST_20261007.md)、[浏览器版](SCE_BASELINE_LATEST_20261007.html)。全国到2026-08（80月），微观到2025-10（70月）；2025-11无CPI发布日，月中参照只79月并报缺口。AR/ARX逐月按可得历史最小二乘；规则更新率/人口分组未训练调优。是滚动样本外回测，没有单独调参验证集，不冒称Agent盲测。持续性上月末MAE0.304、AR(1)0.346；原60月预测逐条不变，16项测试通过。完整run `outputs/sce_baselines_20261007T055057Z_f99c2f6b/`；零新增LLM，Kimi待审批次保护。下一项仍是同计分微观Agent评价与独立机制验证，不直接扩大调用。

**2026-10-07 评价澄清与可直接打开的结果页。** A全国拟合仍为必要检验；已给定中位数不算独立证据。逐年并非唯一切片，已补6/12月滚动诊断。300 Core＋Normal两月全国首发口径MAE0.989，与同月持续性1.000接近；信息权限不同、仅开发参照。60月不是数据上限，本地latest快照到2025-10。读[结果报告末节](SCE_BASELINE_RESULTS_20261007.md#7-2026-10-07-补充共同月份比较与数据范围)、[浏览器HTML](SCE_BASELINE_REVIEW_20261007.html)。零新增LLM；现有完整微观Agent评价适配和独立时期验证仍待做，未扩展到2025/未改旧配置与计分。Kimi待审批次继续保护。

**2026-10-07 统一评价 v1 与五年基线已实现。** 先读[评价契约](SCE_EVALUATION_CONTRACT_V1.md)、[60月结果与验收](SCE_BASELINE_RESULTS_20261007.md)。2020–2024：全国持续性 MAE 月中0.240/上月末0.322pp，AR(1)0.274/0.380；ARX需同窗口比较。A条件统计的分组中位数误差0.588→0.475，W1约0.505→0.504；不能混称B实时结果。正式run `outputs/sce_baselines_20261007T041750Z_5973bbf9/`；官方派生A真值、首发全国B真值、近似计分Agent评价分别标版本。15项测试通过；新增LLM/付费MCP为零，未改运行配置/计分器。来源台账支持仅凭仓库复算全国结果。下一项转换现有Agent输出，按共同月份和同计分评价；长期LLM实验仍需独立冻结输入、窗口与预算。Kimi待审批次继续保留，提交 scoped add。下文“未实现基线/契约”是历史状态。

**2026-10-07 新增：评价与基线设计稿。** [明确评价目标与基线](SCE_EVALUATION_BASELINES_20261007.md)已核对官方Q9定义及经典信息/经历学习论文。建议A以未给定的人群结构为主，B以全国指标跨月MAE为主并检验分布；逐人误差辅助。下一项零API写评价契约与数据使用登记，依次建立持续性、AR(1)/ARX、条件统计、适应性规则Agent，经典Carroll等后续补充。跨期基线代码尚未完成；不把已有两个开发月当正式测试，不改旧筛查或运行配置，不冻结新指标/预算；Kimi待审批次继续保留。

**2026-10-07 开题已由用户确认提交；下一步转向机制验证。** [各环节差距、改进与验收](SCE_IMPROVEMENT_PLAN_20261007.md)。主要瓶颈为预期水平偏低、群体回答过窄，篮子/Q1/单类信息小试均未稳定改善；下一项先零API明确评价目标及共同背景＋个体价格视图，再分别做模型响应与信息匹配对照。新试验以群体分布/关系为主要评价、逐人误差辅助是待审建议，不追改旧试验结论。A约束重建、B截止前预测分别设计；新配置及预算未冻结。平台回执待本地归档，不能写成未提交。Kimi待审批次继续保护。

**2026-10-07 开题提交版已准备（提交前历史记录）。** [两页PDF与唯一入口](../proposal/README.md)、[结构检查与微调依据](../proposal/submission_review_20261007.md)。沿用原六节/排版；按用户意见进一步理顺十一处段落，明确合成篮子的依据、用途与验证，以及模拟/真实SCE趋势方向一致但水平偏低、分歧不足的发现，将问题与解决思路衔接；第四节已补充SCE/CE/BLS/EIA/NYT具体来源与用途，区分已使用和待研究资料；官方1–2页及≤20MB要求覆盖，最新两页约0.25MB，逐页视觉核验通过。提交文件 `proposal/build/socioverse_challenge_proposal_20261007.pdf`；截止10-12 23:59北京时间，用户在研究目录参赛入口上传并留回执。尚未确认平台提交；Kimi待审原稿未动，研究配置不变。

**2026-10-06 E/P 信息接触对照已完成。** [结果与准确路径](INFORMATION_EXPOSURE_RECEIPT_20261006.md)。48人×两月×三组=288真实回答全部合法，无重试，参考价估算$0.135045；34定向/回归测试与288官方scripted轨迹通过。匹配组Q9 IQR比共享组增加（0.66→1.76、1.30→2.88pp），但个人MAE更大（4.05→4.66、4.74→5.10pp），匹配未稳定优于随机；不升级主方案。分析包 `outputs/sce_exposure_analysis_20261006T151924Z_47735326/`，5/6月Q9共同比较47/48人。下一步先离线设计“共同背景＋个体价格接触/新闻”，调查频率依据，不能直接扩大此遮罩。此次$1授权实验已结束；新实验独立冻结。Kimi未审批次继续保护。

**2026-10-06 Q1真实对照已完成：** [实验结果与路径](HOUSEHOLD_STATE_PILOT_RECEIPT_20261006.md)。用户新授权后执行200调用/200合法回答，温度0.5、无重试，参考价估算$0.179942。5/6月个人MAE 3.5244→3.6038 / 3.7108→3.7260，群体差距局部改善但分散度不稳定，不升级Q1为主配置。严格配对50/49（6月1条真人原始Q9无效）；完整月真值默认路径已修复，未重新模拟。下一步先准备未知财务属性占位对照，心理模块另验；本轮不扩大调用。旧文待授权/未运行均为历史状态，Kimi未审批次继续保护。

**2026-10-06 Q1单模块已接线：** [对照运行卡](HOUSEHOLD_STATE_RUN_CARD_20261006.md)。完整月人口按Q1五类每类10人，两月各50人，同人两组共200份提示预览；只新增当月自报财务变化，CE/幸福/满意/Normal扩展不启用。17项相关测试、100条SocioVerse规则式轨迹及实际Q1观察通过，新增模拟API=0。总上限$1/最多200次无自动重试，新数据发送和预算确认已向用户发出，尚待答复，不能从运行命令中推定授权。准备包`outputs/sce_q1_trial_20261006T142504Z_a6740800/`，默认prepare；获得授权后execute并用`analyze_sce_household_state_trial.py`配对评价。A开发诊断不代表全国、B预测或因果；Kimi待审批次未动。

**2026-10-06 最新离线成果：** [家庭状态审计与五套心理画像验收](PSYCHOLOGICAL_PROFILES_ACCEPTANCE_20261006.md)。数理五题复算315/315一致；GSS2018两题联合2336人，合成完整月人口五套侧车，5/6月1211/1278人有心理值、23/19人未知。财务明显变差组预期更高，仅开发月相关性。已更正教育/收入非空≠有效覆盖。9项定向测试及原始donor核对通过。下一项Q1模块单独接线、实际提示预览和运行卡，心理模块另做对照；正式P/E/B、Normal扩展、计分/开题与Kimi待审批次未改，零新增模拟API。旧文“未实现/未下载”为历史状态。

**2026-10-06 额度接力记录：** [下一次执行顺序、预期效果与依据](literature/sce/psychological_attributes/NEXT_SESSION.md)。先做已有SCE Q1/数理字段离线诊断，再做GSS2018联合样本支持；通过后才构建侧车、申请新对照实验。本条保存工作状态，不代表启动模拟或冻结配置。

## 2026-10-06 最新：心理与家庭状态专题调研

三名 Luna Max 并行研究理论、数据和合成方法，主 Agent 交叉复核；成果见 [唯一入口](literature/sce/psychological_attributes/README.md)、[整合综述](literature/sce/psychological_attributes/literature_review.md)、[实施草案](literature/sce/psychological_attributes/implementation_proposal.md)。优先检查已有 SCE 财务经历 Q1 和 numeracy；GSS 幸福/财务满意联合 donor 暂作探索，不视作稳定人格或已验证机制。下一项是零 API 的字段覆盖/关系诊断与 donor 共同支持审计，再生成多套合成侧车；通过后才拟新实验卡。心理合成器、Normal 心理扩展尚未实现，未新增模拟 LLM/付费 MCP。较早模型对照仍是单独候选，不与心理新增一起改。2021-05/06 已是开发数据，不作独立测试；A 重建与 B 事前可得性分别声明。Kimi 未审批次继续保护，以下较早条目保留追溯。

## 2026-10-06 最新：真实价格体验五组小试完成

200 次 DeepSeek 调用全部有效、无重试，用量保守估算 $0.185111。实际提示与冻结预览逐条一致。每月20人同人五组，对应真人等权评价；篮子/排序尚无稳定改善，Q9人群IQR仍不到1pp，真人约5.2/5.4pp。见 [完整记录及文件路径](PRICE_EXPERIENCE_PILOT_RECEIPT_20261006.md)。**暂不扩跑五组300人**；先固定条件做较早模型的小试，另申请 OpenRouter 授权/预算；同时离线审查环境专家叙述及信息相关性。计分器、Normal及Kimi待审批次未改。下方“尚未授权/运行”为历史状态。

更新：2026-10-06（价格体验机制 v1 已完成离线落地与工程验收；旧 D050/D051/D052 和既有真实实验保留）。只推进 SCE；队伍名为水上挽月。日期以 [ROADMAP](ROADMAP.md) 为准。每项任务只标真实进度。

## 当前接力：价格体验对照 + T01 方法研究 + 提案审定

- **2026-10-06 消费背景数据扩展（零新增模拟 LLM / 付费 MCP）**：见 [唯一数据入口与验收](CE_CONSUMPTION_DATA_INDEX.md)、[执行计划](CE_DATA_BUILD_PLAN_20261006.md)。Interview ZIP、官方 XLSX 字典、Diary ZIP 和收入分组年表各有独立原始存储与哈希。两月完整人口 1,234/1,297 人均有篮子，按既有 Core 分成 300+934 / 300+997；两月 300 Core 的分配与 v1 各 300/300 一致。篮子审计覆盖真实 CE donor 复算、完整 ID/画像、回退、候选支持及调查加权分布；两月 1,051 个匹配特征未变的重复 ID 篮子全不变。本轮仅 A 后验代理，不声明 B 线历史可得。Diary 周记录按本调查 FMLD/EXPD 联结，购买日数与缺失单独保留；不能与 Interview 跨调查逐户联结。Normal 已具备篮子输入，**答案扩展算法仍未改**；下一项是五组真实小试，以及独立设计篮子条件 Normal 扩展。旧运行、旧配置、计分器和 Kimi 待审批次保留。

- **2026-10-06 机制 v1 已完成（零新增真实 LLM / 付费 MCP）**：见 [使用入口](PRICE_EXPERIENCE_MECHANISM.md)、[工程验收](PRICE_EXPERIENCE_ACCEPTANCE_20261006.md)、[真实对照运行卡](PRICE_EXPERIENCE_RUN_CARD_20261006.md)。官方 CE 2020Q4 5,203 条可用联合记录，为两月各 300 人分配合成篮子；构建侧车、四臂配置、个体信息视图和实际 LLM 提示词接线已实现。保留 77 信号/30 新闻，4×300×2 实际提示预览同公共事实、同问卷；48 项相关测试及两月 600 条框架观察/规则式记录通过。规则式答案不使用该机制，不能充当效果验证。仅 A 后验代理，TOTEXP 份额不是个人 CPI 权重；不强制角色、注意系数或答案高低。现成侧车与 20 人小试包在 `outputs/price_experience_20261006_v1/`，准确路径见入口。两个 Luna Max 子 Agent 完成 [CE 可行性](MECHANISM_DATA_FEASIBILITY_20261006.md) 与 [输出诊断/独立实现审查](MECHANISM_OUTPUT_DIAGNOSTIC_20261006.md)。计分器、Normal、提案和 Kimi 未审文件未动。
- **下一项优先：五组真实小试（尚未授权/运行）**：两月各固定 20 人，对照旧 v2-abstract 与四个新臂，共 200 条目标回答，最多 400 次尝试；建议新总上限 $2，各“月×组”$0.20。运行前核对模型/价格、数据发送范围并获明确新授权。先看原始 Core 的水平、分位数/尾部、Q8 格式、个人 Q9 支持档数和模板复用；不以方差增加为成功、不用 Normal 隐藏误差。若有可解释改善，固定设计后换独立月份验证，再扩大到 300 人及 donor seed 敏感性。B 线、跨月状态、购买频率和格式实验分别开发。

- **2026-10-05 并行文献研究首轮完成**：三名 GPT-6 Luna Max 子 Agent 分别研究预期形成、家庭价格体验、Agent × 经济学；主 Agent 核对 SocioVerse/ConsumerSim 案例并整合。[文献入口](literature/sce/README.md)、[中文综述](literature/sce/literature_review.md)、[改进方案](literature/sce/research_design.md)、[原文阅读指南](literature/sce/reading_guide.md)。共登记 28 条来源（23 项论文/报告、5 项案例/代码/数据资源），14 份公开 PDF 已本地归档；原文在 `data/raw/literature/sce/20261005/`，Git 只备份笔记、来源和哈希。全文与摘要/预览分别标明；没有修改实验配置、运行源码或开题，也没有新增模拟 LLM/MCP 付费调用。方案尚未冻结。
- **10-05 的机制准备计划（10-06 已完成，保留追溯）**。① 检查已保存回答的圆整、Q9 概率模板、分位数与新闻/指标引用；② 核查 SCE–CE 的共同字段、版本、联合样本支持与合成篮子假设；③ 做同人同事实的当前标题＋摘要/易读居民表达样例，准备固定模型/P/E 的最小对照运行卡。依据价格体验研究补变量，但不按性别或就业确定购物/开车角色，不以加噪声或统一抬高答案作为成功标准。后续再依独立月份结果决定是否加入个体观察视图、跨月状态或校准；A 重建后验约束与 B 预测信息截止分别声明。

- **2026-10-05 开题排版按用户要求更新**：正文首行缩进两个汉字；中文楷体、英文数字 Times New Roman、1.25 倍行距；P/E/B 表格加完整边框并调整列宽。A4 两页，验证方案从第二页开始，PDF 已视觉核验；正文内容不变。复用 `python3 proposal/render_proposal.py` 生成同名候选 PDF，未提交平台、未新增 API 调用。

- **2026-10-05 用户修正开题写作要求，已落实**：开题面向评委，沿用原 `proposal.md` 的标题、六节和 P/E/B 表格，只更新陈旧进展与核心经济学认知；不在正文罗列具体模型、人数、用量或内部截止日期。当前 [候选稿](../proposal/proposal_submission_candidate_20261005.md) 已依原稿重修并导出、视觉核验为 2 页。上一个较大改写的候选已本地归档，原待审批次未改。模型/参数/费用仍留在实验文档；未来 Agent 继续按原稿框架更新，不重新构造报告体系。候选尚未提交平台。

- **2026-10-05 开题候选与机制诊断完成（零新增 API）**：见 [机制诊断及 CPI 对照](INFLATION_MECHANISM_DIAGNOSTIC_20261005.md) 和 [两页提交候选](../proposal/proposal_submission_candidate_20261005.md)。当前流程已贯通，但有效性及干净包独立复现未完成；价格体验优先调研，收入/教育的作用不能直接否定。模拟未贴合后来实现的 CPI，不能据此证明或排除训练记忆；输出理由频繁使用暂时性/基数效应叙述，且 E 本身含对应观点，应区分共享信息影响与参数知识。开题可固定问题/框架/验证计划，把瓶颈作为研究任务；提交候选 PDF 已视觉核验为 2 页，未提交平台。原待审稿与旧 PDF 保留，正式参数未冻结。下一步先由用户审阅开题，同时梳理价格体验与信息形成文献、检查新闻相关性规则，再设计小额受控对照，不新增付费调用。

- **2026-10-05 两月真实 LLM 开发实验完成（Codex）**：见 [真实实验记录与文件路径](CORE_NORMAL_LLM_RECEIPT_20261005.md)。按月 300 Core，最新标题＋摘要 prompt，DeepSeek 官方 API；600 次调用、600 条有效回答，无重试，保守估价 **$0.536425**（非正式账单）。5/6 月技术审计、同人日期分组、联合 Normal 扩展、全月同计分器对照均通过；Normal 分别 934/997 人、不增加 API 调用。扩展 Q9 **2.965%/3.858%**，真实全月同计分器 **4.000%/4.802%**；总体偏低且人群分歧过窄。扩展较直接加权未稳定改善，保留两者，不调参挑优。下一步先做零 API 的回答集中方式与输入关系诊断，再提出固定 P/E 的小型对照；不自行扩大付费范围。两月均已获明确范围授权，6 月曾被拦截后补充答复并通过。Kimi 待审批次继续保留。下面的“待授权/未运行/真实调用零次”是较早阶段记录，以本条为准。

- **2026-10-05 Core/Normal 开发版已完成（Codex，零付费）**：见 [验收与结果](CORE_NORMAL_ACCEPTANCE_20261005.md)。新增 study 内联合回答经验收缩、离线诊断与已完成 Core 运行扩展入口；5/6 月已将规则式 300 Core 扩为 934/997 Normal，完整人口保持 1,234/1,297。独立核验联合 Q8/Q9、ID、概率和、权重守恒及源码；20 项定向测试通过。200 个离线 Core 抽样、600 组收缩敏感性结果显示扩展未稳定超过 Core 直接加权，后者保留为必要基线，参数不冻结。Normal 不读取真实答案校正水平，不声称增加独立信息或恢复个人心理；本版本仅 A 线、按月独立。下一轮建议按月 300 Core×两月、最新摘要 prompt，预算总 $2（每月 $1）及数据发送目的地待明确授权，见 [候选运行卡](CORE_NORMAL_RUN_CARD_20261005.md)；旧 73 人计划未执行，不混作新范围。Kimi 待审批次继续保留。

- **2026-10-05 真实开发运行启动被自动审批拦截**：用户同意尝试并询问成本，已核实官方价格并解释 73×2 开发检查、单次预计 $0.00093–0.00156、正常整轮 $0.14–0.23、建议 $1 上限。自动审批要求明确确认本批画像/环境提示词发送至 DeepSeek 及预算，已补问；命令未执行、真实调用仍为 0。运行卡记录此状态，得到明确答复后使用新 run_id 执行，不绕过拒绝。

- **2026-10-05 按月 P、运行与 Analysis 已验收（Codex，零付费）**：见 [本轮验收与接力](MONTHLY_POPULATION_ACCEPTANCE_20261005.md)。已生成两月完整人口与 300/500 人候选包，支持独立随机及固定随机优先级选样；画像按月更新，搬家后旧住房不直接沿用，真实权重/答案留在评价层。4 次 300 人单月规则运行共 1,200 条有效回答，实际 P/E 注入通过核验；后两次还保存并核验执行源码。评价入口已匹配 73 人两月 146 条、月度 300 人各 300 条真实问卷；完整两月评价数据共 2,531 条，官方派生值聚合对账通过。定向测试 42 项通过。运行入口可切换月包路径，新增生效配置与源码快照，并修复调用前预算预留。最新摘要版真实 LLM **尚未运行**，按 [运行卡](DEV_RUN_CARD_20261005.md) 待用户确认建议 $1 上限；正式规模、Normal 投影与预测线 P/E 未冻结。另有 [开题修订草稿](../proposal/proposal_track_a_revision_20261005.md) 待用户审阅，原提案和 Kimi 待审批次保留。

- **2026-10-05 下一步已启动：P 离线抽样检查完成（Codex）**：见 [执行计划与本轮结果](NEXT_EXECUTION_PLAN_20261005.md)。新增 `scripts/check_sce_population_precision.py`，开发月 2021-05/06 分别使用完整 1,234/1,297 人抽样框；73/100/300/500 人、简单随机/年龄×教育×粗就业分层、每项 200 次，共 3,200 次，无 API 调用。只按人口属性选样，选样后才用真实官方 Q9_mean 诊断；聚合按调查权重×抽样概率倒数。简单随机 100 人的月度中位数平均绝对偏差约 0.56pp，300 人 0.28–0.36pp，500 人 0.16–0.23pp；分层并不始终改善。四项定向测试通过，固定 73 人面板差与旧审计一致。证据 `outputs/population_precision_20261005T042754Z_64e2388c/summary.json`。下一步实现 A 每月完整人口框/代表性抽样和独立评价权重，再做最新摘要版小额开发运行；73 人继续仅作工程诊断。未冻结正式规模，未改运行配置，未触碰 Kimi 待审批次。

- **2026-10-05 开题与官方赛道 A 对齐（待合并到提案）**：把同一 SCE 目标明确写成两项可分别评价的研究任务：A 线用已知历史人口/环境重建月度微观分布，评价未作为约束的分布、人群差异和跨期变化；B 线只用 t 截止前信息预测 t+1 的 SCE 回答/统计量，与上期值及简单宏观基线比较。两线 P/E 和结果标签分开，不能把 A 线的回顾性输入声称为 B 线预测。P 的下一步是 A 月度完整样本加权或代表性抽样、B 用已公开资料生成轮换人口；实验仍须报告群体/地区/时期误差。E 与 P 的机制聚焦个体价格暴露和新闻注意力，相关假设要通过同 E、同 P 的对照与消融验证。官方 Case 6 PMI 只作为“主体状态更新—带截止日的信息—问卷聚合—独立验证”的结构参照；其月内 21 日 nowcast 截止、300 家企业规模和企业经营机制不移植到 SCE 的 t→t+1 B 线。当前提案 `proposal/proposal.md` 属 10-03 用户待审未提交批次，本轮不直接覆盖。官方依据：https://socioverse.fudan-disc.com/challenge/ 。

- **2026-10-05 A/B 人口与答题时间澄清（待实施）**：2021 全年完访固定面板实测为 **73 人**，保留为运行/跨月诊断，不作全国代表性主样本。已有离线审计 `outputs/population_review_20261003T062417Z_2116848b/summary.json` 显示，这 73 人的真实 Q9 加权中位数在 2021-01/02 比全月完整样本分别高 **2.197/2.153 个百分点**，5 月相同、6 月低 0.415 点；仅此已说明主样本不能直接沿用。A 线可用目标月完整 SCE 微观人口与调查权重构建或加权抽样 P；Q8/Q9 答案仅留评价层，正式效果评价前先离线量化人口边际与轮换差异。B 线在 t 截止时不能使用 t+1 真实受访者名单、画像、权重或作答日期；用截至 t 已公开的人口资料和历史轮换/答题日分布构建合成 P。B 线预测整月统计量时可统一以 t 截止，不必猜未来具体作答日；若另做月内逐日 nowcast，才从历史可得的经验日分布抽样，并按各信号真实发布时间筛选 E，不能默认均匀分布。[纽约联储 SCE FAQ](https://www.newyorkfed.org/microeconomics/sce/sce-faq)说明核心微观数据滞后九个月公开，SCE 每月约 1,200 位受访者、持续轮换。人口方案应在主规模付费运行和正式效果结论前确定；73 人小样可只作工程检查，不据其误差定论。现有运行配置不变，未运行真实 LLM。

- **2026-10-05 用户修正开发月方案**：主提示词为 `sce-q8-q9-v2-abstract`（新闻标题＋摘要），开发月先做单臂 73 人 × 2021-05/06，不再把标题版对照列为必做；LLM 入口默认已改为该版本，正式命令仍须显式记录 `--prompt-version`。暂不切换 Sim Model，沿用已连通的模型，具体模型和费用上限在真实调用前核定。早答者先按真实 `survey_date` 与统一 E 截止日分组评价，**不随机分配信息**；如以后做逐人时点 E，再按每条信号/新闻实际发布时间过滤。当前统一 E 只适用于截止日后的个人比较；截止日当天答题时刻未知，另列。此次未调用真实 LLM，未改 E/人口/仿真工件。下方较早“两臂”段落是历史方案，以本条为准。

- **2026-10-05 Codex D050–D052 初次独立复核**：见 [审计与开发月执行评审](CODEX_AUDIT_D050_D052_20261005.md)。77 信号的结构/来源/日期集成核验通过；识别统一 as_of 与早答者不一致、汽油和新闻版本证据、NYT 整月预筛、运行脚本强制 v1 prompt 与 12 步窗口，以及 E 审计标签失真。73 人 × 2021-05/06 的标题/摘要两臂方案已评审。初次复核只读，未触碰 10-03 未提交批次。

- **2026-10-05 Codex 零付费接手进度**：运行入口已加 v2 prompt 显式选择和步数校验；v2 环境源码已修新闻截止前重筛、汽油/NYT 版本及混合来源标签；新建 2021-05/06 两月专用 E/仿真工件。73 人 × 2 月 scripted 验收 146/146 有效、真实 LLM 0 调用，定向测试 33/33。原全年 v2 产物未覆盖，待冻结后以新版本重建。剩余：处理早答者的评价口径，确认汽油/新闻版本的结论标签与模型费用上限，再做摘要版真实 LLM 开发验证。见上述审计报告末节；10-03 未提交批次继续保留。

- **2026-10-05 D052 提示词 v2 渲染器落地（Kimi，用户已定版过目）**：
  ① **实现**：`studies/sce_inflation_expectations/model.py` 新增 `build_sce_messages_v2(ob)`（约 160 行），`SCEEnvironmentProvider` 接入 `events_by_step`（reset/advance_to/observe_batch 的 macro_information 新增 "events" 键）；`_decide_openai_one` 按 `prompt_version.startswith("sce-q8-q9-v2")` 选择渲染器，**v1 渲染器原样保留**（旧开发窗 replay 不受影响，但 observations 会多出空 "events" 键，属预期）。
  ② **渲染四块**：最新发布（CPI 同比/环比、失业率+非农、可感知价格行+汽油单价）→ 趋势（6 条 × 12 点=11 历史+最新，`_trend_line` 要求 hist 非空否则返回 None 防单点假趋势）→ 新闻（30 条 `- May 3: "标题"`，无 URL/摘要）→ Q8/Q9 问题块与 v1 逐字节同契约。按 D049b **已移除"上月自己的回答"注入**。
  ③ **真实样例定稿**：`studies/sce_inflation_expectations/reports/PROMPT_V2_SAMPLE_20261005.txt`（2021-06、真实 persona sce_u70118889，4,903 字符 ≈ 1,225 tokens，用户已看过样例并确认风格）。
  ④ **测试**：新增 `PromptV2Test` 5 用例（结构/12 点趋势/v1 环境优雅降级/prompt_version 选择/events 流入 observation），单文件 21/21，全量 106/106。
  ⑤ **未冻结**：按 D045c，提示词 v2 需开发月（2021-05/06）真实 LLM 验证后才冻结为正式配置，随后主窗口 2021 全年整窗重跑；同质化问题（D051 已入档：模拟月内 std 0.27–0.81pp vs 真实 5.5–7.5pp）在同一轮开发月验证中一并评估。运行前需核实 `run_sce_local.py` 的 decision_args 传参入口如何带 `prompt_version="sce-q8-q9-v2"`；真实 LLM 运行涉及费用，需用户确认预算。
  ⑥ **摘要变体（2026-10-05 用户要求做一版）**：`build_sce_messages_v2(ob, include_event_abstracts=True)`，每条标题后接 NYT 摘要（`— abstract`），块标题变为 "Recent news headlines (with brief summaries):"；`prompt_version="sce-q8-q9-v2-abstract"` 自动启用。摘要早已存于环境 JSON 事件条目，无需重建环境。样例 `reports/PROMPT_V2_ABSTRACT_SAMPLE_20261005.txt`（同 persona 同月，9,472 字符 ≈ 2,368 tokens，约为纯标题版 1,225 的两倍）。默认仍为纯标题；开发月验证可做 标题 vs 标题+摘要 消融。测试 108/108。

- **2026-10-04 D051 E v2 历史序列扩展到 6 条（Kimi，用户选定"加 5 条"）**：
  ① **新口径**：每步历史序列从"仅 CPI 总量 11 个月"扩为 6 条 × 11 个月——CPI 总量同比、失业率、食品/能源/住所分项同比、汽油零售价月均价水平；非农保留最新值（机制上对居民太抽象）。每步记录数 22→**77**（11 最新 + 66 历史）+ 30 事件。
  ② **成本核实**：分项/汽油历史零新数据（components_cpi.jsonl、EIA CSV 已覆盖全部历史月）；失业率历史补抓 2020-01..10 共 10 份就业首发 PDF。工程发现：v1 `transcribe_empsit` 的非农模式在疫情版式失效（2020-04 "fell by 20.5 million" 不匹配），v2 新增仅取失业率的轻量转录 `_unemployment_rate_only`（复用 v1._compact 与失业率模式），**v1 文件未改**。
  ③ **数值抽查**：2020-04 失业率 14.7（疫情峰值首发值）、2020-05 13.3（首发值，后修订为 13.0——PIT 保留首发）、能源序列 2020 负值→2021-04 +25.1、汽油 $2.08→$2.99 单调上行，均与史实一致。
  ④ **环境已重建**（同路径三件套），测试更新（记录数 77、6 序列各 11 refs 有序、首发值抽查），v2 模块 9/9。
  ⑤ **暂缓问题入档**：模拟回答同质化风险（P 影响弱 + E 雷同 → 横截面分歧不足；候选方向：persona 化 E 视图 / temperature 消融 / 个体经验引导），用户明确"先放着"，将在提示词 v2 冻结前的开发月验证中一并评估。

- **2026-10-04 D050 as_of 口径变更完成（Kimi，用户提出的信息时差修正）**：
  ① **实证依据**：SCE 微观 `survey_date` 实测 2021 年全部 15,109 人月——中位访谈日每月 15 号（P25=8、P75=21；≤13 号 45.1%、≤15 号 51.7%），晚于 M−1 期 CPI（每月 10–13 号发布）与就业报告（M 月第一个周五）→ 中位真实受访者填答时已看到 M−1 期数据，旧口径（as_of=t−1 月末）使模拟者系统性少看一期。
  ② **新口径**：目标月 M 的最新参考期 R=M−1，as_of = R 期 CPI 首发日当天 23:59:59 ET；就业首发日恒早于 CPI 发布日自动合规，published_at < as_of 硬校验不变。已写入 [RESEARCH_PROTOCOL](RESEARCH_PROTOCOL.md) §1 与 [proposal](../proposal/proposal.md) 时点隔离段。
  ③ **事件层联动**：NYT 事件窗从"仅 M−1 全月"扩为"M−1 全月 + M 月 1 日至 as_of 日"；front_page+strong 层不截断，低层按命中密度+时间补至 30 条预算（token 量基本持平）。
  ④ **数据补齐**：补抓 ref 2021-11 的 CPI/就业首发 PDF；`extract_cpi_components.py` 补两条措辞变体模式（2021-11 roundup 句式 "over the last 12 months...and the food index increased 6.1 percent" 与 "shelter index rose 3.8 percent, the largest 12-month increase"），**分项提取 145/145 零 handoff**。
  ⑤ **环境 v2 按新口径重建**：`scripts/build_sce_environment_v2.py` 主循环改为独立转录（不再从 v1 skeleton 拷贝 as_of/signals/broadcasts），bundle targets、information_program.broadcasts、external_events.as_of 全部覆盖为新口径；每步 22 信号 + 30 事件，产出三件套同路径。测试更新：历史序列起点 2021-04、分项断言改用 2021-04 实测值（food 2.4/energy 25.1）、事件断言改为月份∈{M−1,M} 且 pub_date≤as_of、新增 as_of=CPI 发布日断言。
  ⑥ **影响范围**：提示词 v2 的输入将变为 M−1 期最新数据 + 当月上旬新闻（与真实受访者一致）；v1 环境产物与历史验收文档不改写；主窗口正式运行前配置需重新冻结（开发月验证后整窗重跑）。

- **2026-10-04 E v2 三源全部落地、环境 v2 重建完成（Kimi）**：
  ① **CPI 分项 140/140 清零 handoff**：`scripts/extract_cpi_components.py` 重写模式集（命名分组 verb/num + `_since_is_12m` 校验 + `_ARTIFACT_FIXES` 修复 pypdf 断词 "Th e"/"f ood"/"e nergy"），28 份首发 PDF × 5 分量（食品/在家食品/能源/住所/汽油 12 月同比）全提取，每条带原文引文+页码+sha256 → `data/raw/bls_initial_releases/components_cpi.jsonl`；历史序列所需 refs 2019-12..2020-10 共 11 份 PDF 已补抓归档（2020-05 谷底 0.1 与史实吻合）。
  ② **EIA 汽油零售价接入**：`scripts/fetch_eia_gasoline.py`（FRED GASREGW，源头 EIA，免 key，周度周一观测）404 周 2019-01..2026-09 → `data/raw/eia_gasoline/gasoline_retail_regular_weekly.csv`(+.sha256) 与月度 `..._monthly.jsonl`（月均价+同比+完整溯源）。
  ③ **NYT 事件层定版**：`scripts/build_nyt_events.py` 强/弱双词表 + **词边界匹配**（修复 "rent"~"apparently/Republican"、"wage"~"waging" 子串误命中——此前抽查的加沙/枪击噪音实由此引入）；四层优先级 front_page+strong > strong_keyword > front_page+broad > front_page，仅弱词非头版丢弃。**用户 2026-10-04 定：最高层（头版+强词）全量纳入永不截断，其余层共享每月 30 条上限；同层内命中关键词多者优先、时间新者破平**（命中密度作为相关性代理）。**词表扩充（用户 2026-10-04 选定）**：大宗商品+粮食（commodity/commodities/grain/wheat/soybean）、住房市场（home price/housing market/mortgage）、批发上游（producer price/wholesale price）、财政扩展（fiscal policy/stimulus check/relief package/spending bill/infrastructure bill/unemployment benefits）、通缩方向对称（deflation/prices fell/falling prices/price drop/price cut）、油气补充（opec/oil market）；裸 "price"/"oil" 经实测（每月仅 44-52/21-22 篇命中、头版 4-5 篇含比喻用法）决定不采纳以保护免截断顶层的纯度；"economy" 单词降级为弱词（"economic recovery/rebound" 完整词组保留强词）。税收政策（tax）用户未选、未加。匹配面=标题+摘要+snippet（进模型上下文的仅日期+标题；摘要存台账与环境 JSON 但默认不展示，可由 prompt_version 开启，见 D052⑥）。15 个月缓存重建台账 450 条（`data/raw/nyt_archive/events_ledger.jsonl`，重建零网络零费用；每月 30 条 ≈ 1,600 tokens）。抽查 2021-05：CPI 冲击(05-12)/Colonial Pipeline 汽油抢购(05-12)/大宗商品短缺(05-03，5词命中)/芯片短缺与产业链(3词×3)/失业救济辩论/Fed 通胀路径(3篇)/二手车价格，命中密度排序后尾部噪音降至 2-3 条。
  ④ **环境 v2 重建**：`scripts/build_sce_environment_v2.py` 每步 22 条信号（4 个 v1 头条 + 5 分项 + 11 条历史序列 + 2 条汽油：月均价+同比）+ 30 条事件；分项 source_url 修复为复用同稿头条 CPI 的真实归档 URL（原实现拼文件名产假 URL）；published_at < as_of 硬校验全通过。产出 `studies/sce_inflation_expectations/environment/environment_main2021_v2.json`、`external_events_environment_main2021_v2.json`、`simulation/simulation_main2021_v2.json`。
  ⑤ **测试 95/95 全绿**（新增/更新：build_nyt_events 16、extract_cpi_components 13+全归档回归、fetch_eia_gasoline、build_sce_environment_v2 集成）。
  ⑥ **未做**：提示词 v2（等用户审阅 `studies/sce_inflation_expectations/reports/PROMPT_IO_REVIEW_20261003.md` 后共同定）；2026 前瞻窗 v2 环境（主窗稳定后扩展）；B 线人口外推配置（契约已定，实现未启动）。

- **2026-10-03 深夜 Kimi 完成 Codex 复审四项具体修复（D047 执行）**：① **评价真值修复**：`scripts/build_sce_evaluation_truth.py` 改用 Q8v2part2（带符号数值；Q8v2 实为 1/2 方向码）+ Q8/Q9 独立有效掩码（Q9 纳入不再绑 Q8 非缺失）+ Q8 聚合用此前验收的 mid-distribution 插值；**12 个月 × 点估计/密度双指标与官方 headline 对账全部归零差**（真值文件 `data/evaluation/sce_truth_main2021.json` 已重生成，gitignored）。
  ② **修正后主窗口对比**（73×12 run `sce-local-openai-20261003T055121Z-1dc7cd15` × 冻结计分器）：逐人 Q9 MedAE 2.243pp（与 Codex 复算一致）、Q8 点估计 MedAE 2.200pp；聚合月 MAE 点 1.86 / 密度 2.17pp；**真实受访者自身 Q8−Q9 内部不一致 median +0.49/mean +2.53pp，模拟为 +1.39/+1.38（同向同量级）**——不一致本身是真实行为特征，不应强制两题一致；真正缺口是水平整体偏低 ~2pp 与横截面分歧不足（模拟月内 std 0.27–0.81 vs 真实 5.5–7.5）。
  ③ **住房 Q43 更正**：确认为仅问新入组者（问卷 p.27/32；实测每个 userid 仅一条 Q43 记录、从未改答）；`build_sce_population.py` 删除 ±6 月向未来借用，改为入组回答前向沿用（2021 人月覆盖 99.64%，73 人主窗口 panel 全部 2021-01 入组当月作答、信息年龄 0），元数据记录 source_month/info_age/D3 迁居标记；测试 7/7，dev100 与 main73 人口已重建。
  ④ **计分器自包含迁移**：纯 Beta 拟合内核原样迁入 `studies/sce_inflation_expectations/scoring/beta_fit_kernel.py`（算法/参数一字未改，与 diagnose_sce_beta.py 的 fit 函数体逐字节一致），`sce_q9_frozen.py` 改本地导入；**3,741 条封存行逐条等价（状态 0 不一致、数值最大差 0）**，study 目录复制到 /tmp 隔离导入测试通过，provenance 钉版哈希已更新且 live==pinned。scorer 测试 3/3。
  ⑤ **POPULATION_WAVE_STATS 更正并重生成**：Q9 十档表头改为正确档界（≥12/8–12/4–8/2–4/0–2/−2–0/−4–−2/−8–−4/−12–−8/≤−12）；TVD vs 窗口均值参数从全 60 月更正为 14 月主窗口；组间方差占比表述改为实测（全期最高 1.9%/主窗口 2.1%），"个体内"更正为"组内个体间"；自相关 0.597 降级为描述性线索；轮换表新增"重返"列并注明左截断/事后退出口径；16 条无权重行保留两套计数；housing 漂移解释与 B 线校准频率表述按复审软化（TVD 阈值降为告警参考）。
  **A/B 契约草案已列**：[A_B_LINE_CONTRACTS](A_B_LINE_CONTRACTS.md)（两线各自的输入/约束/生成对象/独立验证量/来源，按 D048 修正解释：A 线可用当期人口与宏观约束、A−B 不解释为纯信息时效效应、封存为可选验证非死线）。**未动任何运行配置、未运行实验**；提示词 v2 暂缓（用户先审阅当期提示词/输入/输出/分布）。下一步待用户确认契约草案 → core 规模零 LLM 抽样精度试验 → normal estimator 定义。

- **2026-10-03 深夜 用户定案 E 的机制聚焦（D049a–d）**：① E 加历史序列（采纳）；② 不注入"上月自己的回答"（否决，持续性由 E 序列内生）；③ SCE≠CCI 的机制区分——通胀预期由居民可感知价格（食品/房租/油气/供应链）驱动而非个人财务状况，E 聚焦改为可感知价格分项+汽油价格，分歧来源设计为差异化价格暴露与注意力（租客→房租、驾车者→油价、低收入→食品）；④ **事件层纳入 E**——疫情供应链、地缘冲突推油价、贸易摩擦关税等重大供给事件以居民语言进入信息环境，逐条登记日期与报道证据；10/15 前用零成本公开渠道，Event MCP 付费新闻层降级为后续增强。开题报告 §一/§二/§四/§五 已按此改写（含住房 99.6% 覆盖更正、全年回测基线与两个缺口的靶点定位）。**重做清单（详见下条接力）**：E v2（分项转录+序列化+事件层台账）→ 提示词 v2 → 开发月验证 → 冻结 → 主窗口整窗重跑；73×12 运行保留为 v1 基线。

- **2026-10-03 深夜 双 key 就位并验证（Kimi）**：NYT Archive API key 存于主仓库 `.env`（`NYT_ARCHIVE_API_KEY=...`，gitignored），实测 2021-06 拉取 4,260 篇文章元数据（带 pub_date，走本机代理）；OpenRouter key 存于官方仓 `.env`（`OPENROUTER_API_KEY=...`，gitignored），鉴权直连通过，模型目录 466 个，候选全在列：openai/gpt-4o-2024-{05-13,08-06,11-20}（日期钉版，知识盲版对照首选）、qwen/qwen-2.5-72b-instruct、meta-llama/llama-3.1-70b/8b-instruct、deepseek/deepseek-chat-v3-0324。OpenRouter 为 OpenAI 兼容端点（https://openrouter.ai/api/v1），注意：extra_body 的 thinking 参数是 DeepSeek 私有，OpenRouter 渠道不可传。审阅材料已生成：`studies/sce_inflation_expectations/reports/PROMPT_IO_REVIEW_20261003.md`（v1 提示词全文/代表回答/逐月对照）。**进行中**：E v2 数据层 `scripts/extract_cpi_components.py` 已跑通 59/85（食品/在家食品/能源/住所/汽油五分量 12 月同比，每值带引文+页码+PDF哈希），剩余 26 条已定位三类措辞变体（2026 新稿 "for the 12 months ending"/"over the last year"、2021 合并句 "energy...12-months, and the food index increased X percent"、2021-03 括号式 "(+1.7 percent)" 与 Table A 列序变化——Table A 的"最后一个数字=12月同比"假设在部分版式不成立，y/y 是三个 >100 指数水平值之后的第一个数），待适配；EIA 汽油周度零售价接入未做；NYT 事件层拉取脚本未写（通道已就绪）。未提交 git 的本轮改动较多，待用户过目后统一提交。

- **2026-10-03 用户澄清主线（D048，覆盖此前过度预测化解释）**：[A/B 两线定义](A_B_RESEARCH_DESIGN.md)：A=利用已知人口/宏观信息重建历史微观结构，B=只用t期可得信息预测t+1。A可用当期边际/宏观约束，评价须区分约束与未参与拟合的微观结构；两线不强求E相同。SCE发布前封存只是一种验证方式。Kimi先继续字段/计分导出等具体修复，再分别列两线输入、约束、生成对象与验证量；本轮未改运行配置。

- **2026-10-03 Codex Core/Normal 独立复审完成（D047，方案未替用户冻结）**：见 [复审与 Kimi 执行清单](CORE_NORMAL_REVIEW_20261003.md)。主要修复：Q8 真值误取方向码、Q9 纳入绑在 Q8 非缺失上；Q43 是入组题，历史前向可恢复 2021 人月 99.64% 记录覆盖；冻结 scorer 3,741 行全等价，但 study 独立导入失败（外层 scripts 依赖）。建议粗分层+持续 ID/逐月 active，normal 明确权重与估计器，B 禁用当期真实边际校准。**SCE 9 月结果预计 10/7 23:00 北京发布，内部建议 10/6 18:00 完成封存**，官方日历证据见 ROADMAP 顶部。用户的2.24pp已复现为个体Q9 MedAE；模拟横截面离散度明显偏低，先修评价再做开发月受控消融。原实现与运行均未改。

- **2026-10-03 E authoring 完成（Kimi 实现代理）**：`scripts/build_sce_environment.py` 参数化物化 E——取数通道为 httpx+浏览器头走本机代理（curl 被 Akamai 403）；发布日期逐稿自证（稿内 embargo 行=归档 URL 日期），34 份首发稿 PDF 归档 `data/raw/bls_initial_releases/<ref>/`（manifest 含 SHA-256/USDL/4 值转录引文）。产出主窗（2021-01..12，12 步，非农为新增加的第 4 信号）与前瞻段（2026-06..10，5 步）两套 environment/simulation 配置，官方 schema 校验通过，targets 新机制（{target_month, as_of} 按 conceptual step 索引）已接入 provider_args。测试 54/54（新增 12 例）。报告：[ENVIRONMENT_AUTHORING_REPORT](../studies/sce_inflation_expectations/reports/ENVIRONMENT_AUTHORING_REPORT.md)；开发窗配置未动。

- **2026-10-03 Codex 计分器新月份复查完成（D044）**：先封存方案与两版代码，再对 2020-04/2021-10/2022-12 全月 3,741 条问卷对照；2,784 条 Beta 的≤0.001比例 71.98%→87.07%，MAE 0.074535→0.046990，三个共同样本月度中位数误差均下降，预设条件全通过。**建议冻结候选为 `sce_q9_approx_v1`**；开放连续子组 MAE/p95 略有/明显恶化，需报告；仍为近似指标。见 [结果与 Kimi 集成验收清单](SCORER_HOLDOUT_REVIEW_20261003.md)及[运行前方案](SCORER_HOLDOUT_PLAN_20261003.md)。原两版源码未改；Kimi 移植后对封存结果逐行核验，同一冻结版计分真实和模拟问卷。三个月成为选型验证集，不再称独立最终测试。

- **2026-10-03 正式实验框架定案（用户，D045）**：四段时间（主窗口 2021 全年 12 月微观级 = 10/7 必交付；延伸段 2022-01..2025-10 随后；前瞻段 2026 汇总级 = 06–08 回测 + **09/10 封存预测须在官方发布前完成**）+ A/B 两线（A = 当月微观 P 基准，B = ≤M−12 旧微观 P 外推，A−B = 信息时效效应）+ 测试切分变更（取消留出测试月，连续窗口连续评估）。配置冻结：temperature=0.5、计分器（D044）、提示词版本待开发月调试后锁。预算约束解除。详见 [ROADMAP](ROADMAP.md) 顶部修订块。
- **10/4 进展（进行中）**：① 月份通用化已完成——model.py 的 TARGETS 改为 provider_args.targets 驱动（决策层改从 Observation 取目标月），旧开发窗字节级复算仍 PASS，新增通用化单测；运行器新增 `--environment/--simulation/--population` 三选件开关，manifest 记录实际使用件哈希。② **A 线 panel 实测：2021 全年 12 个月全部在册的 userid 只有 73 个**（≥11 个月 229 个）——已按严格 panel 生成 `population_main2021_a73.json`（73 人 × 12 月），如要 100 人须放宽到 ≥11 月池（个别月份无真实作答，评价层按月在册过滤），**待用户定**。③ E 物化代理进行中：主窗口（12 月 × 4 信号含非农新增）+ 前瞻段（2026-06..10）BLS 首发稿取回/转录/配置产出。④ 评价层真实回答提取脚本待做（10/5 对比的另一半数据）。

- **2026-10-03 计分器冻结完成（D044，解除 10/5 对比的最大阻塞）**：Codex 预注册留出方案（2020-04/2021-10/2022-12），Kimi 原样运行通过全部八项规则（Beta MAE 0.047 vs 0.075，≤0.001 比例 87% vs 72%）；冻结实现 `scoring/sce_q9_frozen.py`（原版分发 + 钉版候选替换 Beta 分支，provenance 自报哈希有测试守门）。真实与模拟问卷统一此算法，官方差异另报。提案"已完成的可行性验证"段也已更新（真实模型小试 + 真实人口抽样的评审口径表述）。

- **2026-10-03 P 真实抽样完成（Kimi + 实现代理）**：`scripts/build_sce_population.py`（panel 模式：只取所有目标月都在的 userid，seed 确定、来源文件哈希、分布元数据；白名单测试守门）。**100 人 × 202105+202106** 已生成：`studies/sce_inflation_expectations/population/population_real100.json` + roster + sampling_meta（两月交集池 1070，抽 100）。就业 = Q10_1..10 多选（问卷 p.11–12，每月必答，全覆盖）；住房 = Q43（p.32，**旋转模块每月仅约 12% 人被问**），±6 月借用后覆盖 42%（58/100 无该属性，prompt 回退 unknown）——**住房维度完整性受 SCE 设计限制，若要扩白名单属协议变更，待用户定**。两个语义纠正：`_NUM_CAT` 实为 numeracy（High/Low）非家庭人口；xlsx `tenure` 为面板受访月数非住房。prompt 映射只增不删（旧 20 人试点 prompt 字节不变）。运行器已接 `--population`，并按所跑人口动态绑定 E 的 persona 视图（weight 整数化保持试点字节级复算 PASS）。报告：[POPULATION_SAMPLING_REPORT](../studies/sce_inflation_expectations/reports/POPULATION_SAMPLING_REPORT.md)。测试 38/38；真实 100 人 scripted 干跑 200/200 有效。10/5 正式运行的模拟 vs 真实对比仍需评价层提取真实回答（weight/Q8v2/Q9 只在评价层，脚本未做，列入 10/4-5 任务）。

- **2026-10-03 真实 LLM 首轮已完成（Kimi，D043）**：用户批准装 llm 扩展 + $0.30 预算上限。`--list-models` 目录核对通过（端点含 deepseek-flash/v4-pro，与选型文档一致）；`--sample 2` 两条一次有效、估费 $0.0007；**20 人 × 2021-05/06 正式开发小试完成**：40/40 一次通过 Q9 语法门（零重试零错误），点预期中位数 3.0（05）/4.0（06），40 次调用估费 **$0.014**。run_id `sce-local-openai-20261003T011717Z-427a1baf`，审计链完整（llm_calls 40 行全含提示词/原始响应/usage）。期间修复一处工程问题：运行产物（含 duckdb 与引擎 live 文件）全部迁入按 run_id 的审计目录，运行副本保持纯净，--force 重导出不再能误删产物。性质登记为历史回顾性条件模拟（不声称盲测/严格复现）。下一步：正式对比等冻结计分路径（Codex 复查月份）；temperature/提示词消融先冻结设计。

- **2026-10-03 本地 harness 已实现并离线验收（Kimi）**：SCE study 首次在主仓库获得完整可运行实现——`studies/sce_inflation_expectations/model.py`（四个 abc + 双模 B：scripted 与云端 v3 逐字段一致；openai 真实 LLM 带全量审计 sidecar：提示词+原始响应+哈希、requested/returned model、request_id、fingerprint、usage、重试与错误逐条落盘；Q9 校验不归一化、失败不回退规则、SDK 内置重试关闭、调用次数/费用双闸门、超长提示拒绝）+ `__init__.py` + environment/population/simulation/grounding/resources 配置件 + JSON 格式 study.yaml。入口：`scripts/run_sce_local.py`（自动单向导出→官方仓运行副本执行，轨迹按 run_id 独立 duckdb，运行配置只写 run_manifest 不回写副本，P1 导出保护不阻塞复跑）；`scripts/sce_llm_probe.py`（--list-models 免费目录核对 / --sample N 计数小样，需 --confirm-spend）；`scripts/audit_local_scripted_replay.py`（与 v3 归档逐字段复算）。**验收结果**：两次本地 scripted 运行 answers 40/40、observations 40/40 与云端 v3 归档完全一致（replay_audit_vs_v3.json verdict=PASS）；单元测试 31/31 通过（含 mock-openai 的有效/重试/失败/闸门分支）。证据：`outputs/local_runs/sce-local-scripted-20261003T003537Z-8e6b2f5b/`。**下一步（待用户动作）**：用户在官方仓 `.env` 放入 DeepSeek key 并确认 $0.30 预算 → --list-models 目录核对 → --sample 2 两条小样 → 40 条开发小试。model.py 的 openai 路径真实连通性尚未实测（openai 包未装，装前与用户确认 `pip install -e ".[llm]"`）。

- **2026-10-03 最新接力，覆盖下方旧选型说法**：[模型核查与 Kimi 接入清单](MODEL_SELECTION_20261003.md)已完成。用户确认已有 Kimi/DeepSeek API；建议首轮复用 DeepSeek `deepseek-flash`（当前映射 V4.1-Flash、显式关闭思考），2 条接入小样后考虑原 20×2 开发小试；建议预算 $0.30，**尚未批准/运行**。Qwen2.5-72B 在硅基流动仍有公开价；GPT-4o 固定 API 版本仍列在官方目录，地区/账号可用性另核；旧 `deepseek-chat=V3` 与“2024 都是严格盲测”表述已更正。Kimi 下一步做本地客户端审计接线与离线 mock；服务目录、实际模型回包/usage、预算确认完成后再调用。正式模型/测试期与计分配置均未改变。

- **2026-10-01 Codex独立复核完成**：[结果与交接](BETA_AND_KIMI_REVIEW_20261001.md)。原计分器未改；新增独立诊断脚本，完整两月1,780条Beta记录的≤0.001误差比例67.2%→84.3%，仍非官方精确复现。候选是否采用待用户决定；保留SCE目标。
- **Kimi优先修复**：① `export_study_runtime.py` 重导出会删除运行副本内已有trajectory等产物（已用临时目录证实），真实运行前需保护/分离run_id产物；② v3源码写字面量反斜杠n，归档日志却为LF，需核实转换或实际运行源码，不再称证据链完全闭合。现有40条回答匹配与文件哈希自洽仍成立。之后推进历史P/E、有限真实B和提案，不反复消费云端额度重跑scripted。
- **Kimi P1/P2 已完成（2026-10-02，D039）**：① P1：`export_study_runtime.py` 重导出遇目标副本派生产物/改动即拒绝并列清单，`--force` 显式覆盖；新增 4 项测试，全套 16/16 通过；官方仓运行副本 `--verify` 仍通过。② P2：answers.jsonl 确认为平台自运行状态导出（非 model.py 产出，矛盾消除一半）；observations.jsonl 与平台 audit_manifest 哈希一致但与归档源码存在一层未记录换行转换，保留为格式层缺口；平台轨迹库 `panel_live.jsonl` 与 answers/observations 内容 40/40 一致（独立佐证）；[CLOUD_V3_AUDIT_RECEIPT](CLOUD_V3_AUDIT_RECEIPT.md) 结论已降级，运行证据链附加协议（封存源码哈希、行为函数自报哈希、记录转换、轨迹库交叉核对）已入 [RESEARCH_PROTOCOL](RESEARCH_PROTOCOL.md) 第 6 节。
- **Q9 计分方针已定（用户 2026-10-02，D039）**：统一采用明确命名的近似密度指标，同一算法处理真实与模拟问卷，论文明确说明近似性质并报告与官方 headline 差异。具体冻结哪一版算法（原实现/候选变体）按 Codex 建议在未参与诊断的核验月份复查后确定，不由测试表现反向选择。待办：选定复查月份 → 实现冻结版计分模块与差异报告。
- **Kimi 后续**：T02 主体已完成（P 核验 + 核验月 E 日历，见 [T02_PE_ACCEPTANCE](T02_PE_ACCEPTANCE.md)），收尾待办为就业/住房问卷码表映射、正式窗口月份补齐、脚本固化；有限真实 B 试验准备；提案待用户审定（结尾内生指标展望句去留未定）。
- **Sim 主路径已定（用户 2026-10-02，D040）**：Sim 探索与正式运行云端平台优先，v4 解冻按 D034 报价确认卡路径；本地 harness（socioverse2_repo + 自带 API）降为后备。不耗平台额度的准备工作（persona 提示词设计、Q8/Q9 回答格式稳定性小样测试）可先行。GitHub 远端已同步至 `59cd61c`。
- **v4 已配置未运行（2026-10-02 晚，D041）**：经 webbridge 逐步操作用户浏览器（每步用户确认），v4 从 v3 创建并切换 `llm_kind="openai"`（试钉 gpt-4o-mini）、LLM 决策代码已写入 model.py 并通过语法校验；**未运行、未扣 Sim 费**。运行冻结原因更新：① 运行前报价确认不可得（平台刻意不公开模型/单价）；② 平台自述 v4 运行时审计接线未完成；③ 三轮对话 $6.78 后余额 **$-0.20** 透支。**额度路径（用户截图确认）**：平台无即时充值入口，10-12 前提交开题提案、10-15 初筛通过后每队追加 $70；提交入口为「研究目录」页顶部参赛卡片。**10-15 前云端模拟全部暂停**，主线转为：本地完成提案提交 + 本地 harness 做提示词冻结与格式干跑（自备 API，成本自控）；10-15 后云端 v4 正式运行。完整记录见 [CLOUD_V4_PREP_RECEIPT](CLOUD_V4_PREP_RECEIPT.md)。
- **本地运行方案已立项（2026-10-02，Kimi）**：官方仓库架构核查完成——LLM 走任何 OpenAI 兼容端点（`SV_LLM_*`）、人群可用 FilePopulationProvider（不需 Population MCP）、E 在 build 时物化（**不需复刻 Event MCP**，运行时从不联网）、引擎本地装配写 DuckDB。本地待办清单（Sim 模型选型/人群抽样/E authoring/审计接线/云端衔接）见 [LOCAL_HARNESS_RUN_PLAN](LOCAL_HARNESS_RUN_PLAN.md)。模型选型为研究口径决策，待用户定（GPT-4o 的 2023-10 截止可支持"窗口内外对比"设想）。

- 交接入口：[AGENT_HANDOFF](AGENT_HANDOFF.md)；用户发给 Kimi 的[启动提示](KIMI_START_PROMPT.txt)。以下负责人是协作安排，不表示已经启动了另一 Agent。
- **云端 v3 已完成（2026-10-01，Kimi）**：v2 流程报告生成（6/6 不含论文/文献阶段）；/sv-iterate 创建 v3 scripted 审计版并冷跑 20 人 × 2021-05/06，`model.py` 仅 +22 行审计 diff。run_id `sce_inflation_expectations-v3-2c40f389c0d24e1ab1e963918b3bfec9`；`audit/v3/` 六件（run_manifest/cost_ledger/audit_manifest/observations×40/answers×40/validation_errors 空）+ v3 `model.py` 全部取回，`scripts/audit_cloud_v3_audit.py` 核验通过：文件哈希与清单逐条一致、Observation 哈希 40/40 自洽（算法与源码一致）、回答与 v2 归档逐字段一致 40/40。费用账本 `billing_status=not_available`。云端对话费约 $10.67，Sim 未动。取件坑与 base64 通道见收讫文档。
- **v4 已冻结（用户 2026-10-01 决定，D034）**：平台工作区无法确认真实 LLM provider/模型 ID/知识截止/报价；v4 保持冻结，优先完成开题提案（内部目标 10-08）。未来解冻路径：授权走到 v4 sv-run 确认卡只读报价 → 用户批准预算 → 运行。
- **T03-L 本地验收已完成（2026-10-01，Kimi）**：补装 `scipy 1.17.1`/`openpyxl 3.1.5`；SCE 测试 12/12（Q9 计分 5 + 新增导出 7）；v2 归档审计两脚本通过。新增 `scripts/export_study_runtime.py`（单向导出 + `--verify` + 逐文件 SHA-256）与 `tests/test_export_study_runtime.py`，已真实导出到官方仓 `studies/sce_inflation_expectations/`（gitignored，不另养源码）。MCP 两服务连接与免费目录实测通过：`event_tool` 21 个来源（含 nyfed_sce/fred/bls/census_acs/sipp 等）、`user_pool_survey_mcp` 免费探测全过（matraix_1m 56,583 索引用户等），付费工具均未调用，脱敏归档在 `data/raw/mcp_checks/2026-10-01/`。完整命令与边界见 [LOCAL_RUNTIME_ACCEPTANCE](LOCAL_RUNTIME_ACCEPTANCE.md) 末节。`scoring/sce_q9.py` 本轮未动。
- **Kimi 后续**：v4 按用户决定执行或冻结；v3 证据写入提案（流程可行性段）；T02 历史 P/E 与发布日历；需要时补取 v3 轨迹 DuckDB/报告原文。
- **Codex T01独立诊断已完成**：方法与候选取舍见上述2026-10-01复核。生产 `scoring/sce_q9.py` 未改；后续采用候选须先明确版本/口径，再用未参与诊断的计分核验月份验证。
- **后续汇合 T02**：历史 P/E 与发布日历/简单基线；MCP 小样可取 2020-04、2022-06、2024-12（注意结构化取数按次计费，先核预算）。提案沿既有日程并行推进。
- 主仓库大量文件未提交；最近本地 commit 仍为 2026-09-27 的 `d63cbae`。分任务检查后保存，不假定最新工作已推送 GitHub。今日改动文件：`scripts/export_study_runtime.py`、`scripts/check_mcp_free_capabilities.py`、`scripts/audit_cloud_v3_audit.py`、`tests/test_export_study_runtime.py`、`docs/{LOCAL_RUNTIME_ACCEPTANCE,NEXT_ACTIONS,DECISIONS,CLOUD_V3_AUDIT_RECEIPT}.md`（归档 `data/raw/{mcp_checks,cloud_exports}/2026-10-01/` 在 gitignore 内）。

## 已完成

- [x] SCE 2020–2024 年 60 个月数据与跨人聚合核验：[审计](SCE_DATA_AUDIT.md)。不含从十区间重新拟合个人密度。
- [x] Event/Population MCP 公开文档和客户端审计：[记录](SOCIOVERSE_MCP_AND_PMI.md)。未验收真实服务。
- [x] 项目目录、开发规则、study draft 元信息、统一日程与交付清单。
- [x] 今日 P/E/B 材料与云端首试包：[交接计划](TODAY_PEB_EXECUTION_PLAN.md)、[平台上传顺序](../proposal/cloud_input/README.md)。已补下官方 SCE 2017–2019 微观、图表指南、2019 ACS PUMS 字典/说明及 BLS 2021 年四份归档发布稿；下载清单见 [补充来源](peb_source_manifest.json)。
- [x] 平台报告 v2 以 20 人 × 2 月完成 deterministic scripted 首试；40 条原始 JSONL、`model.py`、`environment.json` 和 `simulation.json` 已取回并核对哈希。环境中六条 BLS 信号与 20 个合成画像和本地来源逐字段一致；本地 P/E 重演 40 条 Q8/Q9 全部一致。状态与证据边界见[云端 v2 首试记录](CLOUD_V2_PILOT_RECEIPT.md)；取件阶段结束，C4 仍未全部通过。
- [x] T01 计分器首轮复现：Q9 单档均匀与相邻双档三角分支在 2020-01、2022-06 的真实个人派生值上基本精确；广义 Beta 分支仍有开放尾和空档误差。官方个人 `Q9_mean` → 月度 chart 已复核，自己的 Beta 拟合 → chart 尚有约 0.007/0.011 个百分点误差。[完整记录](SCE_Q9_SCORING_REPLICATION.md)。

## 执行方式：云端证据归档，本地能力开始验收

按 [云端预试验方案](CLOUD_PILOT_PLAN.md) 已完成 v2 的小样流程及原始回答、B 代码、E/P、simulation 配置复核。真实运行 Observation、独立 run ID 和费用流水未持久化；这些缺口在下一次运行前改设计，不继续追取 v2。2026-10-01 用户已配置 Claude Code + Kimi，开始 T03-L 本地开发验收；沿用已有代码/材料，不重做整套框架。以下 T00–T04 是验收职责，执行位置按可用能力决定。

## 优先前置：项目级数据可得性

### T00｜最小数据可得性筛查（Agent 主导，部分基础已完成，历史输入未验收）

- 范围：Y 真值、P 人口、E 信息、B 问卷/计分、基线与数据许可；不只检查 P/E。
- 具体步骤、当前缺口及进入后续工作的门槛见 [数据审计中的 T00 清单](SCE_DATA_AUDIT.md)。
- 输出：各用途的数据验收卡、实际样例、时间证据、月份覆盖与可做任务的结论；沿用已有来源台账。
- 当前 Y 与部分计分材料已有实测；首试两月的 BLS 原始发布 E 与平台保存的环境配置已核对，但运行时 Observation 未保存；历史 P 仍待核实。可选新闻/CE 不阻塞公开基础版。
- T01 可利用现有数据开展小范围计分验证，T03 可同步验收平台；完整 Agent/批量回测按数据验收门槛推进。

## 随后：三个准备任务按依赖汇合

### T01｜计分器（首轮实现并验证，Beta 精确复现未完成）

- 输入：SCE 官方问卷、方法附录、已下载真实 Q9 概率与派生字段。
- 修改区：`studies/sce_inflation_expectations/scoring/`、相关 `tests/`；更新数据审计。
- 已实现：`scoring/sce_q9.py` 按官方分支处理十档回答；只读审计脚本在两个相隔较远月份逐人对照均值、四分位数、IQR 等，并对照全国指标。结果和命令见[计分复现](SCE_Q9_SCORING_REPLICATION.md)。
- 尚需验收：Beta 开放尾和不连续概率档的原始优化细节；扩展到 60 个月的覆盖和误差统计。不能把当前近似 Beta 结果命名为纽约联储官方 headline。
- 后续：T04 先导出 B 的原始 Q9，再在本地计分；只有数值口径和云端依赖都通过后，才考虑把模块集成到 SocioVerse2。无法完成时先与导师讨论并记录点预测目标调整，不按测试表现挑目标。

### T02｜历史 P/E 验收与构建（Agent；P 侧与核验月 E 日历已完成 2026-10-02）

- 前置：T00 的对应来源/字段/时间样例检查；T02 负责扩展到实际 P/E 管线与正式月份覆盖。
- 输出：逐月 release 日历、历史 P 版本证据、开发月宏观信息快照与字段契约；登记来源和修订版本。
- 修改区：`data/`、study 的 `population/`、`environment/`、`grounding/`。
- **已完成（Kimi，见 [T02_PE_ACCEPTANCE](T02_PE_ACCEPTANCE.md)）**：P 侧三份 SCE 微观快照（2017–2019 / 2020–2024 / 2025-01..10，共 106 月 130,216 条）字段核验——提案所需画像字段（`_AGE_CAT`/`_EDU_CAT`/`_HH_INC_CAT`/`_REGION_CAT`/`_NUM_CAT`/`_COMMUTING_ZONE`/`_STATE`）全部存在且非空率约 100%，每月 976–1,377 人与提案口径一致；P 白名单契约已定（`weight` 与 `Q8v2`/`Q9_*` 仅进评价层）。E 侧三个核验月（2020-04、2022-06、2024-12）6 份 BLS 归档首发稿已取回存档（`data/raw/bls_check_months_initial_releases/`，含 manifest 与首发值表）；curl 被 Akamai 403，改用 FetchURL 文本抽取，已在 manifest 注明。2020-02 就业稿重发注记与 2024-10 非农异常低值均已记录备查。
- 验收：P/E 不带同期真实回答/权重（契约已写死）；unknown 和 future 发布时间被隔离（本轮未接入无 vintage 来源）；过去发布值基线有日期依据。
- 待做：就业/住房字段的问卷码表映射（persona 需要时）；正式窗口确定后按同法补齐该窗口全部月份；统计与校验脚本固化到 `scripts/`。
- MCP 优先取 2020-04、2022-06、2024-12 小样检查：已改用 BLS 公开归档页完成，零 MCP 费用；无服务权限直接推进官方宏观数据路径。

### T03｜云端能力验收（原始配置/回答已复核，历史日志缺口留待新版本）

- 已核对官方工作流和公开上传/导出代码；本地 Agent 尚未进入用户账号。用户的 Event 查询反馈见下一条，其他能力仍按实际回执验收。
- 2026-09-30 用户转述平台已在同一 `sce_inflation_expectations` study 创建 v2，保留 v1 快照，并报告：六条 BLS 历史 E 经 `observe_batch` 进入 B，20 条合成 P 已物化，40 条 Q8/Q9 scripted 原始回答已生成，真实 LLM/新付费 MCP 调用为零。完整状态和诊断数值见[首试记录](CLOUD_V2_PILOT_RECEIPT.md)。v1 只有 synthetic E 方案，没有运行基线。
- 平台进一步说明：托管工作台当前无 ZIP/二进制下载按钮，观察面板只读，但能通过对话分块输出文本。40 条 JSONL、199 行 `model.py`、318 行 `environment.json` 与 497 字节 `simulation.json` 的原始字节已还原并与平台 SHA-256 匹配。环境里的六条 BLS 信号和 20 个合成画像与本地来源相同；simulation 的两步、scripted 决策、seed 42 与原始回答相符。本地按代码复算 40 条 Q8/Q9 全部一致。平台确认**未保存 v2 实际传给 `decide_batch` 的 Observation**，先前展示是事后检查；独立 run ID 和费用流水也未持久化。v2 取件到此结束，下一次运行需留真实输入日志。代码的静默缺失回退、Q9 与 E 无关、仅收入字段影响 Q8 等局限见[完整审计](CLOUD_V2_PILOT_RECEIPT.md)。C4/T04 尚未全部完成。
- 用户指出真实 LLM 回放的**模型参数时间泄漏**：目前不知道托管研究助手的模型/截止，未来模拟 B 的基础模型也未选定。v2 代码审计确认 B 为规则式、无模拟 LLM 调用，也未直接引用 SCE 真值；但 `0.55` 等系数是事后编写且无来源，不能报告预测效果。真实 LLM 前按[时间泄漏协议](MODEL_TEMPORAL_LEAKAGE.md)登记模型来源；可把[只读模型溯源问题](../proposal/cloud_input/request_llm_provenance.md)发给平台。训练边界晚于目标 `as_of` 或未知的 2021 年 LLM 结果不能称严格事前预测。
- 按 C0–C4 验证：输入与建模确认、极小合成文件人口、MCP 样例、定制计分、scripted 两月流程、完整导出与本地重算。
- 云端费用确认遵守平台流程，记录 Agent 与 Simulation 两类余额；不根据旧 FAQ 推断上传不可用。
- 若通过，继续云端或云端生成回答/本地计分；若受规模、代码控制、依赖、导出限制，再启动 T03-L 本地环境验收（Python 3.11+、官方 demo、依赖锁定）。
- 输出：能力/费用/导出验收记录见[CLOUD_V2_PILOT_RECEIPT](CLOUD_V2_PILOT_RECEIPT.md)；回答、模型、环境和模拟配置已取回并复核。独立 roster 尚未取回；历史 Observation、run ID、费用流水确认未保存。当前优先 T01 官方 Q9 计分与 T02 历史 P/E，不为 v2 反复索取不存在的记录。

### T04｜最小完整流程（Agent，依赖 T01 可用计分范围 + T02 + T03）

- 输出：云端可运行的 scripted P/E/B 流程、可导出的代码/配置/回答和本地复核、持续性基线；采用本地运行时提供 `run.py --dry-run`。
- 验收：至少两个相邻开发月贯通；固定种子可重复；模拟输入没有真值；输出记录版本与数据哈希。

### T05｜提案（二稿完成，待用户审定/提交）

- 2026-10-01 二稿：按评委视角重写 [proposal.md](../proposal/proposal.md)，采用官方 P×E→B 框架与平台话语，结构为研究问题/P-E-B 设定表/验证方案/已完成可行性/计划成本风险/预期贡献；删去 Q9 Beta 差异、scripted/v3/run_id 等内部术语（证据仍在内部文档，见 [proposal/README](../proposal/README.md)）。PDF 已重建（2 页，含中文首行缩进 2em）：`cd proposal && pandoc proposal.md -o build/proposal.pdf --pdf-engine=xelatex -V CJKmainfont="Songti SC" -V mainfont="Times New Roman" -V geometry:margin=2.2cm -V fontsize=11pt -V indent=true -H <含 \usepackage{indentfirst} 与 \setlength{\parindent}{2em} 的头文件>`。结尾"内生经济指标展望"一句为可选项，用户可删。
- 验收：解释 Agent 的额外价值如何通过对照验证，说明概率计分/历史人口/信息时点的风险与替代方案。
- 账号、邀请码及提交回执由用户确认；队名已知不代表报名已完成。

## 随后进入

- T06：小规模 LLM 开发试验与总预算冻结，依赖 T04 和[模型身份/时间边界登记](MODEL_TEMPORAL_LEAKAGE.md)；未知截止允许标注为探索性回顾模拟，不得声称严格事前预测。
- T07：正式方案冻结与测试，依赖 T06 和完整历史输入验收。
- T08：论文、必要消融、复现包与演示，依赖 T07；清单见 `submission/README.md`。

交接时写：任务编号、已改文件、命令/证据、剩余缺口。任务板只记录结果；不要把研究长文再复制到这里。

### T02 补充｜SCE 逐期波动统计（2026-10-03 完成，人口模拟设计实测依据）

- 新交付：`scripts/analyze_sce_wave_stats.py`（纯 pandas，参数化 `--months`，默认主窗口 202011–202112，背景全 2020–2024）+ 输出 `studies/sce_inflation_expectations/reports/POPULATION_WAVE_STATS.{md,json}`（所有聚合未加权/加权双版）。
- 三个设计问题实测结论：① core 层分层最有效维度为 employment（组间方差占比 1.85%、组间中位数极差 6.3pp）/ education / age，income 次之，region/numeracy 最弱；任一单维组间方差占比 ≤1.2%，分层价值在覆盖组间差而非降总方差。② normal 层外推平稳性成立：Q9_mean within-person 相邻月自相关 0.597（加权，n=57,717 对），但只能外推结构不能外推水平（2021 年 Q9_mean 从 4.4 升至 6.8）。③ B 线（≤M−12 旧人口）可用但不应裸用：income/employment 的 lag-12 TVD 均值 0.032–0.038（加权 0.034–0.041），建议按年校准；housing 表观漂移为小样本噪声（月 n≈150）。
- 编码核实：`Q8v2` 本文件仅 1(up)/2(down) 两码、无"持平"码（以 `Q8v2part2` 符号佐证）；`Q8v2part2` 有个别录入异常值（最大 10000，|x|>100 已剔除并计数）。
- 复算：`/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/analyze_sce_wave_stats.py`；2021-06 Q9_mean 加权/未加权均值已独立复算一致。无 git commit。
