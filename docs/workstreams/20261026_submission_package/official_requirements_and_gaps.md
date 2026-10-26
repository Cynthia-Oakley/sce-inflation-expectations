# 官方提交要求与研究包缺口

**核查日：2026-10-26（Asia/Shanghai）**  
**范围：**官方赛事页、SocioVerse2 中文指南/FAQ、官方本地仓库说明，以及本项目现有 study、提交清单和数据文档。只读核查；本轮没有改冻结研究源/配置，没有发送模型请求，也没有操作或检查仍在运行的主线进程。

## 一、来源与证据边界

| 来源 | 核查记录 | 用途 |
|---|---|---|
| [SocioVerse Challenge 2026 赛事页](https://socioverse.fudan-disc.com/challenge/) | 2026-10-26 核查官网英文动态正文的 Reproducibility statement，确认需固定随机种子、声明模型/调用/费用、提供一命令执行脚本并说明复现哪些结果；本次未保存动态正文哈希。[本日机器记录](../../sources/challenge_requirements_20261026.json)。此前精确赛事条款见本仓库 2026-10-24 的[核查记录](../../sources/challenge_requirements_20261024.json)，当次保存脚本 URL 与哈希。 | PDF/MP4/研究包、复现、数据与命名要求；不能由静态页面目录文字单独推断动态条款。 |
| [从零构建 Study](https://socioverse.fudan-disc.com/docs/zh/guides/build-a-study/) | 2026-10-26 逐页核查。 | `study.yaml`、P/E/运行配置、模型接口、发现字段、grounding 和先干跑后实调的官方平台约定。 |
| [一个 Study 的解剖](https://socioverse.fudan-disc.com/docs/zh/concepts/study-anatomy/) | 2026-10-26 逐页核查。 | 规范目录、`trajectory/` 与 `reports/` 的产物含义、运行种子、版本和本地输出约定。 |
| [包装既有模拟器](https://socioverse.fudan-disc.com/docs/zh/guides/wrap-legacy-model/) | 2026-10-26 逐页核查。 | Path C 支持在 study 内增加 adapter、原模拟器源码零修改及确定性 parity 检查。 |
| [LLM 接入与干跑](https://socioverse.fudan-disc.com/docs/zh/guides/llm-clients/) 与 [FAQ](https://socioverse.fudan-disc.com/docs/zh/faq/) | 2026-10-26 打开并核对干跑、密钥、费用、结果与可复现性条目。 | `scripted` 零 API 干跑、真实 LLM 的密钥与非确定性、运行结果持久化。 |
| 官方本地仓库 `../socioverse2_repo/README_zh.md`、`pyproject.toml`、`studies/opinion_diffusion/` | 本地 HEAD `fa678ff6aea0e5a6497a7ffac15459123200a150`；只读。checkout 有两处与本审计无关的未提交改动（`scripts/gen_mcp_json.py`、`tests/test_gen_mcp_json.py`），不能直接作为打包源码。项目 Python 要求 `>=3.11`；项目版本在 `socioverse/__init__.py` 为 `0.2.0`；pyproject 声明 Apache-2.0。 | 官方仓库 README 将规范 Study 目录称为挑战赛提交格式；依赖/上游版本核对。该许可证只说明平台代码，不覆盖本研究数据或其他来源。 |
| 本项目 [组委会反馈记录](../../sources/organizer_feedback_20261015.json) | 记录日期 2026-10-15；文件注明邮件由用户提供、邮件发送时间未核验。 | G1–G5 具体审稿关注点；作为反馈证据，不冒充官网条文。 |

术语：**赛事硬要求**指挑战赛页面/动态正文的提交要求；**平台约定**指 SocioVerse2 对 Study 的标准结构与运行行为；**工程选择**指为本项目降低复现门槛的实现；**组委会反馈**是对报告与研究包应回应的评审意见。不要把后面三类都标成官网强制字段。

## 二、要求与现状

| 项目 | 类别 | 核查到的要求/约定 | 当前证据与缺口 |
|---|---|---|---|
| 研究报告 | 赛事硬要求 | 中文或英文 PDF，4–8 页，图表计入页数。 | 当前有报告草稿/HTML素材；最终 PDF 尚需从导出文件独立检查页数、引用、图表、单位及结果口径。 |
| 演示视频 | 赛事硬要求 | MP4，最长 5 分钟；展示真实 Study 工作流。在线平台回放是替代展示形式。 | 最终 MP4 尚未交付；应在包可执行后录制，并明确区分真实运行、离线干跑和缓存重算。 |
| 研究包位置与说明 | 赛事硬要求 | 包含 `studies/<your_study>/` 格式；README 必须给出复现说明。 | `studies/sce_inflation_expectations/` 已有 `study.yaml`、`model.py`、`grounding/`、`environment/`、`population/`、`simulation/`、子目录 README；但现有 [Study README](../../../studies/sce_inflation_expectations/README.md) 标注的是 2026-10-03 的 2021-05/06、20 合成画像本地演示。它不是 A82 生产运行说明。 |
| `study.yaml` | 平台约定；赛事格式的核心文件 | 有研究问题、时间单位/每步含义、指标、相对产物引用及路由元数据。官方从零构建指南要求 `domain`、`tags`、`legacy_simulator`、`provider_refs`、`adjustable_params`、`status`、`demonstrates` 等发现字段。 | 当前文件明确 `n_steps=2`、`seed=42`、2021-05/06、`status=local-dev`、20 人演示 run note。不得把 `seed=42` 或该小样本规模当作 A82 的正式 seed/规模。 |
| P / E / simulation | 平台约定；与赛事的 Study 格式一致 | 标准产物为 `population/population.json`（P）、`environment/environment.json`（E）、`simulation/simulation.json`（决策/collector/store 引用、`n_steps`、`seed` 等）；从零构建指南还要求四个接口实现和注册。 | 现有 JSON refs 指向 20 个合成画像及两个月 BLS 演示输入。A82 实际 82×512×1 的生产配置与队列记录在 `docs/workstreams/20261023_main_run/`、受忽略的运行目录和运行收据中；还没有一个面向提交者、与实际 A82 完全一致且可独立运行的 Study 配置包。 |
| trajectory / reports | 平台约定 | `trajectory/` 是运行生成的面板/指标数据库与历史；`reports/` 是渲染结果。官方 FAQ 明确运行库通常 gitignore，干跑输出和正式报告可分开。 | A82 的真实答卷和个人轨迹留在本地忽略目录是合适的默认状态；包应交付可许可的聚合表/图和重算方法，而不是把私有轨迹复制进 `trajectory/`。可随 Study 提供的 `reports/` 应限定为最终论文/聚合报告。 |
| 一命令执行脚本 / 文件名 | 一命令脚本为赛事硬要求；脚本文件名是工程选择 | 官网英文动态正文的 Reproducibility statement 要求固定随机种子、披露模型/调用数/费用、提供 one-command execution script，并写明哪些结果可复现。官方 FAQ 示例为 `python scripts/demo_offline.py`；官方 Study 文档描述 `build_simulator(...); sim.run()`。官网未规定脚本必须叫 `run.py`。 | 当前 Study 没有 `run.py`；旧 README 的多条命令和 A82 主线的不同入口尚未收敛为可提交的一命令执行脚本。提交包必须提供一个能从干净环境执行、明确失败边界的一命令脚本；可命名 `run.py` 或其他名字。再通过 README 将零 API 干跑、封存结果重算、需单独授权的真实 LLM 模式区分清楚，不能让复现命令默认触发 API。 |
| 零改动 adapter | 平台能力/工程选择 | 官方 Path C 支持在 study 下通过 adapter 包装既有模拟器、保持旧源零修改，并以固定种子和确定性客户端做逐步 parity 检查。 | 这是避免碰冻结源的可行方式，不是赛事硬性要求。若采用，adapter 必须只接现有接口；要证明其 parity，不能仅凭“adapter”名称声明。 |
| 干跑、真实 LLM 与授权 | 赛事硬要求 + 平台约定 + 项目贡献规则 | 赛事要求清楚区分 dry-run 与真实 LLM；官方平台 `scripted` 模式无需 key、由种子决定，可做完整流程干跑；真实模型需要凭据，非零温度结果不能保证逐次复现。任何付费/数据外发须写明范围、端点、费用并另有本批明确授权。 | 老 Study README 的 `scripted/openai` 双模属于本地 smoke path；A82 生产路径使用项目独立队列及真实模型路由。包需要显式禁用 API 的默认 dry-run、单独的真实模式确认/预算阈值，并说明此前的运行授权不自动授权新调用或公开数据。当前未触发任何 API。 |
| seed、模型、调用数、成本 | 赛事硬要求 | 研究包声明所用种子、模型、调用规模与成本。组委会 G4 要求把实际值、运行时间、失败/修复与估算区分，并避免把重复遍数误说成独立随机种子。 | 已有逐运行账本、A82 运行与费用记录及补跑说明，但尚未收敛到随包的单一、经哈希索引的清单。需分别列抽样/供体/提示等种子、正式模型/供应商/路由、主调用与技术补跑、token/费用、未知费用预留、耗时、失败和修复；不要用 smoke 的 `seed=42` 填补缺项。 |
| 一键复现范围 | 赛事复现门槛 + 工程选择 | 复现声明必须讲清哪些结果可复现；“有 README”本身不足以通过复现门槛。官方 FAQ 区分确定性干跑、真实 LLM 非确定性新跑和已存轨迹精确重放。 | 需将三件事分开：①离线 `scripted` 干跑只证明结构/接口；②已有合法数据与封存回答的离线聚合重算才核对论文核心表图；③真实 API 生成既昂贵又可能随机，不是复算既有结果。缓存缺失应返回失败并说明缺项，不能静默写入虚假成功。 |
| 真值获取与隔离 | 赛事硬要求 + 组委会 G1/G5 | 提交说明真值来源、取得时间/版本与隔离方式；目标答案不得成为生成输入。组委会另要求校准与验证量分清、公开/可得时间与模型知识边界分开。 | 本项目有评价层隔离和多份来源/下载清单，但最终交付仍需一张与报告月份对应的“真值来源—抓取/下载时间—版本—用途—是否进入输入—许可状态”表。A 是条件历史重建，不能改称严格事前预测；2023–2025 等已参与开发/查看的月份不得事后改名盲测。 |
| 数据授权、脱敏与许可 | 赛事硬要求 + 组委会 G5 | 外发数据须有授权或可分享依据并去标识；下载公开不等于允许再分发。组委会要求逐源分别说明研究使用、模型处理和包内再分发范围、隐私及新闻/汽油历史版本证据。 | 逐源许可/模型处理授权/再分发目前没有完整核清。本报告所附 [数据放行初表](../../../submission/data_release_policy.json) 是保守打包决定，不声称许可证全核验。默认不带微观数据、新闻文本、单人轨迹或回答。 |
| 来源/依赖与路径 | 工程选择 + 组委会 G4 | 对方应能按 README 安装并运行，不依赖未登记的相邻工作仓、本机路径或私有密钥；锁定 SocioVerse2 版本/commit 和 Python/依赖。 | 旧 Study README 把 Python 绝对路径写入示例，且指向 `../socioverse2_repo/.env`；不能原样进 ZIP。官方 SocioVerse2 当前本地 commit 为 `fa678f…`、版本 `0.2.0`、Python `>=3.11`、Apache-2.0；发布前须选干净已发布版本或固定 commit，并补齐本项目依赖锁。上游仓有未提交改动，不随研究包复制。 |
| 报名字段、作者与提交回执 | 赛事流程 | 赛事源记录注明提交入口位于研究目录页；子赛道枚举、账户额度、最终作品状态在既有核查里标为未核实。 | 用户尚未要求上传/提交，本轮不登录、不发布、不生成正式提交行为。作者、导师、最终命名及平台当日表单字段留到交件前复核。 |

## 三、与项目现状的直接冲突

1. `studies/sce_inflation_expectations/README.md` 和当前 `study.yaml` 描述的是旧 smoke study：两步、2021-05/06、20 个合成画像、`seed=42`。这适合证明官方接口和本地流程，不代表 A82。
2. `submission/README.md` 与 `docs/workstreams/20261023_main_run/` 记录的主线是 82 个月（2019-01—2025-10）×512 人×一遍、41,984 逻辑人月、独立批处理/费用/恢复协议。它与当前 Study 的范围、规模、运行入口、模型和产物不是同一可提交运行配置。
3. 根目录 `README.md` 仍有早期十二期运行数字；提交材料已更新到 A82。提交包应以本批最终冻结协议及已完成收据为单一事实源，不能把旧主页文字当 A82 说明。
4. A82 个人轨迹、原回答、提示词和部分输入/真值在 `outputs/`、`data/` 忽略目录，无法指望新下载后自动存在。须列“可复算所需文件”的精确清单和许可处理，给出离线可运行的安全聚合结果或最小公开结果快照；不能让合成 smoke 数据伪装成 A82 结果。
5. README 中硬编码 Conda 与相邻仓路径不便独立解压；现有 A82 管线脚本文件多、用途各异，不等同一条可复现入口。最终 README 要从干净临时目录实测相对路径、依赖和结果校验。

上述发现仅用于提交包工作规划。本轮不改写 `study.yaml`、冻结代码、任务板、研究主线、运行中的 API 进程或旧结果。

## 四、包装建议（不改变冻结运行）

1. 等主线运行和收据封存后，再按显式文件清单导出 Study；`study.yaml` 需指明本次被包装对象的真实范围，旧 20 人 demo 改为独立示例或删出发布包，不能静默用它替代。
2. 选择一种 truthful route：原生 SocioVerse `build_simulator` Study；或官方 Path C adapter 包装冻结运行实现。README 说明正式答案实际经哪个入口生成、SocioVerse 核心参与在哪个阶段，以及 parity 检查的证据。不可把离线接口干跑称作全期复现。
3. README 至少分三段：`dry-run`（无 key、零网络、固定 seed）、`recompute`（读取包内/用户本地的获准缓存，重算指定图表/摘要）、`real`（明确需重新授权的 API 生成，默认不执行）。每一模式列前置数据、输出位置、是否网络、能检验什么和失败方式。
4. 发布实际 A82 的机器可读 run receipt / manifest，登记输入/代码哈希、官方仓版本、种子定义、模型精确标识和路由、并发/超时、逻辑调用与物理请求、失败与技术修复、token/费用/耗时、真值取得与隔离，并由一个命令执行脚本调用。真实 LLM 结果非确定；主张逐字节复现应指被保留的封存轨迹/输入快照重算。
5. `trajectory/` 和整批个人数据不进入 ZIP；仅在数据放行表确认后打包合成 smoke fixture、代码、所需 schema/最小 mock 和可公开的月级聚合。每个缺失外部文件应给官方下载/申请路径、版本选择和本地目标路径。
6. 录屏展示提交者解压后的真实 Study 包，先运行不联网 dry-run，再用授权聚合重算展示与正式结果一致；屏幕应隐藏路径、key、匿名单人响应和原始新闻内容。

## 五、验收状态

- **现在已能交付：**要求与缺口清单、保守数据放行初表、现有主线结果/运行记录的位置索引。
- **仍是提交阻断：**与 A82 真实运行一致的干净 Study 导出；锁定的上游/依赖；官方要求的一命令执行脚本；三模式 README 和默认零 API 的运行门；有许可的复算输入；逐源数据放行与真值时间表；从 ZIP 干净解压执行；PDF 与 MP4 最终件。
- **未作出的声明：**已全部授权再分发、真实 LLM 可逐次重现、A82 是完全盲测/严格事前预测、所有提交条件均已通过、作品已经上传。
