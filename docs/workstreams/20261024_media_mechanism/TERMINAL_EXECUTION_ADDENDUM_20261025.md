# 新闻机制 V3：Terminal 执行附录

2026-10-25。仅补传输、启动和评价接口；不改变 Kimi 冻结的研究提示、人口、新闻或评价真值。原研究包及其未批准的授权文件保留。当前尚未发送这批真实模拟请求。

**执行后更新：本批现已运行和评价完成，请勿再次run。**用户Terminal运行6,720次，技术可用6,704，实际API报告$4.49955。结果与离线复算见[七期结果说明](RESULTS_20261025.md)。以下保留启动前操作说明作为追溯；不要将它当作新的授权或待运行任务。

## 本次运行的范围

七期：2019-05、2020-09、2021-06、2021-09、2021-12、2022-06、2023-12。每期96人，R0/Q0/Q1/Q2/Q3五组，每组两遍，共6,720个请求；同一人的两遍不是两个居民。具体机制见 `EXPERIMENT_DESIGN_AND_RUN_PLAN.md`。

目的地仍为 OpenRouter → 固定 SiliconFlow FP8 → DeepSeek V3.2；温度0.5、JSON、关闭思考、最多1024输出token。使用自购OpenRouter额度，不使用平台Chat。

外发内容仍是原包中的去标识人口画像（年龄组、学历、收入档、地区/州、住房、就业、数理标签）、合成CE支出/美联储信心/食品采购角色、公开价格/新闻/政策、本人严格更早Q8/Q9及历史摘要和信息先后标签。原始ID、调查权重、本期真人答案、实际作答日期和第三方原始个人记录不进入请求。完整提示只在本地保存。

原包估费 **$6.213**，累计硬上限 **$32.11028**，不是预先扣费；已报费用、未知费用预留和在途预留共用这一上限。实际余额不足会停止，不能保证一定完成。原包的极端全输出预留约$25.69，也不是预计支出。

## 中午开始运行

工作目录：`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge`。

最终终端执行目录：`outputs/sce_media_mechanism_terminal_20261025_v2/`。v1仅是适配器开发过程中的未启动准备归档，不要用。

先读配置（不调用API）：

```bash
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/run_sce_media_mechanism_terminal.py review \
  --run-dir outputs/sce_media_mechanism_terminal_20261025_v2
```

确认上述资料范围、目的地、6,720次和$32.11028累计上限后，**你本人**在macOS Terminal执行以下命令，即为本批明确授权；命令会单独记录新适配器授权，不改Kimi原授权文件。现在不由Agent代为执行。

```bash
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_media_mechanism_terminal.py run \
  --run-dir outputs/sce_media_mechanism_terminal_20261025_v2 \
  --confirm-scope-and-budget
```

进程会独立在本机后台运行，每10秒在终端显示进度，不需要Codex逐批调度。不要再执行旧 `run_sce_media_mechanism_v3.py run`，两种入口不能同时使用。

在其他终端重新查看（不调用API）：

```bash
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_media_mechanism_terminal.py watch \
  --run-dir outputs/sce_media_mechanism_terminal_20261025_v2
```

Ctrl+C只退出观察，后台继续。`caffeinate`防止空闲睡眠，但不能保证合盖、断电或网络可用。请接电并保持网络。

## 容错、预算与恢复

- 首32次最多8并发，至少31份Q8/Q9格式可用才进入主批；这一门槛与拟合效果无关。
- 主批先32并发，完成256次后最多64。出现临时错误后先收齐在途，再降并发，最低8。
- 408/429/500/502/503/504等已登记状态、连接中断和超时，采用30/60/120/240/300秒有界冷却，尊重合法Retry-After。最多连续5轮未恢复、50次恢复或累计30分钟冷却。
- 凭证/余额、模型或供应商不符、费用异常、输入哈希变化立即停止，不换供应商。
- **不自动重发已经尝试的失败位置。**等待恢复只继续从未发送的位置；本批主请求仍最多6,720次，未加入额外补跑预算或次数。
- 每次发请求前先持久写入意图，每个回包立即保存。程序崩溃后，没有回包的意图计为“已尝试、费用未知”，保留全额预留，不当成从未发送。
- 操作系统进程锁防止双开；完成的分段记录有哈希，不覆盖旧档。恢复沿用同一累计费用，不重新获得一份预算。

如果后台**确实停止**，而且你同意只继续未发送位置，可人工执行：

```bash
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_media_mechanism_terminal.py resume \
  --run-dir outputs/sce_media_mechanism_terminal_20261025_v2 \
  --confirm-scope-and-budget
```

正在运行时重复启动会被锁拒绝；凭证、余额、供应商等强异常仍需先排查，不能靠resume绕过。不要删除锁、账本或运行目录。若6,720个位置均已尝试，则只能离线评价；少量失败是否额外补跑，完成后再决定。

## 自动评价与输出位置

生成结束后，由独立子进程读取隔离真值并评价，不在发送阶段解析本期答案。使用原冻结Q9近似计分器和共享MAE/W1/IQR/加权统计；合法十档按登记规则等比例归一化，保留原始回复。失败字段保持缺失，不用先验或真人答案补成成功。

- 总状态：`outputs/sce_media_mechanism_terminal_20261025_v2/latest_receipt.json`
- 逐次意图和原始回复：`round_0001/segment_*/dispatch_private.jsonl`、`calls_private.jsonl`
- 日志：`round_0001/worker.log`
- 简明结果：`round_0001/evaluation/RESULTS.md`
- 完整逐月/逐遍结果：`round_0001/evaluation/summary.json`
- A82单遍参照、新闻量档/上期预期档/Fox实际接收分层：`round_0001/evaluation/comparison/summary.json`

若人工恢复，后续在round_0002等目录，旧目录保留。**照抄本人上期基线同时列出**，严格使用相同人、权重、月份和遍数支持；基线缺失者另报支持人数。该96人子样本的中心误差不能直接称为完整全国调查误差。A82只有一遍，不虚构第二遍。七期均已检查过，只是探索性机制诊断。

如果只是评价失败，切勿重跑模拟；在新目录离线重算：

```bash
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/run_sce_media_mechanism_terminal.py evaluate \
  --run-dir outputs/sce_media_mechanism_terminal_20261025_v2 \
  --out outputs/sce_media_mechanism_terminal_evaluation_manual_v1
```

工程定位：官方Core仍负责原70个离线输入单元验收；真实发送改用本地逐请求适配器，评价直接读持久账本，不伪造官方引擎的study.duckdb或run_manifest。

## 验收证据

本轮验收记录放在最终执行目录的 `execution_acceptance.json`；全6,720份原提示的伪接口回放在 `outputs/sce_media_mechanism_terminal_offline_20261025_v1/summary.json`。工程回包明确标记为非真实结果，不得进研究评价。原研究协议、提示和70个Core验收不变。

43项定向测试通过，覆盖502、429及Retry-After、断网/超时、预算与未知在途、认证/供应商/费用强停止、哈希、防双开，以及“同支持基线＋A82单遍＋分层”评价输出。测试用的常数答卷产生两条相关系数未定义警告，属于伪数据性质，不是运行或格式失败。最终217项文件哈希一致；真实调用、授权记录与启动进程均为0。
