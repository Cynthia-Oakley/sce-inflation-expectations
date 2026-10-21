# V3.2同输入比较：准备完成，真实调用待授权

2026-10-21。配置：[v32_comparison_config.json](v32_comparison_config.json)。本轮与Kimi的全时段P/E补齐并行，保持旧回访者人口，不混入新入组或近期合成人口改动。

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

模型元数据：[OpenRouter当前路由](https://openrouter.ai/api/v1/models/deepseek/deepseek-v3.2/endpoints)；推理开关参照[官方文档](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)。路由支持不等于真实接口已验收；当前仍0新增真实调用。V3.2完整训练截止尚未证实，不把“2024年中”当作本轮无泄漏依据。

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

共享文件修改前已保全：`outputs/sce_shared_runtime_snapshot_20261021_before_v32_v1/`；旧协议/manifest未改，旧批复算使用原冻结源码。不要重建或重启已执行账本。当前新包授权为false，不能当作已开始或已批准。
