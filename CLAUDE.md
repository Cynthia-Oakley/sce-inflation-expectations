# SCE 项目入口

本目录是SCE研究主仓库。遵守[AGENTS.md](AGENTS.md)与[CONTRIBUTING.md](CONTRIBUTING.md)。

首次接手先读[设计总纲](docs/DESIGN.md)、[当前交接](docs/AGENT_HANDOFF.md)和[当前任务](docs/NEXT_ACTIONS.md)，再按任务进入专题。历史KIMI_START_PROMPT已归档，不再作为当前任务指令。

本地官方SocioVerse2引擎的真实LLM流程已运行；当前主线是使用真实上期信念的A条件历史重建。12期参考配置仍未超过同支持持续性基线，不称为严格B自主预测。具体结果与限制以DESIGN和当前配置为准。

官方框架、`/sv-*`技能和MCP配置位于相邻`socioverse2_repo/`；本目录不自动继承它们。运行官方工作流时读其规则与技能，SCE源码只维护本仓库，向宿主单向导出并记哈希。

开工检查工作区及保护清单；旧批次完成后不得重复启动，新增真实调用按具体数据范围/目的地/预算取得授权。只更新当前任务与交接条目，历史细节放对应workstream，不继续在公共页前置长快照。
