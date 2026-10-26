# 主批次技术失败的一次补齐

## 用户Terminal命令

原82月运行已结束。用户要求对技术失败位置额外尝试一次；这不是重启旧运行。

```zsh
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u "/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/scripts/run_sce_monthly_repair.py" run \
  --run-dir "/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/sce_monthly_main_technical_repair_20261024_v1" \
  --confirm-one-time-repair
```

每10秒显示本次361位置的完成、可用、错误、在途和新增费用。独立后台程序继续工作，不依赖Codex；Mac防空闲睡眠随worker启用。Ctrl+C仅退出观察，不会重新发送或停止后台。禁止删除锁文件重启；若需再看进度，同一命令将`run`改成`watch`并去掉确认参数。

## 具体范围

- 345连接失败、5超时、1次HTTP502：各补一次原Q8/Q9任务。
- 10份原Q8成功、Q9接口未通过：发送同样原任务，但合并时只取合法新Q9，保留原来成功的Q8。
- 不重跑29份有效问卷的连续密度计分边界；不重跑63份合法比例归一化。
- 提示文本与原state逐一核对哈希；相同DeepSeek V3.2、OpenRouter→SiliconFlow FP8、温度0.5、JSON、关闭思考、最多1024输出token。原目标样本、环境、参数和权重不变。
- 16并发起步、32次完成后最多32并发；临时传输故障允许有界冷却，只继续本次尚未发送的请求。已发送的补跑请求不再自动重试。若失败持续、鉴权/供应商/预算等硬错误出现，保存并停止。

## 预算

主批次API已报$28.907374187；含未知失败费用预留$30.115641293。按主批次平均调用费估计，361次新增约$0.249；按最大输入字节和满输出保守预留$2.10849，额外硬上限$2.11。两者合计最高记账约$32.22564，仍低于原已批准的$40，不是新增$40预算。

CLI确认参数记录用户此次人工补跑的授权。准备与离线回放不调用API；只有用户运行上述`run`命令才会启动。

## 输出与评价

所有新产物位于`outputs/sce_monthly_main_technical_repair_20261024_v1/`：

- `calls/`：此次补跑的原始回包、发送意图、费用、不可改写分段。
- `combined/positions_private.jsonl`：原41984人月的逐字段覆盖视图；只替换原先失败且本次成功的字段。
- `combined/calls_private.jsonl`保留原主批次raw调用；`manual_repair_calls_private.jsonl`单独保留新增raw调用。覆盖后的状态不伪装为某一次完整原始回答。
- `combined/receipt.json`保留逻辑名册41984；另外明确列物理API尝试数，最多41984＋361＝42345。补跑不增加人口权重，不重复计人；成本为主批次＋补跑之和，未知费用仍保守预留。
- `evaluation/`、`readout/`：补齐视图的独立进程微观评价和全国组合。原主批次、评价和readout均不覆盖；旧相同概率向量使用已冻结分数缓存，新向量才拟合。
- `worker_receipt.json`：最终状态；正常结束为`repair_and_separate_evaluation_complete`。仍失败的字段保留显式输入后备并计数，不假定361份一定全部补成功。

这是技术修复版本，和原始一遍主结果同时保留。不能因新答案拟合较好才采用；合并只看接口合法性，不看真人答案、MAE或分布成绩。

## 离线验证

```zsh
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -m pytest tests/test_sce_monthly_main_repair.py tests/test_sce_monthly_main_resilient.py -q
```

18项通过：成功Q8保护、部分修复、再次失败、计费累计、逻辑人口去重、原数据不改，以及现成队列的限流/冷却/预算/供应商保护。准备阶段还逐一核对361份原始提示和state；运行包内`offline_validation.json`记录确定性回放与计分缓存兼容检查。

## 补跑完成后的6份残余（2026-10-24核查）

补跑和两级评价于15:59:25完成。残余不是6份全部拒答：

- 2020-10、2024-11、2025-03各1份APIConnectionError，无回包、无usage，无法由本地记录进一步确定上游根因。
- 2019-01、2023-06、2024-02各1份正常stop回包、Q8合法，但Q9重复键同时缺档：2019-01重复bin5/缺bin9，另两份重复bin2/缺bin4。回包包含实际经济解释，没有拒答文字或content_filter结束标记。
- 所见证据不支持将问题归因于政治敏感拒答；连接失败没有内容证据，也不能据此断言具体上游原因。
- 六份各在不同月份；其分析权重占对应月样本质量依次为2019-01 0.2499%、2020-10 0.1393%、2023-06 0.3630%、2024-02 0.2481%、2024-11 0.3399%、2025-03 0.1082%。这是权重质量，不是MAE影响上界；中位数附近仍需离线敏感性。

当前优先分析既有82月，保留显式后备；未启动第三轮补跑，也不根据字典顺序默默重命名重复概率键。总体结果/组合与微观分组先解释，近11个月严格B资格与最终研究包工程接着收束；新增模拟按必要性另列，不自动扩大预算。

## 六份残余的一次后续补跑

用户随后明确希望六份再尝试一次。新增薄适配器复用首轮的队列、监督、验证、按字段合并和缓存评价；原已使用代码不改。只发送剩余6份的相同原始输入，3份补Q8/Q9，另3份只合入合法新Q9并保留原成功Q8；不改人口、环境、温度或模型。

```zsh
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u "/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/scripts/run_sce_monthly_repair_followup.py" run \
  --run-dir "/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/sce_monthly_main_six_repair_20261024_v1" \
  --confirm-six-position-repair
```

预计新增约$0.004，保守预留$0.03504、新增硬上限$0.04，仍计入原$40；含原预留的累计最大约$30.39061。最多6次，不自动再次尝试已发送的补跑失败，不切供应商。各位于不同月份，仍按原月份顺序发送。

新结果在`sce_monthly_main_six_repair_20261024_v1/`，原主批次及首轮补齐不覆盖。原始、首轮raw和本轮raw分别保留，字段来源逐层追溯，逻辑人月41984不变；全部6次尝试完成时，物理调用累计42351。`last_manual_repair_receipt`记录本轮细节，费用为三轮累计。评价复用首轮已经计分的向量，新回答才新增拟合。

12项定向测试通过，六位置原提示确定性回放通过；准备时真实调用0。用户执行命令才启动，正常完成仍显示`repair_and_separate_evaluation_complete`；如仍有失败按实际记录，不承诺一定零缺口。分析前的组织方案见[82月分析框架](../20261024_fullperiod_analysis/README.md)。
