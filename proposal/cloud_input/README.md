# 今天在 SocioVerse2 平台上的提交顺序

**已有 study 的当前步骤（2026-09-30）：**平台报告 v2 已用[真实历史 BLS E](sce_2021_05_06_bls_release_e.json)及 20 人合成 P 完成两月 scripted 流程。40 条原始 JSONL、完整 `model.py`、`environment.json` 与 `simulation.json` 已经本地校验；v2 取件阶段结束。平台确认实际运行 Observation、独立 run ID 和费用流水未保存，不再索取旧记录；下一次运行须持久化后才能直接验收运行时输入。当前转向[官方 Q9 计分与历史 P/E](../../docs/NEXT_ACTIONS.md)。进度和代码局限见[首试记录](../../docs/CLOUD_V2_PILOT_RECEIPT.md)。下面的新建 study 流程仅供以后参考，当前无需重新上传或运行。

四份 PDF：[2021-03 CPI](../../data/raw/bls_2021_initial_releases/cpi_2021_03_released_2021_04_13.pdf)、[2021-03 就业](../../data/raw/bls_2021_initial_releases/employment_2021_03_released_2021_04_02.pdf)、[2021-04 CPI](../../data/raw/bls_2021_initial_releases/cpi_2021_04_released_2021_05_12.pdf)、[2021-04 就业](../../data/raw/bls_2021_initial_releases/employment_2021_04_released_2021_05_07.pdf)。均为公开新闻稿；不需上传 SCE 微观原始数据。

**若新建 study：**先上传/粘贴 [主输入说明](sce_cloud_input.md)、[合成画像 CSV](../../data/fixtures/sce_20_synthetic_personas.csv)、[画像字典](persona_fixture_dictionary.md)、[真实历史 BLS E](sce_2021_05_06_bls_release_e.json)，然后粘贴[第一条消息](first_message.md)。[合成 E 备用文件](../../data/fixtures/sce_2_month_synthetic_environment.json)只用于真实 E 无法导入时排查流程。平台若已因上传自动发消息，应在同一 study 对话中补发第一条消息，让它先停在方案确认节点。

**检查方案后**，按平台显示的权限与费用确认，再粘贴[第二条消息](after_plan_prompt.md)。这一步要求 scripted 最小实验；若平台的操作确认卡显示费用，应先在界面确认具体金额。实际运行记录填[实验记录模板](experiment_log_template.md)。

若平台不能打开官方网页，可补传已下载的 [SCE 核心问卷](../../data/raw/sce_audit_20260928/questionnaire.pdf)、[方法论文](../../data/raw/sce_audit_20260928/methodology.pdf)、[图表指南](../../data/raw/sce_p_sources/chart_guide.pdf)。不要上传 2017–2024 或 latest 的原始 SCE 微观工作簿；它们含真实受访者回答，今日首试不需要。

本地深入调研：[P 人口](../../docs/P_INPUT_RESEARCH.md)、[E/Event MCP](../../docs/E_EVENT_MCP_SPEC.md)、[B/问卷](../../docs/B_SCE_SURVEY_SPEC.md)。若云端助手需要规则的细节，可按需额外上传其中一份。下载 URL、时间与哈希见[既有 SCE 清单](../../docs/sce_source_manifest.json)和[本次补充清单](../../docs/peb_source_manifest.json)；原始大文件目录在 Git 中被忽略，源文件只保存在本机。

本仓库已收到并核对 40 条原始回答、B 代码及 E/P、simulation 配置；独立 roster 尚未取回；v2 历史运行 Observation、run ID 和费用流水未保存。
