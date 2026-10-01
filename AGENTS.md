# 项目协作规则

适用范围：整个 `socioverse_challenge/`。

1. 首次接手先读 `docs/AGENT_HANDOFF.md` 与 `docs/NEXT_ACTIONS.md`。确定任务后按需读取：目录看 `docs/PROJECT_STRUCTURE.md`，方法看 `docs/SCE_PROJECT_PLAN.md`，研究边界/实验变更看 `docs/PROJECT_CHARTER.md`、`docs/RESEARCH_PROTOCOL.md`、`docs/DECISIONS.md`。候选指数文档仅在回溯选题时读，不每轮重读全部资料。
2. 唯一主线：水上挽月、赛道 A、美国 SCE 一年期通胀预期。BIE 是扩展；不得自行换目标、as_of、测试期或数据口径。方向已确定不等于实验配置已冻结。
3. `../socioverse/`、`../指标跟踪/` 为外部只读参考。`../socioverse2_repo/` 是官方参考与本地工作流宿主，上游核心默认只读；T03-L 可管理必要运行副本和已有配置。SCE 新实现唯一放本仓库 `studies/sce_inflation_expectations/`，运行副本从这里单向导出并记录哈希，不复制第三方整仓或维护第二份源码。
4. 遵守 `CONTRIBUTING.md`。开工检查 git status；保留用户与其他 Agent 改动。多 Agent 获授权后每项任务划定文件范围，不同时改公共决策/配置。
5. 事实写原始来源、版本和核查日；区分官方要求、本项目约定、已验证结果与待验证假设。未实现目录/配置明确标 draft，不能称可运行。
6. 历史输入记录 observed_at/reference_period、published_at、vintage、as_of 与来源；未知可得日先隔离。观测月份、抓取时间、MCP 缓存名不能替代历史发布时间/版本。
7. 同期真值和真实问卷派生字段仅进评价层；P/E/B 显式白名单传递输入。不得用未公布的当期画像、权重或答案初始化 Agent。
8. 真实 LLM 调用前跑通确定性离线流程；正式测试前冻结目标、窗口、prompt、模型、预算与种子。测试结果不能用于调参；修复必须另留版本。
9. 不提交密钥、受限数据、原始大文件与自动运行产物；运行结果按 run_id 保留，禁止覆盖。提交打包使用明确文件清单。
10. 每项任务结束更新 `docs/NEXT_ACTIONS.md`；研究决策变更追加 `docs/DECISIONS.md`；改日程只更新 `docs/ROADMAP.md`。交接写清目标、输入、输出、验证命令、缺口和下一步。
11. 账号操作、授权、署名、提交和预算等不替用户作未经确认的承诺；已授权的本地开发与数据审计继续推进。

12. 2026-10-01 起按用户协作安排允许 T03-L 本地开发验收；历史云端方案仍见 `docs/CLOUD_PILOT_PLAN.md`。先用现有 Conda 环境和小样验收，不因本地工具可用就扩大真实调用。Codex 主导独立调研/复核，Kimi 主导实现/测试；文件分工和任务状态以任务板为准，公共文件同一时间由一人整合。
