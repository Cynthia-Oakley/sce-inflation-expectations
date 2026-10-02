# 本地运行方案（socioverse2_repo harness + 自备 LLM API）

更新：2026-10-02（Kimi）。背景：云端余额 $-0.20 透支，10-15 初筛通过后才追加 $70；10-15 前 Sim 主线转本地。本文基于对官方仓库实际源码的核查（非推测）。

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
  - **DeepSeek v3**：`https://api.deepseek.com`，deepseek-chat；
  - **GPT-4o**：cutoff 2023-10——若选它，**2024 年测试月落在其训练窗口之外**，可实现用户设想的"窗口内 vs 窗口外"准确度对比（回顾性条件模拟 vs 严格盲测并存）；
  - 决策点：模型选型是研究口径问题，由用户定（建议先在开发月小样上测格式稳定性再定）。
- 待办：端点连通 probe → Q9 十档格式稳定性测试（非负/总和 100/可解析）→ 冻结 temperature、max_tokens、重试规则。

### 2. Population 机制

- 本地用 FilePopulationProvider，不碰 Population MCP。
- 两条路线：① 与云端可比对：先用 v2/v3 的 20 个合成画像（`data/fixtures/sce_20_synthetic_personas.csv`）生成 roster，本地 scripted 复算应与云端 v3 逐字段一致；② 主线：按 T02 白名单契约从 SCE 微观数据抽样真实画像（`_AGE_CAT`/`_EDU_CAT`/`_HH_INC_CAT`/`_REGION_CAT`/`_NUM_CAT`/`_STATE`/`tenure`），agent_id 跨月持久。
- 待办：写 roster 生成脚本（带抽样 seed 与来源哈希）；人口规模先 20，预算确认后再扩。

### 3. Event MCP"复刻"（实为不需要复刻）

- 运行时从不联网取数；E 全部在 build 时物化。我们已有：2021-05/06 开发月 6 条 BLS 首发信号（`proposal/cloud_input/sce_2021_05_06_bls_release_e.json`）+ 3 个核验月 12 条首发值（`data/raw/bls_check_months_initial_releases/`）。
- 待办：写 E authoring 脚本，把首发稿信号转成 `environment/external_events.json` + environment.json 的 broadcast/layer 声明，字段带齐 `reference_period/published_at/vintage/as_of/source_url`（协议 §2）；只用结构化数值，不写 summary 散文。

### 4. 引擎运行与审计接线（本地自主权 = 补云端缺口）

- 云端 v4 没完成的审计接线，本地自己做：唯一 run_id、行为函数自报 `__file__` SHA-256 写入 run_manifest、逐条 Observation 哈希、提示词全文与 LLM 原始响应全量落盘、费用自记（按 API 端点返回的 usage）。
- 待办：改造主仓库 `studies/sce_inflation_expectations/model.py` 为 scripted/openai 双模（保持与云端 v4 同构），审计 sidecar 直接写进决策层；单向导出到官方仓运行副本（沿用 `scripts/export_study_runtime.py`）。
- 验收顺序：本地 scripted 复算（与云端 v3 归档 40/40 一致）→ 本地 1 agent × 1 步真实 LLM 干跑 → 格式稳定性小样 → 20 × 2 正式小试。

### 5. 与云端的衔接

- 本地产出的提示词、配置、模型登记直接复用到云端 v4（10-15 后）：云端运行 = 同一研究在平台官方通道的证据版。
- 本地模型身份已知 + 云端模型身份未公开：两条线的结论类别分别标注（协议 §5）。

### 6. 前置依赖检查

- conda `socioverse` 环境已有 scipy/openpyxl；真实 LLM 运行需 `pip install -e ".[llm]"`（openai 客户端）——安装前与用户确认；
- `.env` 放 `SV_LLM_API_KEY`/`SV_LLM_BASE_URL`（gitignored，不入库）；
- 官方仓 `socioverse2_repo` 有两处既有未提交修复，勿动上游核心；SCE 源码唯一维护在主仓库。
