# SCE 项目交接入口

> **2026-10-06 消费数据扩展已落地**：先读 [消费数据唯一入口](CE_CONSUMPTION_DATA_INDEX.md)、[执行计划](CE_DATA_BUILD_PLAN_20261006.md)。新的完整月人口篮子位于 `outputs/ce_population_baskets_20261006T063749Z_a8be0d98/`：1,234/1,297 人，既有 300 Core 与 Normal 采用相同合成规则，Core 篮子保持一致。Diary 原始 ZIP 已独立归档，周级数据与购买日支持单独清洗；它不是全年频率或实测注意力。新输入不代表 Normal 算法或运行配置已更新；零新增模拟 LLM/付费 MCP，当前仅 A 后验代理。原始和个体产物 Git 忽略，来源、脚本、验收与任务板可版本保存；Kimi 待审批次继续保护。

> **2026-10-06 价格体验机制 v1 已落地**：先读 [使用入口](PRICE_EXPERIENCE_MECHANISM.md)、[工程验收](PRICE_EXPERIENCE_ACCEPTANCE_20261006.md)、[待授权真实对照卡](PRICE_EXPERIENCE_RUN_CARD_20261006.md)。官方 CE 2020Q4 联合 donor 为两月各 300 人建立消费侧车；四臂公共事实/问卷一致，2,400 条实际提示预览、600 条框架观察和规则式记录通过核验，48 项相关测试通过。`scripted` 只验接线，不使用消费背景回答；真实机制 LLM 仍未运行。现成 20 人小试包和 300 人侧车在 `outputs/price_experience_20261006_v1/`。当前仅 A 后验代理，TOTEXP 不是 CPI 篮子，排序不是实测注意力。先核对新实验模型/价目与数据发送范围并获新预算授权，再做同人五组对照；下方“下一步准备机制材料”为旧阶段记录。计分器、开题与 Kimi 待审批次未改，提交仍必须 scoped add。

> **2026-10-05 文献首轮已整合**：先读 [文献入口](literature/sce/README.md)、[综述](literature/sce/literature_review.md) 与 [改进方案](literature/sce/research_design.md)。三名 Luna Max 子 Agent 与主 Agent 完成四主题研究，23 项论文/报告及 5 项案例/代码/数据入口、14 份本地公开 PDF。下一步是无 API 的回答诊断、SCE–CE 字段核查、同信息表达样例与对照运行卡；不得将文献建议视为已冻结参数或已验证机制。A 后验重建与 B 事前预测的边界继续分别声明。未改开题、运行配置及 Kimi 待审批次。

> **2026-10-05 开题候选已按原稿重修**：[两页开题候选稿](../proposal/proposal_submission_candidate_20261005.md) 与 [机制诊断/CPI 核对](INFLATION_MECHANISM_DIAGNOSTIC_20261005.md)。保留原提案标题、六节与 P/E/B 表格，面向评委阐述框架、经济学逻辑和验证，不写运行参数/人数/内部日程。基础流程通过，行为有效性仍待检验。原提案与 Kimi 待审批次未覆盖，平台未提交，正式参数未冻结。

> **2026-10-05 最新：真实两月开发实验已完成**。先读 [实验结果与准确路径](CORE_NORMAL_LLM_RECEIPT_20261005.md)。各 300 Core、934/997 Normal；600 次真实调用全部有效，估价合计 $0.536425。总体水平偏低、人群分布过窄，扩展未稳定优于直接加权。下一步先做无 API 诊断，再提出固定 P/E 对照。下方待授权/尚未运行为历史状态；Kimi 待审批次仍保留。

> **2026-10-05 Core/Normal 更新**：新增 [统计扩展开发验收](CORE_NORMAL_ACCEPTANCE_20261005.md) 与 [待授权真实 Core 运行卡](CORE_NORMAL_RUN_CARD_20261005.md)。按月 300 Core 可扩至完整人口，离线收益尚不稳定，保留直接加权基线；真实运行候选总上限 $2、数据目的地须明确确认，不把旧 73 人计划视为已执行。

> **2026-10-05 接力更新**：先读 [当前任务板](NEXT_ACTIONS.md) 与 [按月人口、运行及评价验收](MONTHLY_POPULATION_ACCEPTANCE_20261005.md)。本地已有真实 LLM 历史运行；本轮新按月人口、4 次规则式运行和独立评价入口已验收，新摘要提示词真实开发运行尚待预算确认。下文 10-01 的“未实现入口/未运行 LLM/缺依赖”等为历史状态，不作为当前执行依据。Kimi 10-03 待审批次继续保留，提交必须 scoped add。

> **2026-10-03 用户最新方向澄清**：先读 [A/B 两线研究定义](A_B_RESEARCH_DESIGN.md)（D048）。A是已知信息下的历史微观重建，B是t→t+1预测；下文旧交接中的事前可得性禁令不能一概套到A线。实时实现进度见任务板，旧文“尚未运行LLM/未冻结计分”等表述仅为历史记录。

更新：2026-10-01。读者：用户、Codex、负责实现的 Claude Code + Kimi。本文中的“Kimi”指用户已配置成功的 Claude Code + Kimi API，不假定已使用原生 Kimi Code CLI。

这是新 Agent 的背景与任务入口；实时进度以 [NEXT_ACTIONS](NEXT_ACTIONS.md) 为准，日期以 [ROADMAP](ROADMAP.md) 为准。本文不替代原始证据或研究协议。

## 1. 背景与当前阶段

用户是复旦大学管理学院金融专硕，申请加入魏忠钰教授的 DISC 科研实习。导师建议先参加 SocioVerse Challenge 2026，参照 ConsumerSim，选择一个指数进行 Agent 模拟与重建。当前队伍为“水上挽月”，按赛道 A 筹备，美国 SCE 居民一年期通胀预期是用户确定的研究主线。金融交易 Agent 平台是长期方向，企业 BIE、多国与内生价格形成均不进入当前最小项目。

研究采用 B=f(P,E)：P 是家庭画像，E 是截至指定时间已公开的信息，B 是模拟家庭对 SCE 问卷的回答。随后独立计分并与官方调查统计量比较。ConsumerSim 提供框架参照，SCE 的概率语义、计分和数据可得性需要单独验证。

**我们处于“准备材料 + 已跑通一个很小的规则式工程试验 + 部分计分复现”阶段。尚未完成真实 LLM 的 SCE 实验，也没有预测效果结论。**

拟主目标是 Q9 个人密度均值的跨人加权中位数；Q8 点预测是另一统计量。主次目标、正式窗口、人口规模和预算尚未冻结。候选窗口是 2020–2024；开发/验证/测试划分见研究协议，不能将候选配置当成已批准正式运行。

## 2. 目录与唯一源码

工作区：`/Users/wushuyue/Documents/科研/DISC`。

- **研究主仓库**：`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge`。协议、研究实现、数据审计、计分、测试、提案和交接都在这里。私有远端为 `https://github.com/Cynthia-Oakley/socioverse-challenge-2026.git`。
- **唯一 SCE 实现目录**：`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/studies/sce_inflation_expectations`。目前是骨架加计分器，不是完整可运行 study。
- **官方框架及本地工作流宿主**：`/Users/wushuyue/Documents/科研/DISC/socioverse2_repo`。含官方 `.claude/skills/`、MCP `.env` 和生成的 `.mcp.json`。框架固定 commit 为 `fa678ff6aea0e5a6497a7ffac15459123200a150`；生成脚本及其测试有本地修复，未提交。
- **云端 v2 原始归档**：`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/cloud_exports/2026-09-30/sce_inflation_expectations_v2`。仅作证据，不直接改写或当成新的生产源码。
- **早期调研参考库**：`/Users/wushuyue/Documents/科研/DISC/socioverse` 和 `/Users/wushuyue/Documents/科研/DISC/指标跟踪`。按需只读，不重做选题、不批量重排这些目录。

开发通常在研究主仓库启动；执行官方 `/sv-*` 工作流时在官方框架根目录启动，并读其规则与对应技能。不要在 DISC 父目录直接启动 Python 工作流：这里的同名 `socioverse/` 调研目录可能影响包解析。

若官方运行器必须将 study 放到自己的 `studies/` 下，先实现从主仓库**单向导出有版本/哈希的运行副本**，源码仍只维护一份；产物归档回主仓库的忽略目录。当前尚未实现这个适配入口，不手工维护两份持续变化的 model.py。最终提交包不能依赖这台电脑上的相邻 clone。

## 3. 已有成果与证据边界

1. **官方数据**：已下载 SCE 2020–2024 微观表、chart、问卷和方法材料；60 个月官方个人派生值到全国统计量的聚合已核验。另有 2017–2019 SCE、ACS 2019 说明和 BLS 2021 发布稿。来源清单见 `docs/sce_source_manifest.json`、`docs/peb_source_manifest.json`，原始文件见 `data/raw/` 对应 manifest。下载到当前文件不证明其历史版本当时可得。
2. **云端 v2**：2021-05、2021-06 两个月，20 个固定合成家庭；截止点分别是前月末纽约时间。E 为六条带发布时间的 BLS 首发信号。B 为 deterministic scripted，40 条 Q8/Q9 回答；模拟 LLM 调用数由平台摘要记为零。原始回答、model.py、environment.json、simulation.json 已取回并核对哈希，独立公式重演全部一致。
3. **v2 不是行为验证**：Q9 是与 E 无关的哈希模板；Q8 用事后编写的规则和无依据系数。Q8 中位数 1.43/2.31 只是流程诊断。v1 只有计划，没有 synthetic E 基线结果。
4. **v2 审计缺口**：实际运行传入 B 的 Observation、独立 run ID 和费用明细未保存。已有配置和重演不能补造这些证据。v2 取件已结束，下一版通过日志修复。
5. **Q9 计分**：`scoring/sce_q9.py` 已实现单档均匀、相邻双档三角及广义 Beta。2020-01、2022-06 的前两分支基本精确；Beta 开放尾和空档仍有差异，两个全国聚合误差约 +0.0068/+0.0111 个百分点。不能叫完整官方算法，也不能把计分误差称为预测误差。
6. **提案**：`proposal/proposal.md` 有草稿，尚未核验最终提交。报名、邀请码、导师署名和提交回执仍由用户确认，不从队名或平台访问成功推断。

详细证据按任务阅读：`docs/CLOUD_V2_PILOT_RECEIPT.md`、`docs/SCE_Q9_SCORING_REPLICATION.md`、`docs/SCE_DATA_AUDIT.md`。

## 4. 本地环境：可运行到哪一步

2026-10-01 检查：Claude Code 2.1.286 已安装；用户确认 Kimi 驱动成功。Conda `socioverse` 为 Python 3.11.16，SocioVerse2 0.2.0 已安装。Codex 在临时目录实际跑通官方离线示例（12 人 × 4 步，48 次规则决策，退出 0），原有 demo 未覆盖。

因此**基础本地 scripted 运行可用**。仍需分别处理：

- 该环境缺 `scipy`、`openpyxl`，SCE 计分及工作簿审计尚不能在这个环境完整运行。
- 缺 `openai`；官方项目 `.env` 未配置非空 `SV_LLM_API_KEY/BASE_URL/MODEL`。Claude Code 能对话，不会自动让模拟 B 使用其模型连接。检查未打印任何凭证；其他环境变量是否配置、实际 provider 能否调用仍待验收。
- Event/user_pool key 和 MCP 注册配置存在；尚未在本轮实际验证远端工具连接、字段和历史版本能力。
- SCE study 自身仍未在本地贯通。官方 demo 通过不等于 SCE 通过。

版本、检查方式与下一步命令见 [LOCAL_RUNTIME_ACCEPTANCE](LOCAL_RUNTIME_ACCEPTANCE.md)。代码助手费用、模拟 B 的 LLM 费用、组委会 MCP 费用分别记录。MCP 凭证仅供数据服务，不能代替 Kimi 模型凭证。

## 5. 必须保留的研究约束

- 输入 P/E 必须有明确来源与历史可得性；FRED 当前快照没有发布时间/vintage 时继续隔离。MCP 可访问不代表其回包满足历史时点要求。
- 当期真实答案、Q9 派生值、全国真值及尚未发布的同期人口/权重不得进入 B。P/E/B 用字段白名单，真值只在评价阶段读入。
- SCE 历史画像、ACS/SIPP/GSS 的联合分布及人格补充都要有证据或明示假设；不能把 user_pool 当作自动具有美国 SCE 代表性的人口。
- 2021 年历史回放使用训练截止较晚或未知的 LLM，有模型参数前视风险。限制 E 或写历史 prompt 无法消除它。此时称“回顾性条件模拟”；严格事前主张需要时间证据或未公布目标的前瞻封存。
- v2 的缺失 E 静默回退必须在新版本改为明确失败/隔离；从“Q9 合计 100”不能推断“官方个人密度已拟合”。
- 不为了对账调系数后冒称官方算法，不依据正式测试表现改目标、prompt 或测试窗口。改变研究口径先登记决策。
- 新运行保留唯一 run_id、源码版本和 dirty 状态、P/E/prompt 哈希、实际 B 输入、原始回答、模型身份、起止时间、失败/重试与费用来源。不保存隐藏思维过程，不把密钥写入日志。

完整约束见 `docs/RESEARCH_PROTOCOL.md`、`docs/MODEL_TEMPORAL_LEAKAGE.md`。

## 6. 协作分工与交接方式

- **用户**：研究目标与范围取舍、模型与预算、外部账号与最终提交。
- **Codex**：独立方法调研；Q9 Beta 差异定位、历史数据证据与前视风险分析；对关键实现和结果做独立复核。
- **Kimi**：按已定数据契约持续实现、测试、运行入口与日志、依赖和复现包；发现口径不明确时先做不依赖该决定的工作，记录具体缺口。

不要求每次修改都等 Codex。既定协议内的可逆实现、测试、文档与离线验收由 Kimi 连续推进；研究目标/as_of/测试期改变或新增付费规模由用户决定。独立验收重点是官方统计口径、输入隔离、运行日志和论文结论，不逐行审批日常代码。

每项任务在 `NEXT_ACTIONS.md` 标记负责人、可改文件和状态；同一时间公共协议/任务板只有一名整合者。可并行做只读调研，不同时改同一模块。用户负责在两个工具间发任务；本交接不表示双方已建立自动通信或调度。

每次交付仅需：任务号；改动文件；执行命令与关键结果；证据/产物路径；未解决问题；下一步。可审查的小块分别 commit，明确选文件；不得 `git add .`、reset 或 stash 他人未提交工作。

## 7. 第一批任务（沿用 T 编号）

**Kimi 先做 T03-L：本地 SCE 运行验收。** 使用已有 Conda 环境，补研究依赖，复跑现有计分测试与 v2 审计，保存依赖清单；读取官方工作流，设计主仓库到运行器的单向导出入口。再用免费 MCP 目录/画像查询验证连接与 schema，原始回包脱敏归档。先不批量取数、不运行真实模拟 LLM。验收记录更新 `LOCAL_RUNTIME_ACCEPTANCE.md`。

**Codex 可独立做 T01：计分差异研究。** 找官方原始拟合程序或足以解释 Beta 边界的来源，按误差形态定位，不反复优化以追拟合；给出可复现范围、不可辨识部分和是否需要主目标取舍。Kimi 此时不同时改 `scoring/sce_q9.py`。

**随后 Kimi 做 T04 的开发版流程。** 复用已有两月 P/E 建立可运行 study；原始 v2 不变，新版本修复 E 缺失处理并保存实际 Observation、输入哈希和 run_id；完整导出并能离线重算。规则式 B 明确标为工程用，Q9 暂留原始档与近似计分标签。

**T02 与提案继续并行。** 历史 P 基期证据、E 发布日历、最后已公布 SCE 基线；只对有证据的月份扩展。依据已有结果更新提案，不等待全量 LLM 实验才写。主/副目标取舍需要用户确认，截止日期只查 ROADMAP。

**T06 在上述准备后开展。** 冻结一次小额真实 B 实验的模型/提示/输入/预算和结果类别，先 20 人 × 2 月；通过审计后再扩大。不要因代码助手已连接 Kimi 而自动开启几十个月或千人模拟。

## 8. Git 与接力提醒

2026-10-01 检查：主仓库最新本地 commit 为 `d63cbae`（2026-09-27），之后大量研究、脚本、数据说明和 study 文件仍是未提交修改/新增；不能认为这些已经在 GitHub 备份。官方框架另有两处生成器修复。开工重新检查两个仓库状态，不把已有 dirty 文件当成自己的本轮改动。

源码可分任务提交；原始数据和云端归档大多在 `.gitignore` 内，Git push 不会备份它们。需要额外的合规数据备份，不能强制加入仓库。密钥只留本机受保护的配置中，日志/交接只记录是否配置。

启动提示可直接复制 [KIMI_START_PROMPT.txt](KIMI_START_PROMPT.txt)。
