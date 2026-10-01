# 水上挽月｜SocioVerse Challenge 2026

更新：2026-10-01。方向：**赛道 A · 美国 SCE 居民一年期通胀预期模拟与重建**。

本仓库 `socioverse_challenge/` 是研究协议、版本归档与本地验证入口；远端为 [私有比赛仓库](https://github.com/Cynthia-Oakley/socioverse-challenge-2026)。队伍名已由用户确定；报名提交、邀请码与平台权限尚未在本仓库核验。

## 从这里开始

**新 Agent 接力入口：[项目交接](docs/AGENT_HANDOFF.md)**。用户可将[启动提示词](docs/KIMI_START_PROMPT.txt)发给已配置的 Claude Code + Kimi；[本地验收记录](docs/LOCAL_RUNTIME_ACCEPTANCE.md)说明已通过与尚缺内容。

1. [项目结构与目录职责](docs/PROJECT_STRUCTURE.md)：文件放哪里、官方 study 如何对应、提交怎样打包。
2. [推进日程](docs/ROADMAP.md)：阶段、依赖、日期与验收门槛；这是唯一日程来源。
3. [当前任务板](docs/NEXT_ACTIONS.md)：实际进度与下一步；从第一项未完成任务开始。
4. [SCE 研究方案](docs/SCE_PROJECT_PLAN.md)：P/E/B、目标变量、数据和实验设计。

后续 Agent 先读 [AGENTS.md](AGENTS.md)；开发与 Git 规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。

当前执行建议：**云端 v2 作为已归档小样，开始本地开发验收；Codex 负责独立调研与复核，Kimi 负责实现和测试**。2026-10-01 已通过本地官方规则式 demo，SCE 专用依赖、MCP 连通性和真实 B 尚待验收。历史[云端预试验方案](docs/CLOUD_PILOT_PLAN.md)及[上传材料](proposal/cloud_input/README.md)继续保留。已有全国真值核验不等于全部历史输入已可用。

**2026-09-30 当前入口：**平台 v2 的两月 scripted 流程与配置已取回核对，见[首试记录](docs/CLOUD_V2_PILOT_RECEIPT.md)。[Q9 计分首轮复现](docs/SCE_Q9_SCORING_REPLICATION.md)已完成：单档/双档个人派生值基本精确，广义 Beta 仍是有误差的近似；暂不把它作为官方 headline 上传平台。下一步按[任务板](docs/NEXT_ACTIONS.md)完善计分与历史 P/E，下一次运行前补齐直接输入审计。已有[开题提案草稿](proposal/proposal.md)。

## 当前成果与缺口

- 已完成：SCE 2020–2024 年 60 个月公开微观数据审计、官方主统计量与点预测的跨人聚合核验。
- 已建立：`studies/sce_inflation_expectations/` 目录骨架和 draft 元信息；**尚不能运行完整 SCE 模拟**。
- 待完成：十区间概率的个人密度拟合、历史 P/E 可得性、发布日历、平台离线集成、基线和真实模型实验。
- 尚无 Agent 预测效果；实验窗口、模型、预算仍未冻结。BIE 企业预期只保留为后续扩展。

## 项目区域

- `docs/`：研究依据、协议、决策和进度。
- `studies/sce_inflation_expectations/`：本项目唯一的 P/E/B 实现与研究包。
- `data/`：本地数据与来源登记；原始、受限和派生实数文件默认不入 Git。
- `scripts/`：取数、审计、打包等辅助入口；现有 `audit_sce_sources.py` 保留。
- `tests/`：将来放计分、时间隔离、确定性运行等关键测试。
- `proposal/`、`submission/`：提案源稿与最终提交清单。
- `outputs/`：临时审计产物；正式仿真输出按 study 内的目录规则管理。

完整树和未来文件状态见 [目录说明](docs/PROJECT_STRUCTURE.md)。

## 专题索引

- [研究边界](docs/PROJECT_CHARTER.md) · [评测协议](docs/RESEARCH_PROTOCOL.md) · [决策记录](docs/DECISIONS.md)
- [数据实测审计](docs/SCE_DATA_AUDIT.md) · [学校取数清单](docs/SCE_DATA_REQUESTS.md) · [MCP 与 PMI 核查](docs/SOCIOVERSE_MCP_AND_PMI.md)
- [报名说明](docs/REGISTRATION_PLAN.md) · [交付清单](submission/README.md)
- 历史选题依据：[指数初筛](docs/INDEX_SELECTION.md)、[分类审计](docs/INDEX_TAXONOMY_AUDIT.md)。保留追溯，不再并行开发。

`../socioverse/`、`../指标跟踪/` 是只读参考库；`../socioverse2_repo/` 是官方代码参考与本地工作流宿主，不纳入本仓库、不作为最终复现必须存在的相邻目录。SCE 源码仍唯一维护在本仓库。`assets/路线图-中文版.png` 是早期静态图，当前安排以 ROADMAP 为准。

比赛硬截止：提案 **2026-10-09 23:59**，终稿 **2026-10-31 23:59**，北京时间。依据：[赛事官网](https://socioverse.fudan-disc.com/challenge/)，本次核查 2026-09-28。
