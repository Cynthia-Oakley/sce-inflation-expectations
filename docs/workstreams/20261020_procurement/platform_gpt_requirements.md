# 官方GPT接入：已知能力与最小确认项

核查日2026-10-20。成功读取免费initialize、tools/list、get_user_pool_simulation_capabilities。未运行收费问卷、未发送个人资料、未消耗平台Chat额度。原始证据仅本地：`data/raw/mcp_checks/2026-10-20_procurement_free_v1/evidence.json`。

用户随后提供官方文档库。本轮以浏览器取得六份在线正文，对照LLM接入、计费、FAQ、数据服务和Python provider参考。新证据：`data/raw/mcp_checks/2026-10-20_official_model_docs_v1/receipt.json`，保留取得时间、URL和哈希；没有再次调用MCP或访问账号。以下区分框架能力、平台界面与实际付费接口。

## 文档已确认什么

1. **这份API参考介绍Python框架。**包括研究接口、引擎、数据结构、人口provider与轨迹存储。[用户给出的参考目录](https://socioverse.fudan-disc.com/docs/zh/reference/)
2. **自带人口与逐人信息受框架支持。**文件provider可读CSV/Parquet；观察和历史可由决策模型渲染进每个人的提示。我们现有本地输入方式有对应框架接口，不需要为了用GPT先换一套人口。[Population provider](https://socioverse.fudan-disc.com/docs/reference/providers/)、[LLM接入](https://socioverse.fudan-disc.com/docs/zh/guides/llm-clients/)
3. **本地LLM通过配置模型凭据接入。**`SV_LLM_API_KEY`、`SV_LLM_BASE_URL`、`SV_LLM_MODEL`分别处理凭据、OpenAI兼容端点和模型；具体研究还可能在decision_args中指定模型。文档没有说明如何把参赛MCP凭据用于本地通用GPT调用。[配置说明](https://socioverse.fudan-disc.com/docs/zh/guides/llm-clients/)
4. **Agent和Sim是两个额度账户。**平台上的模拟决策和MCP数据服务计入Sim，助手对话计入Agent。这证明Sim用途覆盖模拟，但没有给出本地通用GPT的可调用端点或单价，也没有确认本次$70追加在哪条余额。[额度与计费](https://socioverse.fudan-disc.com/docs/zh/hosted/quotas-and-billing/)
5. **在线界面存在导入限制。**FAQ明确当前不能通过界面上传自己的数据，文件人口建议在本地运行；也未提供直接下载研究包的按钮。因此“平台团队帮忙导入既有study”仍需另确认，不能直接宣布可迁移。[在线FAQ](https://socioverse.fudan-disc.com/docs/zh/hosted/faq/)
6. **Population MCP是另一个服务。**公开说明的模拟入口仍是从平台池抽人再统一答卷，与本日实际schema一致；自带文件人口属于框架provider，不能据其存在就推定该收费MCP接受本地逐人输入。[数据服务](https://socioverse.fudan-disc.com/docs/guides/data-services/)

**当前结论：本地同输入运行的工程基础已具备；平台额度如何支付它的GPT调用，公开文档仍未给出完整接入方式。**没有据此断言平台永远不支持。待确认应聚焦“计费通道或既有研究包导入”，不再反复询问框架是否能自带P/E。

## 当前事实

- 服务：user_pool_mcp 1.27.0；实际llm配置gpt-4o-mini；并未确认执行GPT-4o。
- 别名目录包含GPT=gpt-4o-2024-08-06，但模拟调用schema无model字段。
- 模拟顶层字段：platform_id、distributions、user_count、questionnaire、auth、prompt_language、max_workers、seed、allow_virtual_users、sampling_mode。
- 没有已声明的逐人persona/messages/history输入。questionnaire的additionalProperties不是任意字段会被服务消费的保证。
- 官方文档说本地引擎可接OpenAI兼容服务，不等于参赛额度附带通用OpenAI兼容网关。[数据服务](https://socioverse.fudan-disc.com/docs/guides/data-services/) · [官方源码说明](https://github.com/sii-research/SocioVerse2)

## 平台若能提供以下能力，就可以继续做同输入适配

1. 接收本地每人的完整messages，或明确接收可等价渲染的persona、E、本人历史；不自动叠加另一位平台persona。
2. 返回实际model/snapshot，说明模型及温度能否固定；不要求必须GPT-4o，实际支持的GPT模型也可登记。
3. 关闭隐式联网、检索及历史目标信息补全，说明服务端system prompt是否固定。
4. 返回原始Q8/Q9文本，保留概率不合法/失败而不静默归一化或补答；说明重试策略。
5. 返回逐次用量/费用或明确单价和硬上限，并确认计入Simulation额度而非Chat Agent额度。

可向平台转述（只是本地草稿，未发送）：

> 我们已在本地官方引擎完成SCE逐人问卷管线，并阅读LLM接入、计费及在线FAQ。想确认两点：①参赛Sim额度是否提供支持本地自带逐人messages的GPT调用通道，如有请提供用户可用的接口说明、模型和计价；②若没有，团队能否协助导入现有study，在平台按原P/E与提示运行并导出原答？希望复用现有研究包，减少平台Chat重新构建的消耗。另请确认追加的$70计入哪条余额。

**不采用的推断**：不把别名当实际执行模型，不把问卷任意字段当已支持参数，不将另一次人口池模拟称同输入公平模型对照。当前无运行任务、无新增付费授权等待执行。
