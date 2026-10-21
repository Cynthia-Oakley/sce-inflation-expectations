# V3.2同输入比较：AtlasCloud已按约停止

2026-10-21。配置：[v32_comparison_config.json](v32_comparison_config.json)。本轮与Kimi的全时段P/E补齐并行，保持旧回访者人口，不混入新入组或近期合成人口改动。

## 当前执行结果

**最新状态：**人工低并发补齐已获批准，但2次中1有效/1上游429，按约再次停止；未继续752份。累计18次/5有效/13次429，报告费用$0.003359、含未知失败保守记账$0.044795；没有拟合结果。原恢复路径终止，以下12份补齐设计仅作历史记录，不得据其继续运行。详[技术收据v2](v32_technical_result_v2.json)。

已离线准备[SiliconFlow单一供应商新批次](v32_siliconflow_plan.md)，8Core/31测试通过，具体新接收方授权待确认；不把原AtlasCloud5份并入新批成绩。

用户已明确授权原768次/$4。首次16并发技术段中4份有效、12次HTTP429，错误明确标记`upstream_provider_shared_pool`；队列9.10秒后停止，剩余752份未发送，无自动重试。4份回包模型/供应商一致、JSON/Q8/Q9可用，reasoning token均0；不能据此比较拟合优劣。成功回包报告$0.00269434；失败实际扣费未知，保留其保守预留$0.03837168，合计记账$0.04106602。见[公开技术收据](v32_technical_result_v1.json)。

低并发恢复包`outputs/sce_v32_manual_429_20261021_v1/`已离线备好，4项测试通过。建议成功4份原样复用，只对12份429人工再发一次，最多2并发；合并16份全部可用后，继续原752份首次请求。总最多780次尝试，原$4上限不变，恢复及剩余调用的总保守预留$2.462657。再次429或致命错误停止。2并发能否解除上游共享池限流尚未实测，不能承诺。

原人工补齐曾因“无自动重试”单独确认，现已获批并执行到再次429停止；不再运行此恢复路径。原始12份失败留在原账本，恢复后也不能宣称全程零错误或只发生768次尝试。SDK中的`attempt_idx=0`表示各显式请求内部无自动重试；人工重发的12个逻辑槽另以`approved_manual_retry_slot_keys`及原账本来源保留。

```bash
# 下面准备已完成，不能重新创建同名包
python scripts/prepare_sce_v32_rate_recovery.py retry --parent outputs/sce_v32_comparison_calls_20261021_v1 --folder outputs/<fresh_manual_package>
# 新人工补齐授权落盘后，才运行12份；原始4份不重跑
python scripts/continue_sce_pending_calls.py run --folder outputs/<authorized_manual_package> --workers 2
# 仅12份均返回可用、合并16份通过技术检查时，下面命令才会准备752份尾段
python scripts/prepare_sce_v32_rate_recovery.py remainder --parent outputs/<finished_manual_package> --folder outputs/<fresh_tail>
python scripts/continue_sce_pending_calls.py run --folder outputs/<authorized_tail> --workers 2
```

以下保留本轮原设计和准备证据。

## 要回答什么

在完全相同的信息下，换用V3.2是否能更好保留不同家庭的原有信念、改善跨人分布和更新，同时减少总体误差。不能用本轮区分模型规模、训练方法与供应商实现各自的贡献。

四期：2020-09疫情低通胀、2021-09通胀上升、2022-06高通胀、2025-03近期政策阶段；每期同96人、每人两遍。均是已经查看过的开发月，不称独立验证。

- 对照：复用上一轮食品背景组768份Qwen2.5-72B回答（DeepInfra FP8）。
- 新增：OpenRouter `deepseek/deepseek-v3.2`，锁`atlas-cloud/fp8`，不回退供应商；使用自购OpenRouter额度。
- P/E、合成采购角色、8篇新闻、本人真实上期Q8/Q9和更早摘要、信息先后标签、题目与无数值结构示例均逐字保持。
- 温度0.5、JSON模式、最多1024输出token，OpenRouter `reasoning.enabled=false`，无自动重试。请求超时120秒，最多16并发；超时不是模型内容参数。
- 十档有限非负且合计为正时，按用户已确定规则等比例归一化；保留原答、原始合法率及归一化份额。字段缺失、负概率和接口失败不补造。

## 技术检查与运行方式

有效包：`outputs/sce_v32_comparison_trial_20261021_v1/`。768项原提示一致检查、8个官方Core零API单元、30项相关测试已通过。准备过程只哈希真人当前真值及旧计分缓存，不读取当前答案来选择输入。

前16次是总768次中的技术段，每月固定取4次，不另收费重跑；全部回包且归一化后可用率至少99%，检查通过后同一队列继续其余752次。不看这16次的拟合成绩，不按结果调整输入。技术段或后续失败按实际保留；不自动重试。每个请求实时存储原答、供应商、usage、费用、时间和HTTP错误码，断网不抹去已得回答。

这仍是官方引擎验收过的输入，真实请求由已有SCEOpenAILLM和逐请求调度器执行，不能写成所有真实调用都在Core循环中完成。两模型调用不同时，旧Qwen控制的时间差是限制。

### 为什么此前分很多批

旧运行入口按“月份×组×遍数”保存和调度，断网时整个单元停止；部分阶段还使用短队列，工程上确有多次启动成本。不是已测得账户TPM上限才这样拆分。

上一轮价格对照共2,304请求，8并发，平均延迟12.032秒，实际3,469.36秒（57.8分钟），无接口错误；`2304×12.032÷8`约57.8分钟，说明该轮主要时间花在模型响应。该批账本没有限流错误；不能由此保证新供应商没有限流。

本轮准备、离线检查和真实调用分开；获批后技术段与正式段连续执行。实际稳定并发能力、V3.2延迟和429情况由本批回包判断，不预先保证16并发能线性加速。HTTP429或致命错误会停止继续派发，不绕开服务限制。

## 评价与选择

复用冻结Q9计分器、共同支持和设计权重，Q8单独计分。主看W1、变化W1、高低先验组偏差/保留、跨人IQR和重复波动；同时报告每月中心MAE/RMSE、个人误差及照抄本人上期。稀疏组明确标记，月/人/重复各自的统计单位沿用已有评价。

新V3.2只计分一次，旧Qwen从缓存合并，不重调API、不重拟合旧概率。不能因四个月表现较好自动升级为最终主模型。宏观加权组合的权重与独立评价将在连续月份结果上按预定时期完成；这四个月不用于证明样本外组合胜出。

模型元数据：[OpenRouter当前路由](https://openrouter.ai/api/v1/models/deepseek/deepseek-v3.2/endpoints)；推理开关参照[官方文档](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)。路由支持不保证实际容量；已有4份技术回包，原技术段未过扩展门槛。V3.2完整训练截止尚未证实，不把“2024年中”当作本轮无泄漏依据。

## 费用与复现

预估$0.5207985：将旧Qwen实际token数按V3.2输入$0.26/百万、输出$0.38/百万重估；不同分词器与输出长度会改变实际费用。按消息UTF-8字节上界、每次预留1024模板token和最大输出，保守预留$2.434494；请求硬上限$4。平台Chat/Sim额度不在本次使用范围。旧Qwen调用费用属于旧批，不重复计入新费用。

```bash
python scripts/run_sce_frozen_trial.py prepare --config docs/workstreams/20261021_fullperiod/v32_comparison_config.json --folder outputs/<fresh_trial>
python scripts/run_sce_frozen_trial.py dry-run --folder outputs/<fresh_trial> --workers 4
# 以下仅在该批明确数据外发/预算授权落盘之后执行
python scripts/continue_sce_pending_calls.py prepare-fresh --parent outputs/<authorized_trial> --folder outputs/<fresh_ledger>
python scripts/continue_sce_pending_calls.py run --folder outputs/<fresh_ledger> --workers 16
python scripts/evaluate_sce_model_comparison.py --ledger outputs/<finished_ledger> --out outputs/<fresh_evaluation>
```

共享文件修改前已保全：`outputs/sce_shared_runtime_snapshot_20261021_before_v32_v1/`；旧协议/manifest未改，旧批复算使用原冻结源码。不要重建或重启已执行账本。原始及人工补齐均已获授权并按约停止；不得重启或补发。SiliconFlow备用包是新接收方，授权仍为false。
