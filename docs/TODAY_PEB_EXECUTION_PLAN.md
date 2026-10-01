# 2026-09-29｜P/E/B 材料准备与云端首试执行计划

状态：**本地材料完成；云端账号内的小试尚未执行**。供其他 Agent 接力的本轮任务单；研究口径以 `RESEARCH_PROTOCOL.md` 为准，云端操作以 `CLOUD_PILOT_PLAN.md` 为准。

## 目标与今日交付

为“水上挽月”赛道 A 的美国 SCE 一年期通胀预期研究准备可审计的 SocioVerse 输入包，并给出今日小规模云端实验的操作顺序。成功标准是材料明确、时点边界明确、可以在平台创建 study 并得到可核查的最小流程结果；此轮不把小试结果当预测效果结论。

1. **P**：查证 SCE 官方问卷、微观数据、变量说明、人口结构与历史发布资料；将可公开获取的必要源文件下载到 `data/raw/`，保留原名、来源 URL、抓取时间、哈希与使用许可/限制。整理可用于历史 P 的字段、月份覆盖和当时可得性；外部 ACS/CPS/SIPP/CE 只按首试必要程度列优先级。产出 `docs/P_INPUT_RESEARCH.md` 与上传用的小型公开/合成人口材料（若数据许可或历史时点无法确认，先用合成样例）。
2. **E**：核对 Event MCP 公开能力与真实可调用范围，列出明确 collector、所需字段、参考月份、历史发布时间、vintage、as_of、排除规则和服务返回时的验收动作。产出 `docs/E_EVENT_MCP_SPEC.md`；实际服务未调用时如实标注待平台验证。
3. **B 与 Y**：查证 SCE 官方问卷及方法，逐题说明点预测、Q9 十区间概率、无效回答处理和官方跨人统计口径；划清目标真值与 Agent 输入。产出 `docs/B_SCE_SURVEY_SPEC.md`，附可供云端 Agent 自查的官方链接和可上传的精简说明。
4. **云端输入包**：在 `proposal/cloud_input/` 放一个总入口、来源索引、P/E/B 约束和首试提示词，文件短小、可直接上传或粘贴；不放受限微观原始数据、密钥或真实当期问卷答案。`proposal/cloud_start_prompt.md` 可修订为当日版本，但保留它的“先确认计划/费用”闸门。
5. **交接记录**：更新 `docs/NEXT_ACTIONS.md` 的真实进度，写明本地可直接使用的材料、未验收项和平台内下一步；`git diff --check`、链接/源文件哈希等轻量核查通过。

## 分工与文件边界

并行研究 Agent 仅写各自文件，主 Agent 汇总和改公共文件，避免交叉覆盖。

| 分工 | 写入范围 | 核查重点 |
| --- | --- | --- |
| P | `docs/P_INPUT_RESEARCH.md`、必要的 `data/raw/sce_p_sources/` 文件与清单 | 官方 P 字段、历史可得性、画像替代、许可 |
| E | `docs/E_EVENT_MCP_SPEC.md` | collector、查询参数、时点/vintage、新闻过滤、返回证据 |
| B | `docs/B_SCE_SURVEY_SPEC.md` | 官方问卷原文、Q8/Q9、密度规则、加权统计、无效响应 |
| 主 Agent | 本计划、`proposal/cloud_input/`、总索引/进度 | 消解矛盾、下载复核、云端首试步骤、整体质量 |

各 Agent 必须先读 `AGENTS.md`、`RESEARCH_PROTOCOL.md` 和现有审计；事实写来源链接及核查日期，无法访问/尚未实测的部分明确标“待验证”。外部资料目录 `../socioverse/`、`../指标跟踪/`、`../socioverse2_repo/` 只读。

## 执行顺序与检查点

1. **已完成：计划先落盘。** 保存本文件后开始研究，避免中断时失去范围和路径。
2. 并行调查 P/E/B；主 Agent 查看已有源文件、官方网页与当前项目草稿，减少重复下载。
3. 汇总官方事实与项目假设；下载公开且必要的原始文件，登记 URL/时间/哈希；把历史版本与实时抓取分开标识。只要求今日两个月小试所需最小材料，不为可选库做大规模下载。
4. 编写云端可用输入包：研究目标、P 样例/字段、E 精确查询清单、B 问卷与计分、信息截止、预期输出、停止/费用闸门。
5. 核查云端首试最小步骤：先 study 计划确认；再验证文件物化与 Event 小样；再跑 20 人×相邻 2 个开发月的 scripted 流程；如费用、权限和口径明确，再由用户决定是否运行真实 LLM。平台账号操作与付费调用应记录实际结果，不能由本地文档推断成功。
6. 核查所有新增文件路径、来源和 Git 忽略，更新任务板。未完成事项保留为明确待办，避免用“已备材料”掩盖关键缺口。

## 停机交接格式

若中断，后续 Agent 先读本文件、`docs/NEXT_ACTIONS.md` 和 `git status --short`。按“已核实来源/已下载文件/未核实主张/待执行平台步骤/最近检查命令”五项继续；不要重做已验收的 SCE 60 个月跨人聚合，不要把现存未提交修改清空。项目私有远端已存在，但本轮没有授权自动提交报名、付费运行或上传受限数据。

## 本轮交接结果（2026-09-29）

- **已核实来源**：纽约联储 SCE 主页面、FAQ、核心问卷、2017 方法、图表指南；Census 2019 ACS 1-year PUMS 于 2020-10-15 发布，标准 2020 ACS 1-year PUMS 未发布；SocioVerse Event 工具签名及其 observation-date 保证。详细证据分别在 `P_INPUT_RESEARCH.md`、`B_SCE_SURVEY_SPEC.md`、`E_EVENT_MCP_SPEC.md`。
- **已下载文件**：此前 SCE 2020–2024/latest 微观、问卷和方法仍在 `data/raw/sce_audit_20260928/`；新增 SCE 2017–2019 微观、13 页图表指南、2019 ACS 字典与 ReadMe。URL、字节数与 SHA-256 分别记录在 `sce_source_manifest.json` 和 `peb_source_manifest.json`。当前快照不能自动当成 2021 年可得版本。
- **可直接交平台的文件**：从 `proposal/cloud_input/README.md` 开始，上传 `sce_cloud_input.md`、20 人合成 CSV、字典及合成 E 备用 JSON；按 `first_message.md` → 审核计划/费用 → `after_plan_prompt.md` 两段操作。两目标月统一为 2021-05、2021-06；各自 as_of 为前月末纽约时间。
- **未核实主张**：SCE 各历史微观版本首次上线日、Event MCP 真实服务返回及其逐条发布/修订字段、个人 Q9 密度拟合、云端文件物化/导出/成本/运行成功、ACS 真实 P 构造。这些不能在提案中写成已验证效果。
- **平台下一步**：用户在 SocioVerse 登录后先按上传指南提交第一段，取得平台计划与能力反馈；确认费用后跑 20×2 scripted 并导出。将实际 study ID、回包、失败项和费用填入 `proposal/cloud_input/experiment_log_template.md` 的副本。成功后再依据真实材料写开题报告；失败则针对具体卡点补调研。
- **检查**：20 条合成 P/8 列/ID 唯一/权重和 20、2 条合成 E、四个新增下载 SHA-256 均已核对；`git diff --check` 通过。未执行云端实验、报名、付费或 Git 提交。

### 平台反馈后的补救（同日）

用户转述 SocioVerse Agent：`fred` 两次成功取回当前 CPI/失业率，但没有发布时间与历史版本，按协议隔离后只能退回合成 E。这表明原输入包缺少真实历史 E 的后备来源。现已下载四份 2021 年 BLS 归档 CPI/就业首发 PDF，整理成[六条真实历史信号](../proposal/cloud_input/sce_2021_05_06_bls_release_e.json)，发布时间和首页数值已通过 `python3 scripts/verify_bls_pit_e.py` 核验。修正操作见[补救说明](E_PIT_RECOVERY.md)及[给平台的补救提示词](../proposal/cloud_input/real_e_recovery_prompt.md)。下一步在**同一 study**导入这份 JSON、检查 E 物化并继续 20×2 scripted；平台实际导入、运行与导出仍未验证。
