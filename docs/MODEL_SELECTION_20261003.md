# 本地 SCE 首轮模型选择与 Kimi 接入交接

核查日：2026-10-03。负责人：Codex。状态：公开资料与本地源码核查完成；选型、预算为建议，尚未冻结或运行。

## 1. 推荐结论

用户确认已有 Kimi、DeepSeek API。**建议首轮复用 DeepSeek 官方 API 的 `deepseek-flash`，显式关闭思考模式，做历史回顾性流程小试。** 当前官方将其映射为 DeepSeek-V4.1-Flash；这不是最初候选中的原版 V3，也不是不可变的权重快照。该方案减少开户步骤；不表示其 SCE 拟合效果已优于其他模型。[官方接入说明](https://api-docs.deepseek.com/)、[模型目录 API](https://api-docs.deepseek.com/api/list-models/)。

若希望首轮就使用较早的开放权重模型，备选为硅基流动 `Qwen/Qwen2.5-72B-Instruct`。若已有适用地区和账号下可用的 OpenAI 官方 API，研究对照优先考虑 `gpt-4o-2024-08-06`。无需为本次小试同时开通三家；正式主模型在开发期验收后再定。

本轮未读取密钥、未发送真实 persona、未调用任何模型或平台 MCP。用户账号可调用性、余额与延迟仍待实际验收。文档列出模型≠账号调用成功；API 响应自报 model≠独立证明底层权重身份。

## 2. 候选核查

### DeepSeek 原版 V3：旧接入建议需要更正

官方更新日志规定 `deepseek-chat` / `deepseek-reasoner` 于 2026-07-24 停用；此前已经映射到 V4，不能再把 `deepseek-chat` 写成 V3 的固定 ID。现行接入页给出 `deepseek-flash` 与 `deepseek-v4-pro`。[更新日志](https://api-docs.deepseek.com/updates/)。

原版 V3 [开放权重](https://huggingface.co/deepseek-ai/DeepSeek-V3)仍可取得，但没有因此获得当前官方托管端点。Together 的旧 V3 名称还存在升级重定向记录；不能仅凭旧模型字符串认定版本固定。[Together 停服与重定向](https://docs.together.ai/docs/deprecations)。首轮不建议为原版 V3 自建 GPU 推理服务。

### 推荐工程首试：DeepSeek-V4.1-Flash（现行别名）

- `base_url=https://api.deepseek.com`，`model=deepseek-flash`；OpenAI Chat Completions 兼容。
- 默认开启思考。通过 `extra_body={"thinking":{"type":"disabled"}}` 关闭；这是官方 SDK 用法所需的额外参数，不能只设 temperature。[思考模式](https://api-docs.deepseek.com/guides/thinking_mode)。
- 使用 `response_format={"type":"json_object"}`，提示词明确要求 JSON 并给字段示例；仍须本地验证十档概率及 Q8 字段，JSON 模式不保证数值语义正确。[JSON 模式](https://api-docs.deepseek.com/guides/json_mode)。
- 官方峰时单价：每百万 token 输入未命中缓存 $0.30、输出 $1.20；非峰时减半。预算采用峰时且不计缓存优惠。[官方价格](https://api-docs.deepseek.com/quick_start/pricing)。
- 在本轮读取的官方接入/定价/模式资料中未确认完整预训练及后训练截止，登记 `unknown`；别名可能升级，记录调用日期与实际响应元数据，跨日续跑前复核。

### Qwen2.5-72B-Instruct：仍有可用的托管候选

- 官方[模型卡](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct)提供开放权重，描述 JSON 与角色设定能力；未在该模型卡确认完整训练时间边界。开放权重允许自行锁定 revision，但托管服务的量化、模板及权重 revision 仍需另查。
- 硅基流动公开[价格页](https://www.siliconflow.cn/pricing)的页面数据中精确型号为 `Qwen/Qwen2.5-72B-Instruct`，状态 normal，输入/输出均为 **¥4.13/百万 token**、上下文 32768、声明支持 JSON。可用端点 `https://api.siliconflow.cn/v1`；实际账户未探测。
- 该条数据在网页折叠列表的内嵌数据中，普通网页文本抽取未展开；本轮保存原 HTML 并解析了对应型号与 prompt/completion 价格项。不是依据第三方价格聚合站，也没有把 VL 视觉版本混入。
- Together 的 `Qwen/Qwen2.5-72B-Instruct-Turbo` 已于 **2026-02-06** 从 serverless 停用；不要使用旧教程报价。[停服清单](https://docs.together.ai/docs/deprecations)。

### GPT-4o：保留为时间边界研究对照

- 官方[模型页](https://developers.openai.com/api/docs/models/gpt-4o)仍列出 `gpt-4o-2024-08-06` 与 `gpt-4o-2024-11-20`，标称知识截止 **2023-10-01**；标准输入 $2.50、输出 $10/百万 token，支持 Structured Outputs。建议研究时指定日期版本，不用 `gpt-4o` 滚动别名。
- `chatgpt-4o-latest` 已退役，不等于上述 API 快照全部退役。[弃用页](https://developers.openai.com/api/docs/deprecations)。
- 中国大陆不在官方 API [支持地区名单](https://developers.openai.com/api/docs/supported-countries)中；不能把用户已使用 Codex 当作拥有可用的 GPT-4o API 账号。通过学校或其他服务取得的模型须重新核验服务提供方、具体部署版本与报价，不能套用官方直连结论。

## 3. 成本示例及建议预算

为便于比较，假设每人每月一次调用同时回答 Q8/Q9，每次 2000 输入、400 输出 token；40 条回答、不重试、不缓存。以下为算术估计，不是实测账单：

- DeepSeek Flash：40 × (2000 × 0.30 + 400 × 1.20) / 1,000,000 = **$0.0432**。
- 硅基流动 Qwen2.5：40 × 2400 × 4.13 / 1,000,000 = **¥0.39648**。
- GPT-4o：40 × (2000 × 2.50 + 400 × 10) / 1,000,000 = **$0.36**。

首轮 DeepSeek 可提请批准 **$0.30 的模拟 API 预算**：2 次接入/格式小样 + 40 次计划回答，每条至多补试一次，共最多 84 次；若每次实际计费输入≤4096、输出≤1024，峰时无缓存估计上限为 $0.2064384。上限以这些条件成立为前提，不能把它称作厂商账单硬限额。

Kimi 应先设调用次数上限、输出 token 上限、每次调用前预算预留；输入须用适用 tokenizer 或服务端 usage 校准后校验。超长输入拒绝，不静默截断；SDK 内置重试须关闭或纳入同一次数账本，超时但可能已计费的请求保守预留费用。首次两条后按实际 usage 更新估计。编程助手费用另计，不属于这 $0.30。

## 4. 模型时间边界的研究含义

“2023-10 知识截止”不等于“所有 2024 月份均严格盲测”。还需考虑后训练、版本发布日期、推理服务更新以及 P/E 的历史版本。`gpt-4o-2024-08-06` 这个日期版本在 2024 年初尚不存在；2024-12 则可以进一步核查其是否在 as_of 前已固定，但当前没有完成该证据链。

2020/2022/2024 跨时期误差差异还混合了疫情、通胀水平和人群变化，不能直接归因为训练记忆。可以预注册“标称截止日前后表现比较”，不将其解释为污染的因果估计。更强的证据是未来目标公布前冻结 P/E、模型、提示词并封存预测。

DeepSeek 首轮先登记为**历史回顾性条件模拟**。模型身份可登记和价格可核对已经解决云端两项问题；完整训练截止与不可变权重证据仍未知。关闭联网检索只能控制外部信息通道。

## 5. Kimi 接手清单

目标：在唯一 SCE 源码中完成带审计的本地 Chat Completions 接入。不得因为本建议自动更换正式研究模型或启动付费规模。

1. 源码在 `studies/sce_inflation_expectations/`，官方框架核心不动，运行副本沿既有单向导出流程。先完成离线 mock 验收，确认新增 kwargs、响应元数据和失败分支都能保留。
2. 读取用户本地保存的 DeepSeek key；研究 `.env` 中只配置相应的 `SV_LLM_API_KEY` / `SV_LLM_BASE_URL`，simulation 的 `decision_args.model` 明确填写。密钥不进配置导出、日志、截图或交接。Kimi 编程助手连接与模拟 B 连接分别管理。
3. 核对 `/models`，保存目录中 ID/显示名与核查时间。它只证明服务目录状态；真实调用成功仍需两条小样。不得在 404 后自动换成另一模型继续运行。
4. 推荐开发配置：`model=deepseek-flash`；关闭思考；JSON 模式；`max_tokens=1024`；首轮格式小样 temperature=0，后续行为小试暂建议 0.5（属于待冻结设计选择）。不要把本地抽样 seed=42 冒称服务端确定性种子。
5. 核对本地官方示例 `../socioverse2_repo/studies/opinion_diffusion/model.py:177`：当前薄封装只接受 model/temperature/max_tokens，调用后只返回 content。SCE 自有客户端须增加 extra_body/response_format，以及 requested_model、returned_model、request_id、fingerprint（无则 null）、usage、finish_reason、时间、重试和错误记录。先保存允许的回答 content 原文再解析；不保存密钥及隐藏思维内容。
6. 官方 `scripts/demo_offline.py --llm openai` 会先发一个真实 probe，随后运行 demo，不能把它当作免费连通性检查。SCE 两条小样用明确调用计数的专用入口。
7. 先在既有开发资料上准备 **2 人 × 2021-05** 格式小样，再考虑 **20 人 × 2021-05/06**；均为建议，不改已存实验。首轮复用合成 P 与已核验 BLS E，避免同时改变人口与模型。2024-12 不用于调 prompt，以保留候选测试期。
8. 2 条通过只能说明接入与样例格式正常，不能推出稳定性或预测准确率。40 条小试汇报首次有效率、补试后有效率、Q8/Q9 分布、实际 tokens、错误与计分失败；保留全部尝试，禁止静默归一化或换模型兜底。
9. 真值与同期微观问卷不进入调用上下文。之后在开发期安排固定 P 的 E 对照和固定 E 的 P 对照，区分模型随机变化与信息输入影响；先冻结设计，再看目标拟合。
10. 新运行按 run_id 归档。云端与本地若不是同一模型，不能称为严格复现实验，只能比较流程或另列模型条件。

交付物：模型登记、2 条小样验收、运行配置/输入/代码哈希、逐次回答与 usage、预算测算。模型身份只能写到来源实际支持的精度；任何无法确认的 cutoff/revision/计费字段显式标 unknown。

## 6. 证据与核查范围

公开网页来源见各段链接；DeepSeek 定价/思考模式/JSON 文档与硅基流动价格页原始 HTML 已归档至 `../data/raw/model_selection/2026-10-03/`，`manifest.json` 记录 URL、抓取时间与 SHA-256。这些原始网页按现有规则忽略，不混入源码提交。

本地依据：`../socioverse2_repo/studies/opinion_diffusion/model.py`、`../socioverse2_repo/scripts/demo_offline.py`；项目规则和 [本地计划](LOCAL_HARNESS_RUN_PLAN.md)、[时间泄漏协议](MODEL_TEMPORAL_LEAKAGE.md)。本轮只改研究/交接文档，未安装依赖、修改实验源码或运行配置。各供应商实际接通、当前余额与输出质量均未实测。
