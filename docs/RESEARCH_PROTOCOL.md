# 研究与评测协议（实施前锁定）

## 1. 目标与预测时点

在 `docs/DECISIONS.md` 中冻结以下六项：发布者与原始问题、国家/人群、选项与聚合公式、统计单位（百分点）、目标月份对应的田野期、预测截止 `as_of`。建议首版只做 **1 国 × 1 个调查统计量**。若田野开始日可靠，则首版 `as_of` 设为田野开始前一日 23:59；若不能稳定取得田野期，采用每月固定日并明确此设定的限制。一次实验里不因个别月份调整截止规则。

WWTW 某个问题的百分比与“综合指数”不同，报告标题和代码都应使用实际统计量名称。问卷选项、国家覆盖与权重变化均可能造成断点，应记录并在报告中检验。

## 2. 数据契约

真值表每行至少包含：`target_id, country, reference_month, question, response_option, value_pct, fieldwork_start, fieldwork_end, release_at, source_url, source_version, extraction_method, verified_by`。

输入表每行至少包含：`signal_id, value_or_text, observed_at, published_at, ingested_at, source_url, source_version, as_of, availability_rule`。`observed_at` 是事件发生或数据所指日期，**不等于**公众获知日期。回测只接纳 `published_at <= as_of`；发布时间不明的资料先隔离。事后修订值必须保留原版或排除，不能把最新网页快照当作历史已知值。

初期不导入 551 个候选指标。只取与研究机制有关、能核查发布时间的少数信号。受限微观数据不提交；若仅用公开边际合成人群，要明示“合成画像”与代表性的假设。

## 3. 样本与对照

- 先审计连续月份、缺失、定义变化和真值可核验比例，再定训练/验证/测试切点；测试期必须连续、在时间上最后。
- 首个基线为“上次在 `as_of` 已公布的该统计量”。若历史长度足够，加季节性朴素预测和仅用过去数据拟合的时间序列基线。
- 至少设一个能检验 Agent 附加价值的对照：同一输入集下的规则式或简单文本信号聚合。LLM 与对照接受同一个截止时点的信息。
- 所有调参（prompt、聚合权重、惯性系数、模型选择）只用训练/验证期。测试期开始前记录配置和代码版本；发现问题需另开版本并保留原结果。
- 评价优先报告 MAE（百分点）、RMSE、逐月误差、相对基线差值，以及按预先定义的事件月/平静月切分。小样本下报告区间或逐月误差分布，不宣称显著优胜。

## 4. P/E/B 的最小机制

- **P 人群**：固定、可复现的合成画像与权重；首版按可公开核对的国家人口边际构造。无微观数据时不声称保留真实联合分布。
- **E 环境**：月度或田野前的信息快照；信号的时点、来源与暴露规则可追踪。先实现可用公开输入的版本，再接平台服务。
- **B 行为**：输出与目标问卷选项一致的结构化回答及简短理由。先用确定性规则响应验证流程，再试 LLM；解析失败率和兜底率需要记录。
- **聚合**：画像权重转为目标百分比；平滑或校准若使用，参数只从训练/验证期估计，并设无校准消融。

SocioVerse2 的现行公开文档提供原生 study 与 ConsumerSim 包装案例；先跑官方 `scripts/demo_offline.py`，再复制最接近的模板，按当前 v0.2.0 的实际 schema 实现。不要依据 9 月 24 日的离线文档直接猜接口。

## 5. 复现门槛

每次实验保存配置、代码 commit、数据清单及散列、时间切分、随机种子、模型精确版本、prompt 版本、调用量、成本、输出与失败记录。提供一条**无需密钥**的干跑命令和真实 LLM 路径。验收包括：同一快照与种子重跑一致；任何 `published_at > as_of` 输入被拒绝；真值不进入 Agent 观察；基线与 Agent 使用同一测试期。

来源：[Challenge 要求](https://socioverse.fudan-disc.com/challenge/)、[SocioVerse2 发布说明](https://socioverse.fudan-disc.com/docs/getting-started/releases/)、[Ipsos WWTW](https://www.ipsos.com/en/what-worries-world)。
