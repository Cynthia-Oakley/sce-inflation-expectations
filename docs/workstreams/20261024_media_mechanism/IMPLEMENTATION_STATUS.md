# 新闻机制 V3：实施状态与证据

更新：2026-10-25。主线方案见 `NEWS_MECHANISM_PLAN_V3.md`。本页记录实际完成情况，不把代码就绪表述为模拟完成。

**最新实际状态：用户Terminal真实运行及评价已完成。**6,720尝试/6,704技术可用，15连接失败＋1十档键错误、未知在途0，API报告$4.499549192＋未知费预留$0.057531933。离线分析统一641个人月：Q0中心MAE0.485、Q3 0.439，W1 2.742→2.668；524真实上期支持上Q3 0.433/照抄0.332。2021部分改善但2022高估、微观压缩仍在，删除2021-06后Q3主MAE优势反转。未改默认或重跑A82/B11。详[结果说明](RESULTS_20261025.md)、[图文结果](results_v1/index.html)。下文未启动条目为准备阶段记录，不代表当前状态。

**Codex后续接线：**逐请求容错和独立Terminal入口已补在[执行附录](TERMINAL_EXECUTION_ADDENDUM_20261025.md)。最终执行目录是 `outputs/sce_media_mechanism_terminal_20261025_v2/`，复用原70个Core验收和全部冻结提示，新增完整6,720请求位置伪接口回放；0真实API。自动评价同时列出同支持照抄上期基线，旧job级入口保留，不与新入口混用。用户本人显式Terminal启动才记录本批新授权；当前未启动。

## 已完成

1. **NYT 补充标签**：七个月 1,374 篇 keep，172/172 批成功，0 错误、0 重试。实际 prompt 219,377 tokens、completion 43,361 tokens，按峰值费率估算 **$0.117846**；用户批准上限 $0.61。
   - 原始请求、意图、回复、标签与账本：`outputs/sce_news_mechanism_labels_20261025_v1/`
   - 冻结输入：`outputs/sce_news_mechanism_label_preparation_20261025_v1/`
   - 恢复复算：172 个已尝试批次、172 个有效批次、1,374 篇有效标签，费用一致。
2. **标签审校**：21 条共同新闻逐条复核，84 篇按月×语气分层样本复核。样本原一致率 tone 79/84、persistence 68/84；25 篇形成 26 个字段的独立审校覆盖值，原始标签和回复不改写。
   - 审校规则与覆盖值：`outputs/sce_news_mechanism_label_audit_20261025_v1/review.json`
   - 共同候选和分层样本：同目录 `common_candidates.json`、`stratified_sample.json`。
3. **机制与执行代码**：R0/Q0/Q1/Q2/Q3、4/8/16/32 四档、正式 tone 加权、CPI 确定性加权、Fox 配额、只改新闻的提示替换、唯一 run_id、官方 Core 执行入口、只续未启动任务的恢复、A82 单遍参照评价适配。
4. **离线验证**：80 项相关测试通过；两个月实际各 480 份提示组装通过。七个月完整工程组装、70-job manifest、评价附件及一个官方 Core scripted 任务均通过，提示哈希一致。独立审查后已注册独立 `v32_news_mechanism_v3` 适配器，并锁定评分、归一化和传输依赖。
5. **Fox 旧样本英文文本**：2021-06 26 篇、2022-06 21 篇已补原网页英文标题和导言，CJK 检查为 0；原始 HTML 存于 `outputs/sce_fox_news_20261025_v1/<month>/raw/existing_english/`，结构化映射在同目录 `existing_english/`。Q2 旧池实际 Fox 曝光均为 264 篇。
6. **Fox 新候选与标签**：五个缺失窗口公开采集完成，1,132 篇六字段补标全部有效，估算 $0.124354；410 篇复核后采纳25处覆盖修订。审校后七个月 keep 池为132/145/26/128/282/21/90篇。详见 `FOX_LABEL_REVIEW.md`。
7. **正式执行包与历史证据**：`outputs/sce_media_mechanism_v3_20261025_v1/` 已生成并接入评价；70 jobs、3360提示位置、6720物理调用上限。离线验收 `offline_acceptance.json` 通过。1,179篇候选中1,177篇找到Wayback快照，2篇保持unverified；快照不等于逐字历史文本比对。
8. **70-job 官方 Core 干跑**：70/70完成、70/70 scripted、70/70提示哈希一致、0真实API调用。`authorization_decision.json` 记录用户于2026-10-25选择“暂不启动”；`authorization.json` 保持 `approved:false`。恢复与后续评价命令见 `RUNBOOK_V3.md`。

## 尚未完成

- 6,720 次真实模拟及结果评价：用户已明确**暂不启动**，当前 0 次；后续须重新明确授权，不自动续用本次预算卡。

## 主要源码

- 补标：`studies/sce_inflation_expectations/news_mechanism_labels.py`、`news_mechanism_label_preparation.py`、`news_mechanism_label_runner.py`
- 新闻机制：`studies/sce_inflation_expectations/experiments/media_mechanism_v3.py`、`media_mechanism_v3_preparation.py`、`media_mechanism_v3_execution.py`
- 评价：`studies/sce_inflation_expectations/evaluation/media_mechanism_v3.py`
- 入口：`scripts/prepare_sce_news_mechanism_labels.py`、`scripts/run_sce_news_mechanism_labels.py`、`scripts/run_sce_media_mechanism_v3.py`、`scripts/evaluate_sce_media_mechanism_v3.py`

## 复算命令

```bash
cd /Users/wushuyue/Documents/科研/DISC/socioverse_challenge
PY=/Users/wushuyue/anaconda3/envs/socioverse/bin/python
$PY -m pytest \
  tests/test_news_label_compat.py \
  tests/test_sce_news_mechanism_labels.py \
  tests/test_sce_news_mechanism_label_runner.py \
  tests/test_sce_media_mechanism_trial.py \
  tests/test_sce_media_mechanism_v3.py \
  tests/test_sce_media_mechanism_v3_preparation.py \
  tests/test_sce_media_mechanism_v3_execution.py \
  tests/test_sce_media_mechanism_v3_evaluation.py \
  tests/test_sce_frozen_trial_transport.py \
  tests/test_sce_frozen_trials.py \
  tests/test_sce_fox_news_archive.py \
  tests/test_sce_fox_mechanism_preparation.py -q
```

补标命令仅作审计追溯，**不要重新执行**：原目录已有完整账本，失败或不确定批次也不能借“ resume”重发。后续运行命令将在完整执行包通过干跑后单独登记。
