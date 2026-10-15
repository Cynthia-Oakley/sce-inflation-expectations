# 本地运行方案（socioverse2_repo harness + 自备 LLM API）

## 2026-10-16实际链路与资助使用建议（当前）

用户询问是否仍在使用SocioVerse2，以及如何使用恢复的$70。本轮只核对本地源码、已保存的运行配置及免费探测缓存，没有新模型或付费MCP调用。

### 实际用了什么

- **模拟引擎来自官方SocioVerse2。** 当前Python实际导入`../socioverse2_repo/socioverse/`，`build_simulator`位于其`engine/builder.py`。八期入口`run_sce_expanded_trial.py`和最近入口`run_sce_revision_format_trial.py`都构造官方EnvironmentBundle/PopulationBundle/SimulationConfig，再调用`build_simulator(...).run()`；轨迹使用官方DuckDB存储。官方框架HEAD为`fa678ff6aea0e5a6497a7ffac15459123200a150`，本轮检查engine/schemas/io无本地未提交差异。
- **SCE研究实现由我们编写。** `studies/sce_inflation_expectations/model.py`继承官方PopulationProvider/EnvironmentProvider/DecisionModel/MetricCollector，并通过官方registry注册。画像、环境素材、提示、信念实验、Q9近似计分、基线与分析属于study扩展。
- **外层研究编排主要由本地助手和自写脚本承担。** 批次切分、费用上限、输入哈希、重试约束、快照及报告是自写入口。没有持续调用托管研究助手逐阶段重新规划研究，也没有将底层运行循环换成独立模拟引擎。
- **当前八期不是连续八个月自主递推。** 已保存配置`n_steps=1`，每个目标月独立运行，所需真人历史在构建时注入，用于A条件重建。官方引擎有跨步记忆能力，但B路线的自有信念递推、轮换/新进入者和误差累积仍待接线验收。

### $70如何使用

1. **本地主线保持稳定。** 继续使用官方开源引擎与现有DeepSeek连接。平台额度用于托管研究/平台MCP，自购DeepSeek/OpenRouter另行计费；当前没有取得能把任意本地LLM请求计入资助的转发端点证据。
2. **先按缺口使用Event MCP。** 先免费查目录/能力，再对少量确有缺口的历史源检查发布时间、版本及返回字段。通过后才考虑批量补充；不重复下载已核验SCE/BLS/CE，不把MCP当前快照自动当成历史版本。平台服务不能返回所需证据时，继续隔离严格B输入。
3. **Population服务暂不替换真实SCE人口。** 我们已有更贴近研究对象的真实画像与面板。2026-10-01缓存中人群池提供付费问卷服务，但各池代表性、字段、模型别名和逐人输出须重新验收，不能当成现有P/E/B的透明替代。
4. **平台Simulation仅考虑一个受控小对照。** 优先核实能否直接运行准备好的study，或通过服务提交相同画像/问卷/历史状态，并明确模型版本、价格、实际输入与逐人原回答导出。若这些条件可满足，再固定一小批对照与预算。若接口不能承载相同条件，不能将其输出混入当前实验当同方法重复。
5. **避免长对话重复开发。** 平台研究助手的编排调用与模拟模型调用分开记账。若运行托管版本只支持经助手触发，使用已冻结文件与一次简短运行指令，先审费用/导出能力；不要求其重新检索文献、造人口和改写整套study。尚未验证有独立托管Simulation直调API，不作此承诺。

额度保留按需使用，无需为了使用资助搬迁主线。新增付费范围仍先落实数据/方法/预算要求。本轮未消耗资助。

## 2026-10-02方案与后续历史记录

下文保留早期状态，不作为当前余额、模型、调用或实现完成度的依据。

更新：2026-10-02（Kimi）。背景：云端余额 $-0.20 透支，10-15 初筛通过后才追加 $70；10-15 前 Sim 主线转本地。本文基于对官方仓库实际源码的核查（非推测）。

2026-10-03 Codex 核查补充：模型最新建议、公开价格及接入验收见 [MODEL_SELECTION_20261003](MODEL_SELECTION_20261003.md)。用户已有 Kimi、DeepSeek API；建议先复用 DeepSeek 官方当前 Flash 做小试，尚未批准模型/预算或实际调用。OpenAI 兼容是协议接入条件，不保证所有参数可直接通用；运行期仍需联网调用 LLM，只是无需联网获取 E。

## 官方架构核查结论（2026-10-02 实测）

| 机制 | 位置 | 事实 |
|---|---|---|
| LLM 客户端 | study 的 `model.py` 内 `_make_llm(llm_kind, model=...)` → `_OpenAILLM` | 读 `SV_LLM_API_KEY`（备选 `OPENAI_API_KEY`）+ `SV_LLM_BASE_URL`（**任何 OpenAI 兼容端点**，默认官方 OpenAI）；模型名钉在 `simulation.json` 的 `decision_args.model`，未钉时读 `SV_LLM_MODEL` |
| 引擎 | `socioverse/engine/builder.py` `build_simulator()` + `loop.py`/`memory.py`/`registry.py` | 本地装配运行；轨迹写 DuckDB（`trajectory/study.duckdb`：panel/metrics/events 三表） |
| 人群 | `socioverse/providers.py` | **FilePopulationProvider**（本地 `population/population.json` + `roster.jsonl`）与 McpPopulationProvider（远程 persona 池）二选一——本地运行**不需要 Population MCP** |
| 事件/宏观 | `socioverse/external_events.py` ExternalEventsClient | 三级降级链：远程 Event MCP（`SV_EVENT_API_URL`）→ **local_cache**（`SV_EVENT_LOCAL_CACHE` 目录，`<source>/<YYYY-MM>.json`）→ unavailable。关键设计：**E 在 build 时物化到 `environment/external_events.json`，运行时从不联网**——所以本地不需要复刻 Event MCP 服务，只需 authoring 好 E 文件 |
| 归属规则 | external_events.py 文档字符串 | broadcast 只能从 `bundle.results`（结构化数据）authoring，**禁止用 `bundle.summary`**（那是另一个 LLM 的散文，会污染行为归因） |
| 离线验证 | `scripts/demo_offline.py` | 无 key 离线全跑通（scripted）；`--llm openai` 接真实 LLM（12 agent × 4 步）；运行前自动做一次端点 probe |

## 本地运行待办清单

### 1. Sim 模型（决策 LLM）

- 机制已通：任何 OpenAI 兼容端点均可（`SV_LLM_BASE_URL` + key + model 名）。
- 候选与知识截止（截止越晚，对 2021 目标月的"剧透"越多；但身份可登记是本地路径的核心优势）：
  - **Kimi（moonshot）**：用户已有 API（正在驱动 Claude Code）；`https://api.moonshot.cn/v1`；
  - **DeepSeek**：旧 `deepseek-chat` 已列入官方停用通知，不能用来固定原版 V3。2026-10-03 官方 `deepseek-flash` 映射 DeepSeek-V4.1-Flash；默认思考模式，首试建议显式关闭。完整训练截止未知，版本仍为服务商别名；详见最新选型记录。
  - **GPT-4o**：模型页标称 cutoff 2023-10-01，仍列出日期 API 快照。可做标称截止日前后探索比较，**不能由此认定全部 2024 月份为严格盲测**；需另核后训练/版本时点及 P/E。
  - **Qwen2.5-72B-Instruct**：硅基流动公开页面数据仍列出文本型号及价格；Together Turbo 端点已停服。开放权重版本与托管端点需分别登记。
  - 决策点：模型选型是研究口径问题，由用户定（建议先在开发月小样上测格式稳定性再定）。
- 待办：端点连通 probe → Q9 十档格式稳定性测试（非负/总和 100/可解析）→ 冻结 temperature、max_tokens、重试规则。
- **2026-10-03 进展**：probe 与小样入口已实现（`scripts/sce_llm_probe.py`）并**已实测通过**：--list-models 目录核对（deepseek-flash / deepseek-v4-pro，与选型文档一致）；--sample 2 两条一次有效；随后 20×2 正式小试 40/40 一次通过 Q9 门（D043）。配置现状：temperature=0、max_tokens=1024、retry_max=1、extra_body 关闭思考、JSON 模式——格式稳定性已验，但是否冻结为主运行配置待与用户/Codex 确认（temperature 0.5 的行为小试是候选消融）。

### 2. Population 机制

- 本地用 FilePopulationProvider，不碰 Population MCP。
- 两条路线：① 与云端可比对：先用 v2/v3 的 20 个合成画像（`data/fixtures/sce_20_synthetic_personas.csv`）生成 roster，本地 scripted 复算应与云端 v3 逐字段一致；② 主线：按 T02 白名单契约从 SCE 微观数据抽样真实画像（`_AGE_CAT`/`_EDU_CAT`/`_HH_INC_CAT`/`_REGION_CAT`/`_NUM_CAT`/`_STATE`/`tenure`），agent_id 跨月持久。
- 待办：写 roster 生成脚本（带抽样 seed 与来源哈希）；人口规模先 20，预算确认后再扩。
- **2026-10-03 进展**：路线①完成——v3 的 20 人 population.json + roster.jsonl 已作为配置件入主仓库 `studies/sce_inflation_expectations/population/`，本地 scripted 复算与云端 v3 归档 40/40 一致（见 §4 进展）。路线②真实画像抽样脚本仍为待办。

### 3. Event MCP"复刻"（实为不需要复刻）

- 运行时从不联网取数；E 全部在 build 时物化。我们已有：2021-05/06 开发月 6 条 BLS 首发信号（`proposal/cloud_input/sce_2021_05_06_bls_release_e.json`）+ 3 个核验月 12 条首发值（`data/raw/bls_check_months_initial_releases/`）。
- 待办：写 E authoring 脚本，把首发稿信号转成 `environment/external_events.json` + environment.json 的 broadcast/layer 声明，字段带齐 `reference_period/published_at/vintage/as_of/source_url`（协议 §2）；只用结构化数值，不写 summary 散文。
- **2026-10-03 进展**：开发月（2021-05/06）E 配置件已入主仓库（environment.json + external_events.json，源自已核验的 v3 归档，6 条首发信号带齐 published_at/source_version/source_url）。通用 E authoring 脚本（核验月→正式窗口批量化）仍为待办，归 T02 收尾。

### 4. 引擎运行与审计接线（本地自主权 = 补云端缺口）

- 云端 v4 没完成的审计接线，本地自己做：唯一 run_id、行为函数自报 `__file__` SHA-256 写入 run_manifest、逐条 Observation 哈希、提示词全文与 LLM 原始响应全量落盘、费用自记（按 API 端点返回的 usage）。
- 待办：改造主仓库 `studies/sce_inflation_expectations/model.py` 为 scripted/openai 双模（保持与云端 v4 同构），审计 sidecar 直接写进决策层；单向导出到官方仓运行副本（沿用 `scripts/export_study_runtime.py`）。
- 验收顺序：本地 scripted 复算（与云端 v3 归档 40/40 一致）→ 本地 1 agent × 1 步真实 LLM 干跑 → 格式稳定性小样 → 20 × 2 正式小试。
- **2026-10-03 已完成（Kimi）**：双模 model.py + 审计 sidecar（唯一 run_id、`__file__` SHA-256 自报、逐条 Observation 哈希、提示词全文与原始响应+哈希逐条落盘、usage 费用自记+失败保守预留、调用次数与费用双闸门、SDK 重试关闭、超长提示拒绝、Q9 不归一化、失败不回退 scripted）。运行入口 `scripts/run_sce_local.py`（自动单向导出；轨迹按 run_id 独立 `trajectory/<run_id>.duckdb`；运行配置只写 run_manifest，不回写运行副本，P1 导出保护不阻塞复跑）。**验收第一步已通过**：两次本地 scripted 运行 answers 40/40、observations 40/40 与云端 v3 归档逐字段一致（`outputs/local_runs/sce-local-scripted-20261003T003537Z-8e6b2f5b/replay_audit_vs_v3.json` verdict=PASS）；单元测试 31/31（mock-openai 覆盖有效/重试/失败/闸门分支）。剩余验收步骤（真实 LLM 干跑→小样→20×2）待用户放 key 与预算确认。注：云端 v4 的 model.py 由平台写入、从未取回本地审阅，本地实现是按本仓库协议独立编写的，两者不声称同构。

### 5. 与云端的衔接

- 本地产出的提示词、配置、模型登记直接复用到云端 v4（10-15 后）：云端运行 = 同一研究在平台官方通道的证据版。
- 本地模型身份登记到供应商实际披露的精度，不能把服务商别名当作已核实权重哈希；云端模型身份未公开，两条线分别标注（协议 §5）。模型不同则属于不同实验条件，不能只因提示词相同就声称严格复现。

### 6. 前置依赖检查

- conda `socioverse` 环境已有 scipy/openpyxl；真实 LLM 运行需 `pip install -e ".[llm]"`（openai 客户端）——安装前与用户确认；
- `.env` 放 `SV_LLM_API_KEY`/`SV_LLM_BASE_URL`（gitignored，不入库）；
- 官方仓 `socioverse2_repo` 有两处既有未提交修复，勿动上游核心；SCE 源码唯一维护在主仓库。
