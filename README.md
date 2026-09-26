# 指数调查模拟项目｜工作入口

更新：2026-09-26。此目录是“追指数”参赛研究的唯一工作入口；旧资料保留在 `../socialverse/` 和 `../指标跟踪/`，不把近 3 GB 的参考文件复制进开发仓库。

## 先读三份文件

1. [研究定义与当前判断](docs/PROJECT_CHARTER.md)：任务边界、事实与待验证假设。
2. [研究与评测协议](docs/RESEARCH_PROTOCOL.md)：目标变量、时点隔离、基线和验收条件。
3. [路线图](docs/ROADMAP.md)：10 月 9 日提案与 10 月 31 日终稿之前的交付门槛。

后续协作遵守 [AGENTS.md](AGENTS.md) 和 [版本管理规范](CONTRIBUTING.md)；每项重要选择写进 [决策记录](docs/DECISIONS.md)。当前执行事项见 [下一轮任务板](docs/NEXT_ACTIONS.md)。

## 项目边界

- **当前主线**：将 ConsumerSim 的“人群—信息—问卷回答—加权聚合”范式迁移到一个明确的调查统计量，完成 SocioVerse Challenge 2026 赛道 A 的可复现 study。
- **长期方向**：金融交易 Agent 平台是另一项目。它的资料在 `../socialverse/financial-market-simulation-proposal.md`，不进入本项目的 10 月交付范围。
- **资料库**：`../指标跟踪/` 是候选指标与方法学缓存，不是可直接用于历史回测的 point-in-time 数据库。

## 当前状态

- 候选：Ipsos *What Worries the World*（WWTW），**尚未定题**。它是调查项目而非单一官方指数，必须先确定国家、题目、统计口径和观察窗口。
- 比赛：提案截至 **2026-10-09 23:59（北京时间）**，最终提交截至 **2026-10-31 23:59（北京时间）**。
- 平台：SocioVerse2 **v0.2.0 已于 2026-09-25 公开**；`2026-09-24` 的旧笔记中“开源包不可用”的判断已过期。官方离线示例可作为环境验收。
- Git：本目录只保存研究设计、代码、允许再分发的小型派生数据和复现说明。原始 PDF、缓存、大体积数据、密钥与运行产物不入库。

## 证据入口

- [Challenge 官方页](https://socioverse.fudan-disc.com/challenge/)
- [SocioVerse2 发布说明](https://socioverse.fudan-disc.com/docs/getting-started/releases/)
- [SocioVerse2 安装指南](https://socioverse.fudan-disc.com/docs/getting-started/installation/)
- [Ipsos WWTW 2026-09 官方页](https://www.ipsos.com/en/what-worries-world)
- 本地旧资料：[ConsumerSim 精读](../指标跟踪/ConsumerSim_精读笔记.md)、[旧路线图](../socialverse/resource-research/09-项目路线图.md)、[IDX-0100 方法学缓存](../指标跟踪/methodology/IDX-0100/methodology.md)

旧报告是调研记录，不自动成为当前事实。官方版本、数据与软件接口变动时，更新决策记录和本页状态。
