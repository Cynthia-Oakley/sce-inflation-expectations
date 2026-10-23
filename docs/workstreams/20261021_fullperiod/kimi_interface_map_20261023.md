# 新分层运行包：工程接口映射与最小修改清单（Kimi交付B包第一阶段）

2026-10-23。只读勘察，未修改任何文件，新增 API = 0。对应 [core_normal_readiness_plan_20261023.md](core_normal_readiness_plan_20261023.md) 的 B 包："梳理哪些接口固定旧六格/512人；给出最小修改清单与适配器边界"。等 Codex 冻结网格/抽样/Normal 契约后，再按本文第 4 节做目录、manifest/哈希、面板字段与干跑。

## 1. 链路与数据格式（环节间契约）

月度重建管线共七环，环节间全部用文件传递，格键与人数只在少数点渗入：

1. **每月输入目录** `<delivery>/<yyyymm>/`：`population.json`（personas，attributes 含 education_group/employment_status/age_group/household_income_band/numeracy/region）、`sampling_private.json`（stable_priority 旧六格 SRS 排序键）、`belief_state_private.json`、`environment.json`、`news_label_index.json`。
2. **网格 manifest** `core_allocation_proposal.json`：`months[].allocation{<cell_key>:{frame_n, allocated_n}}`，cell_key 现为 `edu|work` 六格字符串＋`unknown`。
3. **准备输出**：`selected_private.json`（每人 persona/stratum/inclusion_probability/raw_survey_weight/analysis_weight=w/π/weight_valid）、`{month}_weights_private.json` sidecar、`{month}_resolved/baselines/draws_private.json`、`state_dependencies_private.json`（节点＋logical_reuse_key）。
4. **提示组装**：`prompts/<month>/`（templates/initial_states/timing/baskets/news_quantity_frame 等 private 文件）＋ summary（planned_unique_requests、估算费用）。
5. **组装 bundle**：`manifest.json`（n_per_month、各输入路径与 sha256、budget_estimate）＋ `evaluation_recipe.json`（schema_version 1、predeclared_groups、sparse_display{min_n 20, min_ess 10}、failures 规则）。
6. **执行包**：`protocol.json`（months、arms、generation_repeats、n_per_month、planned_calls、technical_gate、concurrency_stages、macro_combination、价格/温度）；运行后 receipt＋calls/positions jsonl。
7. **评价与面板**：`truth_private.json`（含 stratum、survey_weight、full_wave 整波真值）→ `cases_private.json`（面板契约：month/userid/repeat/real/arms/权重/profile/stratum）→ 面板 adapters 按必需键读取。

## 2. 硬编码点清单

### A. 旧六格键（`edu|work`）

| 位置 | 写死内容 | 最小改法 |
|---|---|---|
| `population_stratification.py:4-17` | `cell_key()` 返回六格键 | 旧模块不动；新网格经 key 函数参数化或新适配层 |
| `experiments/monthly_reconstruction_inputs.py:64-66` | `choose_core` 按六格分组并校验 cell 集合==allocation 键 | `prepare()` 增加 grid/cell_key_fn 参数 |
| 同上 `:124-165` | `stratified_bands` 用六格重建前期波次、要求帧数一致 | 前期波格定义必须与目标月同网格——适配器要一起换 |
| 同上 `:168-187` | `prior_grid_allocation` 硬编码六格 cells＋512/24（目录外月份如 2019-01） | 改由新网格 manifest 提供前期波 allocation |
| `evaluation/monthly_reconstruction.py:89,146` | truth 行带 `stratum`；groups 只按 entry_status＋stratum | stratum 是透传字符串，代码可不改；分组维度可参数化 |
| `panel/adapters.py:17,138` | `record['cell']=cell_key(profile)` 六格 | 改从 case 读 `stratum` 或加 grid_version 开关 |
| `panel/sections.py:47-75`、`panel/render.py:668` | 六格中文标签/排序/标题 | 新增细格标签与排序配置 |
| `monthly_reconstruction_pipeline.py:45`、`monthly_reconstruction_execution.py:31` | recipe 文本 / randomness 注记写"六格" | 文本随契约更新 |

### B. 512/24/96 人数

| 位置 | 写死内容 | 最小改法 |
|---|---|---|
| `monthly_reconstruction_inputs.py:226-227` | 强制 `target_core_n==512 and minimum_floor==24` | 读 manifest；floor 随 54 格重定（54×256 无法维持 24） |
| 同上 `:186,251-252,304,309` | allocate_core(512, min 24)、`len(people)!=512: raise`、`n_per_month:512` | 全部参数化为 proposal/参数 |
| `monthly_reconstruction_pipeline.py:101`、`monthly_reconstruction_execution.py:30,37` | manifest/protocol 的 n_per_month=512、technical_gate 按旧规模标定 | 透传＋按新 planned_calls 重标定 gate |
| `evaluation/entry_initialization.py:118,227` | preflight 探针 `sizes=(96,512)` | 非主链路，可同步候选规模或不动 |

### C. "全部人口都是 LLM Core"假设（Normal 接入点）

- 提示/执行层本就是节点驱动、与人数解耦，**无需改**；Normal 不调 LLM 天然兼容。
- 评价层 `evaluation/state_continuity.py:85-93`（assemble_cases）强制 node 集合==truth 集合；Normal 无 node，进不了 cases。
- **现成挂点**：`evaluation/monthly_reconstruction.py:73-74` 的 `full_wave_private.json` 已按整波构建真值，是 Core＋Normal 评价的天然数据口。
- 最小改法：新增 Normal 合成适配层（Core 各格答卷分布 → 按格人口比例合成），产出独立的格级分布摘要（复用 `evaluation/metrics.py` 加权分位数/W1），与 fixed_roster 摘要**并列**，不混入 cases_private.json，避免冲击面板共同支持逻辑。
- 已有雏形 `evaluation/core_normal.py`（3×3×3 粗格、prior_strength=5），格定义与 54 格不同，按 Codex 冻结契约重定，不直接沿用。

### D. 新闻配额

`news_quantity.py:7-24` 完全 ID-only（48:28:20 最大余数在全月帧分配后子集取 Core），**不依赖六格键与 Core 人数，无需改**。旧 `heterogeneous_news.py` 的 96 人硬编码只被旧 continuity 模式调用，月度重建链路不走。

## 3. 可直接复用、无需修改

- `population/grid_sampling.py`（Codex 新模块）：`frame_cells/plan_core/draw_core` 已提供任意格键的保底＋质量分配、sha256 种子化格内无放回抽样、π/design_weight/poststratified_weight 两层权重。格键是任意字符串，天然支持 54 格。
- `evaluation/metrics.py`：quantile/distribution_summary/wasserstein1/headline_errors 接受任意权重数组并自动剔除无效权重。
- PastScoreCache、resolve_draw、执行器 execute/verify、state_continuity_runtime、冻结计分器 sce_q9_frozen——均与格定义/人数解耦。
- 四个 scripts 入口（prepare/assemble/run/evaluate_sce_monthly_reconstruction.py）纯 argparse 透传，只需新增参数。
- evaluation_recipe 的 sparse_display 阈值与 macro_combination 结构语义不变（54 格下更显重要）。

## 4. 待 Codex 冻结契约的接口边界（未定前不动工）

1. **新网格 manifest schema**：是否沿用 `allocation{cell:{frame_n, allocated_n}}` 仅换 54 格键？unknown 池如何表达？这决定 prepare() 的校验改写。
2. **保底名额与预算分配**：54 格 × 256/384/512 各档 floor（4/6/8 候选）；unknown 池是否占 Core 预算。
3. **声明评价权重用哪层**：w/π（design_weight）还是格内比率校准后的 poststratified_weight；recipe 的 weights 字段与面板 weight_field 需指明。两层都留 sidecar，但不能混叫一个权重。
4. **抽样排序契约**：delivery 侧 `stable_priority` vs `draw_core` 的 sha256 排序，二选一；若换排序需 delivery 补新 sidecar。
5. **Normal 产物 schema**：每格答卷分布的原子形式（完整 Q8＋Q9 联合答卷 vs 统计量）；Normal 不进 cases（本文建议），格级摘要的具体字段；unknown 池参与合成还是仅披露。
6. **前期波次网格**：容差带重建需前期波同格定义；目录外月份（如 2019-01 的上期 2018-12）的 54 格 allocation 由谁注册。
7. **面板网格版本**：新批次 cases 带新 stratum 键时，面板加 grid_version 维度还是并列；标签/排序配置同步。
8. **recipe/技术门版本**：evaluation_recipe schema_version 是否升 2；technical_gate 按新规模重标定。

## 5. 契约到位后我的工作范围（预告）

各月目录生成、manifest/哈希登记、面板字段适配与新增接线的官方 Core 干跑；复用 grid_sampling 与 metrics，不另写配额/权重/中位数/Normal 算法，不覆盖旧冻结输出（旧六格 41,984 准备包原样保留）。
