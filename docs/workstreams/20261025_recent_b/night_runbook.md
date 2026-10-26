# 路线B夜间运行说明

2026-10-25，北京时间。**新版v3已离线准备完成，尚未启动。**用户要求先准备好新包、再由本人在本地终端运行；旧v2的“暂不启动”记录保留，不作为v3的预算授权。下方启动参数由操作者明确确认本批范围与$8上限，才会写授权并调用模型；本次准备没有API费用。当前为回顾性时点信息回测，不是尚未公开结果的封存预测。报告保留v0.3。

## 本次运行包

唯一使用：`outputs/sce_recent_b_overnight_20261025_v3/`。v1/v2保留为未启动的旧准备归档，不再执行。包内protocol.json、execution_policy.json与acceptance.json可查范围、检查结果和哈希。

人口与供体改为逐月更新：2025-11→2025-01，2025-12→2025-02，2026-01→2025-03，此后依次推进；2026-08/09均使用本地微观上限2025-10。选择条件是“调查月末加九个日历月的推定日期严格早于截止日”，属于依据官方九个月规则设定的保守可得性假设，**不是已核实每期历史字节版本**。后续能取得更直接的当时版本证据时另留版本，不偷换本包。实际供体距目标10—11个月，完整联合Q8/Q9保留；先验按已公开上期全国Q9±0.05pp校准，11期最大偏差0.0469182pp。就业/收入按源记录、不加宏观新校正；不设出入，不做连续递推或Normal代答。

本批会发送：去标识年龄组、学历、收入档、地区/州、住房、就业、数理标签；合成CE支出、美联储信心及食品采购角色；匿名联合供体构造的合成Q8/Q9起点及合成参考月份标签；公开历史食品价格、NYT新闻、政策。目的地OpenRouter（openrouter.ai）→固定SiliconFlow FP8→DeepSeek V3.2。不发送原始ID、人口权重、近期目标真值、真实近期本人答卷、真实作答日期、Q1/Q2、第三方原始个人资料。原始源文件是较晚下载的版本，可得性按上述规则推定；不宣称严格事前预测。

范围2025-11至2026-09共11期，每期512个代理家庭，每人一次，主批5,632请求。OpenRouter→固定SiliconFlow FP8→DeepSeek V3.2，温度0.5、关闭思考、JSON、最多1024输出token。前32次最多8并发，至少16份正常回包且其中双字段格式可用率≥95%后继续；主阶段32→64并发。

主批估计$4.36；主批＋自动补跑共用$8硬上限，不预扣$8，计入已报费、未知费预留和在途最大费用，触顶保存并停止。全批字节上界及满输出的保守预留约$27.49，只是极端上界、不是预计扣款；调度按实际已花加未知及在途逐次守卫，不预锁全部上界。已批准的新闻分类14次/111篇另费$0.009965，不从OpenRouter主批再次扣除。费率仍为输入$0.259、输出$0.80/百万token；请求本身锁定该最高价格。

## 晚上直接复制到本机终端

如先检查配置，下列命令仅核对冻结文件，不读取密钥、不创建授权、不调用API：

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/run_sce_recent_b.py review --run-dir outputs/sce_recent_b_overnight_20261025_v3
```

阅读并接受上述数据范围、可得性假设与$8硬上限后，手动执行：

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_recent_b.py run --run-dir outputs/sce_recent_b_overnight_20261025_v3 --confirm-scope-and-budget
```

该参数确认这份已列明范围与预算，并在本机写启动记录；不会启动旧82月队列。程序从现有本地配置读取OpenRouter密钥，不要把密钥粘贴进命令。

控制器启动独立后台Python进程并保持防空闲休眠，终端每10秒显示北京时间进度。请接电并保持电脑开盖，可锁屏。关闭观察窗口或Ctrl+C只结束观察，已启动的后台继续；无需Codex逐批调度，不依赖Codex对话额度。关机、合盖睡眠或系统强杀仍可中断进程，不能承诺这类情况自动恢复。

需要重新看进度时：

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_recent_b.py watch --run-dir outputs/sce_recent_b_overnight_20261025_v3
```

不要删除锁文件或复制运行目录重新启动。再次执行run时，已有launch会转入观察，不会另起第二批。后台死亡但无收据会明确提示，未知是否已计费的发送意图不会冒充未发送而自动重发。

## 容错与自动补跑

主阶段复用已经验证的队列。连接/超时/HTTP408/429/常见5xx等临时故障触发分段停止时，会先收齐在途请求，再按30/60/120/240/300秒有界冷却，尊重Retry-After；恢复后降并发继续从未发送位置。最多50轮、累计等待30分钟；连续多轮不能健康恢复则保存并停止。每份失败保留，不在SDK内部偷偷重试。

当主批所有位置均已尝试，自动按传输、截断或Q8/Q9格式失败筛一轮补跑，16→32并发。每个失败位置最多多一次，整个批次物理尝试最多11,264次，通常远少于此数；成功位置不重跑。补跑继续使用原提示、原初始状态、原模型及供应商；不按真值或拟合误差挑选。有效非负概率和不等于100时仍按既有规则归一化；有效概率的密度拟合边界不触发API重抽。

补跑结果按字段覆盖：原Q8成功而Q9失败时，只合入有效新Q9，保留原Q8。主批、补跑原始回包分别归档，最终合并是明确字段视图，不伪造一份“原始完整回复”。补跑后仍失败则保留合成先验回填并报告，不再自动循环。原始技术失败累计数不会因补好而消失；最终remaining_q8/remaining_q9才表示剩余缺失。

认证、余额、预算、价格/供应商不一致等强异常立即停止新增发送，不自动换供应商。若在主批范围完成前长期中断，不会擅自把未运行位置称作完整结果。

## 完成后在哪里看

- `worker_receipt.json`：整条流程是否结束；有remaining技术字段时状态会明确区分。
- `combined/receipt.json`：逻辑人数、主批/补跑/物理调用、实际费用与未知费预留、剩余Q8/Q9。
- `main_stages/`与`repair_stages/`：不可改写的逐段原始messages、响应、发送意图及收费记录。
- `combined/positions_private.jsonl`：字段合并视图；不作为合成原始文本发布。
- `evaluation/index.html`、`summary.json`、`monthly_national.csv`：主批与补跑结束后自动启动独立评价进程生成，全国MAE/RMSE/bias、逐月图与基线；组合沿已有λ=0，不在11期上重新拟权。
- `generation.log`、`evaluation.log`、`terminal_worker.log`：错误定位日志。

近期没有公开逐人真值，Q8及人际IQR只描述模拟输出，不报告真人W1/个人误差。人口/供体的确切历史发布时间由九个月规则推定，历史字节版本未认证；全国历史中位数校准不能消除个体经历差异。新闻/政策同期文本版本及模型知识边界也未完全认证，按限制披露，不称严格事前预测。

## 本轮验收

48项定向测试通过，含九个月月末/跨年边界、禁止未来波次、逐月供体窗口重置、缺失权重、就业仅用较早本人记录、冻结路径绑定、只读review不创建发送器，以及原网络冷却、技术补跑与独立全国评价检查。官方Core 11单元/5,632个决策及全部实际提示通过；验收另逐一核对5,632份源波次/供体/原始联合字段与先验约束。旧A四份主来源哈希和报告v0.3不变。此为工程验收，尚无本批真实模拟成绩。

实现：`recent_b_prompts.py`、`recent_b_night.py`、`recent_b_evaluation.py`；CLI为`prepare_sce_recent_b_run.py`、`run_sce_recent_b.py`。全部复用现有匹配/新闻/价格/官方Core/单次队列/冷却/字段合并及指标模块，不修改旧冻结运行。

来源：[OpenRouter端点目录](https://openrouter.ai/api/v1/models/deepseek/deepseek-v3.2/endpoints)、[额度与限流说明](https://openrouter.ai/docs/api/reference/limits)。公开页面复核不等于保证账号始终有可用余额；运行时仍由预算及服务器错误守卫控制。
