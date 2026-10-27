# 水上挽月｜SocioVerse Challenge 2026

更新：2026-10-27。赛道A“历史重建与未来预测”；研究对象为美国SCE居民未来12个月通胀预期。

## 从这里开始

1. [项目设计总纲](docs/DESIGN.md)：研究问题、P/E/B、信息边界、评价及主要结果。
2. [当前任务板](docs/NEXT_ACTIONS.md)：近期工作与最终交付；[可视待办](docs/current_todo.html)由其生成。
3. [Agent交接](docs/AGENT_HANDOFF.md)：运行现场、保护文件、入口及下一步。
4. [文档分类索引](docs/README.md)与[脚本索引](scripts/README.md)：按问题找资料与运行入口。

协作先读[AGENTS.md](AGENTS.md)与[开发规范](CONTRIBUTING.md)。日程只在[ROADMAP](docs/ROADMAP.md)维护。

## 已做到哪里

已完成2019-01—2025-10的82月历史重建，最新T0原始Core全国Q9 MAE **0.2984pp**，统计扩展后 **0.3014pp**，仍落后公开历史持续性 **0.2232pp**。2021显著改善但仍是主要失败时期，微观分歧收缩依然存在。

近期B的11月回顾性时点模拟，最新Core原始/冻结组合MAE为 **0.3485/0.1443pp**，持续性 **0.1727pp**。周度固定300户、47周对应11份月真值，原始模拟MAE **0.1516pp**，同月持续性 **0.1727pp**；有局部增量，仍漏报9月上升。下游月度模拟在循环信贷上提供局部用途线索，其他结局混合；不主张普遍预测优势。

**本地交付入口：**[研究包与验收](docs/workstreams/20261027_submission_update/README.md)、[研究/论文/视频框架](docs/workstreams/20261027_final_delivery/index.html)、[固定研究包指针](submission/latest_package.json)。默认零API：官方Core规则示例＋封存聚合误差重算；完整个体重现仍需受控资料，不能以聚合缓存代替。

A以明确历史重建条件运行；B/周度并非事前封存的真实未来预测。模型知识、旧人口与文本版本边界均保留。源码在study内维护，真实大批量生成使用本地冻结消息调度，官方Core承担接口与离线验收；不将本地适配器生成冒称全部由官方Core在线执行。

## 项目区域

- [study](studies/sce_inflation_expectations/README.md)：SCE实现的唯一维护地。
- [运行与评价流程](docs/EXPERIMENT_PIPELINE.md)：准备、干跑、授权运行、缓存评价。
- [data](data/README.md)：本地来源、历史版本、输入与真值分层；原始/受限数据默认不入Git。
- [文献](docs/literature/sce/README.md)与`docs/workstreams/`：理论依据与各批证据。
- [提案](proposal/README.md)与[最终提交](submission/README.md)：报告与研究包交付。
- `outputs/`：本地按批保存输入、回答与分析，禁止覆盖；完整微观产物不入Git。

[私有仓库](https://github.com/Cynthia-Oakley/socioverse-challenge-2026)用于版本保存。本地提交不等于已经推送。`../socioverse2_repo/`是官方引擎宿主，本仓库单向导出运行副本；其他参考资料库保持只读。详[目录职责](docs/PROJECT_STRUCTURE.md)。

开题报告已由用户提交；最终研究报告、研究包与演示视频按组委会通知于2026-10-31 23:59（北京时间）前提交。完整验收、许可与时点要求见[最终提交清单](submission/README.md)；具体安排仍以ROADMAP为准。
