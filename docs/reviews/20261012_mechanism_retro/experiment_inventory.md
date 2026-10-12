# SCE 两周工程与实验清单

盘点日期：2026-10-12。范围覆盖 2026-09-29 至 2026-10-12 可核验的代码、冻结运行卡、非个人汇总和 run 输出。本文只汇总群体结果，不复制姓名、原始 ID、个人回答、逐人配对表、新闻全文或密钥。机器可读副本见 [experiment_inventory.json](experiment_inventory.json)。

## 结论概览

本轮已把 SCE 的本地模拟、留痕和离线评价做成可运行的研究基础设施，并完成了 2021-05/06 每月 300 Core 的 DeepSeek 真实调用。研究效果仍不支持“已可靠重建居民预期”：两月全国 Q9 偏低，人群差异远窄于真人。之后的机制试验大多是开发期小样；有些改变了中心，有些增加了回答差异，但尚无一个候选稳定地同时改善中心与人群分布。

当前可列为**已采纳基础设施**的，是冻结的项目近似 Q9 计分器、逐 run 保存提示/回答/输入哈希/费用估计的本地引擎入口、Core/Normal 扩展和统一离线评价。这里“冻结”指真实与模拟问卷共用固定算法与哈希；它仍不是纽约联储官方 Beta 实现的逐人精确复刻。DeepSeek 是已使用的参考服务，不等于已证明优于其它模型或已核实不可变权重。

**保留候选**包括：近期全国价格补充、新闻相关加权、央行信心文字；SCE 原生支出关联仅保留为本地研究候选，真实 QSP5 外发模拟仍是准备包且待具体审批。简要文字经历已完成开发试验，但当前暂停、未采纳，产物仅为复核保留。**未稳定改善、暂缓**包括：CE 合成篮子/排序、Q1 财务经历、价格/新闻个体匹配、数值年龄经历、就业收入宏观人口更新及模型扩容。等价措辞有实际离线消息预览和候选分配记录，但未接入 runner、未真实交叉运行；不得把草案或离线候选当成执行。

离线统计基线最初为 2020-01 至 2024-12 共 60 月，后扩展到最新核验范围：全国 headline 2020-01 至 2026-08 共 80 月，微观分布 2020-01 至 2025-10 共 70 月；三者都没有 LLM 调用。另有 2021 全年的 Qwen 旧输入复用小样；其消息继承旧 DeepSeek 上期答案，E 只有 4 条 BLS 信号，不能当作新版 77 信号环境下的长期验证。四时期年龄/信心试验每期 12 或 48 个所选调查记录，属于开发诊断，和 2021 年每月 1,234/1,297 人总体及每月 300 Core 主实验完全分开。

## 各环节实际状态

| 环节 | 已有实现或产物 | 还缺什么／应如何表述 |
|---|---|---|
| Literature | `docs/literature/sce/` 已覆盖预期形成、价格体验、CE/SCE 支出、新闻、信心、数理能力、年龄经历和概率表达；另有来源/哈希台账与本地原始归档。 | 文献支持研究问题，不直接给出可移植的 Agent 参数。新闻曝光、购物频率和“经历唤起”仍需本项目数据与干预识别；不能把相关性或合成属性写成因果机制。 |
| Study | `studies/sce_inflation_expectations/study.yaml`、`studies/sce_inflation_expectations/model.py`、`studies/sce_inflation_expectations/resources.json` 与 `scripts/export_study_runtime.py` 提供 SCE study 及单向运行副本导出；官方 SocioVerse2 版本/本地环境在 `docs/LOCAL_RUNTIME_ACCEPTANCE.md` 记录。 | 锁定到一次真实运行的依赖/框架完整环境尚未作为自包含研究包交付；当前仍主要是 A 线开发回放，不能称完整 B 线预测研究。 |
| Population | `studies/sce_inflation_expectations/monthly_population.py`、`studies/sce_inflation_expectations/core_normal.py`、`studies/sce_inflation_expectations/population_forecast.py`、`studies/sce_inflation_expectations/price_experience.py` 与 `scripts/build_sce_population.py` 支持白名单 SCE 画像、Core/Normal 及人口比例候选、CE 合成支出侧车。 | 同期画像与权重属 A 线事后条件，不能据此称 PIT。真实 QSP5 仅在本地完成关联研究，尚未获准外发用于 LLM。宏观就业/收入候选没有接入正式 P。 |
| Environment | `studies/sce_inflation_expectations/environment_authoring/availability.py`、`studies/sce_inflation_expectations/environment_authoring/vintages.py`，以及 `scripts/build_sce_environment.py`、`scripts/extend_sce_environment_sources.py` 支持日期/可得性校验和历史资料；主试验包含 77 条宏观信号及新闻。还有新闻池/50:50 抽取与近期 EIA/USDA 高频价格入口。 | 部分汽油/新闻历史版本、NYT 纸版发布时间未独立核实；最新 E 截至 2026 的文件有 draft 标记。输入时点合格也不消除模型预训练知识泄漏。 |
| Dataset | 核心 SCE 月度数据已审计 106 个月、约 130,216 个受访者-月份记录；SCE 支出模块、CE Interview/Diary、BLS/BEA 与 NYT 资料均有不同层级的归档。 | 个人/原始下载与轨迹在忽略目录；SCE 微观公开时点、各指标完整 vintage 及新闻文本历史版本仍未全覆盖。当前本地核验范围不等于官网最新状态。 |
| Simulation | `studies/sce_inflation_expectations/model.py` 支持 deterministic scripted 与 OpenAI 兼容 LLM；`scripts/run_sce_local.py` 已完成规则干跑和 DeepSeek 真实调用，多数机制试验复用相同入口或独立可审计试验入口。 | 真实 LLM 结果仍是小样、回顾性、单次/少次生成；服务别名不等于可验证模型权重和训练截止。云端 v2/v3 只作为流程证据，v4 真实 LLM 未运行。 |
| Trajectory | `outputs/local_runs/sce-local-openai-20261005T092656Z-202105-8d2e3b2c/llm_calls.jsonl` 展示本地调用记录；试验级 manifest/输入/分析示例见 `outputs/sce_q1_trial_20261006T142504Z_a6740800/trial_manifest.json` 与相邻分析目录。 | 自动输出大多被 Git 忽略，完整复现需本地受限输入/运行环境；云端 v2 没有历史 Observation、独立 run ID/费用账单，v3 sidecar 与源文件间仍有换行转换说明缺口。 |
| Analysis | `studies/sce_inflation_expectations/scoring/`、`studies/sce_inflation_expectations/evaluation/`、`studies/sce_inflation_expectations/news_exposure_analysis.py`、`studies/sce_inflation_expectations/confidence_response_diagnostic.py` 支持共同比较、人口分布、Q8/Q9 分开评价、来源/成本审计及长窗口统计基线。 | Q9 广义 Beta 尾部/空档差异尚存；全国 headline、项目近似重算及小样等权结果是不同口径，不能拼在一起排序。完整未见月份与严格 PIT 的 B 验证尚未完成。 |
| Reports | `docs/` 有逐项运行回执，`outputs/` 有可离线复算 summary、图和 HTML；主项目状态在 `docs/project_status.md`。 | 尚无最终研究论文/交付报告；`studies/sce_inflation_expectations/population/README.md`、`studies/sce_inflation_expectations/environment/README.md`、`studies/sce_inflation_expectations/simulation/README.md`、`studies/sce_inflation_expectations/trajectory/README.md`、`studies/sce_inflation_expectations/reports/README.md` 留有早期“待实现/无结果”文字，和现有源码及 10 月运行记录不一致，见末节状态冲突。 |

## 实验族清单

### 1. Q9 计分器冻结与共同评价

- **日期与改变：**2026-10-01 起独立复核，后续 10-03 固定执行核；P/E/B 不变，变化只在评价实现与证据封存。人类和模拟均从原始 Q9 十档走同一版本，Q8 另算。
- **规模与结果：**2020-01、2022-06 两月共 2,534 份官方记录中，均匀和相邻双档三角分支逐人高度吻合；Beta 开放尾/不连续档存在误差。已用 3,741 条 sealed holdout 行复算，内核迁移前后逐字段差异为零。公开官方派生均值的加权中位数可对账，近似拟合后全国值仍有约 0.007–0.011pp 差异。
- **状态：**已采纳为**冻结的项目近似评价基础设施**；不声称官方逐人 Beta 精确复刻，也没有把计分器上传为云端官方计分。
- **证据：**`studies/sce_inflation_expectations/scoring/sce_q9_frozen.py`、`studies/sce_inflation_expectations/scoring/beta_fit_kernel.py`、`docs/SCE_Q9_SCORING_REPLICATION.md`、`outputs/sce_confidence_analysis_20261011_v2/summary.json` 中冻结来源哈希。

### 2. 云端 scripted 与本地真实 LLM 通路

- **日期与改变：**云端 v2/v3（2026-09-30/10-01）用两期 BLS E、20 个合成画像、scripted B；本地 10-03 起验收导出和引擎，10-05 开始真实 DeepSeek。B 的 scripted 与 LLM 分支明确分开。
- **规模与结果：**云端 v2、v3 各有 20 人 × 2021-05/06 = 40 条 scripted 答案，模拟 LLM 调用 0；v3 40/40 Observation 与答案内容有平台轨迹佐证，但文件换行转换层未完全闭合。云端真实 LLM v4 配好后未运行，报价卡未给价格，且云端对话额度已透支。真实本地 LLM 结果见下方 300 Core 主实验。
- **状态：**scripted 与本地真实 LLM 路径均属已采纳工程能力；云端 scripted 仅作流程证据，不是预测效果。v4 仅准备/未运行。
- **证据：**`docs/CLOUD_V2_PILOT_RECEIPT.md`、`docs/CLOUD_V3_AUDIT_RECEIPT.md`、`docs/CLOUD_V4_PREP_RECEIPT.md`、`docs/LOCAL_RUNTIME_ACCEPTANCE.md`、`studies/sce_inflation_expectations/model.py`。

### 3. 300 Core + Normal 主运行

- **日期与 P/E/B：**2026-10-05；P 为当月完整 SCE 人口框，2021-05 的 1,234 人、2021-06 的 1,297 人，各抽 300 Core，其余为 Normal。E 为每月 77 个宏观信号 + 30 条新闻标题/摘要。B 为 DeepSeek 官方 `deepseek-flash`、`sce-q8-q9-v2-abstract`、temperature 0.5；月间冷启动、不输入本人上期答案。
- **规模与结果：**共 600 次 API 调用、600 份有效回答、0 重试；保守费用估算 $0.536425（非供应商账单）。Q9 全国中位数 5 月 2.952% 对全月近似计分 4.000%，6 月 3.860% 对 4.802%；Normal 扩展没有稳定改善 Core 直接加权。模拟跨人 Q9 标准差约 0.585/0.646pp，真人约 6.874/7.111pp，分歧严重偏窄。
- **状态：**真实端到端主流程与审计基础设施已采纳；Normal 是可复算的统计扩展，未被证明有准确性增益。该运行是两个月 A 线开发，不是预测/全国胜出结论。
- **证据：**`docs/CORE_NORMAL_LLM_RECEIPT_20261005.md`、`docs/CORE_NORMAL_ACCEPTANCE_20261005.md`、`outputs/local_runs/sce-local-openai-20261005T092656Z-202105-8d2e3b2c/`、`outputs/local_runs/sce-local-openai-20261005T092656Z-202106-e4f49f76/`、`outputs/core_normal_expansion_20261005T093623Z_65145ce1/`、`outputs/core_normal_expansion_20261005T094550Z_b1b09dd8/`。

### 4. 早期 60 月基线、最新 80 月全国与 70 月微观基线

- **日期与改动：**2026-10-07 先完成 60 月版，随后扩展为最新可核验范围。使用官方 SCE headline/CPI 历史和人口分布统计，构建持续性、AR(1)、ARX、规则更新及人口条件分布基线；0 次 LLM。
- **规模与结果：**早期全国版为 2020-01 至 2024-12，共 60 月，其报告数值作为早期窗口结果保留。最新全国 headline 覆盖 2020-01 至 2026-08 共 80 月；上月末持续性 MAE 0.303750pp、AR(1) 0.346464、规则 25% 更新 Agent 0.438750。月中为 79 月：持续性 0.231646、AR(1) 0.256516、规则 Agent 0.356962。ARX 上月末/月中分别覆盖 66/67 月，须与相同月份持续性基线比较。最新微观分布为 2020-01 至 2025-10 共 70 月：历史分布 W1 0.501307，人口条件 W1 0.500891；年龄×教育组中位数误差 0.579344→0.482376。另有 Core 抽样精度诊断；它是从真实答案理想化下采样，不是新 LLM。不同覆盖窗口和评价对象的指标不横向排序。
- **状态：**最新 80 月全国与 70 月微观离线基线已采纳为后续比较参照；早期 60 月结果仍保留作历史 run 记录，不是当前覆盖状态。它们都不等于 Agent 已通过长期验证。可比信息权限和 2021 以外新版 Agent 长跑仍未完成。
- **证据：**`docs/SCE_BASELINE_RESULTS_20261007.md`、`docs/SCE_BASELINE_METHODS_AND_LATEST_20261007.md`、`docs/SCE_EVALUATION_CONTRACT_V1.md`、`studies/sce_inflation_expectations/evaluation/baselines.py`、`outputs/sce_baselines_20261007T041750Z_5973bbf9/`、`outputs/sce_baselines_20261007T055057Z_f99c2f6b/`、`outputs/sce_core_size_20261007T061115Z_ec4e8ba9/`、`outputs/sce_core_size_replay_20261007T061426Z_74fe5ffd/`、`outputs/sce_core_size_replay_20261007T061510Z_93b5b374/`。

### 5. DeepSeek、Qwen 与 LLaMA 模型族

- **短窗同输入试验（2026-10-08）：**2021-05/06 各 20 个既有 Core 案例，固定旧 P/E/问题和消息，temperature 0.5；LLaMA 3.1-70B 为 41 请求/40 有效回答，Qwen2.5-72B 首轮指定路由不通过健康门而 0 调用，后来续跑 40 有效回答。Qwen 5 月 Q9 个体 MAE 2.479pp（DeepSeek 2.911），6 月 3.544（DeepSeek 2.965）；方向未改善，分布仍窄。LLaMA 5 月水平较近、6 月更差，两月个人回答 IQR 仅约 0.036pp。均未升级正式模型。
- **小模型/类似模型补充：**Qwen2.5-72B 40 份有效；LLaMA3.3-70B 只有 4 个案例、LLaMA3.1-8B 只有 1 个案例通过格式，触发格式门后停止，不能作性能排名。API费用及失败留在原始收据中。
- **旧输入全年复用（2026-10-08）：**同一 20 人、2021-01..12 的旧输入，Qwen 240 份有效回答/246 次请求；DeepSeek 新调用 0，复用旧回答作对照。E 只有 4 条 BLS 信号，旧版消息中 220/240 含 DeepSeek 上期点预测，161/240 与 Qwen 自己上期值不同。Qwen 月度 MAE 0.884pp 对 DeepSeek 0.952（下降 7.2%），仅 6/12 月改善，方向匹配 3/11 对 5/11，分布距离反而 2.642 对 2.546pp；预设门槛未过。
- **后续全年四模型卡：**2021 每月 300 Core × 12 月 × 4 模型，14,400 请求仅离线准备，建议 $20 总预算未获批准；实际调用 0。其 simulation.json 是旧 scripted 模板，不是执行配置。
- **状态：**DeepSeek 保留为已运行参考服务；不作最优模型结论。Qwen/LLaMA 不替换，进一步扩模暂停；四模型全年只准备、未运行。别名/服务路由没有给出独立的权重版本或训练截止证明。
- **证据：**`docs/SCE_EARLIER_MODEL_TRIAL_RECEIPT_20261008.md`、`docs/SCE_MODEL_FOLLOWUP_20261008.md`、`docs/SCE_QWEN_REUSE_RESULT_20261008.md`、`docs/SCE_ANNUAL_MODEL_COMPARISON_20261008.md`、`outputs/sce_model_followup_analysis_20261008_v3/summary.json`、`outputs/sce_qwen_reuse_comparison_20261008_v1/summary.json`、`outputs/sce_annual_models_prepared_20261008_v1/summary.json`。

### 6. CE 合成消费篮子、信息排序与答题视角

- **日期与 P/E/B：**2026-10-06。P 加入由 CE Interview donor 条件抽样的食物/汽油/住房/其他份额；不是所选 SCE 受访者本人账单。E 在保留共同事实下试了同一视角措辞、展示篮子和按篮子排序；B 沿用 Q8/Q9。
- **规模与结果：**2021-05/06 各 20 人、五组，每人每月五条回答，共 200 次真实 DeepSeek 回答，温度 0。完整机制的 Q9 个体 MAE 5 月比原基线低约 0.289pp，6 月仅低约 0.002pp；Q9 跨人 IQR 每组都不到 1pp，而同批真人约 5.2/5.4pp。答题视角本身不改善稳定；排序也无稳定收益。
- **状态：**未稳定改善、暂缓扩样；合成篮子保留为价格暴露代理，不称真实支出/个人价格或已验证的注意权重。
- **证据：**`docs/PRICE_EXPERIENCE_PILOT_RECEIPT_20261006.md`、`docs/PRICE_EXPERIENCE_MECHANISM.md`、`studies/sce_inflation_expectations/mechanism/`、`outputs/sce-experience-trial-20261006T080038Z-594845/trial_manifest.json`、`outputs/sce-experience-trial-20261006T080038Z-594845/analysis/summary.json`。

### 7. SCE 原生 QSP5 九类真实篮子

- **本地数据研究（2026-10-09）：**2020–2024 与核心 SCE 重叠 15,931 人月全部按 ID+月份关联；其中 11,327 条完整九类支出、合计 100% 且有有效权重。2020–2024 统计关联显示高食品份额组 Q9 中心较高，但为相关、非因果。固定岭回归做 2020–21 训练、2022–24 复查，本人篮子对 Q9 中心 MAE 只改善 0.039–0.063pp，Q8 未改善。
- **拟议真实模拟：**2021-05/06 各 32 人，三组“不加篮子/本人篮子/随机错配篮子”，192 份 DeepSeek 提示，规则干跑已通过。运行前具体授权审核拒绝：已有许可只涉及 CE 合成篮子，未覆盖真实 QSP5 支出占比向 API 外发。随后已向用户问明具体范围；在明确答复前真实调用为 0、费用为 $0。v4 是准备包，不是完成实验。
- **状态：**本地统计基础设施已完成；真实人篮子 LLM 对照仅准备，审批待回复。不能把 CE 试验授权套用到 SCE 原始支出。
- **证据：**`docs/SCE_NATIVE_SPENDING_20261009.md`、`docs/literature/sce/native_spending/DATA_AND_METHOD_20261009.md`、`studies/sce_inflation_expectations/native_spending.py`、`studies/sce_inflation_expectations/native_spending_trial.py`、`outputs/sce_native_spending_trial_20261009_v4/trial_manifest.json`、`outputs/sce_spending_audit_20261009_v2/summary.json`。

### 8. Q1 家庭财务状态

- **日期与 P/E/B：**2026-10-06。P 增加当月 SCE Q1 过去一年家庭财务变化描述；E、问卷、模型和计分不变。五类 Q1 各抽 10 人/月。
- **规模与结果：**2021-05/06 各 50 人、原输入/Q1 两组、共 200 次回答；6 月有一份真人 Q9 无效，故 Q9 配对 49 人。Q1 使“财务变差—不变”的群体差更接近真人，但逐人 MAE 两月均小幅恶化，跨人离散没有稳定改善；6 月更集中。
- **状态：**未稳定改善、暂缓升级正式 P；不把一个分组差距改善当整体成功。
- **证据：**`docs/HOUSEHOLD_STATE_PILOT_RECEIPT_20261006.md`、`docs/HOUSEHOLD_STATE_ACCEPTANCE_20261006.md`、`outputs/sce_q1_trial_20261006T142504Z_a6740800/trial_manifest.json`、`outputs/sce_q1_analysis_20261006T143540Z_33c159ad/summary.json`。

### 9. 价格信息接触与个人通道匹配（2026-10-06）

- **P/E/B：**P 使用 5/6 月真实白名单画像与 CE 合成篮子；E 在相同其它输入下比较 shared、shuffled、matched 三个“食品/汽油/住房单通道”视图，并关闭新闻；B 其它相同。
- **规模与结果：**每月 48 人，三臂，共 288 次真实调用。匹配提高部分跨人分散（IQR 5 月 0.66/1.54/1.76，6 月 1.30/2.22/2.88pp），但 matched 的 Q9 个体 MAE 高于 shared，且不稳定胜过 shuffled；两月分布距离变差。真实回答 IQR 约 5.98/5.81pp，模拟仍窄。
- **状态：**未稳定改善、暂缓这类“只看一个品类”的路由；保留对个体接触的研究问题。不得将单通道模拟当作实际购物/阅读行为测量。
- **证据：**`docs/INFORMATION_EXPOSURE_RECEIPT_20261006.md`、`docs/literature/sce/information_exposure/README.md`、`outputs/sce_exposure_analysis_20261006T151924Z_47735326/summary.json`、`outputs/sce_exposure_trial_20261006T150949Z_533cc2be/trial_manifest.json`。

### 10. 调查月近期价格与地区汽油匹配（2026-10-10）

- **P/E/B：**20 人/月；在 CE 合成篮子和原 77 信号/新闻上比较原输入、加 USDA 乳品广告价+全国 EIA 汽油、州→PADD 区域汽油、同包置换汽油地区。不是个人实际交易价，食品仍全国报价。
- **规模与结果：**2021-05/06 两月四臂，共 160 次真实调用。全国近期价格使小样 Q9 中位数误差 0.793→0.754、2.801→2.349pp，W1 同向小降，但配对区间跨 0；Q8 没有相同改善。地区匹配对中位数较全国组近，但 W1 两月都比随机组略差。真人 IQR 5.20/5.42pp，匹配组仅 0.38/0.33pp。
- **状态：**全国近期价格保留为候选弱信号；地区汽油匹配未稳定改善，暂缓升级。仅针对这次汽油处理，不能概括为地区因素无效。
- **证据：**`docs/PRICE_CONTACT_EXPERIMENT_PLAN_20261010.md`、`docs/PRICE_CONTACT_EXPERIMENT_RECEIPT_20261010.md`、`docs/sources/sce_price_contact_20261010.json`、`outputs/sce_price_contact_trial_20261010_v1/trial_manifest.json`、`outputs/sce_price_contact_trial_20261010_v1/analysis/summary.json`。

### 11. 新闻候选标注与 50:50 新闻暴露

- **标注完成：**2026-10-11。5/6 月候选 1,140 篇，复用 163 条旧标签，对 977 篇新标注；按最终池得到每月 200/201 篇主要候选。后续四个时期 2,278 篇候选完成标注，286 次尝试、285 份有效回包，1 个断线批次在单独同意后补齐。标签完成不等于居民模拟运行。
- **实际曝光试验：**2021-05/06 各从 300 Core 中抽 48 人，shared/random/related-weighted 三组共 288 次模拟请求。related-weighted 是每次抽样的 50% 均匀概率 + 50% 相关权重概率混合，相关项权重 2，其余 1；并非“每人一半文章必须相关”。同人同篮子同数值 E，增加三条共同 A1 新闻和五条个人新闻，固定 DeepSeek、温度 0.5。
- **结果与状态：**5 月相关加权没有胜过随机；6 月 Q9 中位数误差比随机低 0.168pp，但两月配对区间都跨 0，分布距离近乎不变，人际 IQR 0.57/0.94pp 远小于真人 4.93/4.63。标注和抽取实现可用，新闻机制保留候选；不升级为已改善机制。四时期后来确有居民真实模拟：confidence 试验 768 次，以及两轮历史表示试验各 288 次，均沿用既有新闻输入；这些是分别改变信心或历史信息的试验，不是新闻消融。**未在四时期单独重复 shared/random/matched 新闻分配对照。**
- **证据：**`docs/literature/sce/news_selection/news_exposure_results_20261011.md`、`docs/literature/sce/news_selection/selection_trial_20261011.md`、`docs/literature/sce/news_selection/multiperiod_labels_20261011.md`、`docs/literature/sce/news_selection/news_exposure_results_20261011.json`、`docs/literature/sce/news_selection/multiperiod_labels_summary_20261011.json`、`studies/sce_inflation_expectations/news_exposure_trial.py`、`studies/sce_inflation_expectations/news_exposure_analysis.py`、`outputs/sce_news_exposure_analysis_20261011_v2/summary.json`、`outputs/sce_multiperiod_news_label_analysis_20261011_v1/summary.json`、`outputs/sce_confidence_trial_20261011_v1/trial_manifest.json`、`outputs/sce_lifetime_trial_20261012_v2/trial_manifest.json`、`outputs/sce_lifetime_text_trial_20261012_v1/trial_manifest.json`。

### 12. 美联储信心合成标签（2026-10-11/12）

- **P/E/B：**每期 48 人、2022-03/09、2023-03、2024-03；在同样的人口、CE 合成篮子、新闻 50:50、价格和问卷下，比较不加信心/增加来自全国 Gallup 波次分布的央行信心句。两臂都加同一段三句历史 Fed 政策摘要；因此本轮处理差异是额外 confidence 文字，不能把变化归因于共同政策摘要或整个政策信息包。每输入生成两遍；合成全国信心不是真实受访者态度。
- **规模与结果：**768 次 API 调用、767 份有效、1 份 Q9 合计 99% 原样保留；无重试。四期等权 Q9 中心 MAE 0.736→0.565pp（下降约 23.3%），但 W1 仅改善约 2.3%；模拟人际 IQR 0.72pp，真人约 5.78pp。八个中心改善区间中七个含 0。
- **状态：**预登记继续门槛通过，因此保留为机制候选；尚不升级正式 P，也不称恢复真人分布或全国预测。需与政策信息接触、问卷形状区别。
- **证据：**`docs/literature/sce/belief_proxies/confidence_trial_20261011.md`、`docs/literature/sce/belief_proxies/confidence_response_diagnostic_20261012.md`、`docs/literature/sce/belief_proxies/confidence_result_20261012.json`、`studies/sce_inflation_expectations/confidence_trial.py`、`studies/sce_inflation_expectations/confidence_analysis.py`、`outputs/sce_confidence_analysis_20261011_v2/summary.json`、`outputs/sce_confidence_response_diagnostic_20261012_v2/summary.json`。

### 13. 年龄与历史经历：详细数字试验

- **日期与 P/E/B：**2026-10-12；四时期 2022-03/09、2023-03、2024-03，每期 12 人；在原输入外增加共同历史或年龄对应数字历史，继承 Fed 信心、新闻分配、CE 份额、价格 E 和原问卷。不是人口全样本。
- **规模与结果：**24 个运行单元、288 次调用，287 个 Q9 有效。四期等权、两遍均值 Q9 中心误差：原输入 0.624pp、共同历史 0.733、年龄对应历史 0.969；年龄对应 W1 3.241，对比原输入 2.976。人际 IQR 0.499pp，真人 4.082。预登记门槛未通过。
- **状态：**未稳定改善、暂缓正式接入；保留来源时代库和负结果。12 人/期只作开发诊断，不能代替 300 Core 或全国结果。
- **证据：**`docs/literature/sce/heterogeneity_and_probability/lifetime_trial_20261012.md`、`docs/literature/sce/heterogeneity_and_probability/lifetime_trial_summary_20261012.json`、`studies/sce_inflation_expectations/lifetime_trial.py`、`outputs/sce_lifetime_trial_20261012_v2/trial_manifest.json`、`outputs/sce_lifetime_analysis_20261012_v1/public_summary.json`。

### 14. 年龄经历数字版与简要文字版表示

- **日期与 P/E/B：**2026-10-12 同期重跑；保持三组：原输入、年龄对应详细数字、年龄对应简要文字，仅替换历史经历块的表示；每期 12 人、两次生成、四时期。它不仅删数字，还改变篇幅、粒度、年龄提示，因此不算严格的单因素“只改数字”实验。
- **规模与结果：**另 288 次调用、287 个模拟 Q9 有效。中心误差原输入 0.534、数字 0.879、文字 0.742pp；文字比数字低约 15.6%，但仍差于原输入。W1 原输入 2.881、数字 3.191、文字 3.089；文字相对数字没有两遍一致改善，人际差异仍远低于真人。8 个中心差区间均含 0。
- **状态：**不升级正式配置；简要文字机制暂停、未采纳，试验产物仅保留作复核，不列为当前优先候选。不要把相对失败数字版的改善写成相对正式输入的成功。
- **证据：**`docs/literature/sce/heterogeneity_and_probability/lifetime_text_trial_20261012.md`、`docs/literature/sce/heterogeneity_and_probability/lifetime_text_trial_summary_20261012.json`、`studies/sce_inflation_expectations/lifetime_text_trial.py`、`outputs/sce_lifetime_text_trial_20261012_v1/trial_manifest.json`、`outputs/sce_lifetime_text_analysis_20261012_v1/public_summary.json`。

### 15. 等价措辞扰动与概率报告行为

- **措辞状态：**A/B/C 方案仍未冻结或获批；已有 6 人×3 模板的 18 份完整离线消息预览，manifest 登记 36 次候选分配，0 次新 API，且未接入 runner，故没有等价措辞真实交叉运行。旧 CE experience 的 `expression_shared` 臂确有 40 份真实回答（两月各20），但改了答题框架，不能当作本次同事实等价措辞证据。模板变动不称 SFT/RFT。
- **概率报告诊断：**2026-10-12 仅离线重算 106 月 SCE 描述统计和 767 份既有模型回答；没有新增 API，也未改原回答/计分。真实 Q9 每人非零档数中位数 4、模型约 8–10；约 59% 真人通缩档为 0、该模型样本为 0%。5%取整的群体中心平均移动约 0.182pp，10%约 0.493pp，说明表达精度可能影响终值，但没有证据指定真人应采用哪种风格。
- **状态：**等价措辞为仅准备；概率报告结果为测量诊断基础设施。依用户选择，暂不在提示词强制增加取整/零概率/报告风格属性；保留模型原生回答和敏感性说明。
- **证据：**`docs/literature/sce/heterogeneity_and_probability/prompt_variant_plan_20261012.md`、`docs/literature/sce/heterogeneity_and_probability/prompt_variation_practice_20261012.md`、`docs/literature/sce/heterogeneity_and_probability/user_choices_20261012.md`、`docs/literature/sce/heterogeneity_and_probability/age_reporting_followup_20261012.md`、`docs/literature/sce/heterogeneity_and_probability/age_reporting_summary_20261012.json`、`docs/reviews/20261012_mechanism_retro/prompt_frequency_audit.md`、`studies/sce_inflation_expectations/age_reporting_audit.py`、`outputs/sce_age_reporting_audit_20261012_v3/summary.json`、`outputs/sce_lifetime_trial_draft_20261012_v3/trial_manifest.json`、`outputs/sce-experience-trial-20261006T080038Z-594845/trial_manifest.json`。

### 16. 就业/收入宏观人口更新

- **日期与 P/E/B：**2026-10-08；新增 91 份 BLS 和 92 份 BEA 报告，2,473 条带发布时间的宏观观测版本；P 的就业/收入比例按每个上月末构建；没有模拟 B。
- **规模与结果：**37 个月滚动回测（2022-10..2025-10），0 次 LLM。新就业人口比 MAE 1.349pp，参与率联合 1.359；原失业率更新 1.323、旧画像 1.466。失业标签与原始样本没有稳定改善。收入多数组别/整体分布不如旧画像；个别高收入组有局部改善。
- **状态：**保留数据和研究代码，宏观更新未稳定改善、暂不接入正式 P；也尚未做固定 P/E 下对 Q8/Q9 行为的传导试验。
- **证据：**`docs/SCE_MACRO_PROFILE_EXTENSION_RECEIPT_20261008.md`、`docs/SCE_POPULATION_MACRO_UPDATE_SPEC_20261008.md`、`studies/sce_inflation_expectations/macro_profile_sources.py`、`studies/sce_inflation_expectations/macro_profile_extension.py`、`outputs/sce_macro_profile_sources_20261008_v7/summary.json`、`outputs/sce_macro_profile_backtest_20261008_v1/summary.json`。

## 口径与状态冲突

1. **小样、全国和四时期不得混排。** 2021-05/06 每月 300 Core 是主实验；5/6 月 20 或 50 人、四时期每期 12 或 48 人是机制筛查；80 月全国 headline 和 70 月微观基线是离线统计历史基准，早期 60 月数值另作为旧窗口记录。即便数值同叫 MAE/W1，也须按样本、时期覆盖、Q8/Q9、权重、计分版本和共同有效掩码区分。
2. **不把相对失败版改善当成采纳。**文字经历相对详细数字经历好 15.6%，但比同期原输入差；Fed 中心信号虽通过继续研究门槛，分布仍不够；新闻只在 6 月有有限中心信号；全国价格配对区间跨 0。上述均不是正式配置升级。
3. **当前文档有过期状态文字。**`studies/sce_inflation_expectations/population/README.md`、`studies/sce_inflation_expectations/environment/README.md`、`studies/sce_inflation_expectations/simulation/README.md`、`studies/sce_inflation_expectations/trajectory/README.md` 和 `studies/sce_inflation_expectations/reports/README.md` 仍写“待实现/无模拟结果”等模板状态；源码和 10 月运行目录已证明部分职责实现/真实运行。`studies/sce_inflation_expectations/README.md` 还写真实 LLM 等 key/预算确认，属于 10-03 入口状态，不代表 10-05 后的实跑。未修改这些公共说明，交由总复盘者决定如何收敛。
4. **计分器名称需始终带“近似”。**冻住版本便于同口径比较，不意味着纽约联储官方 Beta 尾部/空档分支已完全复现。官方派生 Q9 headline 与项目重算样本不得直接拼成一列挑成绩。
5. **模型身份和时间边界不完整。**`deepseek-flash` 等是回包服务标签；LLaMA/Qwen 结果另有固定服务路由，但训练截止/不可变权重并不齐备。日期提示与严格环境 E 都不能排除模型参数记忆。
6. **准备包不等于运行。**SCE 原生 QSP5 `v4` 只到真实调用前，明确外发许可未核验；全年四模型 14,400 请求只准备，未批准/未执行；四时期居民模拟已实际带入新闻输入，但尚未单独重复 shared/random/matched 新闻消融；等价措辞有离线候选消息，未接 runner、未真实运行。
7. **受保护改动。**`docs/sources/sol_handoff_protected_files_20261010.json` 所列 15 份用户/Kimi 待审文件保持只读，本任务没有改写、还原或提交它们，也没有改公共配置/运行文件。

## 一句话状态表

- **已采纳基础设施：**共同冻结的项目近似计分、P/E 白名单检查、本地 scripted/LLM runner、run_id 轨迹与费用/哈希审计、Core/Normal 的可复算扩展、统一离线评价、80 月全国与 70 月微观离线基线（早期60月版本另存）。
- **保留候选：**近期全国零售价格、新闻相关加权、央行信心文本；SCE 原生支出关联仅作为本地研究候选，外发模拟待审批。都需要更强留出或样本扩展，当前不进正式 P/E/B。简要文字经历机制已暂停、未采纳，产物保留作审计。
- **未稳定改善、暂缓：**CE 篮子/信息排序、Q1、通道匹配、地区汽油匹配、详细年龄经历、宏观就业收入人口更新、Qwen/LLaMA 扩模。
- **仅准备/未运行：**真实 SCE 篮子 LLM 外发、在四时期单独重复 shared/random/matched 新闻消融、2021 全年四模型 14,400 请求、三模板等价措辞交叉试验。四时期本身已在 confidence 与两轮 history 真实模拟中包含新闻输入。
