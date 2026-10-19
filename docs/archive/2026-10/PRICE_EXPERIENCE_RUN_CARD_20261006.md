# 下一轮价格体验真实 LLM 对照卡

状态：**2026-10-06 五组小试已完成**（200 次调用、无重试，估价 $0.185111）；[结果与路径](../../PRICE_EXPERIENCE_PILOT_RECEIPT_20261006.md)。下文为执行前冻结方案，授权范围内本轮已结束。本卡不替代实际运行记录；旧文“待授权”是此前状态。

当前冻结计划：`outputs/sce-experience-trial-20261006T080038Z-594845/initial_plan.json`。入口为 `scripts/run_sce_experience_trial.py`，默认只生成计划，真实执行需 `--execute --confirm-spend`；十个“月×组”分别有 $0.20 闸门，总上限 $2。两个年龄/收入/地区样本覆盖核查、200 条实际提示预览和最大尝试费用检查均已完成；两月各组同人，月间不是固定面板。样本覆盖三年龄组、三收入组、四地区、owner/renter，仍不宣称代表全国；尚不扩大人数或追加其他模型调用。

2026-10-06 核对 [DeepSeek 官方目录与价目](https://api-docs.deepseek.com/quick_start/pricing/)：`deepseek-flash` 当前文档映射 DeepSeek-V4.1-Flash；本地免费目录查询成功。费用闸门保守按峰时、未命中缓存的输入 $0.30/百万、输出 $1.20/百万计算，不把该估算冒称账单。实际 returned_model/fingerprint 与每次 usage 留原档；若本轮身份标记变化或出现未解决的无效回答则停止。请求只包含粗粒度画像、合成 CE 支出份额和公共经济新闻；真实问卷答案/调查权重不进入提示词。

## 目的和范围

先确认模型能否对家庭消费背景和信息顺序作出稳定、可区分的响应，再考虑扩大规模。当前为赛道 A 的历史重建开发实验，不能称为 B 线预测，也不把 20 人结果写成全国指标。

准备好的两月小试包：

- `/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/price_experience_20261006_v1/n20/202105/`
- `/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/price_experience_20261006_v1/n20/202106/`

每月从当前 300 Core 中用 seed=42 不放回抽 20 人，不读真人答案。每月所有组使用相同 20 个 ID 和画像、相同 E 和问卷、相同 CE 分配；两月不是同一个固定面板。每包包含 `population.json`、`environment.json`、`simulation.json`、`experience.json`、抽样及哈希清单。此次不使用 Normal 扩展，不做 SCE 水平校准。

## 组别与调用数

五组：重新运行的原 v2-abstract 基线，以及 `expression_shared`、`basket_shared`、`focus_only`、`basket_focus`。因此是 **20 人 × 2 月 × 5 组 = 200 条目标回答**；每条最多补一次，最多 400 次尝试。每个“月×组”设 40 次调用上限。

复用此前 DeepSeek 官方端点和模型候选 `deepseek-flash`，明确关闭思考、temperature=0、max_tokens=1024、retry_max=1。运行前必须重新核实目录、当前价目、数据目的地和授权，不假定滚动模型别名仍是旧版本。实际 returned model、request ID、usage、时间和提示词哈希均记录。小试期间不临时更换模型、提示词、问卷、篮子种子或新闻集合。

建议运行时交替安排各组，预先固定顺序并记录起止时间；若 API 模型或端点发生变化，停止并标记该轮不能直接配对。20 人仅检查接入与初步效应，不保证有足够统计功效识别微弱机制。

## 费用与停止条件

建议新总上限 **$2**，每个“月×组”上限 **$0.20**。用户已于 2026-10-06 授权本轮预算，不沿用旧两月授权；不授权重复或扩样。

以旧运行账本使用的输入 $0.30/百万 token、输出 $1.20/百万 token 作参考，而非声称当前官方报价：此前约每回答 0.0009 美元，新篮子段会增加输入；200 条目标回答粗略是几角美元量级。保守上界用实际提示词 UTF-8 字节数加 256 个 input token，再加 1024 个 output token；按本版最大提示词和最多 400 次尝试，留 $2 较宽裕。实际执行前按当时核实的价目重算，若不在上限内缩小调用数或重新批准。

任一运行遇到费用闸门、画像/篮子错配、处理未进入实际提示、事实清单变化或大量不合法 Q9，停止并留存原始失败。不用规则式答案填补、不自动归一化概率、不把技术失败补成有效样本。

## 可以直接替换参数的命令

以下真实模式命令仅供批准后执行；不是自动授权。第 1 月 basket_focus 的配置已经有现成文件：

```bash
cd /Users/wushuyue/Documents/科研/DISC/socioverse_challenge
sce_project_root="$PWD"
sce_pilot_dir="$sce_project_root/outputs/price_experience_20261006_v1/n20/202105"
python scripts/run_sce_local.py --llm openai --model deepseek-flash \
  --population "$sce_pilot_dir/population.json" \
  --environment "$sce_pilot_dir/environment.json" \
  --simulation "$sce_pilot_dir/simulation.json" \
  --mechanism studies/sce_inflation_expectations/mechanism/basket_focus.json \
  --experience "$sce_pilot_dir/experience.json" \
  --prompt-version sce-q8-q9-experience-v1 \
  --temperature 0 --max-tokens 1024 --retry-max 1 --max-calls 40 \
  --extra-body '{"thinking":{"type":"disabled"}}' \
  --price-in 0.30 --price-out 1.20 --cost-cap-usd 0.20 --confirm-spend
```

其余新组只换 `--mechanism` 文件。同月原基线去掉 `--mechanism/--experience`，改用 `--prompt-version sce-q8-q9-v2-abstract`。次月替换目录里的 `202105` 为 `202106`。真实命令保留每组新 run_id 的默认行为，不能覆盖旧运行。

## 预先固定的判断方法

1. **工程门槛：** 核对每组实际提示、P/公共事实/问卷一致性、ID、原始回答、失败与费用。不能只看运行成功或理由提到了食品/油价。
2. **先看 Core：** 与旧基线及相同真人匹配样本比较 Q8 与 Q9 个人密度均值的中位数、IQR、分位数和固定尾部占比；Q9 统一现有冻结研究计分器，官方近似误差另报。
3. **分别看回答形状：** Q8 的不同数值数量与整数/半百分点网格；Q9 非零档数、最大档/最高两档质量、整向量模板重复。个人 Q9 更宽，不等于人群分歧更大。
4. **成功不能仅是标准差上升：** 分位数/分布与真人更接近，且总体水平、Q9 题内形状和合法率没有明显变坏，才值得进入下一轮。小试只供方向判断，不能选参数后再把这两个月当独立验证集。
5. **扩展条件：** 输入和初步效应可解释后，固定参数，换未用于开发的月份验证；再用每月 300 人检验稳定性、换 donor seed 检查分配不确定性。Core 原始效果与 Normal 后处理分开报告。

不要求预期上调，也不预设每类家庭答案必须如何变化。若无改进，保留否定结果，下一步将原 SCE 问卷表达/整数报告格式、购买频率、非均匀信息接触或模型记忆实验分别设计，不合并成无法解释的大改动。
