**2026-10-08 续跑结果已更新：** Qwen2.5-72B原DeepInfra路由在显式允许降级探针后完成40份；Llama3.3-70B/3.1-8B分别4/1份有效，问卷概率总和错误触发暂停。Qwen5月误差更小、6月更大，暂不替换正式模型。见[完整记录](SCE_MODEL_FOLLOWUP_20261008.md)和[可复核汇总](sources/sce_model_followup_final_20261008.json)。含前轮API已报费用$0.08185786、未知429另预留$0.00137398；没有Phala调用。下文“仅调查/千问未调用/缺授权”均为此前阶段的封存说明，不能当作当前状态。

**2026-10-08 状态释义已查明：`-2` 是性能降级。** OpenRouter当前官方页面代码定义 `DegradedPerformance=-2`，另列 `Down=-5`、`Disabled=-10`；先前脚本仅接受0过严，不能把千问被拦截解释为不可调用。见本文末节和[公开证据快照](sources/sce_openrouter_status_models_20261008.json)。本次仅免费目录/来源调查，未改检查器、未新增真实调用。

**2026-10-08 较早模型真实对照已有结果。** 用户明确同意 OpenRouter/固定DeepInfra 的画像发送范围和两模型总$0.50后执行。[结果与准确路径](SCE_EARLIER_MODEL_TRIAL_RECEIPT_20261008.md)：LLaMA 3.1-70B完成40回答/41请求（1次Q9合计99%重试），API记录$0.0414368；Qwen指定路由两次目录status=-2，未通过原健康门，0调用，不换供应商。Q9同计分共同比较5/6月18/19人：LLaMA个体MAE2.421/3.084，DeepSeek2.911/2.965pp；LLaMA月内IQR均0.036pp，比参考更集中；Q8更分散但个体MAE仍约5pp。**不升级正式模型**，20人开发诊断不代表全国/盲测。真实包`outputs/sce_earlier_model_trial_20261008/`、评价最终`outputs/sce_earlier_model_analysis_20261008_v3/`；7项定向测试通过，冻结来源/身份/账务验收，15个待审文件保留。下一项先免费检查千问原路由，恢复后独立续跑并计入已花费用、不重复LLaMA；Q9概率表达另登记机制研究。下文“缺授权/未调用”是此次授权前历史状态。

# 模型发布时间、知识边界与小试状态

核查：2026-10-08（模型目录在 10-07 开始核查）。

## 已核实的时间信息

- **Llama 3.1-70B-Instruct**：Meta 官方模型卡记发布日 **2024-07-23**；预训练数据截止 **2023-12**。这是预训练的披露，不自动证明指令微调资料或当前 API 权重的所有知识都止于该日。[官方模型卡](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md)。
- **Qwen2.5-72B-Instruct**：Qwen 官方发布文章日期 **2024-09-19**。查到的官方模型卡、发布说明及 Qwen2.5 技术报告没有给出可作为精确预训练资料时间界限的明确日期。OpenRouter 目录标 **2024-06**，只能标为服务商目录信息，不升级成官方确认。[官方发布文章](https://qwenlm.github.io/blog/qwen2.5/)、[模型卡](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct)、[官方技术报告](https://arxiv.org/html/2412.15115v2)、[OpenRouter 目录](https://openrouter.ai/qwen/qwen-2.5-72b-instruct)。

因此 2021 两月对照不能排除记忆；若在 2025–2026 检验“训练后时期”，LLaMA 的预训练边界证据更清楚，但仍需保存实际返回型号、路由与不可知的权重构建版本。不把目录日期当作完整无泄漏证明。

## “美国公司的模型是否更像美国居民”

作为可检验假设合理，尚无本项目实证。开发者所在国家不能直接推导训练语料中美国居民的占比；英语语料也含其他国家、经济专家、新闻作者和网络活跃者，不是美国居民代表性样本。指令微调还可能使回答更像谨慎/专业的助手，抵消真实居民的主观差异。

两个模型在相同 P、E、提示词下对照，能检验哪一个回答更适合本项目，不能单独识别差异是否来自美国语料。先看水平偏差、月内分散度、画像组差异，再在已登记的更长窗口检验趋势与阶段稳定性；小样一次生成不用于最终选型。

## 小试状态（截至本文写入）

- 新入口：`scripts/run_sce_model_counterfactual.py`；费用/路由保护：`studies/sce_inflation_expectations/model_counterfactual.py`。原 study 配置与 .env 未改。
- 已有 80 候选请求、40 个匹配参考案例。只发 payload；固定 v2-abstract、温度 0.5、1024 输出 token、DeepInfra 指定路由、无 fallback。执行前免费查询实际 provider 参数、价格和状态；负值状态先阻断。
- 31 项离线测试通过；离线验证请求/参考源哈希通过。新入口默认只做离线检查，无明确执行参数不读密钥/不联网。
- **真实调用未执行。** 第一次执行命令被自动审批拒绝，理由是“仅同意小规模尝试”尚缺对收入/就业/住房等画像发送至 OpenRouter/DeepInfra 及 $0.50 预算的明确授权。没有绕过拒绝，没有模型调用或产生本轮费用；已通过异步问题请求明确确认。
- 预定输出目录 `outputs/sce_earlier_model_trial_20261007/` 在拒绝后核查不存在，不称已有结果。若用户明确确认，按同一预算与范围继续；否则人口指标方案与其他免费工作照常推进。

本次拒绝来自自动审批，不是模型服务故障；尚不能判断两个候选服务是否实际能够回答。

## 状态字段与替代型号复核（2026-10-08，最新）

### 状态含义与原检查的修正方向

OpenRouter 官方 OpenAPI/SDK 仅列合法数值，并未解释负值。继续核查当前模型页面加载的官方脚本，找到明确的 `EndpointStatus` 映射：0 Default、−1 Deprioritized、−2 DegradedPerformance、−3 Deranked、−5 Down、−10 Disabled。[官方页面脚本](https://openrouter.ai/_next/static/immutable/chunks/3dd_vwnwpy31s.js)。脚本原件、哈希和摘录已保存；这证明当前页面代码的命名，不保证未来API永不调整，也没有揭示每次降级的具体故障来源。

[官方供应商文档](https://openrouter.ai/docs/guides/community/for-providers#10-uptime-monitoring-and-traffic-routing)规定：95%以上为正常路由，80%–94%为降级/低优先级，低于80%为down/仅作fallback。本次千问DeepInfra近30分钟成功率92.857%，支持JSON、temperature和1024输出上限，仍为−2。此处uptime表示请求成功比例，不是模型能力分数，也不是每份研究问卷必然成功的概率。

因此，既有 `status != 0` 即停的实现属于本项目保守门槛，阻断范围过大。后续应登记新预检版本：0正常通过；−2保留降级标记，先用原固定案例作少量调用检验身份、结构、费用和稳定性，失败则停；−5/−10不批量运行；其他状态按其含义独立处理、未知状态不猜。原指定provider、无fallback、预算累计、消息哈希与回答验收维持原约定。本轮只调查，尚未修改检查器或恢复调用，不能称千问已完成。

### 有依据的候选顺序（不是SCE效果排名）

- **先补原Qwen2.5-72B**：完成已登记跨家族对照。当前DeepInfra可见，输入/输出每百万token $0.36/$0.40，状态−2；降级后是否真正可用仍需实际小探针验证。
- **Llama3.3-70B-Instruct**：优先新增候选。Meta官方发布2024-12-06，预训练截止2023-12，官方IFEval高于3.1-70B，适合检验指令/概率表达改善，但没有SCE更准证据；微调知识不被预训练截止证明。当前DeepInfra状态0、支持JSON，价格$0.10/$0.32。[官方模型卡](https://github.com/meta-llama/llama-models/blob/main/models/llama3_3/MODEL_CARD.md)。
- **Llama3.1-8B-Instruct**：适合与既有70B比较规模影响，预训练截止证据同属3.1系列；DeepInfra状态0、支持JSON，价格$0.02/$0.04。小模型可能增加问卷理解错误，不能把更随机当作更像居民。[目录](https://openrouter.ai/meta-llama/llama-3.1-8b-instruct)。
- **Qwen2.5-7B-Instruct**：同代较小千问对照，当前Phala状态0、支持JSON，价格$0.10/$0.20。该provider与已授权DeepInfra不同，真正画像发送前需明确纳入运行范围；此次不调用。目录标的上架日不代替Qwen家族官方发布时间。[目录](https://openrouter.ai/qwen/qwen-2.5-7b-instruct)。
- **Qwen3-32B**：能力较新候选，2025-04发布；DeepInfra状态0，$0.08/$0.28。需要独立锁定非思考模式并验证实际服务支持，不能只省略reasoning字段假定关闭；其知识时间界限未在本轮确认，不适合作为2025年无记忆证明。暂排在2024模型之后。[Qwen官方发布](https://qwenlm.github.io/blog/qwen3/)、[模型卡](https://huggingface.co/Qwen/Qwen3-32B)。

当前公开目录未列普通 `qwen/qwen-2.5-32b-instruct`，端点404；不能把仍在售的Qwen2.5-Coder-32B当作同一通用模型。Qwen3-30B-A3B-Instruct-2507也有健康JSON端点，可作为更后备选，不优先增加多家服务商和模型版本的混杂。上述价格为查询时指定端点基础价格，不代表整个OpenRouter所有路由；运行前重新核价。该调查不改变正式模型、运行配置或已完成回答。

原始资料：`outputs/sce_openrouter_status_research_20261008/`；小型公开来源与字段摘要：`docs/sources/sce_openrouter_status_models_20261008.json`。选择依据是时间证据、问卷执行能力、可用性和可审计成本；最终仍需同输入比较水平、分散度、格式有效率与跨期表现，不能仅凭一般智力榜排名决定。
