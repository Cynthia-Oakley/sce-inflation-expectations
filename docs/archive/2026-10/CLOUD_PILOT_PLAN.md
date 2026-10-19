# 云端优先的 SCE 验证方案

核查：2026-09-29；状态补充：2026-09-30。建议采用**云端创建与小规模运行，本地数据准备、独立计分和版本归档**；完整本地 SocioVerse2 部署改为按需。研究目标、历史信息要求与评价协议保持原定义，执行顺序按 [ROADMAP](../../ROADMAP.md)。

**v2 首试进度：**平台已报告 20 人 × 2 月的 BLS E + 合成 P + scripted B 流程；40 条原始回答、`model.py`、`environment.json` 和 `simulation.json` 已通过对话取回、核对哈希。环境的六条信号和 20 个画像与本地来源相同；按本地 P/E 对代码公式重演与 40 条回答完全一致。逐项证据和代码局限见[首试记录](../../CLOUD_V2_PILOT_RECEIPT.md)。托管工作台目前无下载按钮；v2 取件阶段结束。平台未保存实际传给 B 的 Observation、独立 run ID 和费用流水，下一版本须增加记录；本地 C4 的运行时输入/费用完整性尚未通过，不据此直接进入真实 LLM 小试。

## 1. 已核验到什么程度

- 核对官方托管工作流、工作台、额度、限制、MCP 文档及公开前端/StudySpec。所引用固定代码 commit 为 `fa678ff6aea0e5a6497a7ffac15459123200a150`；在线 main 的 backtest 元信息与上传函数本轮也核对一致。
- 用户报告新项目界面有提示词、文件入口及人工确认。公开前端支持上传和导出入口，能为该观察提供代码依据。
- 本轮浏览器进入用户给的新项目 URL 后被重定向至登录页，未获得账户工作台状态；没有登录、创建 study、上传文件、调用付费 MCP 或运行模型。未验证账号额度、上传成功、数据完整导出及云端已安装包。
- 官方 Hosted FAQ 称不能上传/没有下载按钮，但同版本前端已有这些功能；应视为文档与实现冲突，不能用旧 FAQ 断言必须本地，也不能凭按钮断言所需格式和完整研究包导出均可用。

## 2. 平台确实承担研究执行流程

官方流程为：提出研究问题 → 路由与证据整理 → 必要时创建模型 → E → P → 运行 → 报告 → 版本迭代。研究助手负责文件、模型和流程；模拟中的家庭 Agent 负责问卷回答；外部 MCP 提供数据或特定抽样/问卷能力。这三者需分别理解。[S1]

云端通过对话修改 study 产物，存在人工确认节点，真实运行前说明配置与成本。通常不必由我们先写完模型装配代码再启动。开源版也有同类 sv-* 工作流，本地不等于全部手工重写。[S1,S2]

云端提供研究 Agent 和 Simulation 两类额度。研究对话本身消耗前者；模拟和外部能力调用涉及后者。额度文档、比赛页面、能力注册对赠送额/读操作扣费存在不同描述，以账号余额、确认卡和实际记录为准，不在计划中承诺某个免费额度。[S3]

## 3. ConsumerSim 案例的关键区别

用户所链接 `consumer_confidence_us_backtest` 在公开元信息中为 `status: backtest-import`、`rerunnable: false`。内容从已发布的 ConsumerSim 结果生成，显示的研究问题并不是当场重新运行整套研究的证据。[S4]

可运行的 `consumer_confidence` 是另一 study，并依赖 ConsumerSim 外部管线。它可供参照，但不能把其 CCI 问卷、校准、人口扩展和评分不加修改搬到 SCE。建议**新建 SCE 原生 study，参考调查与结果展示方式**，由平台说明可复用模块及必须替换部分。

SCE 至少要定制：Q8/Q9 问题语义、十概率区间、个人密度拟合、两种跨人聚合、历史输入隔离。框架可能不用改；study 内的模型与计分仍需实现和验证。

## 4. P 与 E 的具体安排

### P

- 基础版优先来自有历史可得性证据的 SCE 人口结构/画像；云端先传小型合成或许可允许的数据包，字段含 agent_id、年龄/教育/收入/地区、明确的权重规则与数据字典。
- 不把未公布的同期真实回答、派生通胀均值、真实当期权重上传后混入 P。初期以合成测试文件检验接口；公开匿名记录是否适合托管仍需符合来源条款与平台对真实个体记录的限制。
- “persona/人物画像”可指人口经济属性；若“人格”指 Big Five 等心理量表，当前 SCE 审计没有证明有其联合分布，SIPP 也不能仅凭名称当成该分布来源。额外人格赋值需独立依据或明确是假设，并做有/无人格消融。第一版可以不加。
- `sipp` 在 Event 服务人口采集器中，不是 Population MCP 现成人格池；已注册 persona 池不等于 SCE 面板。是否实际取得、返回哪些字段均待样例验证。[S5]
- Population MCP 不是必须调用的关卡。已有可信 SCE P 可以直接用于 study；避免为“接了 MCP”再把人口结构随机替换。若使用分布抽样，检查联合分布、virtual users 与默认独立抽样。

### E

- 云端优先调用 Event MCP 的相关来源，减少自建取数；先取少量开发月样例并物化为快照，缺口才补官方档案/学校库。
- 不加载包含当期 `nyfed_sce` 的默认全来源集合。宏观值和新闻仍检查实际发布日期、版本、文本更新与截止时点；观测月份过滤不等于历史可得性。[S5]
- 学校新闻全量申请退为补缺路线；当前只需保留权限/小样准备。若 MCP 返回摘要/元数据，模型看到什么必须如实记录。

## 5. 云端预试验的五个检查点

### C0：研究任务确认

先用 [2026-09-29 首试上传包](../../../proposal/cloud_input/README.md) 请求平台解释执行路径、可复用组件、数据缺口、模型/计分安排及产物导出能力。旧版[通用启动说明](../../../proposal/cloud_start_prompt.md)留作参考。先停在方案确认，预算未定前不启动批量 MCP 或真实模拟。平台正常研究对话可能消耗 Agent 额度。

### C1：文件与人口导入

用不含真实个人信息的极小 CSV 和数据字典测试上传；让平台报告实际读取行数、列名、缺失、权重总和，生成 P 后再核对画像数、字段和若干样例。文件上传成功不等于它已进入 population。之后才替换为经过许可与时间核验的历史 P。

### C2：历史信息及计分

请求少量 Event 样例，核对 time/vintage/provenance 与排除的来源。让平台展示并测试从十区间到个人派生值的计分实现；不能接受“用加权区间中点即可”的替代。计分可在云端生成，再下载到本地用真实数据独立核验。

2026-09-29 实测反馈的具体补救：Event `fred` 当前快照缺历史发布时间和版本时仍隔离；针对 2021-05/06 首试，改用[已核对的 BLS 当期发布资料](../../E_PIT_RECOVERY.md)构建真实 E。合成 E 只用于检验文件/模型管线，不能成为历史 E 的默认替代。

若云端环境缺少拟合依赖或结果不正确，优先选择“云端输出原始回答，本地独立计分”，无需立即迁移整套框架。完成主目标计分验收前，界面只能标示流程样例/点预测结果，不标为已重建官方 headline。

### C3：两月流程与小规模 LLM

先 20 个合成人物 × 两个相邻开发月，以 scripted 行为验证读入、结构化回答、月份、存储和导出；合成流程不作为 SCE 有效预测。用已验收 P/E 后，再估价并确认 20–50 Agent × 两月的真实调用。人数只是流程验证，不是正式研究规模。

### C4：导出与本地复核

导出至少应覆盖：study 元信息、P/E 快照、行为/计分代码、prompt 与运行配置、逐人逐月回答、聚合量、模型与成本、来源记录。检查人数×月份的行数、哈希和字段完整性，再在本地重算聚合。

公开代码已有表格 CSV 与 all/Word/LaTeX 导出入口；真实云端后端和整包内容未验收。CSV 实现有行数上限，不能把“下载了 CSV”自动当作全量归档。单份 PDF 或曲线截图不满足此检查点。[S6]

## 6. 如何决定下一阶段部署

- **继续云端**：可控制 P/E/问卷/计分，输出完整可核验，时长、模型和额度足以支持预定规模。通过预试验后再估计正式规模，不一开始运行 500 人×60 月。
- **云端 + 本地分析**：云端生成回答并提供完整导出，本地负责精确计分、基线、图表与版本保存。这也是正式研究可采用的路径。
- **转完整本地运行**：不能导入所需 P、无法隔离真值/锁定 prompt、缺必要依赖、导出不完整、模型选择不满足比较，或长窗口/多种子超出云端实际容量。此时再安装运行环境，申请 MCP 凭证和准备模拟 LLM API；能用冻结数据则不必每次连 MCP。

官方将托管定位为小规模试验环境，文档列 2 CPU/2 GB、通常约十分钟内运行，禁止助手改框架/安装软件/执行 Git。因此 SCE 小试适合先尝试；正式长窗口仍需容量验收。[S7]

## 7. 本地仓库继续承担什么

仓库保留，不删除既有结构。本地负责：研究协议与真值审计、上传材料/字典、平台每个确认节点的决定、导出快照、独立计分和基线、Git 备份与提交包。云端助手不能替我们 commit/push。[S7]

云端是当前 study 的执行端；本地是受控归档和验证端。导出先存被忽略的 `data/raw/cloud_exports/<date>/<cloud_study_id>/`，检查后再将允许入库的代码/配置同步到现有 `studies/sce_inflation_expectations/`。保留 cloud_study_id 与本地 study_id 映射，不盲目覆盖文件，不维护两套不同研究口径。

## 来源

- S1：[云端完整工作流](https://socioverse.fudan-disc.com/docs/hosted/chat-workflow/)
- S2：[工作台](https://socioverse.fudan-disc.com/docs/hosted/workbench/)
- S3：[额度与计费](https://socioverse.fudan-disc.com/docs/hosted/quotas-and-billing/)
- S4：[backtest 元信息](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/studies/consumer_confidence_us_backtest/study.yaml)
- S5：[数据服务](https://socioverse.fudan-disc.com/docs/guides/data-services/)；[能力](https://socioverse.fudan-disc.com/docs/guides/capabilities/)
- S6：[上传实现](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/dashboard/web/v2/chat.js#L256-L302)；[API 前端](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/dashboard/web/v2/api.js)；[表格读取代码](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/dashboard/server/app.py)；[存在冲突的 FAQ](https://socioverse.fudan-disc.com/docs/hosted/faq/)
- S7：[云端限制](https://socioverse.fudan-disc.com/docs/hosted/limits-and-fair-use/)
