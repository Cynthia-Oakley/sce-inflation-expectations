# Kimi 信念动态线：进度与预登记

2026-10-13。状态：已启动。本文先登记输入、有效集、分析计划与经验更新基线设计；新基线结果在此登记冻结之前不得查看（B0 延续的既有汇总统计除外，见"既有暴露"）。

## 1. 研究问题与假设

问题：真实居民如何保留和调整上期一年期通胀预期，现有 LLM 小试在哪里偏离，低参数经验更新器能做到什么。

待检验的工作假设（来自既有证据，非结论）：

- H1 均值回归：真实个人的更新方向与其上期相对当月共同水平的位置相关（高于中位数者倾向下调）。
- H2 不确定性调节：上期个人不确定度（Q9_iqr）越高，本期修正幅度越大（Armantier et al. SR543 的方向性预期，本数据仅作描述验证）。
- H3 LLM 压缩：现有 LLM 在相同先验输入下的更新幅度与跨人保留度显著低于真人（既有斜率 0.134 vs 0.495，仅为四期 12 人描述线索，本轮用同口径补充）。

不以人为增加方差为成功；不把描述性斜率当因果更新率。

## 2. 输入与版本

| 输入 | 路径 | 校验 |
|---|---|---|
| 真实微观缓存 | `outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet` | sha256 `86414d57…dc1b`，与 `summary_public.json` 记录一致（已复算） |
| 上游官方工作簿 | 三份 xlsx，分区 201701–202510 | 哈希见 `docs/literature/sce/factual_mechanisms_20261013/summary_public.json` |
| 先验试验配对评价 | `outputs/sce_prior_analysis_20261013_v1/paired_evaluation_private.json`（384 条） | 现场读 schema 后复用 |
| 先验传递诊断 | `outputs/sce_prior_transfer_diagnostic_20261013_v1/summary.json` | 同上 |
| 相邻匹配参考实现 | `studies/sce_inflation_expectations/factual_mechanism_audit.py`（`adjacent_pairs`，严格日历月） | 只读复用，不重下载 |
| 冻结计分器 | `studies/sce_inflation_expectations/scoring/sce_q9_frozen.py` | provenance live==pinned 运行时断言 |

个体记录只留在本地 `outputs/` 新目录；公开交付不含逐人行。

## 3. 有效集

- 真人面板：严格相邻日历月配对（漏访不算相邻），两期 Q9 十档均合法（0–100、合计 100）且 weight>0。预期复现 103,630 对 / 106 月（2017-02 起），与 `summary_public.json` 对账作为程序正确性验收。
- LLM 同口径：四期（2022-03/09、2023-03、2024-03）×12 人×两遍的三臂回答；真人侧同一人月的十档用**同一冻结计分器**重算中心，不用官方 Q9_mean 与近似值混比。
- 预先确定的人口分组（不在看结果后增删）：年龄三档（Under 40 / 40 to 60 / Over 60）、教育（College / 非 College）、收入（<50k / 50–100k / >100k）、numeracy（High / Low）。

## 4. 分析计划（零 API）

**A. 真人更新事实**（`scripts/analyze_sce_belief_dynamics.py`）：

1. Δ=Q9 中心_t − 中心_{t−1} 的分布：逐月与汇总的加权分位数（5/25/50/75/95）、|Δ|≤0.5pp 占比、方向分裂比例；与既有 `share_absolute_change_at_most_0_5pp` 对账。
2. 跨期排序：逐月 Spearman（复现均值≈0.636），另补 lag-2（连续三月子样本）作持续性参考，注明 11 个月预测窗口重叠带来的机械相关。
3. 条件关系（H1/H2）：按上期"月内去中心位置"分十档看平均 Δ（均值回归曲线）；按上期 Q9_iqr 分四档看平均 |Δ|（不确定度—修正幅度）。
4. 分组：第 3 节四组分别报 1–3 的核心量；每组只作描述，不做显著性断言。
5. 口径说明随结果给出：相邻覆盖约 81–86% 且以回访者为条件；当前权重仅对当期截面有效；轮换与入组影响月份统计。

**B. LLM 同口径比较**（同一脚本第二段）：

1. 三臂（无先验/本人先验/置换先验）与"本人原样延续"免费基线，真人同批对照。
2. 指标：Δ 分布 W1（模型 vs 真人同月同人配对）、更新方向比例、跨人中心 IQR、本人 vs 置换的输入差→输出差弹性（既有：输入差 4.90pp→输出差 0.77pp，复核并分时期）。
3. 两次生成先逐次报告，再按既有做法平均；不冒充独立样本。

## 5. 经验更新基线：预登记（先写设计，后看结果）

**共同设定**：逐人逐月预测同一回访者的当月 Q9 中心；只允许使用 (a) 本人上期中心与上期不确定度，(b) 当月与上月真实截面的共同统计量（A 线诊断，明确标注非 PIT B）。不注入随机噪声。

**候选（低参数）**：

- B0 原样延续：ŷ_t = y_{t−1}。必要对照。
- B1 共同平移：ŷ_t = y_{t−1} + (m̃_t − m̃_{t−1})，m̃ 为当月加权中位数。0 参数。
- B2 部分调整：ŷ_t = (1−λ)·y_{t−1} + λ·m̃_t。1 参数。
- B3 去中心回弹：ŷ_t = m̃_t + ρ·(y_{t−1} − m̃_{t−1})。1 参数。
- B4（仅当 B2/B3 在训练期显示稳定结构后才估计）：不确定度调节 ρ_i = ρ0·exp(−ρ1·IQR_{t−1})，检验 H2 是否有预测增量；若训练期 H2 方向不成立则跳过并记录。

**划分**：训练 2017-02..2021-12（59 个月），验证 2022-01..2025-10（46 个月），按时间向前。参数（λ、ρ、B4 的 ρ0/ρ1）只在训练月用逐月截面内损失（预测 Δ 与真实 Δ 的加权 MAE）估计，验证月一次性评价。

**主指标**（按任务书，中心/W1 在前）：逐月"预测 Δ 分布 vs 真实 Δ 分布"的 W1 均值、逐月预测中心截面 vs 真实截面的 W1 均值、相邻秩相关（预测值与真实值的同月 Spearman）、逐月预测截面中位数与真实中位数的 MAE；逐人 MAE 仅辅助。所有指标对 B0–B4 同口径报告，训练/验证分列。

**既有暴露声明**：`summary_public.json` 的全期汇总（含 B0 的逐月 own_previous_mae）与 10-13 复盘已在启动前看过，开发期统计用于定位问题；本轮不声称全项目盲测。B1–B4 的**结果数值**在本登记之前未计算。

**解释边界**：A 线用了当月真实共同统计量，评价的是"给定共同水平后的个人更新规则"，不能解释为 B 线预测能力；B 线版本须以可得共同序列替换 m̃_t，另行登记。

## 6. 当前步骤与下一步

- [x] 开工检查：git status（15 份待审改动保留，不还原不混入提交）；parquet 哈希复算一致。
- [x] 复核既有相邻匹配实现与先验试验 schema；官方 Q9_mean 与冻结近似值不混比（LLM 侧统一重算）。
- [x] 本进度与基线预登记。
- [x] 实现 `studies/sce_inflation_expectations/belief_dynamics/` + 两个入口脚本 + `tests/test_sce_belief_dynamics*.py`（13/13；全量 495 通过，1 个无关既有失败）。
- [x] 运行 A/B 分析，输出 `outputs/sce_belief_dynamics_20261013_v1/`（验收：106,351/103,630 对精确复现）。
- [x] 按第 5 节跑基线，训练/验证分列（B2 λ=0.30、B3 ρ=0.70；B4 门控触发但 ρ1=0）。
- [x] 写 `kimi_results.md` 与无个人行 `kimi_summary.json`；结论分为"支持显式个人状态/更新规则"与"不支持"两类。

文件边界：新源码仅在上述预留路径；公共任务板/NEXT_ACTIONS 由 Codex 整合；提交 scoped add，与另一端 Git 操作串行。零付费 API、不读密钥、不发微观数据。

## 7. 同日后续进展（10-13 晚，索引）

- 汇合设计草案：`kimi_joint_design_draft.md`（2×2 更新×报告；只需 1 个新 LLM 批次）。
- Codex 互评响应：四点措辞收紧已落回 `kimi_results.md`（不改数字与主线结论）。
- 第二轮锚规则（并入 Codex"个人基准"建议）：预登记 `kimi_anchor_prereg.md` → 结果 `kimi_anchor_results.md`；个人锚 λ=0.50，截面损失收复约七成，按预登记标准记未通过。
- U1 输入规范 v1：`kimi_u1_input_spec.md`（待汇合评审后转正式冻结）。
- U1a 离线准备 v1：新增 `belief_state_preparation.py` + `scripts/prepare_sce_u1a_state.py` + `tests/test_sce_belief_state_preparation.py`（7/7），输出 `outputs/sce_u1a_state_preparation_20261013_v1/`（48/48 人月、0 弃例、锚覆盖 87.5%、0 次 API）。提示词实物见该目录 `preview_sample.txt`。完整批次等待汇合互检与用户最终放行。
- Codex 候选 2（程序报告映射）互检：8 项登记哈希复算一致、另目录完整复跑数值零差异（仅时间戳不同）、0 新 API；意见已回（统一 10% 取整是重要低成本参照，但不证明身份效应为零）。
- Codex 第二轮互检（`codex_kimi_u1_review_20261013.md`）响应：①`kimi_results.md`/`kimi_anchor_results.md` 四处措辞收紧（H1/H2 改描述关系、同质化改工作解释、旧 0.3 标旧候选、"七成"改超额 W1 距离并删未检验归因）；②U1 规范升 v2——基座改回 U0 完整上期回答（Q8 点值与 Q9 拟合均值不再混称）、拆 U1s/U1g 两臂、四分位改"约 50% 概率区间"、假设句标明待检验且无锚者（6/48）关闭、取消 0.30 自动触发改汇合评审决策、修正 48 人月/96/192 计数、分位数主口径左逆经验 CDF；③代码同步改造并修复 summary 自哈希（manifest.json 最后单独写入），新增对已执行试验提示的逐字断言；输出新目录 `outputs/sce_u1_state_preparation_20261013_v2/`（两臂各 48/48、0 弃例、锚覆盖 87.5%、6 例无锚者两臂提示相同、0 次 API），v1 目录保留不动。测试 29/29。实物：`preview_sample_state.txt`、`preview_sample_guided.txt`。

## 8. U1 真实批次执行与评价完成（10-14）

**执行链全部完成。** Codex 对 v2 准备包的独立只读审计通过（`outputs/sce_u1_preparation_audit_20261014_v2/`：48 例、96 提示、状态数值差 0、基座逐字保持、当期/未来扰动检查通过；状态=已通过准备审计、非运行验收）。运行入口实现：`studies/sce_inflation_expectations/u1_state_experiment.py`（引擎决策类，三级哈希链：基座→U0→U1 逐级断言）、`u1_state_trial.py`（prepare/dry_run/execute）、`scripts/run_sce_u1_trial.py`、`scripts/export_sce_u1_answers.py`（按 Codex 接入规范导出）；`scripts/run_sce_local.py` 加 U1 分支与 execution_purpose，`__init__.py` 注册。测试 72/72（含新增 11 项 U1 定向测试）。

**离线验收**：prepare 重建 8 个模拟配置并对已审计准备包逐字断言（成本上界 $0.631、作业上限合计 $0.68 < $1.00 冻结帽）；scripted 干跑 8/8 单元 exit 0、0 次 API。首次 prepare（v1 目录）因 `--prompt-version` choices 未收录新版本失败，修后按不重覆盖约定启用 v2 目录重备，v1 保留。

**真实运行**：`outputs/sce_u1_trial_20261014_v2/`，16 单元（4 月×2 臂×2 遍）192 次 DeepSeek 请求全部成功、0 错误 0 重试、返回模型全为 deepseek-flash；自记峰值费率估算 **$0.144671**（非厂商账单），授权引语与发送范围记入 trial_manifest。导出 `outputs/sce_u1_evaluation_20261014_v1/`：192 行全名册、q8/q9 零缺失。

**评价**（Codex 评价器 + 协议 v2，`outputs/sce_behavior_comparison_u1_20261014_v1/`，0 新 API）。Q9 全名册 47 人月共同样本聚合：

| 条件 | 中心MAE | 截面W1 | 变化W1 | 人际IQR | 秩相关 |
|---|---|---|---|---|---|
| own_previous (U0) | 1.318 | 3.102 | 1.786 | 1.060 | 0.344 |
| own_state (U1s) | 1.141 | 2.664 | 1.738 | 1.494 | 0.385 |
| own_state_guided (U1g) | 1.391 | 2.670 | 1.733 | 1.711 | 0.501 |
| copy_previous 基线 | 0.850 | 1.704 | 2.955 | 4.706 | 0.712 |
| history_anchor_half 基线 | 0.974 | 1.435 | 2.224 | 4.445 | 0.716 |

（真人 IQR 6.249。）配对区间：U1s−U0 截面 W1 −0.438pp [−0.659,−0.120] 不跨 0（分布形状显著更近真人）；中心 MAE −0.177 [−0.558,+0.242] 跨 0（方向改善、幅度不确定）；变化 W1 −0.048 跨 0。U1g−U1s 三主指标区间均跨 0（假设句无可辨识增量）。两臂对两个过去信息基线的中心/W1 差仍不利或跨 0——**未超过简单方法**。Q8：U1s/U1g MAE 1.775/1.612 对 U0 2.000，copy_previous 1.250 仍最优。**项目筛选门槛：两臂均未通过**（仅 repeat 2 过、repeat 1 未过；pilot_signal=false），不升级主机制。解释边界：own_state 对照含"额外本人历史信息"，非纯摘要效应；U1g−U1s 才是假设句增量；四期 12 人、开发月份，不能外推全国或 B 线。

**下一步候选**（待与 Codex 汇合）：状态摘要的 W1 收益值得保留为候选；人际差异仍只有真人约 1/4，同质化主瓶颈未解；按复盘方向，下一步优先"思维方式/更新行为"层而非继续堆信息。公共任务板/NEXT_ACTIONS 由 Codex 整合；本轮新增源码与文档待 scoped 提交（等用户/Codex 串行安排）。

---

## 2026-10-19 仓库治理：设计总纲与归档提案（零 API、无实验）

用户提出六项工程问题（主文档/计划清单/实验台账/复用/路径膨胀/SocioVerse 贴合度）。完成仓库盘点（docs 根 122 条目/286 md、scripts 247 个、outputs 430 目录、docs 根 17 份历史 PLAN），逐项回答用户后，按指示**只新增、不移动、不删除**：

1. **`docs/DESIGN.md`（v1 草案）**：项目设计唯一总纲——研究对象（SCE Q8/Q9）、A/B 两线契约摘要、当前参考配置、评价口径与基线、当前状态（12 期 MAE 0.459 vs 照抄 0.239、IQR 2.42 vs 真人 5.06）、工程架构、研究纪律、文档地图。内容依据 PROJECT_CHARTER / A_B_LINE_CONTRACTS / CURRENT_SIMULATION_CONFIGURATION 整理，待用户与 Codex 评审后转正。
2. **`docs/REPO_HYGIENE_PROPOSAL_20261019.md`（提案，未执行）**：
   - docs 归档方案：根目录保留约 15 份"当前有效层"，90+ 份历史计划/运行卡/回执/云端试点/模型对比系列移入 `docs/archive/2026-10/`；配套规则（新 PLAN 进 workstream、NEXT_ACTIONS 头部定期剪切、EXPERIMENT_STATUS 去日期化）。
   - 分析脚本复用三层方案：① scripts/README.md 索引（零风险立即可做）；② 公共计算收敛到 evaluation/ + 新 analysis_utils.py，新脚本禁止重写 MAE/W1/权重/配对区间；③ 引用扫描后归档一次性脚本。明确不动在册入口与 tests 覆盖的脚本、不重组 studies 平铺模块。
   - 执行步骤（引用扫描→git mv 分批→更新结构文档→跑 pytest）与 4 个待决策点。

另：盘点 Codex 10/17–10/19 工作并向用户汇报（扩大验证 0.459/0.239、心理/处境/新闻量/新闻分配多组阴性结果、ATUS 采购角色菜单已备待运行）。注意：NEXT_ACTIONS 任务板称差异化新闻量 3456 请求批次"正在运行"，但 `outputs/sce_news_breadth_evaluation_20261019_v1` 评价已生成、系统无相关进程，疑似已完成而状态未更新——已提醒用户与 Codex 同步时核实。

未改动任何现有文件、未提交、无付费调用。下一步等用户/Codex 对两份文档的评审意见。

---

## 2026-10-19 真人预期更新六条微观事实（F1–F6，零 API/零网络）

用户要求把"真人如何更新预期"从口头结论升级为有回归与图表佐证的系统分析。交付 `docs/workstreams/20261019_updating_facts/README.md`（教学式，逐事实：问题→方法→数字→图→机制含义→caveat + 参数汇总表 + 与既有工作关系）。

- 数据：`outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet`（sha256 复算一致），与 20261013 线同一有效集口径（103,630 相邻对）；CPI 事后真值用本地 ALFRED CPIAUCNS vintage 2024-03-12，故 F3a 仅覆盖预测月 2017-02..2023-02（74,952 对，报告已醒目标注）。
- 关键数字：F1 惰性 |Δ|=0 占 13.8%/15.4%（unweighted/weighted），十档完全相同 13.7%——不动≈整份复投；F2 变动者 Δ q05/q95≈±8pp、超额峰度 +20~24（高斯不可用）；F3a CG 式回归斜率 **−0.483**（聚类 SE 0.0032，逐年 −0.46..−0.50）——与专业预测者文献正斜率相反，本样本呈过度反应（含测量误差/机械耦合成分，标为描述性）；F3b OLS −0.43 与 20261013 复算一致，t−2 IV 塌缩至 −0.05，建议校准取 |β|∈[0.05,0.43] 敏感性区间；F4 非零格 81.1% 为 5 的倍数、52.2% 为 10 的倍数；F5 between 方差占 52.5%、持续度 0.573、split-half 0.852；F6 k=4 类型表：主流型 60.3%(p=.92,m=1.8)、高频中幅偏高 19.8%、低频小幅 14.6%、通胀担忧型 5.4%(m=13.0,ℓ=14.4)。
- 产出（全部新建）：`studies/sce_inflation_expectations/belief_dynamics/updating_facts.py`、`scripts/analyze_sce_updating_facts.py`（拒绝覆盖）、`outputs/sce_updating_facts_20261019_v1/`（summary+json 6 图+per-person 私有 parquet）、`tests/test_sce_updating_facts.py`（11/11 通过；全量 876 passed，唯一失败为既有 test_extract_cpi_components PDF 归档问题，与本次无关）。
- 用途：F1/F2/F3/F6 直接给出两阶段"改不改→改多少"更新机制与类型分配表的校准参数；F4 支撑与 Codex 表达线汇合的报告层后处理；F5 支撑持久个人成分。待与 Codex 讨论采纳。

## 2026-10-20 剧烈变化期观测指标（regime-conditional skill）——设计与真实数据可行性分析

- 起因：用户转达学长建议——模型总误差虽不敌持续性基准，但可能在预期剧烈变化期战胜基准，需单独设观测指标。此想法与 10/14 讨论中搁置的猜想一致。
- 零 API 分析（真实 SCE reference cache，2017-01..2025-10，77 个有效月；修复了 weighted median 未剔除 NaN 导致的假跳变）：
  - 机制定义（ex-post 诊断口径）：|Δ 全国加权中位数（Q9_mean）| ≥ 0.2pp → 23/77 个月（30%）为剧烈变化月。
  - 持续性基准（上月=本月）误差：平稳月均值 0.071pp vs 剧烈月 0.368pp（5.2 倍）；**剧烈月贡献了全部持续性误差的 76.8%**。
  - 个体层面 |Δ Q9_mean| 中位数：平稳月 1.10pp vs 剧烈月 1.31pp（差异小）——机制效应主要体现在汇总中位数层面，个体噪声全年都大。
  - 主窗口 2021-01..12 含 5 个剧烈月（05/06/08/10/11，|Δmed| 0.34–0.80pp），与 CPI 同比跳升同步——主窗口机制覆盖充足。
  - ex-ante 替代口径：|Δ CPI 同比|（发布滞后下 t 期可得 t−2）与 ex-post 机制月在 2021 年高度重合，可作为 B 线无前视版本。
- 指标设计（待与 Codex 对齐后写入评价层）：2×2 表（平稳/剧烈 × 模型/持续性基准）的逐人 MAE 与汇总 MAE + 剧烈月胜率 + 机制技能值 S = MAE_pers − MAE_model（剧烈月内）。诚实标注：剧烈月里任何"方向正确、不超调 2 倍"的模型都机械性优于持续性，故该指标度量的是**方向响应能力**，须与平稳月表现同报，不能单独宣称胜利。
- 注意：现有模拟只覆盖 2021-05..08 约 4 个月 × 12 人，样本太薄；该指标在 12 个月主窗口正式运行后才有统计意义。模拟侧初步数值建议用 Codex 的接入规范导出后统一计算（避免两边各算各的）。

## 2026-10-20 离线实验分析面板 v0（实现 Codex 设计草案）

- 用户要求按 Codex 的 `docs/workstreams/20261020_procurement/structured_analysis_panel_design.md` 落地面板：模块化、每轮实验后一条命令更新、零 API/零 token。
- 实现（commit c046f48，未 push）：`studies/sce_inflation_expectations/panel/`（adapters/regimes/sections/render 四模块 + 插件式 SECTION_PLUGINS）、`scripts/build_sce_experiment_panel.py`、`tests/test_sce_experiment_panel.py`（10 项全绿）。
- 自动发现 `outputs/*_evaluation_*/cases_private.json`：19 批中 14 批同契约全部接入（REGISTRY 已配 3 批中文名，其余标"未登记"），5 批旧契约显式跳过并注明原因。新实验只要评价层产出同契约缓存，重跑一条命令即入面板。
- 六固定节：总览（+同支持照抄基线）、逐月与剧烈变化期（2×2 + 技能值 S，机制标签来自 sha256 钉死的真值序列 |Δmed|≥0.2pp，页面标注事后口径与机械占优警示）、人群网格（学历×在职六格+独立切片，n<10 灰显）、先验四档与更新（真值分组明确标注）、回答结构（跨人 std、堆整、两遍噪声 vs 人际差异）、质量与元数据（费用/归一化/比较资格提示）。
- 隐私：HTML 仅嵌聚合数据（已 grep 验证无 userid/逐人记录/原始十档）；瘦记录存 panel_data_private.json（27.5MB，本地私有，未提交）。
- 数值抽查：reference 批逐人 MAE 3.4675 vs 其 summary.json 3.4685（−0.001pp，口径差异已说明）；照抄基线 3.0816 vs 3.0739；跨人 W1 2.4292 vs 2.4337。
- 产物：docs/reports/experiment_panel/index.html（849KB，file:// 直接打开，未提交）。v0 未覆盖项见子代理完成报告（机制专用页、逐月信息环境列、自动摘要、导出等），可在插件框架内后续补。

## 2026-10-21 实验面板 v1 三批改造完成（按 experiment_panel_v1_plan.md）

- 依据：用户与 Codex 的 v1 方案 + 统计审阅（experiment_panel_review_20261020.md）。实现由子代理完成，我逐批核验。
- 第一批（27d787a）统计修正：主指标改回群体中位数MAE（十二期复现 0.459191pp 与冻结报告精确一致）；个人MAE/个人绝对误差中位数分列；共同支持主表（Qwen 552、新闻 571、Q8 独立 554/2297）+敏感性表；人×月 Kish ESS（1383.1，修正旧值 2781.9）；重复方差分解复用 temperature.py；实验目录+登记表（19 批分区/机制组/父子链，旧契约 5 批显式未接入）；私有逐人文件移入 git 忽略的 outputs/sce_experiment_panel_private/。
- 第二批（057fe08）可读性：角色四色+线型+标记三重编码（真人黑方/对照蓝圆/候选橙三角/基线灰虚菱）；概览四读数卡+逐月中心/误差差额两主图；三条规则化自动事实（无 LLM）；五页签+hash 可分享导航；Q8 不适用区明示不挂 Q9 牌。
- 第三批（bbf34d0）下钻：月×格点击→真人/模型/基线加权 CDF+分位区间图（注明非箱线图）；先验四档条件均值点线图；组内/组间方差分解；输入差异清单（插件式，不可得标"未提供"）；质量漏斗+月×臂缺失热力+费用四分类；聚合 CSV 与 SVG/PNG 导出。
- 验证：pytest 23 项全绿；node DOM-shim 24 项运行时检查全过；我另用内置浏览器起临时本地服务实证：目录页、概览四卡（0.46pp 主指标、照抄 0.24pp 同列）、逐月×逐遍明细表（剧烈月黄底）、质量页支持口径——截图留存于会话。产物 docs/reports/experiment_panel/index.html（3.07MB，未提交）。
- 遗留：逐月 CPI/食品数值无结构化输入快照（标"未提供"）；prompt 级臂间字段 diff 未接入；漏斗部分环节受缓存字段限制标"未接入"；灰阶打印未实体验证。全部提交在 docs/deepseek-reuse-20261008 本地分支，未 push。

## 2026-10-21 实验面板 v1.1：Codex 定向验收四组问题修复（commit 43665ee）

- 起因：Codex 对 v1 三批的定向验收（experiment_panel_review_20261020.md 末尾 2026-10-21 节）确认主要汇总成绩已对齐冻结值，但列出四组必须先修的问题。我逐条对照源码核实属实后实施修复（子代理执行，我核验）。
- P1 差额图符号反转：多臂时 JS 端误算"对照−候选"却标注"候选−对照"，Qwen 2021-09 的 −0.17pp 改善被画成 +0.17。修复为差额序列移回 Python 端（符合 render.py "数字全在 Python 算"的模块约定），每臂预计算 diffs_vs_control / diffs_vs_persist，前端只消费。实测页面 21-09 柱现为 −0.17（向下=改善）。
- P2-1 独立人数：`_pid` 含月份导致"独立人数"实际等于人×月数。新增 `_uid` 跨月身份键（下划线前缀，不进公开产物），三批真实独立人数修正为 2128/562/543（人×月 2284/571/552 不变）。
- P2-2 下钻 ESS：月×格内先合并本人重复权重再算 Kish ESS（12 人×2 遍确定性例：ESS 24→12）；模型 CDF/分位明确命名"多遍混合分布（repeat-pooled）"。
- P2-3 无共同支持时删除"回退第一臂"，主表显示"无法作主比较"并保留各臂敏感性表；Q8 汇总月份改用 Q8 自身支持（不再沿用 Q9 月份列表）。
- P2-4 方差分解改为同权重加总分解（total=between+within 精确成立，测试容差 1e-9，新增 total_var_pp2）；自动事实规则 2 措辞收紧为"仅误差大小差异，不推断压缩方向"并附两档带符号偏差证据，每条事实标注"（基于臂 X）"。
- 阅读体验：实验目录在选择实验后折叠、详情进入视口，"☰ 实验目录"恢复原位（catalogScroll 此前保存但从未使用）；26 个 arm 名全部接入中文标签（registry.ARM_LABELS，实际键名照实映射）。
- 可复算输出：构建脚本原子发布 index.html + panel_aggregate_v1.json（完整聚合）+ build_receipt.json（stats_version=panel-stats-v1.1、模块与源批次 sha256、python 版本）；新增报告目录 README。
- 验证：pytest 30 项全绿（新增 7 项：差额符号×2、独立人数、drill ESS、空支持、Q8 月份独立、方差恒等式、事实措辞/回执）；十二期中心 MAE 仍精确等于 0.4591912957196014；我另用 kimi-webbridge 在用户 Chrome 实测：目录折叠/恢复、Qwen 差额图 −0.17 方向、中文 arm 名、事实臂标注——截图留存于会话。
- 遗留（Codex 验收中已标注、本次未做）：逐月 CPI/食品数值的结构化输入快照、prompt 级臂间 diff、按批缓存与失败隔离；新批次出现新 arm 名需人工补登记。

## 2026-10-21 面板逐月表新增「全样本|Δ中位|」列（commit 7b30d7b）

- 起因：用户发现剧烈月的"照抄中心MAE"并不比平稳月大（如 2023-12 标剧烈但照抄 MAE≈0），质疑标签口径。核实后确认两个量口径不同：机制标签来自全样本真值序列（约1100–1300人/月、连续日历月差分，标签须跨批次固定一致）；照抄 MAE 来自该批约 95 人抽样子样本，n≈95 时中位标准误约 0.7pp，单月可对不上。用户确认后要求加列消歧。
- 改动：逐月×逐遍明细表在"机制"后新增「全样本|Δ中位|」列（数值来自 sha256 钉死的全样本查找表，系列首月显示"未提供"），guide 文字说明两口径差异与子样本噪声量级；测试断言新列数值透传（30 项全绿）。
- 验证：重建面板后 Qwen 批六个月全样本 |Δ| = 0.02/0.13/0.20(边界)/0.35/0.13/0.45，与标签一致；用户 Chrome 实测截图确认。生成 HTML 未提交（惯例）。

## 2026-10-21 官方MCP reason通道探测（结论：不可行）

- 起因：用户问"官方GPT只回单选"是否属实、能否用reason字段携带十档概率。先核实：`platform_gpt_requirements.md`已有10-20三轮实测记录，限制定位在托管问卷工具封装层（schema仅question/options），非模型能力、非框架限制。
- 执行：platform_survey_pilot.py新增reason_channel_q9变体（题干指令模型在reason中列十个逗号分隔概率），9项离线测试通过；用户批准后1人×1次调用（估$0.004平台Sim额度，累计预留$0.048/$0.10）。
- 结果：reason为模板式单句辩护，仅含数字"12"，枚举指令未遵循；与10-20试测reason几乎同构，提示reason形态由服务端内部提示主导。运行包outputs/sce_platform_reason_channel_q9_20261021_v1/含inspection.json。
- 建议：停止reason方向措辞试探，转正式问询平台（草稿在platform_gpt_requirements.md）；主线继续走本地引擎+OpenRouter/DeepSeek。

## 2026-10-21 全时段数据交付阶段0–2（kimi_data_contract_v2.md）

- 阶段0：实证SCE微观截止2025-10（重下latest与9-28件同哈希）、headline至2026-09；补NYT 2018-12..2019-11缓存；确认BLS ref 2025-10因停摆永久取消（BLS/Reuters来源）；补抓ref 2018-06..2018-12共14份首发PDF（httpx+完整浏览器头过Akamai）；新脚本backfill_bls_release_manifests.py补齐22个月manifest（embargo行重验，2018-10 CPI自定义字体仅部分验证）。
- 阶段1：scripts/build_sce_fullperiod_coverage.py → outputs/sce_fullperiod_data_20261021_v1/coverage.json（93月，82 ready+11 ready_no_micro，内置10项验收过）。实证：tenure恒+1零例外；新闻窗口=M-1全月+M月1日至as_of；标签id须用build_news_pool口径；新闻LLM标签总缺口43,512篇待付费审批。
- 阶段2：三样例月（201906/202303/202606）8类文件全交付，tests/test_sce_fullperiod_data.py 15项全绿；供体池严格早于目标月（4978/11796人）；合成人口PPS整行保联合结构；userid零泄漏扫描通过。
- 重建2019-06环境至11/11历史（新增table_a_pct解析器与handoff护栏，不可抽值不猜）。
- 已知缺口：components_cpi覆盖2020-01..2021-11+2026-04..08（批量阶段需补抽）；EIA汽油2018-12才起步；微观published_at未验证；标签付费待批。
- 记录：docs/workstreams/20261021_fullperiod/kimi_delivery_phase012_20261021.md；NEXT_ACTIONS已更新。批量物化待Codex对齐样例。

## 2026-10-22 新闻标签口径冻结与管线选型（接 10-21 全时段交付）

- 用户冻结精简口径：decision 4值 + topics 旧6值 + scope 旧7值，砍 claim_type/reason_zh/evidence_snippet（省输出token）。
- 试点（$0.10，1868篇全齐）：V3.2 精简提示词与旧标签 decision 一致率仅 74%，人工抽查发现系统性过严（英国央行加息被 exclude）；v2.1 加两条澄清后复测 74.7%——澄清穿不透 V3.2。
- 决定性对照（用户提议）：换回原打标模型 deepseek-flash（官方端点）+ 同一精简提示词，一致率 87.7%/86.8%/80.7% 全达标 → 漂移来自模型而非砍字段。打标模型与模拟模型解耦。
- 用户决定：全量补标 43,512 篇暂缓。管线就绪（scripts/label_sce_news_pool.py，flash variant，$0.08 试点验证过），随时可启动，预估 ≤$4.5。
- 提交：340b739（管线+测试）、ef631c6（flash 变体）、4e7b77c（一致性结论记录）。文档 docs/workstreams/20261021_fullperiod/news_label_slim_pilot_20261021.md。

## 2026-10-22 下午 落实 Codex 对标签管线三点复审

- 真实缺口重算：跨月去重后待标 30,274 篇（非 43,512；唯一候选 38,903，已有标签 8,725），预估约 $2。
- 兼容层 studies/sce_inflation_expectations/news_label_compat.py + 离线验证 scripts/verify_sce_news_label_compat.py：2022-03（legacy7）与 2019-06（slim4）各组装新闻块，生产渲染器输出与仅原文重建逐字节一致；三处硬读旧字段的分析/报告脚本最小 .get() 修复（finalize_sce_news_parts.py 为 Codex 未跟踪文件，修复留工作区）。
- label_sce_news_pool.py 预算/续跑修复：历史费用累计进预算、失败批持久化默认不重发（--retry-failed 显式放行）、原始回复脱敏存 responses/。
- 测试：test_label_sce_news_pool.py 22 项 + test_news_label_compat.py 7 项全绿；flash dry-run 正常。
- 注意：脚本 code_sha256 已变，旧试点目录不可再 execute，新运行须重新 prepare。

## 2026-10-22 全量标签执行（用户批准 ~$2/$3 上限）+ 并发改造

- 新增 full variant + build-manifest：93 窗口跨月去重清单 30,274 篇（候选总计 54,486、唯一 38,903、已标 8,629、跨窗复用 15,583），prepare 直接读清单。
- v1 串行首发：319 批后按用户决定切并发；5 批"多字段回声"校验失败，新增 repair 子命令从已存原始回复离线投影修复（零 API、分类内容不动），2,552 篇全部入库。
- execute 并发化（--workers，默认 8）：worker 纯网络/校验，预算记账与文件写全部留主线程；在途批持预算预占，硬上限精确。实测约 8.6 批/秒（串行 0.64），13 倍。
- v2 续跑 27,722 篇（自动排除 v1 已完成），12 并发。目录：v1 outputs/sce_news_labels_full_20261022_v1（归档），v2 ..._v2。
- 测试 24 项全绿（新增 repair 幂等/不可修复 2 项）。
