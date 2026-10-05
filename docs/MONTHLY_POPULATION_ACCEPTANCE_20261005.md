# 按月人口、运行与评价：本轮验收及接力

2026-10-05。队伍：水上挽月。任务：为历史重建线准备更合理的 Population，并把运行到评价的链路补齐。本轮真实 LLM / 付费 MCP 调用均为 **0**。

## 1. 已完成什么

- 开发月完整人口框：2021-05 为 **1,234 人**，2021-06 为 **1,297 人**。可以生成完整人口或 300/500 人候选样本；不再要求入选者全年都参加调查。
- 画像按目标月更新年龄、教育、收入、地区、就业等。住房只沿用本人截至该月的已有回答；若之后记录过搬家，暂不填写住房属性，避免把旧住房当成当前状态。
- Q8/Q9 答案不参与选样或进入模拟输入。人口文件中的权重统一为 1；真实调查权重和抽样概率单独保存，运行后才用于评价。
- 运行入口可以切换人口、环境、仿真配置路径，保存实际生效输入和源码快照。旧配置与旧结果保留。
- 评价入口按同一个人、同一个月匹配真实回答。真实与模拟的 Q9 十档概率使用同一冻结近似计分器；Q8 和 Q9 分别处理有效答案。

这完成了工程准备。尚未证明真实 LLM 的行为效果，也没有冻结正式人口规模、Normal 外推或预测线人口方案。

## 2. 两种候选选样方式

`independent_srs`：每月从当月完整人口框独立随机抽样。适合先检验横截面分布；相邻月入选者变化较多。

`stable_priority_srs`：每人获得固定随机优先级，各月仍在当月完整人口框中选取前 n 人。避免强求未来完访，同时增加相邻月的重合。每月边际纳入概率为 n/N，评价权重为调查权重除以该概率。

本次固定种子 42，没有根据真实答案挑选种子。两月完整人口重合 1,070 人；300 人独立样本重合 56 人，固定优先级样本重合 243 人；500 人分别为 167、406 人。后者只是候选方案，不代表已经验证跨月记忆。当前运行按月独立初始化；如果要研究同一人的预期更新，还须实现状态衔接并独立验收。

“本月入选、上月未入选”不等于真实调查新进入者；轮换分析需区分这两种情况。

## 3. 运行与评价已实际验收

四次单月规则式运行，每次 300 人，共 **1,200 条有效回答**：

- 独立抽样 5 月：`outputs/local_runs/sce-local-scripted-20261005T043741Z-6321a6d5/`
- 独立抽样 6 月：`outputs/local_runs/sce-local-scripted-20261005T043810Z-1f0e4929/`
- 固定优先级 5 月：`outputs/local_runs/sce-local-scripted-20261005T044714Z-87b226f8/`
- 固定优先级 6 月：`outputs/local_runs/sce-local-scripted-20261005T044805Z-29cda1a1/`

每次 `monthly_audit.json` 核验实际 Observation 的人口、权重、环境、日期、ID、回答数和概率结构。后两次还核验 9 份执行源码快照及实际模型代码哈希。

真实问卷评价入口已经用于原 73 人两月规则运行（146 条匹配）和上述固定优先级两次运行（各 300 条匹配）：

- 73 人：`outputs/local_runs/sce-local-scripted-20261005T025249Z-50d67388/evaluation_20261005T045219Z_ee2a33d5/summary.json`
- 300 人 5 月：`outputs/local_runs/sce-local-scripted-20261005T044714Z-87b226f8/evaluation_20261005T075726Z_23d0609b/summary.json`
- 300 人 6 月：`outputs/local_runs/sce-local-scripted-20261005T044805Z-29cda1a1/evaluation_20261005T075727Z_675d89ad/summary.json`

评价包括个体误差、加权水平与分歧，并分别报告截止日之前、之后、同日及日期未知的记录。73 人的截止后组为 41/43 人；固定优先级 300 人的截止后组为 221/229 人，同日为 4/2 人。只按日期分组，不猜测当天作答时刻、不随机分配指标。

300 人样本的真实 Q9 可计分记录分别为 292/293 条；其余为概率不合法（各 6 条）或两个非相邻正概率档（2/1 条，本计分器不覆盖），均保留状态并从 Q9 配对指标中排除，不填补为成功记录。匹配条数与有效计分条数分别报告。

这些规则式结果用于验收程序；数值误差不用于判断 LLM 效果或选择提示词。

## 4. 数据与可复制入口

以下路径均相对于主仓库 `socioverse_challenge/`；个人数据和自动产物只在本机忽略目录内，不推送 GitHub。

- 当前完整/独立 300/500 人包：`outputs/monthly_inputs_20261005T044205Z_53cbc7e5/`
- 当前固定优先级 300/500 人包：`outputs/monthly_inputs_20261005T044602Z_f8c1a697/`
- 每个包中的 `all/202105/` 或 `n300/202105/` 等月目录含 `population.json`、`environment.json`、`simulation.json`、`sampling_meta.json`、`analysis_weights.jsonl`、`survey_dates.jsonl`；包根目录有 `manifest.json` 与构建源码快照。
- 人口字段缓存：`data/cache/monthly_profiles_7f0ed622ae0915902741.parquet`。仅画像与调查元信息，没有 Q8/Q9；真实答案单独保存在评价文件中。
- 两个月完整评价材料：`data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json`，旁有 `receipt.json` 与构建器快照。共 2,531 条人月记录，来源 SHA 与人口缓存来源一致。

完整评价材料的官方个人派生值聚合可对账：5 月 Q8 为 5.26%、Q9 为 4.00%；6 月为 5.48%、4.80%。这是官方派生字段到 chart 的核验，**不是**原始十档到官方密度拟合的完全复刻。效果比较仍使用本项目同一近似计分器。

在主仓库根目录执行（`socioverse` Conda 环境）：

```sh
python scripts/prepare_sce_monthly_inputs.py --sizes all,300,500
python scripts/prepare_sce_monthly_inputs.py --sizes 300,500 --design stable_priority_srs
python scripts/audit_sce_monthly_run.py --run-dir <单月运行目录> --package-dir <对应月输入目录>
python scripts/evaluate_sce_dev_run.py --run-dir <运行目录> \
  --truth data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json \
  --profile-cache data/cache/monthly_profiles_7f0ed622ae0915902741.parquet \
  --profile-manifest outputs/monthly_inputs_20261005T044602Z_f8c1a697/manifest.json
```

命令生成新目录；占位符须替换为实际路径。运行器接受月包文件的绝对路径，参照 `python scripts/run_sce_local.py --help`。

定向测试：`python -m unittest tests.test_monthly_sce_analysis tests.test_monthly_sce_population tests.test_sce_run_budget tests.test_sce_local_model`，**42 项通过**；另有此前人口抽样诊断 4 项通过。测试涵盖真值/权重隔离、未来住房、搬家、稳定选样、日期边界、加权指标、调用前预算预留和执行源码快照。

当前验证环境：SocioVerse2 0.2.0、Python 3.11、pandas 3.0.6、numpy 2.4.6、scipy 1.17.1、duckdb 1.5.5、pydantic 2.13.5、openai 3.24.0、openpyxl 3.1.5。最终独立提交包与依赖锁定尚待验收。

## 5. 边界与下一步

1. **下一步是 73 人 × 两月真实 LLM 开发验证**：最新标题＋摘要提示词，沿用已连通模型。具体命令和建议 $1 上限见 [运行卡](DEV_RUN_CARD_20261005.md)，目前预算待用户确认；尚未调用。先看回答有效率、分歧是否过小、水平与跨月变化，再决定扩大或改哪一项。
2. 300/500 人月度方案已准备，但不自动扩大付费规模；正式选择结合已完成抽样诊断和开发运行结果。固定优先级的轮换、状态衔接及 Normal 投影另行验收。
3. 当前 E 截止是目标月内前一期 CPI 发布日末，属于回顾性条件重建/月内估计。未来预测线另建 t 截止前的 P/E 与基线。汽油 vintage、新闻历史文本版本及模型知识边界仍有限制，不能声称严格事前预测。
4. 新建 [开题修订草稿](../proposal/proposal_track_a_revision_20261005.md)，明确比赛赛道 A 内的历史重建与未来预测。原提案保留，待用户审阅合并和提交。

Kimi 的 10-03 待审批次未修改、提交或还原。运行/评价用到其中冻结计分器与拟合内核，已在本机保存执行源码快照；因此当前验收不等于仅凭已提交代码在新机器上就能完全复现。待用户审阅该批次后再验收干净 checkout 的独立运行包。方法候选均未写成正式冻结决策。
