# 水上挽月｜SocioVerse Challenge 2026

更新：2026-10-19。赛道A“历史重建与未来预测”；研究对象为美国SCE居民未来12个月通胀预期。

## 从这里开始

1. [项目设计总纲](docs/DESIGN.md)：研究问题、P/E/B、信息边界、评价及主要结果。
2. [当前任务板](docs/NEXT_ACTIONS.md)：近期工作与最终交付；[可视待办](docs/current_todo.html)由其生成。
3. [Agent交接](docs/AGENT_HANDOFF.md)：运行现场、保护文件、入口及下一步。
4. [文档分类索引](docs/README.md)与[脚本索引](scripts/README.md)：按问题找资料与运行入口。

协作先读[AGENTS.md](AGENTS.md)与[开发规范](CONTRIBUTING.md)。日程只在[ROADMAP](docs/ROADMAP.md)维护。

## 已做到哪里

已跑通本地文件P/E → 官方SocioVerse2引擎 → 真实LLM回答 → 轨迹与费用记录 → 冻结近似Q9计分和评价。可复用既有输入、真值缓存与封存回答，区分离线重算和新增调用。

当前主结果是12期×192人×两遍的回访者条件历史模拟：Q9群体中位数MAE **0.459pp**，同支持照抄本人上期 **0.239pp**；跨人差异仍不足。项目工程可运行，整体拟合尚未达到目标。最新六期新闻量候选不能替代十二期成绩。详[当前配置](docs/CURRENT_SIMULATION_CONFIGURATION.md)、[实验台账](docs/EXPERIMENT_STATUS_20261018.md)与[十二期结果](docs/workstreams/20261017_reference_scaleup/results.md)。

当前A线可使用声明过的真实历史画像及上期信念。B线的事前人口、自身信念递推、新入组者和封存预测仍有缺口，不把A线结果称作严格未来预测。

## 项目区域

- [study](studies/sce_inflation_expectations/README.md)：SCE实现的唯一维护地。
- [运行与评价流程](docs/EXPERIMENT_PIPELINE.md)：准备、干跑、授权运行、缓存评价。
- [data](data/README.md)：本地来源、历史版本、输入与真值分层；原始/受限数据默认不入Git。
- [文献](docs/literature/sce/README.md)与`docs/workstreams/`：理论依据与各批证据。
- [提案](proposal/README.md)与[最终提交](submission/README.md)：报告与研究包交付。
- `outputs/`：本地按批保存输入、回答与分析，禁止覆盖；完整微观产物不入Git。

[私有仓库](https://github.com/Cynthia-Oakley/socioverse-challenge-2026)用于版本保存。本地提交不等于已经推送。`../socioverse2_repo/`是官方引擎宿主，本仓库单向导出运行副本；其他参考资料库保持只读。详[目录职责](docs/PROJECT_STRUCTURE.md)。

开题报告已由用户提交；最终研究报告、研究包与演示视频按组委会通知于2026-10-31 23:59（北京时间）前提交。完整验收、许可与时点要求见[最终提交清单](submission/README.md)；具体安排仍以ROADMAP为准。
