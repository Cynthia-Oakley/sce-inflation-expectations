# SCE 一年期通胀预期 study

队伍：水上挽月。赛道：A。状态：**本地可运行（scripted 已验收；openai 真实 LLM 待用户 API key 与预算确认）**。

目标是模拟家庭对未来一年通胀的点预测与十区间主观概率，再按 SCE 口径聚合；总体主指标拟为个人密度均值的加权中位数。P 用历史可得画像，E 用带发布时间和版本的信息。当前主研究不模拟家庭行为决定实际宏观价格。

`model.py` 实现四个 abc 并提供双模 B：`llm_kind="scripted"` 为确定性流程校验规则（与云端 v3 归档逐字段一致，非估计量）；`llm_kind="openai"` 走任意 OpenAI 兼容端点，逐次调用全量审计（提示词/原始响应/usage/requested/returned model/request_id/重试/错误），Q9 校验不归一化、失败不回退规则。P/E/B 输入白名单见 [RESEARCH_PROTOCOL](../../docs/RESEARCH_PROTOCOL.md)。

## 运行入口（已验收，2026-10-03）

```bash
PY=/Users/wushuyue/anaconda3/envs/socioverse/bin/python
# 1. scripted 离线运行（零费用；自动先做单向导出）
$PY scripts/run_sce_local.py --llm scripted
# 2. 与云端 v3 归档的 40/40 复算审计
$PY scripts/audit_local_scripted_replay.py <run_id>
# 3. 真实 LLM（需用户先在官方仓 .env 放 SV_LLM_API_KEY；两条命令均计次数）
$PY scripts/sce_llm_probe.py --list-models                     # 免费目录读取
$PY scripts/sce_llm_probe.py --sample 2 --model <model> --confirm-spend
$PY scripts/run_sce_local.py --llm openai --model <model> --max-calls 100 \
     --extra-body '{"thinking": {"type": "disabled"}}' --confirm-spend
```

运行产物：轨迹库在官方仓运行副本 `trajectory/<run_id>.duckdb`，审计 sidecar 在本仓库 `outputs/local_runs/<run_id>/`（observations.jsonl / llm_calls.jsonl / metrics_history.json / cost_ledger.json / run_manifest.json）。两个位置均被 gitignore，按 run_id 保留、禁止覆盖。

各子目录的 README 定义职责；结构见 [项目结构](../../docs/PROJECT_STRUCTURE.md)，研究定义见 [SCE 方案](../../docs/SCE_PROJECT_PLAN.md)，当前任务见 [任务板](../../docs/NEXT_ACTIONS.md)。

未来必须保存：可得输入快照、P 抽样版本、问卷/prompt、模型、配置与种子、回答验证、失败与费用、计分方法、基线和留出评测。模拟与评价分阶段运行，真值不进入 B。
