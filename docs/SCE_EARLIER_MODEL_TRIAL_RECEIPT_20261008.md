# 较早模型小试：LLaMA 已运行，千问路由未通过检查

日期：2026-10-08。用户在明确收到数据发送范围和两模型总上限 $0.50 后回复：**“好的，我觉得可以开始，同意。”** 此前自动审批缺授权的阻碍已解除，本次真实命令成功执行。

## 1. 实际执行了什么

- 固定 2021-05/06，每月 20 个既有 Core 案例；每个模型本来计划 40 份回答。每月的同一套画像、环境、逐字一致的消息与已有 DeepSeek 回答比较。两月分别抽样，所选 ID 没有重叠，不称同一批 20 人的跨月面板。
- 保留标题＋摘要提示 `sce-q8-q9-v2-abstract`、温度 0.5、输出上限 1,024 token。没有同时加入新 P、消费篮子或修改 E。
- API：OpenRouter；下游固定 DeepInfra，无 fallback。只发送去标识画像和公开历史信息，不发送真实回答、原始个人 ID 或参考模型回答。
- **LLaMA 完成**：请求与实际返回 `meta-llama/llama-3.1-70b-instruct`，返回 provider 全部 `DeepInfra`，锁定 `deepinfra/turbo`；目录记录 fp8。
- **千问未调用**：`qwen/qwen-2.5-72b-instruct` 的 `deepinfra/fp8` 路由初查与复查均返回 `status=-2`，未通过预先约定的健康条件 0。没有发送千问付费请求，没有换供应商，也不能据此说千问模型本身没有效果。状态码详细含义未独立证实，不将其直接解释为整个服务永久下线。
- 参考回答的实际服务标签是 **`deepseek-flash`**；不从这个标签补造具体权重版本或训练截止日。

这次是**相同消息的模型行为小试**，不是新完整 SocioVerse 引擎运行，也没有 Normal 扩展。正式 study/运行配置不变。

## 2. 调用、费用与校验

- 真实付费请求 **41 次**，最终 **40 份有效回答**；其中一份 Q9 合计 99%，按已登记的一次重试规则重试成功。
- 输入 token **98,947**，输出 token **4,645**。41 次响应均记录 `usage.cost`，相加 **$0.0414368**；也与本次输入/输出价 $0.40/百万 token 算法对上。该数是 API 返回费用记录，不冒充独立账户账单。
- 40 个唯一有效案例覆盖两月各20人；全部请求与返回模型/provider 相符，预算远低于 $0.50，日志逐次落盘。
- 实际原始概率全部通过结构验收；同一个冻结计分器分别拟合真人和模型。真人原始 Q9 有 5月2份、6月1份不合法，因此 Q9 共同比较 **18/19人**。模型两组各20份均拟合成功，没有以模型结果好坏筛案例。
- Q8 独立处理，真人5月1份无有效数值，分别比较 **19/20人**。Q8 真值是带符号 `Q8v2part2`，不是方向码 `Q8v2`。

运行状态为 `partial_or_blocked`：准确表示 LLaMA 已完成、千问被健康门拦截，不虚构80份回答。先前口头“没有重试”已依据最终日志更正为一次格式重试。

## 3. 对照结果怎么理解

以下均为**同一小样本、等权**诊断。Q9 数值指每个人概率回答拟合后的密度均值，再计算这批人的分布；不是官方全国 headline。

### 5月：水平较接近，但分散度更差

- Q9 个体 MAE：DeepSeek **2.911pp**，LLaMA **2.421pp**。
- 真人样本中位数 **3.372%**；DeepSeek **2.374%**，LLaMA **2.997%**。
- 真人样本回答 IQR **2.405pp**；DeepSeek **0.605pp**，LLaMA **0.036pp**。
- 整体分布距离 W1：DeepSeek **2.178pp**，LLaMA **2.279pp**，没有随着中位数改善而变好。

### 6月：水平更偏低，回答仍过于接近

- Q9 个体 MAE：DeepSeek **2.965pp**，LLaMA **3.084pp**。
- 真人样本中位数 **5.534%**；DeepSeek **4.133%**，LLaMA仍为 **2.997%**。
- 真人样本回答 IQR **3.670pp**；DeepSeek **1.106pp**，LLaMA **0.036pp**。
- W1：DeepSeek **2.405pp**，LLaMA **2.927pp**。

原始回答也支持“Q9集中”的判断，而非只由拟合器产生：LLaMA5月有7种、6月8种概率向量；每月各10人给出完全相同的 `[0,0,20,60,15,5,0,0,0,0]`。该向量未出现在实际输入消息作为数值例子；这项重复现象还不能证明原因是训练记忆或美国语料。

**Q8 有不同表现，不能混在一起说所有回答都更同质：** LLaMA 点预测 IQR 是5月 **1.25pp**、6月 **1.00pp**，均大于 DeepSeek 的 **0.50/0.075pp**；但逐人 MAE 两月仍约 **5.00pp**，与 DeepSeek **5.026/5.015pp** 接近，没有解决拟合问题。

人口分组诊断已按年龄、教育、收入、数值理解能力与就业状态保存；只有共同有效人数至少5人的组展示误差，其余只保留人数。这个规模不足以判断各人群是否稳定改善，不据此调整人口或提示词。

### 当前结论

**这次小试不支持直接将 LLaMA 升级为正式模拟模型。** 它5月部分水平指标更好，6月更差；主目标 Q9 的人群分散度明显更低。保留结果，也保留 DeepSeek 当前参考配置，等千问路由通过原健康门后再补其固定对照。

这不是“LLaMA普遍不适合”或“哪个模型胜出”的定论：只有两个开发月、每月20人、每人一次有效生成，服务量化、模型、随机性没有分开检验；2021仍可能在两个模型的训练窗口内。模型开发者所在国家与居民代表性不能由这轮结果建立因果关系。

## 4. 准确路径和复算

项目根：`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/`。

- 冻结参考输入：`outputs/sce_model_counterfactual_20261007/`。
- **真实运行**：`outputs/sce_earlier_model_trial_20261008/`，含 `run_summary.json`、41行 `llm_calls.jsonl`、实际请求副本、运行源码快照、两个模型目录快照及千问免费复查快照。
- **最终评价**：`outputs/sce_earlier_model_analysis_20261008_v3/`，含 `summary.json`、40行本地 `paired_evaluation_private.jsonl` 和计分器快照。v1 是日期格式兼容修复前的未完成目录，不引用它作为结果；v2 是无分组诊断的中间复算，v3 增加分组诊断，主指标与 v2 完全一致。
- 小型聚合摘要：[sources/sce_earlier_model_trial_20261008.json](sources/sce_earlier_model_trial_20261008.json)。真实/模型个体回答与画像不提交 Git。
- 新离线入口：`scripts/analyze_sce_model_counterfactual.py`；指标模块：`studies/sce_inflation_expectations/model_comparison_analysis.py`。调用入口和费用保护维持本次执行时版本，不改源代码重跑。

```sh
conda run -n socioverse python scripts/analyze_sce_model_counterfactual.py \
  --inputs outputs/sce_model_counterfactual_20261007 \
  --run outputs/sce_earlier_model_trial_20261008 \
  --out outputs/sce_earlier_model_analysis_REPLAY
conda run -n socioverse python -m pytest -q \
  tests/test_model_comparison_analysis.py tests/test_sce_model_counterfactual.py
```

输出目录须不存在。评价入口不联网，不读取 API 密钥；运行 `run_sce_model_counterfactual.py --confirm-spend` 则是新真实调用，**不要把它当作评价复算命令**。

7项定向测试通过：共同比较掩码、误差方向、无有效案例拒绝、既有费用/路由保护。实际输入哈希、计分器冻结来源、41条返回身份/费用、40案例覆盖均验收通过。Kimi/用户15个待审文件哈希保持不变；`DECISIONS.md`继续留待审，本轮决策记录于本文。

## 5. 接力

已获授权的千问份额仍为40份、相同输入；更换供应商不在本次授权范围。下次先免费检查 `deepinfra/fp8`，只有原健康/参数/价目条件通过才继续；需实现只补千问的续跑入口，携带本次已花 **$0.0414368** 的账务记录，避免重跑 LLaMA 或重置总预算。恢复不确定，不替用户承诺完成时间，也未创建定时监控。

更重要的研究线索是：Q8较有变化，Q9却大量重复，后续可以独立核查概率表达和条件不确定性机制。先登记新设计，再做确认实验，不在这两月反复调提示词后宣布正式验证成功。
