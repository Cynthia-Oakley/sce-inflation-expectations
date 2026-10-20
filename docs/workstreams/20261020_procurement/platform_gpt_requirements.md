# 官方GPT接入：已知能力与最小确认项

核查日2026-10-20。初次免费证据仅本地：`data/raw/mcp_checks/2026-10-20_procurement_free_v1/evidence.json`。官方MCP先拒绝空选项，随后1人真实选项试测只返回一个选项和理由。用户再要求试OpenRouter后，1次Qwen2.5直接API已返回十个合计100%的概率，存在可无损转换的平铺字段表示差异。均未发送真实SCE个人资料，未使用平台Chat。下文区分模型能力、问卷接口与实际返回。

用户随后提供官方文档库。本轮以浏览器取得六份在线正文，对照LLM接入、计费、FAQ、数据服务和Python provider参考。新证据：`data/raw/mcp_checks/2026-10-20_official_model_docs_v1/receipt.json`，保留取得时间、URL和哈希；没有再次调用MCP或访问账号。以下区分框架能力、平台界面与实际付费接口。

## 文档已确认什么

1. **这份API参考介绍Python框架。**包括研究接口、引擎、数据结构、人口provider与轨迹存储。[用户给出的参考目录](https://socioverse.fudan-disc.com/docs/zh/reference/)
2. **自带人口与逐人信息受框架支持。**文件provider可读CSV/Parquet；观察和历史可由决策模型渲染进每个人的提示。我们现有本地输入方式有对应框架接口，不需要为了用GPT先换一套人口。[Population provider](https://socioverse.fudan-disc.com/docs/reference/providers/)、[LLM接入](https://socioverse.fudan-disc.com/docs/zh/guides/llm-clients/)
3. **本地LLM通过配置模型凭据接入。**`SV_LLM_API_KEY`、`SV_LLM_BASE_URL`、`SV_LLM_MODEL`分别处理凭据、OpenAI兼容端点和模型；具体研究还可能在decision_args中指定模型。文档没有说明如何把参赛MCP凭据用于本地通用GPT调用。[配置说明](https://socioverse.fudan-disc.com/docs/zh/guides/llm-clients/)
4. **Agent和Sim是两个额度账户。**平台上的模拟决策和MCP数据服务计入Sim，助手对话计入Agent。这证明Sim用途覆盖模拟，但没有给出本地通用GPT的可调用端点或单价，也没有确认本次$70追加在哪条余额。[额度与计费](https://socioverse.fudan-disc.com/docs/zh/hosted/quotas-and-billing/)
5. **在线界面存在导入限制。**FAQ明确当前不能通过界面上传自己的数据，文件人口建议在本地运行；也未提供直接下载研究包的按钮。因此“平台团队帮忙导入既有study”仍需另确认，不能直接宣布可迁移。[在线FAQ](https://socioverse.fudan-disc.com/docs/zh/hosted/faq/)
6. **Population MCP是另一个服务。**公开说明的模拟入口仍是从平台池抽人再统一答卷，与本日实际schema一致；自带文件人口属于框架provider，不能据其存在就推定该收费MCP接受本地逐人输入。[数据服务](https://socioverse.fudan-disc.com/docs/guides/data-services/)

**当前结论：本地同输入运行的工程基础已具备；平台额度如何支付它的GPT调用，公开文档仍未给出完整接入方式。**没有据此断言平台永远不支持。待确认应聚焦“计费通道或既有研究包导入”，不再反复询问框架是否能自带P/E。

## 用户质疑后的规范补查：需要收窄上一轮结论

**这次错误不构成GPT-4o-mini不能回答Q8/Q9的证据。**实际得到的是服务端`ValueError`及`questionnaire[0].options must contain at least two options.`，没有模型原始回答或逐次模型身份。合理解释是问卷参数校验拦截；服务端源码闭源，未取得内部调用日志，不将推测的完整执行顺序写成已验证事实。

进一步查阅了[外部能力的使用流程](https://socioverse.fudan-disc.com/docs/zh/guides/capabilities/)、[数据服务](https://socioverse.fudan-disc.com/docs/guides/data-services/)、[研究自身的LLM调用方式](https://socioverse.fudan-disc.com/docs/zh/guides/llm-clients/)、[额度说明](https://socioverse.fudan-disc.com/docs/zh/hosted/quotas-and-billing/)，并对照本地官方`resources/capabilities.yaml`、`sv-build-population`规范。结果如下：

- **问卷服务有一层产品接口。**Population MCP负责从平台池抽人、提交统一问卷、返回JSONL；这与自定义study中的逐人prompt、memory、Action分工不同。它不是文档已承诺的任意messages模型网关。
- **公开规范没有讲清题目类型。**部署schema只写`question`与`options`，条目是通用object；未声明开放题开关、数值范围、Q9合计约束或模型选择参数。免费MCP元数据进一步查询得到`resources=[]`、`prompts=[]`，没有额外题型说明可读。查不到正式用法，不等于证明服务绝不支持。
- **旧问卷示例不能覆盖当前接口。**旧官方仓库的[经济问卷](https://github.com/FudanDISC/SocioVerse/blob/main/questionnaire/quesionnaire_eco.json)17题均标`type: choice`，使用`content/choices`，而当前工具用`question/options`。可作为真实选项的示例，不能将旧字段直接当作新接口的数值题开关。
- **Q9有自然的非空选项。**十个通胀区间本身就能放进`options`，问题正文要求给每档分配概率并合计100%。这是值得验证的候选写法，既不需要空选项，也不需要无意义的占位选项。上一轮没有测试这种写法，因此还不能断言该服务强制单选、不能返回概率。
- **Q8还需检查数值幅度。**可将上涨/下跌/大致不变作为真实方向选项，在正文同时请求百分比幅度。但如果服务只保留方向标签，依然不满足Q8；不能把有选项或语法通过当作功能通过。

已准备[平台格式候选](native_questionnaire_candidates_v1.json)：Q9十档真实选项＋概率要求；另附Q8方向与幅度候选。只做字段和档位检查，**没有新增付费调用、没有已验证的模型输出**。建议下一次先单独Q9、1人技术验证，观察回包是否保留十个概率，还是只剩一个选项或报错。若Q9可用再检查Q8，且逐人本地P/E与历史仍是另一个未解决条件。新增调用需另确认，不沿用已完成的一笔调用批准。

核查元数据：[本次规范核查](questionnaire_norms_check_v1.json)。补查不改变旧试测原始请求、源码pin、错误或费用未知状态，也没有联系平台。此前“不能直接承接”的表述限定为**已提交的空选项开放题格式不被接受**，不扩大为“GPT能力不足”或“所有概率题都不支持”。

## Q9真实十档选项：1人试测已完成

用户明确要求尝试上述另一候选后，按1人、一次新请求执行。使用同一官方MCP和Nemotron美国合成人口，种子20261020、并发1、当前服务配置GPT-4o-mini。只输入公开BLS背景和Q9；不发送SCE个人、历史或答案，不测Q8，不换模型。为技术简化抽取一位女性合成persona，不作人口代表性解释。

**调用成功，但返回形式仍不满足Q9：**服务`status=ok`、`line_count=1`、`llm_model=gpt-4o-mini`；逐人JSONL的回答是`{"q_id":0,"answer":"A","reason":"…"}`。A对应原Q9第一档“12%或以上”，不是十个概率的数组。索引抽样1人、虚拟回退0，服务报告耗时15.956秒。

这次明确越过了空选项校验，获得了单选形式的实际答案；**仍未验证概率分配能力**。服务返回的JSONL是经过服务包装的答案，未附未经处理的模型文本。无法区分是服务内部提示、GPT响应还是解析层导致只剩一个选项，不能据此说GPT本身不会回答Q9，也不能推断所有未公开模式均不支持。单个答案不用于估计模型的拟合水平。

新增请求按原邮件费率预计$0.004，和上一请求按$0.040保守预留合计$0.044，沿用此前明确批准的$0.10累计上限。用户本次“尝试另一候选”的授权与原金额确认分开记录；没有自动重试、追加Q8、扩样或切换模型。回包没有费用/token回执，实际扣费仍未知，估算不是账单。

有效包：`outputs/sce_platform_native_q9_pilot_20261020_v1/`，含请求/协议/授权、能力、完整原始回包、`inspection.json`。公开技术摘要：[native_q9_pilot_result_v1.json](native_q9_pilot_result_v1.json)。旧空选项源码在改动前另保全到`outputs/sce_platform_survey_pilot_source_snapshot_20261020_v1/`，原始协议/请求/回包未改。共用入口已按本轮作小适配，8项离线检查通过；当前无运行中任务。

**下一步的确认问题更具体了：**请平台提供支持逐人十档概率的题型参数/示例，以及未经解析的模型原始文本；如问卷服务只提供选项结果，需要能接本地messages或既有study的模型调用路径。未获得上述支持前不继续调整选项或追加Q8试探。原`native_questionnaire_candidates_v1.json`保留准备时状态与哈希，实际执行状态以本段及运行包为准。

## OpenRouter Qwen直接调用：十档概率已返回

按用户新指令，仅新增1次公开输入的Q9格式检查，选择此前已接通且较擅长JSON的Qwen2.5-72B，经OpenRouter锁定DeepInfra `deepinfra/fp8`，禁止供应商回退。温度0.5、JSON对象模式、最多1,024输出token，无自动重试、不调用LLaMA。使用同一公开BLS背景、Q9问题和十档区间，没有SCE人口、本人历史或真值，也不重启已停止的旧Qwen批次。

**实际收到十个概率，原顺序为`[15,25,30,15,8,4,2,0,0,1]`，合计100%。**每项在0—100内，共用Q9合法性函数通过。回包模型与DeepInfra供应商均匹配，finish_reason为stop。调用约6.632秒，307输入token、108输出token，API报告本次费用$0.00015372。

需保留的细节：题目文字称`q9.bin1`到`q9.bin10`，模型将其按字面返回为平铺JSON键；第一遍读取器预期嵌套对象，报KeyError，原`inspection.json`如实保留。后续**零API地按唯一键名嵌套**，没有改任何概率、归一化或重生成。严格嵌套schema未通过与概率数值合法分别报告，不能隐藏前一个格式差异。完整新读数在`offline_key_readout.json`，正式模型提示可沿用既有清楚的嵌套JSON示例。

本次最多预留$0.001123、设置$0.01子上限，沿用此前明确批准的OpenRouter累计$1上限；此前旧批保守估$0.200809另保留。不把平台MCP的$0.10预算和OpenRouter预算混用；本次走自有OpenRouter余额，没有消耗平台Sim/Chat额度。原供应商价格目录本日免费复核为输入$0.36/百万token、输出$0.40/百万token，未提升请求最高价。

这说明**本地直接调用路径能拿到完整Q9概率**，没有证据表明整个SocioVerse引擎都限制单选。它不独立识别官方MCP单选究竟源于内部提示、模型还是解析：本次同时换了模型、模型可见提示与JSON模式，不是同模型随机对照。1份成功也不能替代此前139/144合法率的完整记录，不能宣称稳定格式已达99%或拟合改善。

因此采购角色实验可以保留“现有本地官方引擎＋OpenRouter Qwen”这条可运行候选，不再用Population问卷服务冒充通用模型接口。模型默认与新批次尚未升级/冻结；大样本仍须保留合法性、同输入和费用验收。官方额度路线继续等待概率题或自带messages的受支持说明。

运行包：`outputs/sce_openrouter_q9_format_20261020_v1/`。入口`scripts/check_sce_openrouter_q9_format.py`复用已有路由、费用上界和Q9校验；本批已执行，不再运行其run命令。旧Qwen研究轨迹和本次初始错误记录均未改写。公开结果：[openrouter_q9_format_result_v1.json](openrouter_q9_format_result_v1.json)。

## 当前事实

- 服务：user_pool_mcp 1.27.0；实际llm配置gpt-4o-mini；并未确认执行GPT-4o。
- 别名目录包含GPT=gpt-4o-2024-08-06，但模拟调用schema无model字段。
- 模拟顶层字段：platform_id、distributions、user_count、questionnaire、auth、prompt_language、max_workers、seed、allow_virtual_users、sampling_mode。
- 没有已声明的逐人persona/messages/history输入。questionnaire的additionalProperties不是任意字段会被服务消费的保证。
- 本日用户批准10人兼容性试测后，服务端明确拒绝`options=[]`：`questionnaire[0].options must contain at least two options.`。一次模拟工具调用、0逐人回答，无付费重发；实际扣费未知。[原始错误与技术结论](official_pool_pilot.md)。数值开放题和Q9十档概率的正式支持成为新增前置条件，不能用单选替代。
- 官方文档说本地引擎可接OpenAI兼容服务，不等于参赛额度附带通用OpenAI兼容网关。[数据服务](https://socioverse.fudan-disc.com/docs/guides/data-services/) · [官方源码说明](https://github.com/sii-research/SocioVerse2)

## 平台若能提供以下能力，就可以继续做同输入适配

1. 接收本地每人的完整messages，或明确接收可等价渲染的persona、E、本人历史；不自动叠加另一位平台persona。
2. 返回实际model/snapshot，说明模型及温度能否固定；不要求必须GPT-4o，实际支持的GPT模型也可登记。
3. 关闭隐式联网、检索及历史目标信息补全，说明服务端system prompt是否固定。
4. 返回原始Q8/Q9文本，保留概率不合法/失败而不静默归一化或补答；说明重试策略。
5. 返回逐次用量/费用或明确单价和硬上限，并确认计入Simulation额度而非Chat Agent额度。

可向平台转述（只是本地草稿，未发送）：

> 我们已在本地官方引擎完成SCE逐人问卷管线，并阅读LLM接入、计费及在线FAQ。想确认两点：①参赛Sim额度是否提供支持本地自带逐人messages的GPT调用通道，如有请提供用户可用的接口说明、模型和计价；②若没有，团队能否协助导入现有study，在平台按原P/E与提示运行并导出原答？希望复用现有研究包，减少平台Chat重新构建的消耗。另请确认追加的$70计入哪条余额。

本日实测后可补充（未发送）：

> 我们已批准并尝试一次10人Population MCP问卷，仅含公开背景与Q8/Q9。服务返回`questionnaire[0].options must contain at least two options.`，没有逐人答案。请问是否支持数值开放题，以及同一人向十个区间分配合计100%的概率？若支持，请给可执行参数和原始回包示例；若不支持，我们需要上述自带messages或study导入路径。也请确认这次校验失败是否产生扣费。

1人试测后可再补一句（未发送）：

> 随后我们将Q9十个真实区间放入options，并在question要求每档概率合计100%，只测1人。服务返回status=ok、llm_model=gpt-4o-mini，但答案仅为answer="A"与reason，没有十档概率。请问该工具是否有概率分配/数值回答模式，能否返回未经解析的模型文本？希望确认接口用途，而非改变SCE问卷口径。

**不采用的推断**：不把别名当实际执行模型，不把问卷任意字段当已支持参数，不将另一次人口池模拟称同输入公平模型对照。当前无运行任务、无新增付费授权等待执行。
