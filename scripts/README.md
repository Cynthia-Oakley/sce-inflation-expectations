# 脚本入口索引

更新：2026-10-19。按用途导航，**不表示所有入口都适用于当前配置**。以下根据现有文件名及原docstring整理；日期和实验参数以对应workstream/冻结运行包为准，不能凭脚本名直接启动付费调用。

## 优先使用的入口

- [run_sce_frozen_trial.py](run_sce_frozen_trial.py)：共用prepare / dry-run / run / worker / evaluate。已接Q8单改、温度三组及单一Qwen/OpenRouter迁移适配（固定供应商、复用旧对照），另支持采购角色的仅工程验收包（禁付费/研究计分）；旧协议仍用原标量温度。新增机制须有适配器及冻结配置，真实调用另需有效授权。
- [prepare_sce_news_breadth_trial.py](prepare_sce_news_breadth_trial.py)：最新已完成新闻量三组试验的准备入口；不要重启旧包。
- [report_sce_news_breadth.py](report_sce_news_breadth.py)、[plot_sce_news_breadth.py](plot_sce_news_breadth.py)：基于已有评价缓存汇总/作图，不再发API。
- [prepare_sce_personal_information.py](prepare_sce_personal_information.py)、[prepare_sce_personal_information_views.py](prepare_sce_personal_information_views.py)：ATUS/SCE角色与菜单的离线准备，不等于真实模拟入口已接通。
- [prepare_sce_procurement_views.py](prepare_sce_procurement_views.py)：六期食品采购角色—价格视图离线准备，复用首发PDF、匹配/打乱及完整提示；不发API，不是付费运行入口。
- [evaluate_sce_outputs.py](evaluate_sce_outputs.py)：统一规范包评价，旧批次须遵守其计分版本和支持定义。
- [render_current_todo.py](render_current_todo.py)：从当前任务板生成固定路径`docs/current_todo.html`。

共享算法优先从`studies/sce_inflation_expectations/evaluation/`、`experiments/`导入，基础分位数/W1/权重先查[metrics.py](../studies/sce_inflation_expectations/evaluation/metrics.py)。不同按人/按月重抽样设计不能自动互换。旧冻结脚本不在本轮重构或移动；部分report脚本仍被模块导入。

运行、预算、失败和新输出目录要求见[共用流程](../docs/EXPERIMENT_PIPELINE.md)。当前任务见[任务板](../docs/NEXT_ACTIONS.md)；每轮证据见[workstreams](../docs/workstreams/)。

- [analyze_sce_advisor_diagnostics.py](analyze_sce_advisor_diagnostics.py)：复用十二期缓存诊断年龄×学历九格，并从旧原回包单独恢复Q8；不重拟合Q9。
- [report_sce_advisor_diagnostics.py](report_sce_advisor_diagnostics.py)：将上述聚合结果作图并接入既有阅读页；同名输出存在时拒绝覆盖。
- [report_sce_q8_delta.py](report_sce_q8_delta.py)：从共用评价缓存生成Q8单改对照图文与费用收据，不发API或重拟合Q9。
- [check_sce_simulation_capabilities.py](check_sce_simulation_capabilities.py)：仅核免费Simulation能力与受支持参数，不执行付费问卷。
- [evaluate_sce_model_migration.py](evaluate_sce_model_migration.py)：连接中断后仅评价全部重复完整的月份，生成只读派生manifest，不补API或改原答。
- [report_sce_model_migration.py](report_sce_model_migration.py)：模型迁移的公共图文、分组、重复分解与去重费用收据，读取已计分缓存。

Q8单改已用共用runner完成384调用；结果见`docs/workstreams/20261019_advisor_followup/q8_delta_results_20261019.md`，不重复运行旧包。人口六格只做设计，不随格式实验更换。温度批次复算用`evaluate_sce_temperature.py`的四遍真值索引适配，再用`report_sce_temperature.py`作图；不重跑已完成API。

## 按用途查找全部入口

下列英文简介保留自原文件，帮助识别；不是新的方法或有效性认定。


### 运行与导出（37）

- [export_sce_confidence_analysis.py](export_sce_confidence_analysis.py) — Recompute frozen analysis with a strict missing-value JSON export adapter.
- [export_sce_u1_answers.py](export_sce_u1_answers.py) — Export completed U1 state/guided runs to the registered comparison schema.
- [export_study_runtime.py](export_study_runtime.py) — One-way export of the SCE study from the research repo to a runtime studies root.
- [run_approved_sce_expanded_news.py](run_approved_sce_expanded_news.py) — Dispatch only never-started, frozen public-news packages under the approved cap.
- [run_nyt_label_quote_adapter.py](run_nyt_label_quote_adapter.py) — Thin entry for source-verified quote restoration and unattempted continuation.
- [run_nyt_label_trial.py](run_nyt_label_trial.py) — Classification runner; offline validation unless --execute is explicit.
- [run_sce_anchor_baselines.py](run_sce_anchor_baselines.py) — Run the preregistered personal-anchor update rules (belief dynamics, round 2).
- [run_sce_anchor_role_trial.py](run_sce_anchor_role_trial.py) — Isolated prior-role trial; no auto-resume/retry and explicit authorization gate.
- [run_sce_annual_model_comparison.py](run_sce_annual_model_comparison.py) — Budgeted exact-message annual questionnaire replay; offline unless confirmed.
- [run_sce_baselines.py](run_sce_baselines.py) — Run the frozen offline benchmark protocol and retain per-month predictions.
- [run_sce_belief_baselines.py](run_sce_belief_baselines.py) — SCE preregistered empirical update baselines (B0-B4), train 201702-202112 /
- [run_sce_cognition_trial.py](run_sce_cognition_trial.py) — Historical cognition input pilot; no auto-resume/retry and explicit authorization gate.
- [run_sce_confidence_trial.py](run_sce_confidence_trial.py) — Offline preparation and budget-gated paired confidence experiment.
- [run_sce_event_probe.py](run_sce_event_probe.py) — Execute a protocol-bound, approved Event data probe once, with no retries.
- [run_sce_expanded_trial.py](run_sce_expanded_trial.py) — Prepare/dry-run/execute the approved expanded experiment in SocioVerse2.
- [run_sce_experience_trial.py](run_sce_experience_trial.py) — Freeze and run the authorized 20-person, two-month, five-arm SCE trial.
- [run_sce_finance_validation_trial.py](run_sce_finance_validation_trial.py) — Separate cross-month finance entry; inherit the audited no-resume runner.
- [run_sce_frozen_trial.py](run_sce_frozen_trial.py) — Shared frozen-prompt trials: prepare, dry-run, gated run, worker, evaluate.
- [run_sce_household_finance_trial.py](run_sce_household_finance_trial.py) — Household financial-circumstances pilot; no auto-resume/retry and explicit authorization gate.
- [run_sce_household_state_trial.py](run_sce_household_state_trial.py) — Prepare a Q1-only paired pilot offline; execute only after fresh approval.
- [run_sce_information_exposure_trial.py](run_sce_information_exposure_trial.py) — Prepare an isolated E/P routing trial; paid execution needs explicit approval.
- [run_sce_information_update_trial.py](run_sce_information_update_trial.py) — Information-time follow-up; reuse old A, run only new B/C; no auto-resume/retry and explicit authorization gate.
- [run_sce_lifetime_text_trial.py](run_sce_lifetime_text_trial.py) — Budget-gated qualitative history comparison, no change to old configurations.
- [run_sce_lifetime_trial.py](run_sce_lifetime_trial.py) — Run the isolated, budget-gated Lifetime Inflation Experience trial.
- [run_sce_local.py](run_sce_local.py) — Local SCE run entry — export the study one-way, run it in the official clone, audit fully.
- [run_sce_model_counterfactual.py](run_sce_model_counterfactual.py) — Replay prepared model-only messages; default is offline validation, not spending.
- [run_sce_model_followup.py](run_sce_model_followup.py) — Continue fixed model comparison without resetting prior spend; default is offline.
- [run_sce_native_spending_trial.py](run_sce_native_spending_trial.py) — Prepare, then explicitly execute the isolated native SCE basket trial.
- [run_sce_news_exposure_trial.py](run_sce_news_exposure_trial.py) — Prepare/dry-run news exposure; real execution needs fresh complete-label approval.
- [run_sce_price_contact_trial.py](run_sce_price_contact_trial.py) — Thin entry for the isolated price-contact experiment.
- [run_sce_prior_trial.py](run_sce_prior_trial.py) — Prepare/dry-run/run the isolated observed-prior trial, with explicit budget.
- [run_sce_purchase_frequency_trial.py](run_sce_purchase_frequency_trial.py) — Purchase-frequency instruction contrast; same data in both arms; no auto-resume/retry and explicit authorization gate.
- [run_sce_reference_news.py](run_sce_reference_news.py) — Budget-bound dispatch of frozen public news, no automatic retry or resume.
- [run_sce_reference_validation_trial.py](run_sce_reference_validation_trial.py) — Reference scale-up; isolated worker plus the existing gated fail-stop dispatch.
- [run_sce_reuse_probe.py](run_sce_reuse_probe.py) — One-model, $0.50 capped archived-message replay; defaults to no network.
- [run_sce_revision_format_trial.py](run_sce_revision_format_trial.py) — Direct-versus-revision response-format pilot; no auto-resume/retry and explicit authorization gate.
- [run_sce_u1_trial.py](run_sce_u1_trial.py) — Entry point for the U1 explicit-state trial: prepare, dry-run or execute.


### 准备与构建（40）

- [build_nyt_events.py](build_nyt_events.py) — Build the NYT salient-event ledger (E v2 event layer, D049d).
- [build_sce_available_environment.py](build_sce_available_environment.py) — Build isolated B month-start input drafts from verified local release archives.
- [build_sce_baseline_inputs.py](build_sce_baseline_inputs.py) — Prepare release-audited aggregate inputs and evaluation-only micro reference cache.
- [build_sce_baseline_review.py](build_sce_baseline_review.py) — Add rolling diagnostics and a portable, offline HTML view of completed runs.
- [build_sce_environment.py](build_sce_environment.py) — Materialize the BLS information environment (E) for sce_inflation_expectations.
- [build_sce_environment_v2.py](build_sce_environment_v2.py) — Build the E v2 information environment for sce_inflation_expectations.
- [build_sce_evaluation_truth.py](build_sce_evaluation_truth.py) — Extract evaluation-layer truth for the SCE main window from the microdata.
- [build_sce_population.py](build_sce_population.py) — Build a real-population Persona bundle by sampling U.S. respondents from the
- [build_sce_price_experience.py](build_sce_price_experience.py) — Build an A-line CE basket sidecar and preview all mechanism arms, fully offline.
- [build_sce_psychological_profiles.py](build_sce_psychological_profiles.py) — Build offline candidate sidecars, not runtime population or new answers.
- [prepare_ce_category_frequency.py](prepare_ce_category_frequency.py) — 专题入口；运行前读文件说明与对应批次记录。
- [prepare_ce_diary.py](prepare_ce_diary.py) — Prepare weekly 2020 CE Diary experience records offline; this script never calls an LLM.
- [prepare_nyt_selection_trial.py](prepare_nyt_selection_trial.py) — Offline entry point; import the study without optional simulation packages.
- [prepare_sce_annual_model_comparison.py](prepare_sce_annual_model_comparison.py) — Prepare fixed 2021 model comparisons offline; never read keys or call APIs.
- [prepare_sce_baseline_sources.py](prepare_sce_baseline_sources.py) — Archive public release evidence for offline SCE benchmarks. No credentials.
- [prepare_sce_belief_trial.py](prepare_sce_belief_trial.py) — Prepare local-only belief inputs; this entry point cannot request a model.
- [prepare_sce_coverage.py](prepare_sce_coverage.py) — Thin entry point for offline multi-period preparation.
- [prepare_sce_expansion_preflight.py](prepare_sce_expansion_preflight.py) — Offline candidate coverage and budgeting only; no execution option.
- [prepare_sce_frequency_candidate.py](prepare_sce_frequency_candidate.py) — Prepare the source-limited offline matching prototype. No network or API.
- [prepare_sce_information_exposure.py](prepare_sce_information_exposure.py) — Prepare six-month news/statistics view inventory; cannot start paid calls.
- [prepare_sce_macro_profile_sources.py](prepare_sce_macro_profile_sources.py) — Free public archive downloads and deterministic aggregate macro extraction.
- [prepare_sce_mechanism_pilot.py](prepare_sce_mechanism_pilot.py) — Create a small, fixed within-month comparison panel without reading answers.
- [prepare_sce_model_counterfactual.py](prepare_sce_model_counterfactual.py) — Offline matched model inputs from completed DeepSeek runs; no API/key access.
- [prepare_sce_monthly_inputs.py](prepare_sce_monthly_inputs.py) — Prepare A-line monthly P/E/simulation packages without model calls.
- [prepare_sce_news_breadth_trial.py](prepare_sce_news_breadth_trial.py) — Freeze varied news-count inputs for the shared engine; no API calls.
- [prepare_sce_news_exposure_demo.py](prepare_sce_news_exposure_demo.py) — Thin, offline entry point for the news exposure demonstration.
- [prepare_sce_news_extension_labels.py](prepare_sce_news_extension_labels.py) — Thin offline entry for new-period public news classification preparation.
- [prepare_sce_news_label_completion.py](prepare_sce_news_label_completion.py) — Thin offline entry; never resends a request.
- [prepare_sce_news_pool.py](prepare_sce_news_pool.py) — Thin offline entry for completing the existing news candidate pool.
- [prepare_sce_persistence_probe.py](prepare_sce_persistence_probe.py) — Prepare local-only previews; there is deliberately no execute mode.
- [prepare_sce_personal_information.py](prepare_sce_personal_information.py) — Prepare local ATUS/SCE role probabilities and quantity-balanced allocations.
- [prepare_sce_personal_information_views.py](prepare_sce_personal_information_views.py) — Create news/price fragments from a prepared ATUS/SCE bridge, without APIs.
- [prepare_sce_prior_trial.py](prepare_sce_prior_trial.py) — Zero-API SCE prior inventory and conditional-update input preparation.
- [prepare_sce_progress_report.py](prepare_sce_progress_report.py) — Create aggregate-only figures for the 2026-10-15 progress briefing.
- [prepare_sce_purchase_frequency.py](prepare_sce_purchase_frequency.py) — Offline matched contact/price materials; previews only, no live provider/API.
- [prepare_sce_reference_news.py](prepare_sce_reference_news.py) — Prepare only unlabeled public articles for reference scaleup; never call API.
- [prepare_sce_reuse_probe.py](prepare_sce_reuse_probe.py) — Prepare an outcome-blind, 20-person annual Qwen replay. Offline only.
- [prepare_sce_revision_draft.py](prepare_sce_revision_draft.py) — Offline prompt drafts, not a runnable/authorized experiment batch.
- [prepare_sce_shared_environment.py](prepare_sce_shared_environment.py) — Export the exact existing Agent public E for baselines; no downloads or LLM.
- [prepare_sce_u1a_state.py](prepare_sce_u1a_state.py) — Prepare the U1 explicit personal-state arms (offline, zero API calls).


### 评价与报告（16）

- [evaluate_sce_model_migration.py](evaluate_sce_model_migration.py) — Evaluate only fully completed repeated months from a stopped model-migration batch, without reruns.
- [report_sce_model_migration.py](report_sce_model_migration.py) — Plot cached model comparisons and publish aggregate execution/cost evidence only.
- [report_sce_advisor_diagnostics.py](report_sce_advisor_diagnostics.py) — Plot cached household-grid and recovered Q8 diagnostics in the existing reader.
- [report_sce_q8_delta.py](report_sce_q8_delta.py) — Render the completed Q8-only pilot from cached evaluation; no API or refit.
- [evaluate_sce_temperature.py](evaluate_sce_temperature.py) — Reuse invariant person-month truth across four temperature repeats; no source or answer rewriting.
- [report_sce_temperature.py](report_sce_temperature.py) — Publish temperature accuracy, repeat-noise decomposition and cost from cached outputs.

- [evaluate_sce_dev_run.py](evaluate_sce_dev_run.py) — Same-person development analysis: actual answers are read only after the run.
- [evaluate_sce_outputs.py](evaluate_sce_outputs.py) — Evaluate normalized SCE bundles without loading inputs into the simulation engine.
- [report_sce_frozen_trial.py](report_sce_frozen_trial.py) — Make an aggregate report from already scored frozen-prompt trial answers.
- [report_sce_information_exposure.py](report_sce_information_exposure.py) — Report all preregistered six-arm contrasts from already-scored answers.
- [report_sce_news_breadth.py](report_sce_news_breadth.py) — Read out matched/random/uniform news exposure using shared scored outputs.
- [report_sce_reference_validation.py](report_sce_reference_validation.py) — Write aggregate Chinese findings and update the existing project reading page.
- [summarize_midus_local.py](summarize_midus_local.py) — User-run MIDUS statistics. Do not execute on real data through an AI agent.
- [summarize_sce_cognition_diagnostics.py](summarize_sce_cognition_diagnostics.py) — Recompute explicitly exploratory response variation and past-only context, with no API.
- [summarize_sce_psychological_waves.py](summarize_sce_psychological_waves.py) — Compare completed wave trial to cached 2018 answers using existing metrics.
- [summarize_sce_retention_predictability.py](summarize_sce_retention_predictability.py) — Small public readout and capacity check; no refit, API, or model selection.


### 分析（58）

- [analyze_sce_stratification_support.py](analyze_sce_stratification_support.py) — Outcome-free six-cell support and minimum-plus-proportional Core allocation draft.

- [analyze_sce_population_factor_priority.py](analyze_sce_population_factor_priority.py) — Compare ten cached trait blocks on identical monthly support; descriptive R2 only.

- [analyze_sce_advisor_diagnostics.py](analyze_sce_advisor_diagnostics.py) — Cached nine-cell household comparisons and independent Q8 recovery.

- [analyze_nyt_selection_trial.py](analyze_nyt_selection_trial.py) — Offline verification of news trial; no classifier or simulation calls.
- [analyze_sce_aggregate_blend.py](analyze_sce_aggregate_blend.py) — Fit MAE/MSE convex weights on existing aggregate trajectories; zero APIs.
- [analyze_sce_anchor_direction.py](analyze_sce_anchor_direction.py) — Compare alignment with older personal answers and common references, offline.
- [analyze_sce_anchor_role_trial.py](analyze_sce_anchor_role_trial.py) — 专题入口；运行前读文件说明与对应批次记录。
- [analyze_sce_attention_support.py](analyze_sce_attention_support.py) — Check external attention/channel predictive support without paid calls.
- [analyze_sce_atus_roles.py](analyze_sce_atus_roles.py) — Audit public ATUS roles and external attention without simulation calls.
- [analyze_sce_behavior_comparison.py](analyze_sce_behavior_comparison.py) — Compare saved SCE responses and same-cohort baselines; never call an API.
- [analyze_sce_belief_dynamics.py](analyze_sce_belief_dynamics.py) — SCE belief dynamics: task A (real panel update facts) + task A' (LLM same-
- [analyze_sce_cognition_low_only.py](analyze_sce_cognition_low_only.py) — Post-hoc Low-only cognition policy using frozen, independent household replies.
- [analyze_sce_cognition_trial.py](analyze_sce_cognition_trial.py) — Offline analysis of a completed SCE cognition presentation trial.
- [analyze_sce_confidence_trial.py](analyze_sce_confidence_trial.py) — Extract evaluation truth or analyze paired confidence trial, no API calls.
- [analyze_sce_event_probe.py](analyze_sce_event_probe.py) — Audit a completed fixed Event probe and hash-linked official source archive.
- [analyze_sce_expanded_trial.py](analyze_sce_expanded_trial.py) — Freeze the development weight, or evaluate held-out months offline.
- [analyze_sce_expansion_diagnostic.py](analyze_sce_expansion_diagnostic.py) — Offline entry point; fresh output folder required.
- [analyze_sce_experience_trial.py](analyze_sce_experience_trial.py) — Analyze the two-month, five-arm SCE price-experience pilot without API calls.
- [analyze_sce_finance_validation.py](analyze_sce_finance_validation.py) — Offline evaluation of completed Q1 cross-month validation runs.
- [analyze_sce_forecast_population.py](analyze_sce_forecast_population.py) — Profile-only monthly drift and B donor diagnostics, no model/network calls.
- [analyze_sce_frequency_controls.py](analyze_sce_frequency_controls.py) — Offline controlled associations in the completed frequency experiment.
- [analyze_sce_heterogeneous_news.py](analyze_sce_heterogeneous_news.py) — Reuse archived news-count replies for a fixed external-attention allocation.
- [analyze_sce_history_forward.py](analyze_sce_history_forward.py) — Time-ordered personal-history checks on cached scores; no network or API.
- [analyze_sce_history_mechanism.py](analyze_sce_history_mechanism.py) — Offline follow-up: personal history coefficients, Sim-only R2 and SCE proxies.
- [analyze_sce_household_finance_associations.py](analyze_sce_household_finance_associations.py) — Zero-API, aggregate-only analysis entry point.
- [analyze_sce_household_finance_trial.py](analyze_sce_household_finance_trial.py) — Offline analysis of a completed SCE household-finance three-arm trial.
- [analyze_sce_household_state_trial.py](analyze_sce_household_state_trial.py) — Evaluate a completed Q1 paired trial offline; no network or new simulation.
- [analyze_sce_inertia_calibration.py](analyze_sce_inertia_calibration.py) — Fixed-weight ConsumerSim-style aggregate sensitivity; zero network or LLM calls.
- [analyze_sce_information_exposure_trial.py](analyze_sce_information_exposure_trial.py) — Evaluate completed E/P routing LLM trial; no network, no new simulation.
- [analyze_sce_information_update_trial.py](analyze_sce_information_update_trial.py) — 专题入口；运行前读文件说明与对应批次记录。
- [analyze_sce_lifetime_trial.py](analyze_sce_lifetime_trial.py) — Offline analysis only; no simulation or model calls.
- [analyze_sce_model_costs_groups.py](analyze_sce_model_costs_groups.py) — Offline cost normalization and group diagnostics for the frozen model pilot.
- [analyze_sce_model_counterfactual.py](analyze_sce_model_counterfactual.py) — Analyze completed model probes offline, with true answers only in this script.
- [analyze_sce_native_spending_trial.py](analyze_sce_native_spending_trial.py) — 专题入口；运行前读文件说明与对应批次记录。
- [analyze_sce_news_exposure_trial.py](analyze_sce_news_exposure_trial.py) — Analyze a completed news trial offline, without new API calls.
- [analyze_sce_news_extension_labels.py](analyze_sce_news_extension_labels.py) — Thin offline entry for new-period news-label acceptance and libraries.
- [analyze_sce_outlook_forward.py](analyze_sce_outlook_forward.py) — Check previous Q2 using validated caches; no original workbooks or API.
- [analyze_sce_past_exposure_gate.py](analyze_sce_past_exposure_gate.py) — Select already-generated information views using frozen past-only predictions.
- [analyze_sce_population_associations.py](analyze_sce_population_associations.py) — 专题入口；运行前读文件说明与对应批次记录。
- [analyze_sce_prior_trial.py](analyze_sce_prior_trial.py) — Offline observed-prior evaluation; never launches an API request.
- [analyze_sce_purchase_frequency_trial.py](analyze_sce_purchase_frequency_trial.py) — Offline evaluation entry point; never calls the simulation API.
- [analyze_sce_reference_validation.py](analyze_sce_reference_validation.py) — Offline evaluation of the 12-month reference scale-up.
- [analyze_sce_reporting_behavior.py](analyze_sce_reporting_behavior.py) — Offline SCE probability-reporting analysis; no API or simulation calls.
- [analyze_sce_reporting_mapping.py](analyze_sce_reporting_mapping.py) — Run the registered personal reporting mapping into a fresh local directory.
- [analyze_sce_response_gap.py](analyze_sce_response_gap.py) — Describe archived human/model gaps without APIs or refitting probabilities.
- [analyze_sce_response_gap_controls.py](analyze_sce_response_gap_controls.py) — Describe conditional response gaps without API calls or density refitting.
- [analyze_sce_retention_predictability.py](analyze_sce_retention_predictability.py) — Predict reported stability from past-only records; zero paid calls.
- [analyze_sce_reuse_probe.py](analyze_sce_reuse_probe.py) — Score archived annual DeepSeek and optional exact-input Qwen offline.
- [analyze_sce_revision_format_trial.py](analyze_sce_revision_format_trial.py) — Offline evaluation, no API calls.
- [analyze_sce_update_direction.py](analyze_sce_update_direction.py) — Run the fixed past-only update-direction diagnostic, without network access.
- [analyze_sce_update_mismatch_profiles.py](analyze_sce_update_mismatch_profiles.py) — Locate observed human/model update mismatches using verified cached inputs.
- [analyze_sce_updating_facts.py](analyze_sce_updating_facts.py) — SCE updating micro facts F1-F6: inaction, lumpy revisions, information
- [analyze_sce_wave_stats.py](analyze_sce_wave_stats.py) — Wave-by-wave descriptive statistics on FRBNY SCE public micro data
- [diagnose_sce_beta.py](diagnose_sce_beta.py) — Independent diagnostic experiments; NEVER imported by the production scorer.
- [diagnose_sce_center_shift.py](diagnose_sce_center_shift.py) — 专题入口；运行前读文件说明与对应批次记录。
- [diagnose_sce_confidence_responses.py](diagnose_sce_confidence_responses.py) — Describe existing answers offline; this entry never starts a simulation.
- [diagnose_sce_reference_regression.py](diagnose_sce_reference_regression.py) — Exploratory regressions on frozen fitted responses; never refits Q9 or calls APIs.
- [diagnose_sce_reference_update.py](diagnose_sce_reference_update.py) — Post-hoc slope diagnostic from existing fitted cases; zero new model calls.


### 审计与验证（42）

- [check_sce_simulation_capabilities.py](check_sce_simulation_capabilities.py) — Free registry/schema verification only; never runs a paid questionnaire.

- [audit_cloud_v2_environment.py](audit_cloud_v2_environment.py) — Verify the pasted v2 cloud environment against the archived local inputs.
- [audit_cloud_v2_model.py](audit_cloud_v2_model.py) — Replay the archived v2 scripted formula against local P/E and raw answers.
- [audit_cloud_v2_raw.py](audit_cloud_v2_raw.py) — Independently audit the v2 scripted pilot's pasted raw JSONL answers.
- [audit_cloud_v3_audit.py](audit_cloud_v3_audit.py) — Independently audit the v3 scripted audit-run artifacts retrieved from the platform.
- [audit_local_scripted_replay.py](audit_local_scripted_replay.py) — Replay audit: local scripted run vs the cloud v3 archive (2026-10-01).
- [audit_nyt_inventory.py](audit_nyt_inventory.py) — Thin entry point for the local-only NYT inventory audit.
- [audit_population_proposal.py](audit_population_proposal.py) — Read-only independent checks of the October 3 population proposal; no API calls.
- [audit_sce_basket_population.py](audit_sce_basket_population.py) — Audit a complete SCE population's synthetic CE baskets, fully offline.
- [audit_sce_behavior_mechanisms.py](audit_sce_behavior_mechanisms.py) — Zero-API audit of official conditional associations and existing LLM compression.
- [audit_sce_coverage_and_age.py](audit_sce_coverage_and_age.py) — 专题入口；运行前读文件说明与对应批次记录。
- [audit_sce_deepseek_reuse.py](audit_sce_deepseek_reuse.py) — Audit archived DeepSeek responses offline; never reads keys or calls APIs.
- [audit_sce_environment_candidate.py](audit_sce_environment_candidate.py) — Offline acceptance of an isolated E candidate; no simulation or API calls.
- [audit_sce_factual_mechanisms.py](audit_sce_factual_mechanisms.py) — Prepare factual mechanism evidence offline; never executes simulation.
- [audit_sce_frequency_quarters.py](audit_sce_frequency_quarters.py) — Existing-data CE quarter/matching audit; never starts simulation or an API.
- [audit_sce_household_state.py](audit_sce_household_state.py) — Audit development months and GSS2018 donor support; no model calls.
- [audit_sce_monthly_run.py](audit_sce_monthly_run.py) — Audit a monthly P/E run and form weighted diagnostic summaries, no APIs.
- [audit_sce_news_responses.py](audit_sce_news_responses.py) — Offline audit of existing inputs/replies; does not call any API.
- [audit_sce_numeracy.py](audit_sce_numeracy.py) — Offline numeracy validation on existing real and simulated SCE answers.
- [audit_sce_pe_diagnostic.py](audit_sce_pe_diagnostic.py) — Read archived P/E/B messages and answers; no network, no providers.
- [audit_sce_psychological_waves.py](audit_sce_psychological_waves.py) — Audit downloaded public GSS waves; never calls a model.
- [audit_sce_q9_scoring.py](audit_sce_q9_scoring.py) — Compare local Q9 density scores with public SCE derived fields and chart data.
- [audit_sce_replies_20261018.py](audit_sce_replies_20261018.py) — Audit archived SCE reply text without API calls, fitting, or source mutation.
- [audit_sce_reuse_run.py](audit_sce_reuse_run.py) — Offline audit of identities, original payloads, retries and cumulative fees.
- [audit_sce_scaleup_coverage.py](audit_sce_scaleup_coverage.py) — Local-only availability audit for a proposed expanded A-line validation.
- [audit_sce_sources.py](audit_sce_sources.py) — Read-only feasibility audit of downloaded SCE workbooks; no model fitting.
- [audit_sce_spending.py](audit_sce_spending.py) — Link real SCE spending baskets and run a fixed offline structural probe.
- [audit_sce_u1_execution.py](audit_sce_u1_execution.py) — Verify U1 real run records and exports without making new API requests.
- [audit_sce_u1_preparation.py](audit_sce_u1_preparation.py) — Read-only audit of prepared U1 messages; no real simulation or API calls.
- [audit_sce_vintage_examples.py](audit_sce_vintage_examples.py) — Offline, bounded CES revision example using verified local BLS PDFs.
- [check_mcp_free_capabilities.py](check_mcp_free_capabilities.py) — Verify connectivity and FREE catalog/field capabilities of the configured MCP services.
- [check_sce_cognition_population_weights.py](check_sce_cognition_population_weights.py) — Post-hoc High/Low population-margin sensitivity; never changes model answers.
- [check_sce_core_normal.py](check_sce_core_normal.py) — Offline expansion diagnostic with real Core answers as oracle response atoms.
- [check_sce_core_size.py](check_sce_core_size.py) — Offline Core-size study: nested samples of observed responses, never an LLM run.
- [check_sce_macro_population.py](check_sce_macro_population.py) — No API: compare macro profile forecasts against lagged SCE distributions.
- [check_sce_population_precision.py](check_sce_population_precision.py) — Offline development-month sampling check; no providers or simulation inputs.
- [check_sce_reference_history_information.py](check_sce_reference_history_information.py) — Check unused regression information already present in the frozen prompts.
- [check_sce_reference_validation.py](check_sce_reference_validation.py) — Small independent aggregate check; reuse scored cases, never refit or call API.
- [validate_sce_scorer_holdout.py](validate_sce_scorer_holdout.py) — One preregistered comparison; imports frozen algorithms without modifying them.
- [verify_bls_pit_e.py](verify_bls_pit_e.py) — Verify the two-month BLS E snapshot against its archived release PDFs.
- [verify_sce_prior_preparation.py](verify_sce_prior_preparation.py) — Verify offline SCE prior input preparation; reuse existing answers only.
- [verify_sce_purchase_frequency_trial.py](verify_sce_purchase_frequency_trial.py) — Focused saved-run verification: actual inputs/parameters/cost and SciPy metrics.


### 下载与数据获取（5）

- [download_sce_atus_reference.py](download_sce_atus_reference.py) — Download public BLS ATUS files through an already connected browser.
- [fetch_ce_diary_public.py](fetch_ce_diary_public.py) — Download explicit public BLS CE Diary CSV archives; no credentials/API.
- [fetch_eia_gasoline.py](fetch_eia_gasoline.py) — Fetch U.S. retail gasoline prices (E v2 data layer, D049c).
- [fetch_gss2018.py](fetch_gss2018.py) — Archive official current public GSS2018 data; no historical-vintage claim.
- [probe_sce_event_sources.py](probe_sce_event_sources.py) — Read the free Event MCP catalog without fetching metered source data.


### 作图与阅读页（36）

- [plot_sce_anchor_role_results.py](plot_sce_anchor_role_results.py) — Plot aggregate prior-role experiment results; no API or private rows read.
- [plot_sce_baselines.py](plot_sce_baselines.py) — Render a standalone scientific figure from a completed baseline run (offline).
- [plot_sce_cognition_results.py](plot_sce_cognition_results.py) — Create static figures from an aggregated SCE cognition evaluation summary.
- [plot_sce_coverage_age_audit.py](plot_sce_coverage_age_audit.py) — Static figures from aggregate coverage/age analysis, no API.
- [plot_sce_experience_trial.py](plot_sce_experience_trial.py) — Plot equal-person medians and interquartile ranges from a completed pilot.
- [plot_sce_finance_validation_results.py](plot_sce_finance_validation_results.py) — Render aggregate-only charts from a completed frozen cross-month evaluation.
- [plot_sce_frequency_controls.py](plot_sce_frequency_controls.py) — Scientific figures from aggregate offline diagnostics; no API or private records.
- [plot_sce_frequency_quarter_audit.py](plot_sce_frequency_quarter_audit.py) — Figures for existing-data CE quarter/matching checks; no private rows/API.
- [plot_sce_history_mechanism.py](plot_sce_history_mechanism.py) — Plot aggregate results for the existing personal-history reading page.
- [plot_sce_household_finance_results.py](plot_sce_household_finance_results.py) — Draw aggregate-only household-finance pilot figures in a fresh directory.
- [plot_sce_household_state_trial.py](plot_sce_household_state_trial.py) — Export a paper-ready Q1 group comparison from completed paired evaluation.
- [plot_sce_information_exposure.py](plot_sce_information_exposure.py) — Scientific figures from the six-arm aggregate readout; no private records.
- [plot_sce_information_update_results.py](plot_sce_information_update_results.py) — Plot aggregate information-time follow-up results; no API or private rows read.
- [plot_sce_news_breadth.py](plot_sce_news_breadth.py) — Figures from aggregate news-allocation results; no personal data or APIs.
- [plot_sce_psychological_wave_results.py](plot_sce_psychological_wave_results.py) — Render the saved aggregate comparison; no data fitting or model calls.
- [plot_sce_purchase_frequency_results.py](plot_sce_purchase_frequency_results.py) — Plot aggregate purchase-frequency contrast results; no API or private rows read.
- [plot_sce_reference_validation.py](plot_sce_reference_validation.py) — Scientific figures from the frozen 12-wave evaluation; aggregate outputs only.
- [plot_sce_regression_contributions.py](plot_sce_regression_contributions.py) — Scientific figure for the existing regression-diagnostic reading page.
- [plot_sce_revision_format_results.py](plot_sce_revision_format_results.py) — Aggregate figures for the revision-format pilot; no API or individual rows.
- [plot_sce_spending.py](plot_sce_spending.py) — 专题入口；运行前读文件说明与对应批次记录。
- [plot_sce_targeted_profiles.py](plot_sce_targeted_profiles.py) — Plot aggregate profile differences; no fitting or API access.
- [render_current_todo.py](render_current_todo.py) — Render the current NEXT_ACTIONS checklist as a small local reading page.
- [render_sce_anchor_direction.py](render_sce_anchor_direction.py) — Render aggregate anchor-alignment diagnostics, without accessing person rows.
- [render_sce_behavior_comparison.py](render_sce_behavior_comparison.py) — Render a frozen public comparison summary as a local, offline reading page.
- [render_sce_confidence_report.py](render_sce_confidence_report.py) — Aggregate-only figures and result update in the existing news reading page.
- [render_sce_expanded_results.py](render_sce_expanded_results.py) — Render frozen aggregate results into the existing project reading page.
- [render_sce_inertia_calibration.py](render_sce_inertia_calibration.py) — Render fixed-weight offline diagnostics into the existing SCE reading page.
- [render_sce_mechanism_evidence.py](render_sce_mechanism_evidence.py) — Render aggregate, zero-API mechanism evidence into the existing reading page.
- [render_sce_news_exposure_report.py](render_sce_news_exposure_report.py) — Append actual aggregate results to the existing news reading HTML.
- [render_sce_news_response_diagnostic.py](render_sce_news_response_diagnostic.py) — Add reviewed diagnostic aggregates to the existing HTML; no browser or network.
- [render_sce_pe_diagnostic.py](render_sce_pe_diagnostic.py) — Render an offline audit into static scientific plots and a browser report.
- [render_sce_population_associations.py](render_sce_population_associations.py) — Render aggregate-only real-data results; no modelling or API in this step.
- [render_sce_population_guide.py](render_sce_population_guide.py) — Render the requested fixed reading handout, not simulation code or inputs.
- [render_sce_prior_report.py](render_sce_prior_report.py) — Render aggregate scientific figures and append results to the existing reading page.
- [render_sce_progress_report.py](render_sce_progress_report.py) — Render the agreed progress briefing as PDF and a matching local HTML reader.
- [render_sce_response_gap.py](render_sce_response_gap.py) — Render the existing reading-page supplement from cached aggregate results.


### 其他入口（23）

- [archive_sce_expanded_public_policy.py](archive_sce_expanded_public_policy.py) — Archive public Fed statements and a Gallup topline; no model API or credentials.
- [archive_sce_gasoline_support.py](archive_sce_gasoline_support.py) — Archive missing weekly FRED GASREGW history separately; preserve original cache.
- [archive_sce_public_brief_sources.py](archive_sce_public_brief_sources.py) — Archive a fixed small list of free official evidence; never calls an MCP/LLM.
- [backtest_sce_macro_profile_extension.py](backtest_sce_macro_profile_extension.py) — Offline rolling population-margin comparisons; no simulation calls.
- [decompose_sce_reference_regression.py](decompose_sce_reference_regression.py) — Attribute existing response-regression R2 and diagnose overlapping predictors.
- [derive_sce_expanded_program.py](derive_sce_expanded_program.py) — Materialize every program prediction WITHOUT reading current real answers.
- [expand_sce_core_normal.py](expand_sce_core_normal.py) — Expand a completed single-month Core run; reads NO actual questionnaire truth.
- [extend_sce_baseline_inputs.py](extend_sce_baseline_inputs.py) — Compile a new latest-data baseline version without rewriting the 60-month sources.
- [extend_sce_environment_sources.py](extend_sce_environment_sources.py) — Append E source caches and prepare an isolated candidate, never run simulation.
- [extract_cpi_components.py](extract_cpi_components.py) — Extract household-perceivable CPI component 12-month changes from the
- [freeze_sce_information_exposure.py](freeze_sce_information_exposure.py) — Freeze prepared information views for the existing executor; no API calls.
- [inspect_sce_beta_reference_support.py](inspect_sce_beta_reference_support.py) — Evaluation-only inverse diagnostic, NEVER an Agent input or scoring rule.
- [inventory_sce_matching_fields.py](inventory_sce_matching_fields.py) — 专题入口；运行前读文件说明与对应批次记录。
- [inventory_sce_population_mechanisms.py](inventory_sce_population_mechanisms.py) — Local public-field inventory only: no model/API/runtime changes.
- [inventory_sce_subjective_models_reference.py](inventory_sce_subjective_models_reference.py) — Inspect public replication data locally; save aggregate inventory only.
- [preflight_sce_run.py](preflight_sce_run.py) — Render/inspect a planned SCE run without instantiating an LLM client.
- [preview_sce_dated_environment.py](preview_sce_dated_environment.py) — Render actual EnvironmentProvider observations offline; never invokes B/API.
- [record_sce_matched_progress.py](record_sce_matched_progress.py) — Describe existing stages on identical person-generation support; no API.
- [replay_sce_core_size.py](replay_sce_core_size.py) — Subsample completed LLM Core responses. No new answers, calls or actual truth.
- [sce_cpi_layout.py](sce_cpi_layout.py) — Deterministically read annual CPI component changes from BLS release PDFs.
- [sce_llm_probe.py](sce_llm_probe.py) — SCE LLM probe — explicit, counted, tiny paid interactions with the configured endpoint.
- [sce_release_available.py](sce_release_available.py) — Parse available first-release CPI fields without inventing missing months.
- [split_sce_basket_population.py](split_sce_basket_population.py) — Split one already-built full basket population into Core/Normal, offline.
