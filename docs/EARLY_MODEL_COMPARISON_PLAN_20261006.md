# 较早模型对照计划（草案）

**核查日：2026-10-06。** 仅为后续设计；不改当前五组 DeepSeek 运行配置，不代表已经运行或批准新增 API 费用。

## 候选核查

| 候选 | 官方时间信息 | OpenRouter 当前目录 | 上下文与 JSON |
|---|---|---|---|
| Qwen2.5-72B-Instruct | Qwen 于 2024-09-19 发布。官方模型卡未列训练/知识截止；OpenRouter 页面另标知识截止 2024-06-30，应视为目录元数据，不能写成 Qwen 官方披露。 | `qwen/qwen-2.5-72b-instruct` 有付费路由（DeepInfra、NovitaAI）；另有 `qwen/qwen-2.5-72b-instruct:free` 页面。付费页当前列 $0.36/M 输入、$0.40/M 输出和 33K 上下文；免费页列 131K。 | 模型卡称支持最长 131,072 tokens，强调 JSON 结构化输出。OpenRouter 模型页称支持 `response_format` JSON Schema；仍应以锁定的 provider 参数支持为准。 |
| Llama 3.1 70B Instruct | Meta 模型卡：2024-07-23 发布；预训练数据截止 2023-12。OpenRouter 目录的知识截止标注为 2023-12。 | `meta-llama/llama-3.1-70b-instruct` 当前可用，页面列 DeepInfra Turbo、Amazon Bedrock；列价 $0.40/M 输入和输出。当前未查到此型号的免费路由。 | Meta 卡列 128K 上下文；OpenRouter 列 131K。OpenRouter 模型页称支持 JSON Schema `response_format`。 |

Qwen 与 Llama 候选当前均可用，无需此刻替换。免费目录会滚动更新；Qwen 的 `:free` 路由适合另做接线试跑，正式比较应使用可固定的付费 provider 路由。若执行前型号或 endpoint 消失，先重新核查并更新冻结记录，不在运行中静默换模。

## 设计与记录

待当前实验结束并冻结后，以两阶段比较控制新增调用：第一阶段只交叉比较 **baseline + basket_focus** 两组，每个候选模型 **20 个固定 ID × 2 个月 × 2 组 = 80 条**，两模型共 160 条目标回答；若第一阶段支持继续，再补其余三组 240 条，累计五组 400 条，不重跑前两组。两阶段均锁同一 P、E、问卷版本、persona-ID 映射、prompt、输出 schema 与评价代码，`temperature=0`。除模型/服务路由外不改其他条件；失败时每条目标回答最多重试一次并留存首答、错误与重试记录。主要用途是模型敏感性/稳健性比较，当前不作优劣排序或效果结论。

其中 baseline + basket_focus 是固定条件的敏感性对照，并非本轮筛出的优胜臂（本轮组合机制没有稳定收益）；若预算更小，可先只跑 baseline（2 模型 × 2 个月 × 20 人 = 80 条），再按事先冻结的方案补另一臂，不因中间结果临时选择有利条件。

继续走现有 OpenAI 兼容入口，`base_url=https://openrouter.ai/api/v1`。去掉 DeepSeek 私有 `thinking` 参数；候选使用同一 JSON Schema 和响应校验。OpenRouter 文档支持兼容模型的结构化输出，可设 `provider.require_parameters=true`；逐模型固定一个确切 provider endpoint，并禁用 fallback/load balancing。请求与响应均记精确模型 slug、provider slug、返回的模型标识、OpenRouter generation/request ID、输入/输出 token 数、单价与费用、prompt/schema 哈希及运行时间。若服务端不能返回或锁定权重构建版本，明确记为未知，不把模型别名当作不可变权重快照。

## 单列费用草案

对本次 trial 的 10 个 `llm_calls.jsonl` 仅抽取 usage 元数据：200 条调用均有 `prompt_tokens`，实测最大值 **2,707**；按 1.5 倍跨 tokenizer 余量，预算估算按每次 **4,061 输入 token**（ceil），每次最多生成 **1,024 输出 token**。输入值是费用估算，不是提示词截断上限；请求应发送完整冻结提示词。若执行时单次输入超过该估算，先重算预算并另行批准。

按上述 token 包络和核查日 OpenRouter 目录价，包含每条最多一次重试：

| 阶段 | 目标回答 / 最多请求 | 按 token 价估算 | 建议单独申请上限 |
|---|---:|---:|---:|
| 第一阶段：baseline + basket_focus | 160 / 320 | 约 $0.625 | $0.80 |
| 第二阶段：补其余三组，累计五组 | 增加 240 / 480 | 约 $0.937 | $1.20 |
| 五组累计 | 400 / 800 | 约 $1.562 | $2.00 累计 |

费用须按阶段向 OpenRouter **另行申请**，与当前 DeepSeek 的 **$2** 分开；第二阶段只在第一阶段结束后单独审批，不预先调用。此估算依赖 tokenizer、provider endpoint 和目录价；开跑前重新核对实际 provider 费率、完整 prompt 的 usage 预览与数据路由，再锁阶段上限。价格或 token 用量高于估算时先重算，不沿用 DeepSeek 预算。

## 解释边界

2021 早于 Llama 的 2023-12 截止，也早于 OpenRouter 给 Qwen 标注的 2024-06 截止；模型仍可能记得或编码 2021 年历史。因此较早发布或较早截止不能消除训练记忆/前视风险，结果只能支持模型敏感性与稳健性讨论。要检验截止内外差异，应另设模型冻结后才公开目标答案的较晚月份，或预先封存的盲日期预测；Qwen 的官方截止未披露，不能仅凭 OpenRouter 元数据声称严格时间盲测。

## 来源

- Qwen：[官方模型卡](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct)；[Qwen2.5 发布公告](https://qwenlm.github.io/blog/qwen2.5/)。
- Meta：[Llama 3.1 官方模型卡](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md)。
- OpenRouter：[Qwen2.5-72B 页面](https://openrouter.ai/qwen/qwen-2.5-72b-instruct)、[Qwen 免费路由页面](https://openrouter.ai/qwen/qwen-2.5-72b-instruct:free)、[Llama 3.1 70B 页面](https://openrouter.ai/meta-llama/llama-3.1-70b-instruct)、[免费模型目录](https://openrouter.ai/collections/free-models)、[结构化输出说明](https://openrouter.ai/docs/guides/features/structured-outputs)、[Provider 路由说明](https://openrouter.ai/docs/guides/routing/provider-selection)。
