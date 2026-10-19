# 仓库治理提案：文档归档 + 分析脚本复用

> 执行状态（2026-10-19）：用户已授权按Codex修订方案整理；已完成总纲/索引、当前任务与交接收束及37份依赖安全的历史文档归档。原提案保留作讨论记录，未采纳的批量规则不作后续自动指令。实际清单见[整理收据](reviews/20261019_repository_cleanup/cleanup_receipt.json)。

> 2026-10-19，Kimi 起草，**提案未执行**。供用户与 Codex 评审；采纳后再分批执行，全部用 `git mv` 保留历史，不删除任何文件。
> 背景：docs/ 根 122 个条目（286 个 md）、scripts/ 247 个文件、docs 根有 17 份 `*_PLAN.md` 历史计划。规则（PROJECT_STRUCTURE.md）存在但未执行清理。

## 第一部分：docs/ 归档方案

### 1.1 保留在 docs/ 根的文档（约 15 份，"当前有效层"）

| 文档 | 角色 |
|---|---|
| DESIGN.md | 设计总纲（本次新增） |
| PROJECT_CHARTER.md / RESEARCH_PROTOCOL.md / DECISIONS.md | 边界、协议、决策 |
| A_B_LINE_CONTRACTS.md / A_B_RESEARCH_DESIGN.md | 两线契约 |
| CURRENT_SIMULATION_CONFIGURATION.md | 当前配置与误差口径 |
| EXPERIMENT_STATUS.md（由 _20261018 改名，去日期化） | 实验台账 |
| NEXT_ACTIONS.md / ROADMAP.md | 任务板、日程 |
| EXPERIMENT_PIPELINE.md / PROJECT_STRUCTURE.md / LOCAL_HARNESS_RUN_PLAN.md | 工程管线、目录、运行方案 |
| AGENT_HANDOFF.md / MODEL_TEMPORAL_LEAKAGE.md / SCE_DATA_AUDIT.md | 交接、泄漏纪律、数据审计 |

### 1.2 移入 `docs/archive/2026-10/` 的类别（约 90+ 份）

1. **已完成的一次性计划/运行卡/验收回执**：全部 `*_PLAN_2026*.md`、`*_RUN_CARD_*.md`、`*_ACCEPTANCE_*.md`、`*_RECEIPT_*.md`（如 CORE_NORMAL_*、HOUSEHOLD_STATE_*、PRICE_EXPERIENCE_*、SCE_LONG_RUN_CARD_DRAFT 等）——内容已沉淀进台账或 workstream。
2. **云端试点历史**：CLOUD_PILOT_PLAN、CLOUD_V2/V3/V4_*、KIMI_TO_CODEX_HANDOFF_20261005、CODEX_AUDIT_D050_*。
3. **10 月上旬模型选型/对比系列**：MODEL_SELECTION_20261003、SCE_ANNUAL_MODEL_COMPARISON、SCE_QWEN_*、SCE_EARLY_MODEL_*、SCE_DEEPSEEK_REUSE、SCE_MODEL_*（结论已写入 DECISIONS/配置文档）。
4. **10 月上旬基线系列**：SCE_BASELINE_*、SCE_EVALUATION_*、SCE_FAIR_*、SCORER_HOLDOUT_*（结论已入台账与契约）。
5. **过时入口文档**：sol_start_here、sol_execution_checklist、next_stage_plan_20261010、project_status.md、TODAY_PEB_EXECUTION_PLAN、KIMI_START_PROMPT.txt。
6. **html 快照**：docs 根全部 .html（保留在 archive，阅读页改由 workstream 内维护）。

### 1.3 两条配套规则（防止再膨胀）

- 新的计划/运行卡/回执**直接写进对应 workstream 目录**，不再放 docs 根；docs 根只留"当前有效层"。
- NEXT_ACTIONS.md 头部只保留当前待办 + 各结论一行链接；历史快照段每周剪切到 `docs/reviews/` 归档文件。

### 1.4 需要先核对再动的

- `B_SCE_SURVEY_SPEC.md`、`E_EVENT_MCP_SPEC.md`、`P_INPUT_RESEARCH.md`、`SCE_PROJECT_PLAN.md`、`SCE_Q9_SCORING_REPLICATION.md` 等**方法专题**：内容仍被引用，建议保留根目录或迁入 `docs/specs/` 子目录——待 Codex 确认引用关系后定。
- `figures/`、`literature/`、`reports/`、`reviews/`、`sources/`、`workstreams/` 子目录**不动**。

## 第二部分：scripts/ 分析脚本复用方案

### 2.1 现状

247 个文件平铺：`analyze_*` 49、`run_*` 34、`prepare_*` 30、`audit_*` 29、`plot_*` 21。大多数是"一个实验一个脚本"，公共计算（MAE/W1/IQR、调查权重、配对重抽样区间、真值装载）在多个脚本里各自重写。

### 2.2 复用分层（从低到高，逐层采纳）

**第 1 层：索引（零风险，建议立即做）**
- 新建 `scripts/README.md`：按主题分组列出脚本，标注 ① 仍在用的入口（如 `run_sce_frozen_trial.py`）② 一次性分析脚本及其对应 workstream。先解决"能不能找到"，再解决"要不要搬"。

**第 2 层：共享函数收敛（推荐，随新任务逐步做）**
- 公共计算只允许从共享模块导入：`studies/sce_inflation_expectations/evaluation/`（已有评价器）+ 新建 `studies/sce_inflation_expectations/analysis_utils.py`（真值装载、权重、MAE/W1/IQR、配对区间）。
- 规范：新分析脚本**不得重写**上述函数；写新脚本前先查 evaluation/ 与 analysis_utils。
- 不做一次性大重构：旧脚本保持原样（结果可复算依赖旧代码冻结），只在新增/修改时执行规范。

**第 3 层：归档（需引用扫描后执行）**
- `scripts/archive/2026-10/` 收容一次性脚本。移动前用 `grep -rn "脚本名" docs/ tests/ studies/` 扫描引用，有引用的保留原位或同时改引用。
- 生命周期规则：一次性分析脚本头部必须写 docstring（输入/输出/日期/关联 workstream）；30 天未被任何文档引用即归档。

### 2.3 明确不做的

- 不移动 `run_sce_frozen_trial.py` 等在册入口及其被 tests/ 覆盖的脚本（132 个测试文件路径敏感）。
- 不改 `studies/sce_inflation_expectations/` 内部结构——160 个平铺模块是工作区，重组成本高于收益，用第 1 层索引解决导航即可。

## 第三部分：执行步骤（采纳后）

1. 引用扫描：对拟移动清单逐个 `grep -rn` 检查 docs/tests/scripts 内引用，输出最终移动清单供二次确认。
2. `git mv` 分批执行（docs 一批、scripts 一批），每批一个 scoped 提交，提交信息列文件数。
3. 更新 PROJECT_STRUCTURE.md 目录树、README.md 链接、AGENTS.md 第 1 条指引。
4. 跑 `/Users/wushuyue/anaconda3/envs/socioverse/bin/python -m pytest tests/ -q` 确认无回归。
5. EXPERIMENT_STATUS_20261018.md → EXPERIMENT_STATUS.md 改名单独提交（链接同步改）。

## 第四部分：待用户/Codex 决策点

1. docs 根"当前有效层"清单（1.1）是否增删——尤其 1.4 的方法专题放根还是 `docs/specs/`。
2. 脚本复用采用"渐进收敛"（本方案）还是一次性大重组（不推荐）。
3. 归档执行时机：建议在当前付费实验批次结束、无进行中任务引用的窗口做。
4. 谁执行：Kimi 可执行全部机械操作；Codex 复核移动清单与引用扫描结果。
