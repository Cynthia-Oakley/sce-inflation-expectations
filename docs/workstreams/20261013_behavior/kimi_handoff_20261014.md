# Kimi 交接说明（2026-10-14）

范围：信念更新线全部已完成工作 + U1 真实批次。本轮无新增 API 之外的事项；当前没有任何正在运行的任务。

## 1. 运行入口与命令

U1 批次已完成，整条链不可重跑（execute 对已有 run_id 拒绝覆盖）：

```bash
PY=/Users/wushuyue/anaconda3/envs/socioverse/bin/python
# 准备（已完成；candidate 是已审计的 v2 准备包，folder 必须不存在）
$PY -B scripts/run_sce_u1_trial.py prepare \
  --folder outputs/sce_u1_trial_20261014_v2 \
  --candidate outputs/sce_u1_state_preparation_20261013_v2
# 离线干跑（8 个 scripted 单元，0 API；已完成）
$PY -B scripts/run_sce_u1_trial.py dry-run --folder outputs/sce_u1_trial_20261014_v2
# 真实执行（已完成，16 单元 192 调用；--approval-note 必填，空则拒绝）
$PY -B scripts/run_sce_u1_trial.py run --folder outputs/sce_u1_trial_20261014_v2 --approval-note "..."
# 导出评价文件（已完成）
$PY -B scripts/export_sce_u1_answers.py \
  --trial outputs/sce_u1_trial_20261014_v2 \
  --out outputs/sce_u1_evaluation_20261014_v1
```

中断恢复约定：`u1_state_trial.execute` 逐 job 串行、出错即停并把 `status` 写成 `stopped_on_error|stopped_audit_mismatch|stopped_on_request_error`；**没有自动续跑**——已存在的 run 目录会让再次 execute 直接拒绝。恢复方式只能是：保留现场、诊断日志（trial 文件夹内 `*_real.log`），要跑就开新 folder/新 run_id 并重新授权。删除 run 目录强行重跑违反归档纪律。

评价/复核入口以 Codex 文档为准：`codex_u1_real_results_20261014.md` §7（audit + comparison 两条命令）。

## 2. 文件归属与状态

**Kimi 已完成并已提交**（scoped commit，详见 git log 最新一条）：

- U1 链路：`studies/sce_inflation_expectations/u1_state_experiment.py`、`u1_state_trial.py`、`scripts/run_sce_u1_trial.py`、`scripts/export_sce_u1_answers.py`、`tests/test_sce_u1_state_experiment.py`；改动 `scripts/run_sce_local.py`（+28 行：U1 分支、prompt-version 白名单、execution_purpose）与 `studies/sce_inflation_expectations/__init__.py`（+1 行注册）。
- 信念更新线早前交付：`belief_dynamics/`、`belief_state_preparation.py`、`scripts/analyze_sce_belief_dynamics.py`、`run_sce_belief_baselines.py`、`run_sce_anchor_baselines.py`、`prepare_sce_u1a_state.py` 及四个对应测试；文档 `kimi_results.md`、`kimi_summary.json`、`kimi_anchor_prereg.md`、`kimi_anchor_results.md`、`kimi_joint_design_draft.md`（v2）、`kimi_u1_input_spec.md`（v2）、`kimi_progress.md`。
- 更早期的独立交付：`scoring/beta_fit_kernel.py`、`reports/PROMPT_IO_REVIEW_20261003.md`。

**仍是草稿/参考，不要当正式配置**：`kimi_joint_design_draft.md`（汇合草案，未被冻结）；`kimi_u1_input_spec.md`（规范 v2，已被实际批次执行，但 U1 机制本身未通过筛选、未升级）。

**不属于 Kimi，未动**：Codex 的 `evaluation/u1_preparation_audit.py`、`u1_execution_audit.py`、`audit_sce_u1_*.py`、`codex_*.md/json/html`、`docs/A_B_LINE_CONTRACTS.md`、`docs/current_todo.html`；以及工作区里其余已修改文件（`docs/DECISIONS.md`、`proposal/proposal.md`、`build_sce_population.py`、`scoring/sce_q9_frozen.py` 等）——**这些不是 Kimi 的改动，归属需 Codex/用户确认，本次提交未包含**。

## 3. 未写进其他文档的问题

- `outputs/sce_u1_trial_20261014_v1/` 是首次 prepare 的失败残留（`--prompt-version` choices 当时未收录 `sce-q8-q9-explicit-state-v2`，dry-run exit 2）。修复后按不重覆盖约定启用 v2。**v1 仅作记录保留，勿复用。**
- 每次修改 `run_sce_local.py` / `__init__.py` 都会使旧试验 manifest 里的 runner 哈希 pin 失效，这是项目既有模式：实际运行代码由 run 目录内 `source_snapshot` 保全，Codex 的 behavior_comparison 不 pin runner 哈希所以不受影响。
- U1 192 次调用返回模型别名全部 `deepseek-flash`；别名一致不能证明后端版本未漂移（Codex 已在复核文档写明）。
- 本批真人通缩档全填 0 占比约 65.9%，模型两臂约 6.3%/12.5%——原始填法差距仍是已知未解项，与 Codex 概率表达线相关。
- 用户的一个待检验想法（已讨论、未登记正式假设）：照抄基线的 MAE 优势可能来自"中位数不动的月份"，LLM 的价值在中位数真实移动的月份（2023-03：LLM 0.24 vs 照抄 2.48）才显现；2022-09 是反例（新闻大但模型冲高回落 overshoot）。逐月数据在 `outputs/sce_behavior_comparison_u1_20261014_v1/summary.json` 各 condition 的 cells 里。

## 4. 正在运行的任务

无。U1 批次 16/16 单元已完成（192 调用、0 错误、自记峰值估算 $0.144671）。无 cron、无后台进程、无未完成的 MCP 调用。
