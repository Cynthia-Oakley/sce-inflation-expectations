# Kimi → Codex 交接说明（2026-10-05）

适用：Codex 接力 SCE 项目前的状态对齐。仓库 `socioverse_challenge`，分支 main，最新 commit `022bc55`。

## 一、当前状态（干净、可接力）

提示词 v2 工作块已闭环并全部提交：

| 决策 | commit | 内容 |
|---|---|---|
| D050 | `d14283e` | as_of 口径改为"t 月 CPI 首发日当天 23:59 ET"（实证：真实受访者中位访谈日每月 15 号，已看到 M−1 期数据） |
| D051 | `7a82aee` | E v2 历史序列扩为 6 条 × 12 点滚动（CPI/失业率/食品/能源/住所/汽油），每步 77 信号 + 30 事件 |
| D052 | `873b4cc` | 提示词 v2 渲染器（`build_sce_messages_v2`），prompt_version 门控，v1 原样保留 |
| 摘要变体 | `022bc55` | `prompt_version="sce-q8-q9-v2-abstract"` 启用标题+摘要版（~2,368 tokens，纯标题版 ~1,225） |

- 全量测试 108/108：`/Users/wushuyue/anaconda3/envs/socioverse/bin/python -m unittest discover -s tests`（约 2.5 分钟；输出中 "verify FAILED" 行是测试故意触发的篡改检测场景，`OK` 即通过）。
- 样例：`studies/sce_inflation_expectations/reports/PROMPT_V2_SAMPLE_20261005.txt`（纯标题）、`PROMPT_V2_ABSTRACT_SAMPLE_20261005.txt`（标题+摘要），同一真实 persona、2021-06。
- 提示词 v2 **未冻结**：按 D045c 需开发月（2021-05/06）真实 LLM 验证后才冻结，随后主窗口 2021 全年整窗重跑。

## 二、重要：未提交文件不要动（10-03 批次待用户过目）

`git status` 里有一批 `M`/`??` 文件是 10-03 D047 修复批次的产物，**用户尚未过目，刻意未提交**：

- `docs/DECISIONS.md`、`proposal/proposal.md` —— 混有 10-03 批次改动 + D050/D051/D052 已批准条目，**不得提交、不得还原**；如需引用 D050+ 决策，以 NEXT_ACTIONS.md 已提交条目为准。
- `scripts/build_sce_evaluation_truth.py`、`build_sce_population.py`、`analyze_sce_wave_stats.py`、`studies/.../scoring/{sce_q9_frozen.py,beta_fit_kernel.py}`、`tests/test_build_sce_population.py`、人口/统计产物若干、`docs/A_B_LINE_CONTRACTS.md`、`reports/PROMPT_IO_REVIEW_20261003.md`。

规则：新工作在新文件或未脏文件上做；提交一律 scoped add，严禁 `git add -A`。

## 三、下一步待办（按优先级）

1. **开发月真实 LLM 验证**（冻结前最后一关）：DeepSeek、73 或 100 人 × 2021-05/06，用 v2 环境三件套 + `prompt_version="sce-q8-q9-v2"`。两件事必须先做：① 核实 `scripts/run_sce_local.py` 的 decision_args 如何传 `prompt_version`（未核实）；② 用户确认预算（此前 20 人 × 2 月约 $0.014，量级参考）。建议把 标题 vs 标题+摘要 作为消融对照一并跑。同轮评估同质化问题（模拟月内 std 0.27–0.81pp vs 真实 5.5–7.5pp，D051 已入档）。
2. **冻结 → 主窗口 2021 全年整窗重跑**（10/7 内部 DDL 的核心交付）。
3. **请 Codex 审计本块**：D050/D051/D052 四个 commit 的方法与数据正确性（重点：as_of 新口径的 PIT 合规性、77 信号的转录抽查、渲染器与 v1 的 Q8/Q9 契约一致性）。
4. 未启动项：B 线人口外推实现、core/normal 规模零 LLM 抽样精度试验（300/500 重复抽样）、2026 前瞻窗 v2 环境。
5. 用户过目 10-03 批次后统一提交 DECISIONS/proposal 等。

## 四、工程环境备忘

- Python：`/Users/wushuyue/anaconda3/envs/socioverse/bin/python`，命令 `cwd=socioverse_challenge`。
- v1 既有文件（`scripts/build_sce_environment.py`、`run_sce_local.py`、`build_nyt_events.py`）与 archived 数据产物**只读不改**；v2 新文件自由改；临时产物写 `/tmp/sce_tmp/`。
- 数据获取优先确定性解析（本地缓存 + 已验证正则），不在上下文里通读 PDF。
- 密钥位置：NYT key 在主仓库 `.env`，OpenRouter key 在官方仓 `.env`（均 gitignored）。OpenRouter 为 OpenAI 兼容端点，extra_body 不可传 DeepSeek 私有 thinking 参数。
- 协作规则全文见 `AGENTS.md`（19 条）与 `docs/AGENT_HANDOFF.md`。
