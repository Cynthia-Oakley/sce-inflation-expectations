# Core/Normal：开发版已贯通，统计收益尚未确立

2026-10-05。本轮真实 LLM、MCP 及其他付费服务调用均为 **0**。本版本属于 A 线历史重建，不属于 B 线事前预测。

## 1. 已实现

当月完整人口 → 随机 Core → 统计扩展 Normal → 全人口汇总。Core 使用已有 `stable_priority_srs` 或独立 SRS；抽样概率为 n/N，不依据真实答案挑人。第一版不支持未登记抽样概率的其他分层设计。

新增源码：

- `studies/sce_inflation_expectations/core_normal.py`：构建联合回答分布、积分汇总、Normal 抽样及支持度诊断。
- `scripts/expand_sce_core_normal.py`：读已结束的单月 Core 运行和完整 P，生成 Normal；不读取真实问卷/全国预期值。完整 P、Core P 必须来自同月同画像，E 一致，Core 运行先通过月度技术审计。
- `scripts/check_sce_core_normal.py`：离线检验抽样/扩展误差。仅在这个诊断程序中，把真实 Core 回答作为已知输入，真实 Normal 只供评价。
- `tests/test_sce_core_normal.py`：选样角色、权重守恒、组支持、无效 Core、固定种子、人口合同和真值隔离等测试。

## 2. Normal 如何生成

细组为教育×粗就业×年龄。以该组 Core 的调查权重形成回答分布；小组按有效 donor 数向“同教育/就业、其他年龄”的组收缩；再无支持时依次借用同教育其他组、全体其他组。借用组排除原细组，避免把同一回答同时当观察和先验重复计数。

开发参数为 `prior_strength=5`，它代表收缩强度，不是已验证的自然常数或冻结参数；同时预先检查 0、5、20 三档。该方法是 ConsumerSim 启发下的**经验收缩适配**，不是其原始分类回答算法或严格贝叶斯后验的完全复刻。

每个 Normal 抽取一个 Core 的**完整 Q8/Q9 联合回答**，保留十档概率总和与个人内部不确定性；不复制 donor 的个人解释或历史。原 Core 失败仍保留状态，不悄悄改成 Normal。当前联合 donor 需要 Q8/Q9 均有效、Q9 可计分，因此部分单问有效 Core 可能不参与联合扩展，覆盖缺口另列。

主汇总对统计分布直接积分，减少一次随机抽样带来的额外波动；另存一份固定种子的 Normal 个体回答。全国 Q9 对个人密度均值分布取中位数；不能先把每组十档概率平均后当成一个“代表个人”，也不能平均各组中位数。

Normal 是统计填补，不会增加独立观察信息。报告只给 donor 质量集中度，不把它改写成完整人口的独立样本有效人数。当前没有后验可信区间、逐人恢复结论或跨月状态衔接。

## 3. 已实际贯通两个月

- 2021-05：**300 Core + 934 Normal = 1,234 人**。
- 2021-06：**300 Core + 997 Normal = 1,297 人**。

输入 Core 来自此前规则式运行，均为 300 个联合有效 donor。这证明接线与统计结构正确，不证明 LLM 行为效果。

最新产物：

- 5 月：`outputs/core_normal_expansion_20261005T090939Z_aa033732/`
- 6 月：`outputs/core_normal_expansion_20261005T090939Z_f5da9a24/`

每个目录含 `normal_answers.jsonl`、`core_answers_original.jsonl`、`summary.json`、执行源码快照。汇总包括 Core 直接结果、扩展积分结果、一次物化抽样结果、各人口组结果、缺失和借用支持度；原运行文件保留。

独立检查通过：Normal ID 唯一且不与 Core 重合；每份 Q8 与十档 Q9 均与 donor 联合回答一致，概率和为 100；各组权重之和与总体一致；源码快照哈希一致。5/6 月分别有 26/23 个 Normal 在细组中没有 donor，已明确回退；借用更大组的 Normal 权重约占 32.6%/30.4%。这提示组支持还有限，不能声称完整人口就自动具有完整行为覆盖。

测试：`python -m unittest tests.test_sce_core_normal tests.test_monthly_sce_analysis`，**20 项通过**（本轮新增 15 项，既有分析 5 项）。

## 4. 离线效果检查：没有稳定超过直接加权

证据：`outputs/core_normal_diagnostic_20261005T090654Z_14d71faa/summary.json`。两开发月 × 两种 Core 规模（300/500）× 50 次独立抽样，共 200 个 Core 样本；每样本检查三种收缩强度，共 600 组扩展结果。使用当月共同有效 Q8/Q9 目标集（5 月 1,214 人，6 月 1,271 人）；Normal 的真实回答不参与扩展分布构建。

以强度 5 为例，真实 Q9 个人派生均值的月度中位数平均绝对偏差（单位：百分点）：

- 300 Core：直接加权为 **0.274 / 0.340**，扩展为 **0.291 / 0.349**。
- 500 Core：直接加权为 **0.153 / 0.231**，扩展为 **0.150 / 0.250**。

顺序为 5 月 / 6 月。完整分布距离与分歧误差也记录在 JSON。部分指标改善，部分变差，因此**保留 Core 直接加权作为必要基线，当前不据这些结果挑选或冻结最优参数**。

这与先前抽样检查的分母/随机流不同，不能将细微差别误解成代码矛盾。这里用官方 `Q9_mean` 隔离统计扩展的误差，未重新拟合真实十档；真实 LLM 阶段的模拟回答仍使用同一冻结近似计分器。上述结果不是 LLM 准确率，也不证明未来月份的可迁移性。

## 5. 复算与下一步

在主仓库、已有 `socioverse` Conda 环境执行：

```sh
python scripts/check_sce_core_normal.py
python scripts/expand_sce_core_normal.py \
  --run-dir outputs/local_runs/sce-local-scripted-20261005T044714Z-87b226f8 \
  --full-package outputs/monthly_inputs_20261005T044205Z_53cbc7e5/all/202105 \
  --core-package outputs/monthly_inputs_20261005T044602Z_f8c1a697/n300/202105
```

程序仅生成新忽略目录。真实个体记录和自动产物不推送 GitHub。已有计分内核仍在 Kimi 待审批次中，已另存本机执行快照；干净 checkout 的独立复现仍待该批次审阅，不提交或还原它们。

建议下一次真实开发验证使用按月 **300 Core × 2021-05/06**，最新标题＋摘要提示词，统计扩展与直接加权并列；具体待授权命令见 [Core 运行卡](CORE_NORMAL_RUN_CARD_20261005.md)。这项范围不同于先前未执行的 73 人静态画像计划，必须明确登记预算和数据目的地，不能沿用它的授权推定。真实全人口 LLM 参照另申请范围与预算，不在本轮自动扩大。

ConsumerSim 依据：[论文 §4.2.2 与 §4.5.1](https://arxiv.org/html/2606.30395v1)；SCE 月度规模与轮换依据：[官方 FAQ](https://www.newyorkfed.org/microeconomics/sce/sce-faq)、[官方主页](https://www.newyorkfed.org/microeconomics/sce)。核查：2026-10-05。
