# 官方GPT接入：已知能力与最小确认项

核查日2026-10-20。成功读取免费initialize、tools/list、get_user_pool_simulation_capabilities。未运行收费问卷、未发送个人资料、未消耗平台Chat额度。原始证据仅本地：`data/raw/mcp_checks/2026-10-20_procurement_free_v1/evidence.json`。

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

> 我们已在本地官方引擎上完成SCE逐人问卷模拟，希望使用参赛Simulation额度调用GPT。现有人口池问卷接口未声明逐人自带输入。请确认是否有接收完整messages或自带persona/E/history的接口，且可固定实际模型、返回原始回答及用量、关闭额外persona/联网/自动重试；若有，请提供schema、计价及授权方式。我们不需要平台Chat Agent编排。

**不采用的推断**：不把别名当实际执行模型，不把问卷任意字段当已支持参数，不将另一次人口池模拟称同输入公平模型对照。当前无运行任务、无新增付费授权等待执行。
