# 目录地图

- 包根README、PORTABLE_REPRODUCTION：评审入口与命令。
- `studies/sce_inflation_expectations/`：正式study；study.yaml、P/E/模型配置、默认run.py、评价组件、报告导读。
- `simulation/reviewer_pipeline.py`：安装原工程独立工作区，公开输入重建与自备Key全链路。
- `reproduction_data/micro/`：正式逐答卷与冻结数值资料，支持快速0API复算。
- `reproduction_data/inputs/`：66,822份完整原样Prompt及原有P/E文本组件。
- `reproduction_data/portable/public_sources.zip`：公开源快照、人口/先验与候选环境/标签、原工程需要的中间输入；带路径、角色、来源哈希清单。
- `reproduction_data/portable/runtime/inputs/`：四条任务的动态模板与初始状态；生成不解析其旁边的evaluation目录。
- `reproduction_data/portable/runtime/evaluation/`：单独的目标、测量缓存与Normal人口框架，生成结束后才由评价进程读取。
- `reproduction_data/portable/evidence/`：原始模型回复、调用凭证、编号映射、来源对账。
- `reproduction_data/portable/calibration/`：A早48个月组合与原宏观/ridge的真实重新拟合，含82个月CPI/日期输入。
- `reproduction_data/portable/downstream/`：经济序列原始快照、原面板/回归程序和参考结果，可重新拟合。
- `archive/research_source_supplement.zip`：完整原工程代码。便携安装会恢复这一份代码，保留原导入结构；主study按职责整理的代码用于快速复算，两份都由哈希对应，不是两个不同科学方法。
- `archive/planning_20261027/`：历史写作和演示计划，非当前运行状态。
- `experiment_logs/`：公开实验台账；原始调用级凭证见portable/evidence。

`install`建立新的 `review_workspace/`，把原工程路径与公开输入恢复在一起。此后 `prepare/run/evaluate/downstream`只依赖该工作区和已安装的SDK，不依赖作者电脑旁边的其他仓库。每次真实运行独立命名，旧研究与旧版ZIP保留。
