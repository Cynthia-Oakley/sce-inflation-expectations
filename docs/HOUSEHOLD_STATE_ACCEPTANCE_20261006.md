# Q1家庭财务经历模块：接线验收与接力

日期2026-10-06。**已经实现候选模块和离线流程；行为改善尚未检验，模拟API零新增。** 用户的新实验数据发送与$1预算确认待回复。具体配置、经济学意义和评价标准见[运行卡](HOUSEHOLD_STATE_RUN_CARD_20261006.md)。

## 本轮交付

- Q1-only模块：只在原v2标题＋摘要提示的问卷前添加一段当月自报财务经历，不添加加减预测值规则。真实通胀回答、调查权重、心理donor及ID均不进入消息。
- 运行入口新增可选`--household-state`，必须与对应提示版本配套；缺失/多余ID、画像/月份错配、额外目标字段和B输入被拒绝。默认运行保持原路径，旧人口/环境/模拟配置未覆盖。
- 新prepare/execute入口：按事先固定的Q1五类分层，从完整1234/1297人各取50人，每类10人；种子42、固定哈希排序，不读取真实通胀答案或权重。独立于正式Core/Normal设计。
- 新离线配对评价入口：真实和模拟十档概率使用同一冻结项目计分器，统一完整配对样本，输出个人MAE、各组中位数、明显变差与不变组差距、跨人IQR及个人密度IQR。更多方差不自动判为改善。
- 候选运行4个作业、200回答，无自动重试；预算总$1、每作业$0.25。实际消息与冻结预览逐份核对、每作业检查输入/代码哈希、模型身份变化/无效返回停止后续作业。费用是token自记估价，不是供应商账单。

## 已验证

17项相关测试通过：Q1白名单/A-B限制/画像绑定、公共事实和问卷不变、fake-client实际provider接线/日志、禁止静默忽略、输入顺序不影响分层选择、手算单档密度、严格配对剔除、方差增加但误差更差不算成功，以及既有消费机制回归检查。

两月各50人通过真实SocioVerse本地引擎规则式运行，100条观察均含正确Q1状态，100条回答合法，模拟API调用计数均0。规则式行为不使用Q1，这些是工程证据，不是改善效果。原始执行中的一次相对路径错误发生在运行创建前，改传绝对路径后完成；未重复付费调用。

200份候选实际提示逐份检查：两组只有Q1段不同，经济事实、标题/摘要和问卷一致，消息不含外层ID/权重/目标字段。各Q1分类译法对应1明显变差、2略变差、3大致相同、4略变好、5明显变好。

## 准确路径

唯一当前候选包：[trial_manifest.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/sce_q1_trial_20261006T142504Z_a6740800/trial_manifest.json)。早期135718、135810、140227准备尝试保留但被新准备包取代；135718之前还有一次预算边界失败的部分目录，不作为有效运行输入。

规则式记录：

- [5月run_manifest.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/local_runs/sce-q1-offline-20261006-202105-v1/run_manifest.json)
- [6月run_manifest.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/local_runs/sce-q1-offline-20261006-202106-v1/run_manifest.json)

规则式运行使用135810准备批次；最新142504批次的P/E/Q1/模拟/提示内容与其一致，最新代码快照与真实运行命令将请求温度恢复为主实验0.5；此前140227候选的0不再使用。不要把这两次规则式运行当作最新真实实验四个作业中的任何一个。

实现与入口：

- [household_state_mechanism.py](../studies/sce_inflation_expectations/household_state_mechanism.py)
- [household_state_analysis.py](../studies/sce_inflation_expectations/household_state_analysis.py)
- [run_sce_household_state_trial.py](../scripts/run_sce_household_state_trial.py)
- [analyze_sce_household_state_trial.py](../scripts/analyze_sce_household_state_trial.py)

## 接力操作

```bash
python -m unittest tests.test_sce_household_state_mechanism tests.test_sce_household_state_analysis tests.test_sce_price_experience -q
python scripts/run_sce_household_state_trial.py  # 新建唯一run_id，只prepare，不付费
```

真实运行必须先得到本次新授权，才使用`--prepared outputs/sce_q1_trial_20261006T142504Z_a6740800 --execute --approval-note '实际用户授权原文'`。不得伪造授权原文或重复未完的真实运行。批准前脚本prepare仅使用白名单P和公开E，从不读取评价真值。

完成后执行：

```bash
python scripts/analyze_sce_household_state_trial.py --trial outputs/sce_q1_trial_20261006T142504Z_a6740800
```

评价输出另建`outputs/sce_q1_analysis_<time>_<suffix>/`，汇总与逐人结果物理分开保留。分析入口拒绝未完成/规则式试验。两个月主误差及核心组间差距都改善才建议扩样；一好一坏报不稳定；失败结果保留。下轮心理模块另做对照，不提前并入主配置。

## 限制与文件保护

同期Q1可能反映共同情绪/方法效应；改进不识别因果。两月已用于诊断、每组每月10人且等额过采样，不是全国代表、独立测试或功效保证。模型知识边界仍未知。更早模型、Normal新条件扩展、心理迁移效度是后续独立任务。

Kimi刻意未提交文件未还原、stash或纳入本轮提交；计分器也未修改。旧提案/运行配置未改。只保存本轮明确源码、测试与文档，原始数据/个人记录/自动产物/密钥继续忽略。未向其他线程或第三方发送项目消息。

## 温度与开发窗口更正

用户指出既有主实验请求temperature=0.5，核实CORE_NORMAL_LLM_RECEIPT一致。20人消费机制小试曾设0，本轮起初沿用小试以减少生成噪声，但不宜未说明就改变主实验条件。真实运行候选已恢复0.5，两组相同；旧候选未执行真实调用，按新run_id重新准备。生成随机性另在后续重复实验评估；模型是否实施该参数仍需供应商/回包证据。5/6月用于已有开发窗口的机制比较，不是以费用限定最终回测范围。Q1是既有SCE财务变化题，现在拟新增为A画像状态输入，不是新增采集数据、真实通胀回答或幸福度。
