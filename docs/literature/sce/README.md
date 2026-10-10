# SCE 文献研究入口

研究主题：美国居民一年期通胀预期的 Agent 调查重建与预测。任务启动日：2026-10-05。

**2026-10-10 持续性、政策与信任专题初核：**[研究笔记](themes/persistence_policy_trust_20261010.md)／[浏览器版](themes/persistence_policy_trust_20261010.html)。补充“价格变化会持续多久”的连接，区分政策理解、央行/政府信任、政治认同与一般乐观；Pew受众构成不直接证明经济报道偏差。当前输入已含Fed暂时性与供应链叙述，先核查解释与曝光，再选机制；未启动新模拟或取得外部微观数据。

**2026-10-06 心理与家庭状态专题：** [新专题入口](psychological_attributes/README.md)、[整合综述](psychological_attributes/literature_review.md)、[实施建议](psychological_attributes/implementation_proposal.md)。理论、数据、合成方法由三名 Luna Max 并行调查；主 Agent 整合。与下方首轮来源目录分开，避免重复计数。价格体验小试已运行但尚无稳定改善；本专题优先家庭状态和信息处理，幸福/满意联合 donor 作为探索。未新增模拟调用；新心理机制尚未实现。

**2026-10-06 落地更新：** [价格体验机制入口](../../PRICE_EXPERIENCE_MECHANISM.md)、[工程验收](../../PRICE_EXPERIENCE_ACCEPTANCE_20261006.md)、[输出诊断](../../MECHANISM_OUTPUT_DIAGNOSTIC_20261006.md)、[CE 可行性](../../MECHANISM_DATA_FEASIBILITY_20261006.md)。补充数据来源单独索引于 [sources/ce_experience_sources_20261006.json](sources/ce_experience_sources_20261006.json)，不混入首轮 28 条文献计数。第一版已离线接入，真实机制效果未验证；下方“未改运行源码/下一步准备”为 10-05 首轮状态。

**第一轮已完成。** 三个 GPT-6 Luna Max 子 Agent 并行研究预期形成、价格体验和 Agent 方法；主 Agent 核对官方案例、交叉检查并整合。共登记 23 项论文/研究报告与 5 项案例、代码或数据资源，14 份公开 PDF 原文已在本地归档。摘要、页面预览与全文分别标明，不称为穷尽式系统综述。

## 阅读顺序

1. [literature_review.md](literature_review.md)：先了解文献对当前瓶颈的解释与边界。
2. [research_design.md](research_design.md)：再看如何形成可检验的改进方案。
3. [reading_guide.md](reading_guide.md)：需要深入时，按顺序读核心原文；包含本地 PDF 链接。
4. [review_plan.md](review_plan.md)：任务边界、分工与来源标准，便于其他 Agent 接力。
5. `themes/`：主题证据笔记；`sources/`：可检查的来源与归档目录。
6. [review_receipt.md](review_receipt.md)：本轮核验、更正、缺口与接力事项。

## 目录职责

- `themes/expectation_formation.md`：预期形成、学习、有限注意与信息干预。
- `themes/household_price_experience.md`：消费价格体验、人口差异与可用数据。
- `themes/agent_simulation.md`：LLM 模拟、分布校准、Core/Normal 与评价。
- `themes/socioverse_cases.md`：SocioVerse 官方案例及 ConsumerSim 的可借鉴边界。
- `sources/`：四个主题各维护一份 JSON 来源清单，记录全文/摘要阅读状态与原文位置。
- [sources/catalog.json](sources/catalog.json)：统一来源索引；[sources/archive_manifest.json](sources/archive_manifest.json)：实际下载、原文路径、哈希与失败历史。
- 原文若下载，放 `data/raw/literature/sce/20261005/<theme>/`（本地忽略），不将整篇论文或受限材料推送到 Git。

本地原文目录：`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/literature/sce/20261005/`。该目录不是 GitHub 备份的一部分；阅读指南逐篇提供可点击文件路径及公开原文链接。

本目录是方法研究材料，不替代研究协议、运行配置或实验记录。已有开发结果保留；文献结论、项目假设与已验证机制分别注明。

## 本轮建议与下一步

优先检验“公共信息怎样变成家庭的价格感知”，保留人口差异、问卷语义与独立评价。先做现有回答圆整/概率模板诊断、SCE–CE 字段与版本核查、同人同信息的表达样例；再制作可审阅的对照运行卡。体验视图、长期状态和校准分步试验，不通过添加噪声或统一抬高答案来追齐全国指标。

本轮未改变人口、E、prompt、模型、运行参数或开题报告，也未新增模拟 LLM/MCP 付费调用。具体设计仍是方法建议。

## 进入 SocioVerse 研究包的方式

这里保存可持续维护的研究笔记与统一来源。后续打包时将引用及选定综述导出到官方 study 的 `literature/` 和 `reports/`，并登记资源；本轮没有生成平台 `literature.json` 或修改 study schema，不把这些 Markdown 文件称为已集成的平台组件。论文原文下载不进入公共/私有 Git 包，按许可与提交需要另行筛选。
