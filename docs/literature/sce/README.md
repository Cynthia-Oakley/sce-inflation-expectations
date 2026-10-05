# SCE 文献研究入口

研究主题：美国居民一年期通胀预期的 Agent 调查重建与预测。任务启动日：2026-10-05。

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
