# V3.2备用供应商：同输入、单一SiliconFlow批次

2026-10-21。这是供应商更换方案，不是已开始的新模拟。[配置](v32_siliconflow_config.json) · [离线准备收据](v32_siliconflow_readiness.json)。新增供应商接收人口和真实上期回答，具体授权卡已发送；当前该包授权false、向SiliconFlow发送0次。

## 为什么更换

AtlasCloud首次16并发时4份有效、12次429；获准改2并发后仅再发2份，1份有效、1次429，按“再次429即停止”终止。累计18次、5份有效、13次429；后752份一次也未发送，原12份429中10份未重发、另1份重发仍失败。错误标记`upstream_provider_shared_pool`，不能据此给出数值TPM上限或认定只是16并发过大。

成功回包报告累计$0.0033592；失败实际扣费未知，保守记账总计$0.04479514。[技术收据v2](v32_technical_result_v2.json)。当前没有足够数据比较模型拟合，不把接口限流当成V3.2模拟能力的阴性结论。

## 新批次保持什么

- 同一`deepseek/deepseek-v3.2`型号，经OpenRouter锁定`siliconflow/fp8`，不回退；服务目录登记FP8、JSON和reasoning支持，尚不代表实际容量已验证。[官方目录](https://openrouter.ai/api/v1/models/deepseek/deepseek-v3.2/endpoints)，2026-10-21免费核查。
- 仍是2020-09、2021-09、2022-06、2025-03各96人的旧食品背景提示，每人两遍。P/E、本人历史、角色、新闻、题目、示例与768份Qwen控制逐字相同。
- 温度0.5、JSON模式、关闭思考、最多1024输出token；最多4并发，前16次技术段包含在768次内，可用率至少99%才自动继续。不按小段拟合结果筛配置，无自动重试或供应商回退。
- **AtlasCloud的5份回答只归档，不与SiliconFlow混算。**新供应商768份均单独生成；Qwen768份全部复用。供应商、分词器、托管实现与模型一起变化，不声称纯参数规模的因果效果。
- 非负有限且合计为正的十档概率仍按用户规则等比例归一化，原答和失败完整保留。四个月是开发比较，仍需完整月份检验和预定组合评价。

## 准备与费用

有效包`outputs/sce_v32_siliconflow_trial_20261021_v1/`：768次相同提示核对、8个官方Core离线单元、31项定向测试通过。真实请求继续使用已有逐请求队列与SCEOpenAILLM，不另造模拟框架。

价格登记输入$0.259/百万、输出$0.80/百万。按旧Qwen实际token重估新增$0.567913，字节/最大输出保守预留$2.756582。新批上限$3.95，加此前保守记账$0.044795仍小于原$4总上限；两批合计的调用预留约$2.801377。不同分词器和输出长度会改变实付；不使用平台Chat额度。

如果完整新批执行，累计实际请求上限为此前18＋新768＝786，原768个逻辑输入不变。旧失败不能从运行总账删掉，也不能宣称零错误。该批原始回包须记录实际model/provider、reasoning token、费用、延迟、HTTP错误与原始概率合法率。

共享文件改动前源码已保全在`outputs/sce_runtime_snapshot_20261021_before_siliconflow_v1/`；AtlasCloud旧协议和原始回包均未改。原路径已按约终止，不恢复剩余请求。

## 执行入口

```bash
# 输入与干跑已完成；使用新的目录才能重新准备
python scripts/run_sce_frozen_trial.py prepare --config docs/workstreams/20261021_fullperiod/v32_siliconflow_config.json --folder outputs/<fresh_trial>
python scripts/run_sce_frozen_trial.py dry-run --folder outputs/<fresh_trial> --workers 4
# 仅新供应商具体授权落盘后运行
python scripts/continue_sce_pending_calls.py prepare-fresh --parent outputs/<authorized_trial> --folder outputs/<fresh_ledger>
python scripts/continue_sce_pending_calls.py run --folder outputs/<fresh_ledger> --workers 4
python scripts/evaluate_sce_model_comparison.py --ledger outputs/<finished_ledger> --out outputs/<fresh_evaluation>
```

研究的月份、原始数据、拟合目标及评价不变；需要用户确认的是新增SiliconFlow接收方与这次全批调用。当前不追加AtlasCloud重试、不自动执行新供应商调用。
