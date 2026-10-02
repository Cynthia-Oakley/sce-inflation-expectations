# 云端 v3 scripted 审计版记录

> 2026-10-01 Codex独立复核补注：下述文件哈希自洽/回答一致检查已复跑通过，但归档`model.py:73`写入字面量`\\n`，取回JSONL为正常LF；临时隔离执行已复现差异。缺少转换记录或实际运行源码版本说明，因此“运行时代码—原始日志”链条仍待补证，不能仅凭现有哈希称完全闭合。详见 [独立审计](BETA_AND_KIMI_REVIEW_20261001.md)。原始归档未改。
>
> 2026-10-02 Kimi 复核补注（P2 收尾）：① `answers.jsonl` 并非 `model.py` 写出——归档源码全文唯一写文件语句在第 73 行、只写 observations；answers 由平台从运行状态导出，其 LF 格式与第 73 行无关，此半截差异消除。② `observations.jsonl` 与平台侧生成的 `audit_manifest.sha256` 逐字节相符，而按归档源码第 73 行执行只会写出字面量 `\n`——说明平台在“执行 → 落盘/哈希”之间存在一次换行规范化，或实际执行代码与持久化代码不是同一份；该格式层断点保留为缺口。③ 内容层获独立 corroboration：平台自身轨迹库 `api_files/trajectory/panel_live.jsonl`（60 行 = 20 agent × 3 step，step 0 为初始状态）中，`action_payload` 与 answers 40/40 一致、`state.signals` 与 observations 的 signals 40/40 一致。**结论：v3 的 Observation/回答内容有平台独立记录佐证；仅 sidecar 文件的换行框架存在未解释的平台侧转换。**后续运行按 [研究协议](RESEARCH_PROTOCOL.md) 第 6 节附加协议执行（运行前封存源码哈希、行为函数自报哈希写入 run_manifest、记录全部转换）。

核查日：2026-10-01。操作：Kimi 经 kimi-webbridge 使用用户已登录浏览器会话（用户授权 D031）；云端写入前均已报备意图。前序 v2 见 [CLOUD_V2_PILOT_RECEIPT](CLOUD_V2_PILOT_RECEIPT.md)。

## 结论

**v3 补齐了 v2 缺失的运行时证据：唯一 run_id、40 条实际传入 `decide_batch` 的 Observation（含逐条 SHA-256）、40 条原始回答、费用账本与哈希清单，全部取回；回答与 v2 归档逐字段一致，确认 scripted B 在同 P/E/seed 下可精确复现；Observation/回答内容与平台自身轨迹库独立记录 40/40 一致。已知缺口：sidecar 文件换行格式与归档源码存在一层未记录的平台侧转换（见文首补注），故不称证据链完全闭合。v4（真实 LLM）仍冻结：平台工作区无法给出模型 ID/报价。**

## 过程与费用

- 平台方案先行停在确认点（全文：`data/raw/cloud_exports/2026-10-01/workbench_v3v4_plan_reply.txt`）；用户批准阶段一+二后执行。
- 阶段一：v2 流程型报告已生成（只写流程与诊断，3 张图），study 管线到报告阶段。
- 阶段二：/sv-iterate 创建 v3 新版本（非 branch），`model.py` 增加 `_audit_observations`（相对 v2 仅 +22 行 diff：audit_dir/run_id 注入与 Observation JSONL+SHA-256 写入），P/E/B/seed/月份不变，冷跑 20 人 × 2021-05/06。
- 本轮云端对话费：方案 $1.13 + 执行 $1.75 + 小文件取件 $1.22 + observations 首块 $0.55 + base64 编码与 answers 取件 $2.84 + observations 补块 $1.58 + model.py 取件 $1.60 ≈ **$10.67 Chat**；另有一次哈希重复循环中断（费用未单列）。Sim 额度未动。期间界面读数：余额 $15.18/$30。
- 中途事件：首次全量取件时平台助手复述哈希陷入重复循环（`47f757c6…` 片段重复 675 次），已中断；改用小文件逐块 + gzip+base64 编码取件后全部 byte-exact。

## run 与产物

- run_id：`sce_inflation_expectations-v3-2c40f389c0d24e1ab1e963918b3bfec9`；UTC 2026-10-01T03:32:21.977346Z → 03:32:22.685069Z；seed 42；20×2；`deterministic-scripted-v1` / `sce-q8-q9-scripted-v1`。
- 取回目录：`data/raw/cloud_exports/2026-10-01/sce_inflation_expectations_v3/`，含 `run_manifest.json`、`cost_ledger.json`、`audit_manifest.sha256`、`observations.jsonl`（101,686 B）、`answers.jsonl`（31,040 B）、`model.py`（217 行，10,590 B，SHA-256 `8b38d958…` 与平台一致）、取件用 `.gz.b64`、`PROVENANCE.md`、`local_v3_audit.json`。
- 费用账本如实记 `billing_status=not_available`、三类调用均为 0、`verified_usd=null`——无平台账单明细，不能把 $0 当已核验账单。

## 本地核验（`scripts/audit_cloud_v3_audit.py`，全部通过）

1. 五个审计文件哈希与 `audit_manifest.sha256` 逐条一致（`validation_errors.jsonl` 为空文件哈希，平台侧无校验错误）。
2. Observation 哈希算法核定：`sha256(json.dumps(obs, ensure_ascii=False, sort_keys=True, separators=(",",":")))`，与 v3 `model.py` 源码一致；40/40 自洽。注意 step-2 含非 ASCII（`ensure_ascii=False` 是必要条件）。
3. 40 条 Observation 覆盖 20 agent × 2 step，`as_of` 符合截止规则（2021-04-30 / 2021-05-31 23:59:59-04:00）。
4. 40 条回答 Q9 十档合计=100、Q8 符号/幅度一致；与 v2 归档 `raw_q8_q9.jsonl` 逐字段一致（40/40）。
5. Q8 诊断中位数 1.43/2.31 与 v2 相同——仍是流程诊断，不是预测效果；未计算官方 Q9 headline。

## 平台能力与限制（本轮实测更新）

- 工作台无下载按钮、无 zip/工作区文件渠道；逐块文本复制仍是唯一取件方式，但 **gzip+base64 通道可 byte-exact 取件**（以 audit_manifest 哈希校验为准），长 JSONL 直接粘贴会丢尾部花括号，不可直接用。
- 平台确认：原生运行不持久化 Observation/run_id/费用流水，须 study 级审计 sidecar（v3 已落地）。
- v4 报价：工作区无可读配置，provider/模型 ID/知识截止/token 估算均「无法确认」；平台称实际报价只会在 v4 运行确认卡给出。

## 缺口与下一步

- v4 决策：是否授权创建 v4 并走到 sv-run 费用确认卡读取实际报价（读到为止、不确认运行），由用户定。
- answers/observations 之外的运行产物（DuckDB 轨迹、报告原文）未取回；需要时按 base64 通道补取。
- v3 仍是 scripted 工程证据；真实 LLM 行为、历史 P 与 Beta 精确计分分别等 v4 预算、T02、T01。

## 追加：隐藏文件 API（2026-10-01 发现）

平台存在未公开的文件接口：`/api/study/<id>/files`（清单）与 `/api/study/<id>/file/<dir>/<name>`（文本内容）。已验证 byte-exact（simulation.json 与 v2 归档哈希一致），并经此补取 roster.jsonl（20 行，补 v2 缺口）与 environment.json。限制：仅文本、二进制 415、audit/ 目录不暴露。后续文本类取件优先走 API，二进制仍走 gzip+base64 对话通道。
