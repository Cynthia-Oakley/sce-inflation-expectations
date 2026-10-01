# 项目结构与目录职责

2026-10-01 补充：用户配置 Claude Code + Kimi 后启动 T03-L 本地能力验收。`../socioverse2_repo/` 同时作为官方工作流宿主；SCE 源码仍唯一维护在本仓库，需要时单向导出运行副本并记录版本，适配入口待实现。新的协作入口见 [AGENT_HANDOFF](AGENT_HANDOFF.md)，以下云端优先说明保留为历史安排。

2026-09-29 执行方式更新：按 [云端预试验方案](CLOUD_PILOT_PLAN.md)，优先让托管研究助手创建/运行小规模 study，本地负责数据准备、独立计分和版本归档。下文技术职责仍有效，但不是要求先本地实现全部模块；完整本地部署仅在云端能力或规模受限时启动。

更新：2026-09-28。本文是目录职责的唯一说明；日程只在 [ROADMAP](ROADMAP.md)，任务状态只在 [NEXT_ACTIONS](NEXT_ACTIONS.md) 维护。

## 1. 本轮审计结论

项目约 87 MB，其中约 86 MB 是已忽略的本地数据；根目录此前只有文档、审计脚本、数据与输出，没有正式 study。旧资料库未混入本仓库。问题主要是：旧选题仍出现在现行协议中、日程有多个版本、队伍名未同步、实现与交付路径尚未建立。

本轮保留现有审计代码和来源清单；建立 SCE study 骨架、提案/提交/测试入口，统一文档职责。未批量移动旧资料，未把未完成的算法包装成可运行系统。当前 Git 中有前几轮调研和本轮整理的未提交修改，不能把“目录整理完成”理解为“版本已备份”。

## 2. 三个名称

- 队伍名：**水上挽月**，用于展示和交付文件名。
- 本地仓库：`socioverse_challenge/`；GitHub：`socioverse-challenge-2026`。沿用现名，避免破坏既有链接。
- study_id：`sce_inflation_expectations`，用于程序路径与实验记录。名字表示研究对象，不承诺已实现实时预测。

## 3. 目录树

下面无标记项已建立；`[待实现]` 表示仅规定位置，当前没有创建虚假的有效配置或运行入口。

```text
socioverse_challenge/
├── README.md                        # 总入口与当前完成程度
├── AGENTS.md                        # 所有 Agent 必须遵守的简明规则
├── CONTRIBUTING.md                  # 编码、Git、实验与交接规范
├── docs/                            # 依据、研究协议、决策、任务板、日程
├── data/
│   ├── README.md                    # 数据分层、来源登记与 Git 边界
│   ├── raw/                         # 原始快照，只追加、不改写，忽略
│   ├── restricted/                  # 授权数据，忽略
│   ├── interim/                     # 清洗中间表，忽略
│   ├── processed/                   # 可得性检查后的 P/E，忽略
│   ├── evaluation/                  # 真值与真实问卷派生值，忽略
│   ├── cache/                       # 服务缓存，忽略
│   └── fixtures/                    # 可入库的小型合成测试样例
├── studies/sce_inflation_expectations/
│   ├── README.md                    # study 状态、运行方式与复现边界
│   ├── study.yaml                   # draft 元信息；不是已完成的运行配置
│   ├── model.py                     # [待实现] 官方接口注册与模型装配
│   ├── run.py                       # [待实现] dry-run / LLM 的统一入口
│   ├── grounding/                   # 事实、假设与来源；grounding.json 待实现
│   ├── population/                  # P 抽样/权重/构建器；population.json 待实现
│   ├── environment/                 # E 时点过滤/快照；environment.json 待实现
│   ├── simulation/                  # B、prompt、实验配置；simulation.json 待实现
│   ├── scoring/                     # SCE 密度拟合与跨人聚合
│   ├── evaluation/                  # 基线和评测代码；不存可被 B 读取的真值
│   ├── trajectory/                  # 输出契约说明；每次运行数据库与日志忽略
│   └── reports/                     # 报告源稿；自动生成图表放 generated/ 并忽略
├── scripts/                         # 下载、审计、导出/打包入口
├── tests/                           # 有独立预期值的关键正确性测试
├── proposal/                        # 1–2 页提案源稿；导出到 build/，忽略
├── submission/                      # 交付清单；审查后的打包产物到 build/，忽略
├── outputs/                         # 临时数据审计输出，忽略
└── assets/                          # 少量人工选定展示资源；旧路线图为历史资料
```

现有 `docs/sce_source_manifest.json` 继续作为已经下载的 SCE 文件清单，避免复制出另一套台账；后续来源登记扩展这个入口或显式迁移引用。`scripts/audit_sce_sources.py` 是实测审计脚本；将来通用算法提取到 `scoring/`，脚本调用它，避免两份算法漂移。

## 4. 官方布局与我们的扩展

赛事公布 `study.yaml`、`population/`、`environment/`、`simulation/`、`trajectory/`、`reports/` 和运行/复现说明的布局。官方框架另外说明 `model.py`、`grounding/`、`resources.json`、`versions/` 等职责。本项目在同一个 study 内增加 `scoring/` 和 `evaluation/`，根部增加日程、数据管理、测试与交付目录。这些是本项目约定，不冒称赛事硬性目录。

`study.yaml` 当前只声明研究身份和一月烟雾测试的占位步数；正式月度映射和运行配置在数据审计后建立。不会用空 JSON 冒充完成的 P/E/B。官方 schema 校验通过仅说明元信息格式正确，不表示能运行。

## 5. 依赖方向与防止污染

1. 原始数据 → 审计/来源登记 → P/E 构建器 → 固定输入快照 → 问卷行为 B → scoring → evaluation。
2. B 只接收明确列出的画像字段、允许的信息记录与自身历史模拟状态，不拿整张微观问卷表，不自行读取 `data/evaluation/`。
3. 同期 SCE 真值单独进入 evaluation。过去已公布的 SCE 可以作为明确标注的输入/基线，但不能自动把整个 SCE collector 加入 E。
4. 同样的 `as_of`、输入版本、目标月份用于 Agent 与对照。目录隔离之外，实施时必须验证真实调用参数中没有真值。
5. MVP 采用外生历史宏观环境与家庭作答；不把跨月记忆宣称为家庭行为内生改变实际 CPI。

## 6. 运行产物与提交包

- 正式运行使用唯一 `run_id`，输出到 `trajectory/<run_id>/`，禁止覆盖旧结果。元记录含 commit、dirty 状态、配置和数据哈希、模型/prompt、种子、成本、失败率。
- 发布材料经过名单筛选再进入 `submission/build/`；不直接 zip 整个工作区，也不只用 git archive（会漏掉需要分享但默认被忽略的实验数据）。
- 研究包以 `studies/sce_inflation_expectations/` 为主体，带上实际依赖的辅助代码、锁定依赖、许可允许的数据/合成样例和复现说明；不依赖本机绝对路径或旁边的官方 clone。
- 最终须分别说明：可免费干跑复现的流程、可从封存回答重算的统计结果、需要真实 LLM 才能重新生成的结果。若受限输入无法分享，提供公开数据对应实验，不能仅给一个无法验证论文结论的玩具样例。

## 7. 官方依据

核查日期：2026-09-28。

- [赛事页](https://socioverse.fudan-disc.com/challenge/)；动态要求来自该页的 `challenge.js?v=20260928c`，本次文件指纹见 [来源记录](challenge_requirements_source.json)。
- [Study 目录说明](https://socioverse.fudan-disc.com/docs/concepts/study-anatomy/)。
- [本次核对的 StudySpec 源码](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/socioverse/schemas/study.py)。本机官方参考 clone 同 commit；尚未进行本项目完整运行环境验收。

## 8. 本轮实际检查

- 官方上述 commit 的 `StudySpec.model_validate` 校验 draft 元信息通过；没有进行完整 P/E/B 配置与 runner 验收。
- 检查 51 个本地 Markdown 链接，未发现缺失目标；文档 JSON 解析通过。
- 检查 12 类密钥/数据/生成产物路径，均被 Git 忽略；目录说明及 study.yaml 仍可纳入版本。
- `git diff --check` 通过。以上仅是本轮结构整理验收，不是模型性能或全流程可复现性的证据。
