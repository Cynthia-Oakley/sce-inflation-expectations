# 给Kimi：统一评价的接入规范

范围：A条件历史诊断；沿用本人先验实验四期、每期12人的固定名册及两次生成。工具只离线评价，不运行模型。程序位于`studies/sce_inflation_expectations/evaluation/behavior_comparison.py`；协议见`codex_comparison_protocol.json`。

## 1. 可以直接复用的内容

- 同计分Q9：十档概率经现有冻结近似计分得到个人密度**均值**，再取跨人中位数。
- Q8：带符号点回答，单独评价，不与Q9均值混称。
- 左逆经验CDF中位数与IQR；插值IQR只作辅助敏感性，旧结果不覆盖。
- 共同有效集、逐组全名册失败计数、逐月与逐次生成成绩，以及按人配对的区间。
- 两种过去信息参照：本人上期照抄；严格过去个人均值的0.5部分调整。没有把当月全国真值加进预测。

## 2. 新结果文件

写入全新的`outputs/<run_id>/evaluation_answers_private.jsonl`，每行一份真实回答，字段如下。以下只是schema，不是已产生新回答的样例。

```json
{"month":202203,"agent_id":"<registered_agent_id>","repeat":1,"arm":"u1_state","q8_point_pct":null,"q9_probabilities":null}
```

- `month`用YYYYMM整数；四期202203/202209/202303/202403，repeat为1/2。
- `agent_id`必须与`outputs/sce_prior_trial_20261013_v2/evaluation_links_private.json`的运行别名完全一致。准备阶段`prior_...`与已运行`belief_...`不同，需用现有映射显式转成统一运行别名，不能猜。
- `arm`是新组名，不能覆盖no_prior/own_previous/permuted_previous及两个基线。
- `q8_point_pct`是Q8带符号数值；`q9_probabilities`是按原问卷顺序的十档0—100概率，和为100。
- 失败回答保留null；请求失败没有记录也会计入缺失数。不能为使结果更好而省略失败、补造答案或提前按真人答案筛样。
- 不导出真实问卷、原始userid、权重或人口字段到这个文件。真人真值由评价程序在本地读取。

同目录`evaluation_manifest.json`须含：

```json
{
  "answers_sha256":"<final_JSONL_hash>",
  "research_line":"A_conditional_history_diagnostic",
  "months":[202203,202209,202303,202403],
  "repeats":[1,2],
  "arms":["u1_state"],
  "model_requested":"deepseek-flash",
  "temperature":0.5,
  "run_ids":["<actual_run_id>"]
}
```

建议另保存实际返回模型/服务商、输入快照/审计记录及费用路径。哈希和名册通过不等于引擎输入已审计，也不能排除相同模型别名背后的服务版本变化。当前入口拒绝不同模型或温度的新组；其他实验需另登记，不混入更新机制比较。

## 3. 执行命令（从项目根目录）

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -B scripts/analyze_sce_behavior_comparison.py \
  --out outputs/<fresh_comparison_directory> \
  --extra-answers outputs/<run_id>/evaluation_answers_private.jsonl \
  --extra-manifest outputs/<run_id>/evaluation_manifest.json
```

不加两个extra参数可复算旧三组及简单基线。已存在输出目录会被拒绝。输出summary/manifest可供阅读；逐人评价与历史状态带private后缀，仅本地保存，不提交。

这些命令已在当前本地工作区验收，需要现有本地数据缓存及冻结计分内核。15项待审文件仍未提交，不能把本次代码保存称作“仅克隆仓库即可一键复算”；正式交付前需按原有审批安排补齐合法可分发的依赖与数据获取说明。

## 4. 怎样判断新机制是否值得继续

先核对输入/名册/时点/失败覆盖，再读指标。Q9主看总体中位数MAE、人群截面W1、跨月变化W1；Q8及排序/IQR为辅助。每次生成与每个月分开报告，再汇总，不能只选有利月份。

项目小试信号：相对原本人先验U0，两次生成都同时降低总体MAE和截面W1，变化W1不恶化，且有效回答覆盖不减少。这是筛选约定，不是学界统一标准，也不表示正式采用。

同样还需把每项差值与**两个**过去信息基线并列。仅超过旧LLM不能称超过简单方法。改善区间含0时，是本批方向仍不明确，不是证明效果为0。不能仅靠人际方差扩大或取整形状更像宣布成功。

报告映射作为附加离线分析，原生回答是主要输出；若使用映射结果作为正式指标，其偏差必须进入评价。四期12人和重复生成不能证明全国表现、连续预测或B闭环成功。

## 5. 与Kimi原C1的关系

本工具history_anchor_half借用0.50作为固定候选，不在这些月份重估。它用冻结近似计分、无当月真值共同平移；不是原C1的同一个估计器，不能引用原C1的0.268pp成绩作为本基线成绩。它只预测中心，不虚构十档概率或个人不确定性。

程序更新后先离线验收实际请求，再按已经确认的发送范围、组数/次数与预算运行；本评价接入说明不触发任何付费调用。

## 6. 2026-10-14：U1 v2两组接入补充

Kimi最新准备组名是`own_state`和`own_state_guided`，manifest与每行arm使用这两个名称。两组总计192份请求，两次生成都保留。

本实验分析用`--protocol docs/workstreams/20261013_behavior/codex_u1_comparison_protocol_v2.json`，其余参数同上。这个新协议加入指导减状态的直接对照与事前42有指导资格者分组；全名册仍主评。默认v1协议保持旧行为，不能靠默认入口推断指导相对状态的增量。

新协议及运行层收据要求见[codex_u1_v2_readiness_20261014.md](codex_u1_v2_readiness_20261014.md)。状态组与旧U0比较增加了更早历史和表示摘要，不能称为纯措辞实验。
