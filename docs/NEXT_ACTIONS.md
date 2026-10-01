# 当前任务板

更新：2026-10-01（T03-L 完成；云端 v3 审计版完成并取回核验，见 [CLOUD_V3_AUDIT_RECEIPT](CLOUD_V3_AUDIT_RECEIPT.md) 与 D031–D033）。只推进 SCE；队伍名为水上挽月。日期以 [ROADMAP](ROADMAP.md) 为准。每项任务只标真实进度。

## 当前接力：v4 决策点 + T01 方法研究 + 提案撰写

- 交接入口：[AGENT_HANDOFF](AGENT_HANDOFF.md)；用户发给 Kimi 的[启动提示](KIMI_START_PROMPT.txt)。以下负责人是协作安排，不表示已经启动了另一 Agent。
- **云端 v3 已完成（2026-10-01，Kimi）**：v2 流程报告生成（6/6 不含论文/文献阶段）；/sv-iterate 创建 v3 scripted 审计版并冷跑 20 人 × 2021-05/06，`model.py` 仅 +22 行审计 diff。run_id `sce_inflation_expectations-v3-2c40f389c0d24e1ab1e963918b3bfec9`；`audit/v3/` 六件（run_manifest/cost_ledger/audit_manifest/observations×40/answers×40/validation_errors 空）+ v3 `model.py` 全部取回，`scripts/audit_cloud_v3_audit.py` 核验通过：文件哈希与清单逐条一致、Observation 哈希 40/40 自洽（算法与源码一致）、回答与 v2 归档逐字段一致 40/40。费用账本 `billing_status=not_available`。云端对话费约 $10.67，Sim 未动。取件坑与 base64 通道见收讫文档。
- **v4 已冻结（用户 2026-10-01 决定，D034）**：平台工作区无法确认真实 LLM provider/模型 ID/知识截止/报价；v4 保持冻结，优先完成开题提案（内部目标 10-08）。未来解冻路径：授权走到 v4 sv-run 确认卡只读报价 → 用户批准预算 → 运行。
- **T03-L 本地验收已完成（2026-10-01，Kimi）**：补装 `scipy 1.17.1`/`openpyxl 3.1.5`；SCE 测试 12/12（Q9 计分 5 + 新增导出 7）；v2 归档审计两脚本通过。新增 `scripts/export_study_runtime.py`（单向导出 + `--verify` + 逐文件 SHA-256）与 `tests/test_export_study_runtime.py`，已真实导出到官方仓 `studies/sce_inflation_expectations/`（gitignored，不另养源码）。MCP 两服务连接与免费目录实测通过：`event_tool` 21 个来源（含 nyfed_sce/fred/bls/census_acs/sipp 等）、`user_pool_survey_mcp` 免费探测全过（matraix_1m 56,583 索引用户等），付费工具均未调用，脱敏归档在 `data/raw/mcp_checks/2026-10-01/`。完整命令与边界见 [LOCAL_RUNTIME_ACCEPTANCE](LOCAL_RUNTIME_ACCEPTANCE.md) 末节。`scoring/sce_q9.py` 本轮未动。
- **Kimi 后续**：v4 按用户决定执行或冻结；v3 证据写入提案（流程可行性段）；T02 历史 P/E 与发布日历；需要时补取 v3 轨迹 DuckDB/报告原文。
- **Codex 下一任务 T01**：官方 Beta 拟合差异与历史证据调研，主要负责 `docs/SCE_Q9_SCORING_REPLICATION.md`；需改 scoring 时先标记占用，避免与 Kimi 同改。本轮完成的是交接/环境检查，尚未新增 Beta 研究结果。
- **后续汇合 T02**：历史 P/E 与发布日历/简单基线；MCP 小样可取 2020-04、2022-06、2024-12（注意结构化取数按次计费，先核预算）。提案沿既有日程并行推进。
- 主仓库大量文件未提交；最近本地 commit 仍为 2026-09-27 的 `d63cbae`。分任务检查后保存，不假定最新工作已推送 GitHub。今日改动文件：`scripts/export_study_runtime.py`、`scripts/check_mcp_free_capabilities.py`、`scripts/audit_cloud_v3_audit.py`、`tests/test_export_study_runtime.py`、`docs/{LOCAL_RUNTIME_ACCEPTANCE,NEXT_ACTIONS,DECISIONS,CLOUD_V3_AUDIT_RECEIPT}.md`（归档 `data/raw/{mcp_checks,cloud_exports}/2026-10-01/` 在 gitignore 内）。

## 已完成

- [x] SCE 2020–2024 年 60 个月数据与跨人聚合核验：[审计](SCE_DATA_AUDIT.md)。不含从十区间重新拟合个人密度。
- [x] Event/Population MCP 公开文档和客户端审计：[记录](SOCIOVERSE_MCP_AND_PMI.md)。未验收真实服务。
- [x] 项目目录、开发规则、study draft 元信息、统一日程与交付清单。
- [x] 今日 P/E/B 材料与云端首试包：[交接计划](TODAY_PEB_EXECUTION_PLAN.md)、[平台上传顺序](../proposal/cloud_input/README.md)。已补下官方 SCE 2017–2019 微观、图表指南、2019 ACS PUMS 字典/说明及 BLS 2021 年四份归档发布稿；下载清单见 [补充来源](peb_source_manifest.json)。
- [x] 平台报告 v2 以 20 人 × 2 月完成 deterministic scripted 首试；40 条原始 JSONL、`model.py`、`environment.json` 和 `simulation.json` 已取回并核对哈希。环境中六条 BLS 信号与 20 个合成画像和本地来源逐字段一致；本地 P/E 重演 40 条 Q8/Q9 全部一致。状态与证据边界见[云端 v2 首试记录](CLOUD_V2_PILOT_RECEIPT.md)；取件阶段结束，C4 仍未全部通过。
- [x] T01 计分器首轮复现：Q9 单档均匀与相邻双档三角分支在 2020-01、2022-06 的真实个人派生值上基本精确；广义 Beta 分支仍有开放尾和空档误差。官方个人 `Q9_mean` → 月度 chart 已复核，自己的 Beta 拟合 → chart 尚有约 0.007/0.011 个百分点误差。[完整记录](SCE_Q9_SCORING_REPLICATION.md)。

## 执行方式：云端证据归档，本地能力开始验收

按 [云端预试验方案](CLOUD_PILOT_PLAN.md) 已完成 v2 的小样流程及原始回答、B 代码、E/P、simulation 配置复核。真实运行 Observation、独立 run ID 和费用流水未持久化；这些缺口在下一次运行前改设计，不继续追取 v2。2026-10-01 用户已配置 Claude Code + Kimi，开始 T03-L 本地开发验收；沿用已有代码/材料，不重做整套框架。以下 T00–T04 是验收职责，执行位置按可用能力决定。

## 优先前置：项目级数据可得性

### T00｜最小数据可得性筛查（Agent 主导，部分基础已完成，历史输入未验收）

- 范围：Y 真值、P 人口、E 信息、B 问卷/计分、基线与数据许可；不只检查 P/E。
- 具体步骤、当前缺口及进入后续工作的门槛见 [数据审计中的 T00 清单](SCE_DATA_AUDIT.md)。
- 输出：各用途的数据验收卡、实际样例、时间证据、月份覆盖与可做任务的结论；沿用已有来源台账。
- 当前 Y 与部分计分材料已有实测；首试两月的 BLS 原始发布 E 与平台保存的环境配置已核对，但运行时 Observation 未保存；历史 P 仍待核实。可选新闻/CE 不阻塞公开基础版。
- T01 可利用现有数据开展小范围计分验证，T03 可同步验收平台；完整 Agent/批量回测按数据验收门槛推进。

## 随后：三个准备任务按依赖汇合

### T01｜计分器（首轮实现并验证，Beta 精确复现未完成）

- 输入：SCE 官方问卷、方法附录、已下载真实 Q9 概率与派生字段。
- 修改区：`studies/sce_inflation_expectations/scoring/`、相关 `tests/`；更新数据审计。
- 已实现：`scoring/sce_q9.py` 按官方分支处理十档回答；只读审计脚本在两个相隔较远月份逐人对照均值、四分位数、IQR 等，并对照全国指标。结果和命令见[计分复现](SCE_Q9_SCORING_REPLICATION.md)。
- 尚需验收：Beta 开放尾和不连续概率档的原始优化细节；扩展到 60 个月的覆盖和误差统计。不能把当前近似 Beta 结果命名为纽约联储官方 headline。
- 后续：T04 先导出 B 的原始 Q9，再在本地计分；只有数值口径和云端依赖都通过后，才考虑把模块集成到 SocioVerse2。无法完成时先与导师讨论并记录点预测目标调整，不按测试表现挑目标。

### T02｜历史 P/E 验收与构建（Agent；学校样例由用户获取，待开始）

- 前置：T00 的对应来源/字段/时间样例检查；T02 负责扩展到实际 P/E 管线与正式月份覆盖。
- 输出：逐月 release 日历、历史 P 版本证据、开发月宏观信息快照与字段契约；登记来源和修订版本。
- 修改区：`data/`、study 的 `population/`、`environment/`、`grounding/`。
- 验收：P/E 不带同期真实回答/权重；unknown 和 future 发布时间被隔离；过去发布值基线有日期依据。
- MCP 优先取 2020-04、2022-06、2024-12 小样检查；无服务权限直接推进官方宏观数据路径。学校先验收新闻样例，不盲目全量下载。

### T03｜云端能力验收（原始配置/回答已复核，历史日志缺口留待新版本）

- 已核对官方工作流和公开上传/导出代码；本地 Agent 尚未进入用户账号。用户的 Event 查询反馈见下一条，其他能力仍按实际回执验收。
- 2026-09-30 用户转述平台已在同一 `sce_inflation_expectations` study 创建 v2，保留 v1 快照，并报告：六条 BLS 历史 E 经 `observe_batch` 进入 B，20 条合成 P 已物化，40 条 Q8/Q9 scripted 原始回答已生成，真实 LLM/新付费 MCP 调用为零。完整状态和诊断数值见[首试记录](CLOUD_V2_PILOT_RECEIPT.md)。v1 只有 synthetic E 方案，没有运行基线。
- 平台进一步说明：托管工作台当前无 ZIP/二进制下载按钮，观察面板只读，但能通过对话分块输出文本。40 条 JSONL、199 行 `model.py`、318 行 `environment.json` 与 497 字节 `simulation.json` 的原始字节已还原并与平台 SHA-256 匹配。环境里的六条 BLS 信号和 20 个合成画像与本地来源相同；simulation 的两步、scripted 决策、seed 42 与原始回答相符。本地按代码复算 40 条 Q8/Q9 全部一致。平台确认**未保存 v2 实际传给 `decide_batch` 的 Observation**，先前展示是事后检查；独立 run ID 和费用流水也未持久化。v2 取件到此结束，下一次运行需留真实输入日志。代码的静默缺失回退、Q9 与 E 无关、仅收入字段影响 Q8 等局限见[完整审计](CLOUD_V2_PILOT_RECEIPT.md)。C4/T04 尚未全部完成。
- 用户指出真实 LLM 回放的**模型参数时间泄漏**：目前不知道托管研究助手的模型/截止，未来模拟 B 的基础模型也未选定。v2 代码审计确认 B 为规则式、无模拟 LLM 调用，也未直接引用 SCE 真值；但 `0.55` 等系数是事后编写且无来源，不能报告预测效果。真实 LLM 前按[时间泄漏协议](MODEL_TEMPORAL_LEAKAGE.md)登记模型来源；可把[只读模型溯源问题](../proposal/cloud_input/request_llm_provenance.md)发给平台。训练边界晚于目标 `as_of` 或未知的 2021 年 LLM 结果不能称严格事前预测。
- 按 C0–C4 验证：输入与建模确认、极小合成文件人口、MCP 样例、定制计分、scripted 两月流程、完整导出与本地重算。
- 云端费用确认遵守平台流程，记录 Agent 与 Simulation 两类余额；不根据旧 FAQ 推断上传不可用。
- 若通过，继续云端或云端生成回答/本地计分；若受规模、代码控制、依赖、导出限制，再启动 T03-L 本地环境验收（Python 3.11+、官方 demo、依赖锁定）。
- 输出：能力/费用/导出验收记录见[CLOUD_V2_PILOT_RECEIPT](CLOUD_V2_PILOT_RECEIPT.md)；回答、模型、环境和模拟配置已取回并复核。独立 roster 尚未取回；历史 Observation、run ID、费用流水确认未保存。当前优先 T01 官方 Q9 计分与 T02 历史 P/E，不为 v2 反复索取不存在的记录。

### T04｜最小完整流程（Agent，依赖 T01 可用计分范围 + T02 + T03）

- 输出：云端可运行的 scripted P/E/B 流程、可导出的代码/配置/回答和本地复核、持续性基线；采用本地运行时提供 `run.py --dry-run`。
- 验收：至少两个相邻开发月贯通；固定种子可重复；模拟输入没有真值；输出记录版本与数据哈希。

### T05｜提案（Agent 已起草，用户审定/提交）

- 已有[开题提案草稿](../proposal/proposal.md)；PDF 尚未生成。范围按研究方案，平台结果显式标为待本地验收。
- 验收：解释 Agent 的额外价值如何通过对照验证，说明概率计分/历史人口/信息时点的风险与替代方案。
- 账号、邀请码及提交回执由用户确认；队名已知不代表报名已完成。

## 随后进入

- T06：小规模 LLM 开发试验与总预算冻结，依赖 T04 和[模型身份/时间边界登记](MODEL_TEMPORAL_LEAKAGE.md)；未知截止允许标注为探索性回顾模拟，不得声称严格事前预测。
- T07：正式方案冻结与测试，依赖 T06 和完整历史输入验收。
- T08：论文、必要消融、复现包与演示，依赖 T07；清单见 `submission/README.md`。

交接时写：任务编号、已改文件、命令/证据、剩余缺口。任务板只记录结果；不要把研究长文再复制到这里。
