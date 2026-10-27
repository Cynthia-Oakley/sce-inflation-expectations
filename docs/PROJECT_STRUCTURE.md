# 项目结构与目录职责

更新：2026-10-27。本页维护目录职责，当前研究全貌见[DESIGN](DESIGN.md)，任务与日程分别见[NEXT_ACTIONS](NEXT_ACTIONS.md)、[ROADMAP](ROADMAP.md)。旧云端阶段说明已转入[历史文档](archive/2026-10/README.md)。

## 开发目录与提交包分开阅读

`studies/sce_inflation_expectations/`是长期开发源码，不应直接整目录压缩提交。先读其[README](../studies/sce_inflation_expectations/README.md)和[文件导读](../studies/sce_inflation_expectations/FILE_GUIDE.md)。**正式审阅从[deliverables](../deliverables/README.md)进入**：当前v05在导出时实际按components/population、environment、behavior及runtime等重排，study根只有3个Python入口。159份主包源码、831份原始源码归档，标准工件和0API聚合复算保留。

v04只做导读与依赖筛选，仍有大量平铺模块，现已由v05替代。开发仓库源码及冻结输入/旧ZIP保留原路径；导出有逐文件迁移及SHA映射，不维护第二套科研算法。[本轮实际整理与验收](workstreams/20261027_clean_release/README.md)，旧[逐文件目录](workstreams/20261027_study_layout/README.md)仅作历史审计。

## 唯一维护地与官方引擎

本仓库`socioverse_challenge/`维护SCE研究代码、协议与报告；GitHub名为`socioverse-challenge-2026`。官方`../socioverse2_repo/`提供引擎与本地运行宿主，上游核心默认只读。本仓库向官方宿主单向导出运行副本并登记哈希，不维护第二套SCE源码。

`../socioverse/`、`../指标跟踪/`是外部只读参考。相邻目录不是可忽略的复现依赖：研究包须声明官方版本与安装/定位方法，不能把本机目录存在当成提交包已独立运行。

## 目录树

```text
socioverse_challenge/
├── README.md / AGENTS.md / CONTRIBUTING.md
├── docs/
│   ├── DESIGN.md / README.md          # 全貌与分类导航
│   ├── NEXT_ACTIONS.md / AGENT_HANDOFF.md / ROADMAP.md
│   ├── CURRENT_SIMULATION_CONFIGURATION.md / EXPERIMENT_STATUS_20261018.md
│   ├── literature/sce/               # 文献、原题与数据参考
│   ├── workstreams/<日期>_<主题>/     # 每轮计划、结果与有限聚合
│   ├── reviews/                      # 跨轮复盘、历史交接快照
│   ├── sources/                      # 来源、核查记录及保护清单
│   ├── archive/2026-10/              # 已整理的历史文档
│   └── figures/ / reports/           # 已有图表与阅读材料
├── studies/sce_inflation_expectations/
│   ├── study.yaml / resources.json / model.py
│   ├── experiments/                  # 准备适配器及共用执行封装
│   ├── evaluation/                   # 评价、基线、共享统计与诊断
│   ├── scoring/                      # 冻结近似Q9计分
│   ├── population/ / environment/ / simulation/
│   ├── mechanism/ / belief_dynamics/ / reporting_behavior/
│   ├── grounding/ / environment_authoring/
│   ├── trajectory/ / reports/        # 契约与可提交的小型证据
│   └── *.py                          # 已有专题实现，暂不重组
├── scripts/                          # CLI入口，索引见scripts/README.md
├── tests/                            # 计分、时点、支持、输入与运行等核查
├── data/                             # raw/restricted/interim/processed/evaluation/cache等
├── outputs/                          # 忽略的逐批产物，不覆盖
├── proposal/                         # 提案源稿与已提交版本记录
└── submission/                       # 最终交付清单与打包边界
```

目录存在不代表对应机制或最终研究包已通过验收。现有分支中既有可运行模块，也有历史/候选实现；状态见台账和各批协议。

## 文档维护规则

- DESIGN只概括当前设计与状态，细节指向专题页；配置、台账、任务、日程各有单一维护位置。
- 新实验的计划、运行卡、回执、结果写入对应workstream，不在docs根持续加日期文件。
- 任务板保留当前可行动工作；历史完成清单与交接快照归档。不能把旧授权或“正在运行”历史段落重新当作现场状态。
- 根目录仍保留方法专题、程序依赖、冻结证据及稳定阅读页，不为减少文件数强行移动。归档清单与原因见[本轮记录](reviews/20261019_repository_cleanup/README.md)。
- 历史文档移动时同时处理入站链接和相对资源；冻结文档/源码/来源清单保持原状。旧HTML和`current_todo.html`保留路径。

## 代码与产物规则

- 新研究算法放study；scripts只作入口。新增统计先查`evaluation/metrics.py`与共用评价层，不另造一套分位数/W1/权重定义。
- 区间估计显式区分按人聚类、按月成块和生成遍数；不同设计不能只因函数名相同而强行共用。
- 原始数据只追加，保留来源、历史稿次、可得日与许可；目标答案与输入物理分层。当前A线已声明的上期信念输入不等于允许输入本期目标答案。
- 真值、人月、完整提示/回包、原始大文件和密钥不提交。运行按run_id保留；经检查的小型聚合、图表和复算说明可入Git。
- 保存与推送、离线重算与API再生成分别说明；不因目录整理改旧运行manifest或重跑付费批次。
