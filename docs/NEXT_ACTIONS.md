# 当前任务板

更新：2026-10-03（Kimi 完成本地 harness 实现、离线验收与首次真实 LLM 20×2 小试；Codex 完成模型选型调研）。只推进 SCE；队伍名为水上挽月。日期以 [ROADMAP](ROADMAP.md) 为准。每项任务只标真实进度。

## 当前接力：v4 决策点 + T01 方法研究 + 提案撰写

- **2026-10-03 P 真实抽样完成（Kimi + 实现代理）**：`scripts/build_sce_population.py`（panel 模式：只取所有目标月都在的 userid，seed 确定、来源文件哈希、分布元数据；白名单测试守门）。**100 人 × 202105+202106** 已生成：`studies/sce_inflation_expectations/population/population_real100.json` + roster + sampling_meta（两月交集池 1070，抽 100）。就业 = Q10_1..10 多选（问卷 p.11–12，每月必答，全覆盖）；住房 = Q43（p.32，**旋转模块每月仅约 12% 人被问**），±6 月借用后覆盖 42%（58/100 无该属性，prompt 回退 unknown）——**住房维度完整性受 SCE 设计限制，若要扩白名单属协议变更，待用户定**。两个语义纠正：`_NUM_CAT` 实为 numeracy（High/Low）非家庭人口；xlsx `tenure` 为面板受访月数非住房。prompt 映射只增不删（旧 20 人试点 prompt 字节不变）。运行器已接 `--population`，并按所跑人口动态绑定 E 的 persona 视图（weight 整数化保持试点字节级复算 PASS）。报告：[POPULATION_SAMPLING_REPORT](../studies/sce_inflation_expectations/reports/POPULATION_SAMPLING_REPORT.md)。测试 38/38；真实 100 人 scripted 干跑 200/200 有效。10/5 正式运行的模拟 vs 真实对比仍需评价层提取真实回答（weight/Q8v2/Q9 只在评价层，脚本未做，列入 10/4-5 任务）。

- **2026-10-03 真实 LLM 首轮已完成（Kimi，D043）**：用户批准装 llm 扩展 + $0.30 预算上限。`--list-models` 目录核对通过（端点含 deepseek-flash/v4-pro，与选型文档一致）；`--sample 2` 两条一次有效、估费 $0.0007；**20 人 × 2021-05/06 正式开发小试完成**：40/40 一次通过 Q9 语法门（零重试零错误），点预期中位数 3.0（05）/4.0（06），40 次调用估费 **$0.014**。run_id `sce-local-openai-20261003T011717Z-427a1baf`，审计链完整（llm_calls 40 行全含提示词/原始响应/usage）。期间修复一处工程问题：运行产物（含 duckdb 与引擎 live 文件）全部迁入按 run_id 的审计目录，运行副本保持纯净，--force 重导出不再能误删产物。性质登记为历史回顾性条件模拟（不声称盲测/严格复现）。下一步：正式对比等冻结计分路径（Codex 复查月份）；temperature/提示词消融先冻结设计。

- **2026-10-03 本地 harness 已实现并离线验收（Kimi）**：SCE study 首次在主仓库获得完整可运行实现——`studies/sce_inflation_expectations/model.py`（四个 abc + 双模 B：scripted 与云端 v3 逐字段一致；openai 真实 LLM 带全量审计 sidecar：提示词+原始响应+哈希、requested/returned model、request_id、fingerprint、usage、重试与错误逐条落盘；Q9 校验不归一化、失败不回退规则、SDK 内置重试关闭、调用次数/费用双闸门、超长提示拒绝）+ `__init__.py` + environment/population/simulation/grounding/resources 配置件 + JSON 格式 study.yaml。入口：`scripts/run_sce_local.py`（自动单向导出→官方仓运行副本执行，轨迹按 run_id 独立 duckdb，运行配置只写 run_manifest 不回写副本，P1 导出保护不阻塞复跑）；`scripts/sce_llm_probe.py`（--list-models 免费目录核对 / --sample N 计数小样，需 --confirm-spend）；`scripts/audit_local_scripted_replay.py`（与 v3 归档逐字段复算）。**验收结果**：两次本地 scripted 运行 answers 40/40、observations 40/40 与云端 v3 归档完全一致（replay_audit_vs_v3.json verdict=PASS）；单元测试 31/31 通过（含 mock-openai 的有效/重试/失败/闸门分支）。证据：`outputs/local_runs/sce-local-scripted-20261003T003537Z-8e6b2f5b/`。**下一步（待用户动作）**：用户在官方仓 `.env` 放入 DeepSeek key 并确认 $0.30 预算 → --list-models 目录核对 → --sample 2 两条小样 → 40 条开发小试。model.py 的 openai 路径真实连通性尚未实测（openai 包未装，装前与用户确认 `pip install -e ".[llm]"`）。

- **2026-10-03 最新接力，覆盖下方旧选型说法**：[模型核查与 Kimi 接入清单](MODEL_SELECTION_20261003.md)已完成。用户确认已有 Kimi/DeepSeek API；建议首轮复用 DeepSeek `deepseek-flash`（当前映射 V4.1-Flash、显式关闭思考），2 条接入小样后考虑原 20×2 开发小试；建议预算 $0.30，**尚未批准/运行**。Qwen2.5-72B 在硅基流动仍有公开价；GPT-4o 固定 API 版本仍列在官方目录，地区/账号可用性另核；旧 `deepseek-chat=V3` 与“2024 都是严格盲测”表述已更正。Kimi 下一步做本地客户端审计接线与离线 mock；服务目录、实际模型回包/usage、预算确认完成后再调用。正式模型/测试期与计分配置均未改变。

- **2026-10-01 Codex独立复核完成**：[结果与交接](BETA_AND_KIMI_REVIEW_20261001.md)。原计分器未改；新增独立诊断脚本，完整两月1,780条Beta记录的≤0.001误差比例67.2%→84.3%，仍非官方精确复现。候选是否采用待用户决定；保留SCE目标。
- **Kimi优先修复**：① `export_study_runtime.py` 重导出会删除运行副本内已有trajectory等产物（已用临时目录证实），真实运行前需保护/分离run_id产物；② v3源码写字面量反斜杠n，归档日志却为LF，需核实转换或实际运行源码，不再称证据链完全闭合。现有40条回答匹配与文件哈希自洽仍成立。之后推进历史P/E、有限真实B和提案，不反复消费云端额度重跑scripted。
- **Kimi P1/P2 已完成（2026-10-02，D039）**：① P1：`export_study_runtime.py` 重导出遇目标副本派生产物/改动即拒绝并列清单，`--force` 显式覆盖；新增 4 项测试，全套 16/16 通过；官方仓运行副本 `--verify` 仍通过。② P2：answers.jsonl 确认为平台自运行状态导出（非 model.py 产出，矛盾消除一半）；observations.jsonl 与平台 audit_manifest 哈希一致但与归档源码存在一层未记录换行转换，保留为格式层缺口；平台轨迹库 `panel_live.jsonl` 与 answers/observations 内容 40/40 一致（独立佐证）；[CLOUD_V3_AUDIT_RECEIPT](CLOUD_V3_AUDIT_RECEIPT.md) 结论已降级，运行证据链附加协议（封存源码哈希、行为函数自报哈希、记录转换、轨迹库交叉核对）已入 [RESEARCH_PROTOCOL](RESEARCH_PROTOCOL.md) 第 6 节。
- **Q9 计分方针已定（用户 2026-10-02，D039）**：统一采用明确命名的近似密度指标，同一算法处理真实与模拟问卷，论文明确说明近似性质并报告与官方 headline 差异。具体冻结哪一版算法（原实现/候选变体）按 Codex 建议在未参与诊断的核验月份复查后确定，不由测试表现反向选择。待办：选定复查月份 → 实现冻结版计分模块与差异报告。
- **Kimi 后续**：T02 主体已完成（P 核验 + 核验月 E 日历，见 [T02_PE_ACCEPTANCE](T02_PE_ACCEPTANCE.md)），收尾待办为就业/住房问卷码表映射、正式窗口月份补齐、脚本固化；有限真实 B 试验准备；提案待用户审定（结尾内生指标展望句去留未定）。
- **Sim 主路径已定（用户 2026-10-02，D040）**：Sim 探索与正式运行云端平台优先，v4 解冻按 D034 报价确认卡路径；本地 harness（socioverse2_repo + 自带 API）降为后备。不耗平台额度的准备工作（persona 提示词设计、Q8/Q9 回答格式稳定性小样测试）可先行。GitHub 远端已同步至 `59cd61c`。
- **v4 已配置未运行（2026-10-02 晚，D041）**：经 webbridge 逐步操作用户浏览器（每步用户确认），v4 从 v3 创建并切换 `llm_kind="openai"`（试钉 gpt-4o-mini）、LLM 决策代码已写入 model.py 并通过语法校验；**未运行、未扣 Sim 费**。运行冻结原因更新：① 运行前报价确认不可得（平台刻意不公开模型/单价）；② 平台自述 v4 运行时审计接线未完成；③ 三轮对话 $6.78 后余额 **$-0.20** 透支。**额度路径（用户截图确认）**：平台无即时充值入口，10-12 前提交开题提案、10-15 初筛通过后每队追加 $70；提交入口为「研究目录」页顶部参赛卡片。**10-15 前云端模拟全部暂停**，主线转为：本地完成提案提交 + 本地 harness 做提示词冻结与格式干跑（自备 API，成本自控）；10-15 后云端 v4 正式运行。完整记录见 [CLOUD_V4_PREP_RECEIPT](CLOUD_V4_PREP_RECEIPT.md)。
- **本地运行方案已立项（2026-10-02，Kimi）**：官方仓库架构核查完成——LLM 走任何 OpenAI 兼容端点（`SV_LLM_*`）、人群可用 FilePopulationProvider（不需 Population MCP）、E 在 build 时物化（**不需复刻 Event MCP**，运行时从不联网）、引擎本地装配写 DuckDB。本地待办清单（Sim 模型选型/人群抽样/E authoring/审计接线/云端衔接）见 [LOCAL_HARNESS_RUN_PLAN](LOCAL_HARNESS_RUN_PLAN.md)。模型选型为研究口径决策，待用户定（GPT-4o 的 2023-10 截止可支持"窗口内外对比"设想）。

- 交接入口：[AGENT_HANDOFF](AGENT_HANDOFF.md)；用户发给 Kimi 的[启动提示](KIMI_START_PROMPT.txt)。以下负责人是协作安排，不表示已经启动了另一 Agent。
- **云端 v3 已完成（2026-10-01，Kimi）**：v2 流程报告生成（6/6 不含论文/文献阶段）；/sv-iterate 创建 v3 scripted 审计版并冷跑 20 人 × 2021-05/06，`model.py` 仅 +22 行审计 diff。run_id `sce_inflation_expectations-v3-2c40f389c0d24e1ab1e963918b3bfec9`；`audit/v3/` 六件（run_manifest/cost_ledger/audit_manifest/observations×40/answers×40/validation_errors 空）+ v3 `model.py` 全部取回，`scripts/audit_cloud_v3_audit.py` 核验通过：文件哈希与清单逐条一致、Observation 哈希 40/40 自洽（算法与源码一致）、回答与 v2 归档逐字段一致 40/40。费用账本 `billing_status=not_available`。云端对话费约 $10.67，Sim 未动。取件坑与 base64 通道见收讫文档。
- **v4 已冻结（用户 2026-10-01 决定，D034）**：平台工作区无法确认真实 LLM provider/模型 ID/知识截止/报价；v4 保持冻结，优先完成开题提案（内部目标 10-08）。未来解冻路径：授权走到 v4 sv-run 确认卡只读报价 → 用户批准预算 → 运行。
- **T03-L 本地验收已完成（2026-10-01，Kimi）**：补装 `scipy 1.17.1`/`openpyxl 3.1.5`；SCE 测试 12/12（Q9 计分 5 + 新增导出 7）；v2 归档审计两脚本通过。新增 `scripts/export_study_runtime.py`（单向导出 + `--verify` + 逐文件 SHA-256）与 `tests/test_export_study_runtime.py`，已真实导出到官方仓 `studies/sce_inflation_expectations/`（gitignored，不另养源码）。MCP 两服务连接与免费目录实测通过：`event_tool` 21 个来源（含 nyfed_sce/fred/bls/census_acs/sipp 等）、`user_pool_survey_mcp` 免费探测全过（matraix_1m 56,583 索引用户等），付费工具均未调用，脱敏归档在 `data/raw/mcp_checks/2026-10-01/`。完整命令与边界见 [LOCAL_RUNTIME_ACCEPTANCE](LOCAL_RUNTIME_ACCEPTANCE.md) 末节。`scoring/sce_q9.py` 本轮未动。
- **Kimi 后续**：v4 按用户决定执行或冻结；v3 证据写入提案（流程可行性段）；T02 历史 P/E 与发布日历；需要时补取 v3 轨迹 DuckDB/报告原文。
- **Codex T01独立诊断已完成**：方法与候选取舍见上述2026-10-01复核。生产 `scoring/sce_q9.py` 未改；后续采用候选须先明确版本/口径，再用未参与诊断的计分核验月份验证。
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

### T02｜历史 P/E 验收与构建（Agent；P 侧与核验月 E 日历已完成 2026-10-02）

- 前置：T00 的对应来源/字段/时间样例检查；T02 负责扩展到实际 P/E 管线与正式月份覆盖。
- 输出：逐月 release 日历、历史 P 版本证据、开发月宏观信息快照与字段契约；登记来源和修订版本。
- 修改区：`data/`、study 的 `population/`、`environment/`、`grounding/`。
- **已完成（Kimi，见 [T02_PE_ACCEPTANCE](T02_PE_ACCEPTANCE.md)）**：P 侧三份 SCE 微观快照（2017–2019 / 2020–2024 / 2025-01..10，共 106 月 130,216 条）字段核验——提案所需画像字段（`_AGE_CAT`/`_EDU_CAT`/`_HH_INC_CAT`/`_REGION_CAT`/`_NUM_CAT`/`_COMMUTING_ZONE`/`_STATE`）全部存在且非空率约 100%，每月 976–1,377 人与提案口径一致；P 白名单契约已定（`weight` 与 `Q8v2`/`Q9_*` 仅进评价层）。E 侧三个核验月（2020-04、2022-06、2024-12）6 份 BLS 归档首发稿已取回存档（`data/raw/bls_check_months_initial_releases/`，含 manifest 与首发值表）；curl 被 Akamai 403，改用 FetchURL 文本抽取，已在 manifest 注明。2020-02 就业稿重发注记与 2024-10 非农异常低值均已记录备查。
- 验收：P/E 不带同期真实回答/权重（契约已写死）；unknown 和 future 发布时间被隔离（本轮未接入无 vintage 来源）；过去发布值基线有日期依据。
- 待做：就业/住房字段的问卷码表映射（persona 需要时）；正式窗口确定后按同法补齐该窗口全部月份；统计与校验脚本固化到 `scripts/`。
- MCP 优先取 2020-04、2022-06、2024-12 小样检查：已改用 BLS 公开归档页完成，零 MCP 费用；无服务权限直接推进官方宏观数据路径。

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

### T05｜提案（二稿完成，待用户审定/提交）

- 2026-10-01 二稿：按评委视角重写 [proposal.md](../proposal/proposal.md)，采用官方 P×E→B 框架与平台话语，结构为研究问题/P-E-B 设定表/验证方案/已完成可行性/计划成本风险/预期贡献；删去 Q9 Beta 差异、scripted/v3/run_id 等内部术语（证据仍在内部文档，见 [proposal/README](../proposal/README.md)）。PDF 已重建（2 页，含中文首行缩进 2em）：`cd proposal && pandoc proposal.md -o build/proposal.pdf --pdf-engine=xelatex -V CJKmainfont="Songti SC" -V mainfont="Times New Roman" -V geometry:margin=2.2cm -V fontsize=11pt -V indent=true -H <含 \usepackage{indentfirst} 与 \setlength{\parindent}{2em} 的头文件>`。结尾"内生经济指标展望"一句为可选项，用户可删。
- 验收：解释 Agent 的额外价值如何通过对照验证，说明概率计分/历史人口/信息时点的风险与替代方案。
- 账号、邀请码及提交回执由用户确认；队名已知不代表报名已完成。

## 随后进入

- T06：小规模 LLM 开发试验与总预算冻结，依赖 T04 和[模型身份/时间边界登记](MODEL_TEMPORAL_LEAKAGE.md)；未知截止允许标注为探索性回顾模拟，不得声称严格事前预测。
- T07：正式方案冻结与测试，依赖 T06 和完整历史输入验收。
- T08：论文、必要消融、复现包与演示，依赖 T07；清单见 `submission/README.md`。

交接时写：任务编号、已改文件、命令/证据、剩余缺口。任务板只记录结果；不要把研究长文再复制到这里。
