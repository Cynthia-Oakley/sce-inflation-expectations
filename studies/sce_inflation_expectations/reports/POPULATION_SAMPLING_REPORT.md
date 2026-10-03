# 真实人口抽样报告（SCE 微观数据 → PopulationBundle）

任务：SocioVerse Challenge 2026「水上挽月」赛道 A，SCE 一年期通胀预期 Agent 模拟的 P 层——从纽约联储 SCE 公开微观数据抽样真实人口。
核查日期：2026-10-03。执行：Kimi（实现代理）。证据文件：`data/raw/sce_audit_20260928/manifest.json`、`data/raw/sce_p_sources/manifest.json`（含来源 URL、抓取时间、SHA-256）。

## 1. 三份微观 xlsx 结构探明

三份文件**第一行均为 FRBNY 版权声明，真实表头在第 2 行**（pandas 读取用 `skiprows=1, header=0`）。

| 文件 | 列数 | 行数 | 月份覆盖 | 关键列差异 |
|---|---|---|---|---|
| `micro_2017_2019.xlsx` | 220 | 47,681 | 2017-01..2019-12 | 无 `Q1a/Q1apart2`、无 `Q9new2_*`（2020–2024 版新增），其余 P 相关列齐全 |
| `micro_2020_2024.xlsx` | 229 | 71,976 | 2020-01..2024-12 | 本任务主数据源 |
| `micro_latest.xlsx` | 229 | 10,559 | 2025-01..2025-10 | 与 2020–2024 版列名一致 |

抽样脚本实际读取的列：`date, userid, tenure, Q43, _AGE_CAT, _EDU_CAT, _HH_INC_CAT, _REGION_CAT, _NUM_CAT, _STATE, Q10_1..Q10_10`（共 21 列）。完整 229 列清单已探明并存于会话证据（T02 文档记录了同样的字段分组）。

## 2. 码表核对（questionnaire.pdf，44 页，pypdf 抽取）

### 就业状况 → `Q10_1..Q10_10`（问卷第 11–12 页）

数据列为 0/1 多选虚拟变量（Q10 为多选题）。问卷原文 "Q10. What is your current employment situation?"（p.11，选项跨 p.11–12）：

| 编码 | 问卷选项 | persona 代码 |
|---|---|---|
| 1 | Working full-time (for someone or self-employed) | employed |
| 2 | Working part-time (for someone or self-employed) | employed |
| 3 | Not working, but would like to work | unemployed |
| 4 | Temporarily laid off | unemployed |
| 5 | On sick or other leave | on_leave（prompt 新增键） |
| 6 | Permanently disabled or unable to work | disabled（新增键） |
| 7 | Retiree or early retiree | retired |
| 8 | Student, at school or in training | student（新增键） |
| 9 | Homemaker | homemaker（新增键） |
| 10 | Other | other（新增键） |

多选优先级（脚本常量 `EMPLOYMENT_PRIORITY`）：1,2 → 3,4 → 5 → 7 → 6 → 8 → 9 → 10。目标月样本中约 6% 有多选（如 disabled+retiree），按优先级取第一个。Q10 每月必答（目标月 2531 行全部有 0/1 值，仅 5 行全 0 → 不产出 employment_status 属性）。

### 住房权属 → `Q43`（问卷第 32 页）

问卷原文 "Q43. Do you (or your spouse/partner) own or rent your current primary residence?"（p.32）：Own (1) / Rent (2) / Other (3) → owner / renter / other。

**关键发现：Q43 是旋转模块**——每月只有约 12% 的受访者被问到（2020–2024 各月非空率 10.9%–14.3%，目标月 202105 为 153/1234、202106 为 162/1297）。这不是缺失，而是问卷设计（抽样按 1/8 轮换）。由于 SCE 是轮换面板（受访约 12 个月），同一人 Q43 命中窗口封顶：在全部 1070 人的两月交集池中，仅 131 人（12.2%）在目标月有 Q43；放宽到 ±6 个月内本人最近回答后覆盖 533 人（49.8%），再放宽窗口覆盖率不再增加（一半人面板存续期内从未被问到）。

**采用方案（默认 `--housing-window 6`）**：优先取目标月本人回答；目标月无则取距任一目标月 ≤6 个月的本人最近回答（住房权属高度稳定，借用邻月本人回答是明示的近似）；仍无则不产出 housing_tenure 属性，prompt 回退 "unknown housing situation"。借用来源与滞后分布全部写入 sampling_meta（100 人样本：目标月 7 人、借用 35 人、缺失 58 人）。

### 无法核实/纠正的两个维度（如实报告，未编造）

- **`_NUM_CAT` 不是家庭人口数**。T02 记录其为「数理能力」，目标月实测取值集合为 {High, Low}，确认是 SCE 派生的**计算能力（numeracy）分类**（来自 QNUM1/2/3/5/6/8/9 题组）。真实画像白名单列中**没有家庭规模变量**。 household composition（Q45new，问卷 p.33）同属 ~12% 覆盖率的旋转模块，且不在白名单派生列内 → **household_size 不进 persona 属性**。替代处理：白名单内的 `_NUM_CAT` 以 `numeracy: high/low` 属性如实进 persona（prompt 文案 "Your score on the survey's numeracy assessment was high/low."），已写入 `_PROFILE_TEXT` 与 `_persona_sentence`。
- **xlsx 的 `tenure` 列是 SCE 面板受访月数，不是住房/居住时长**。依据：取值 1–16 的整数（2020–2024 均值 5.9）；methodology.pdf 原文 "During their twelve-month tenure, each group of respondents ... was randomly assigned..." 及 "the design of the panel, with a constant in- and outflow of respondents each month, ensures a stable survey tenure distribution"。问卷中与居住时长对应的是 Q42（"How many years in total have you lived in the State..."，xlsx 无此列）。结论：`tenure` 不译为 persona 属性（白名单允许但它是流程元数据而非人口特征），仅其分布进入 sampling_meta。

### 画像分类列实际取值（目标月 202105+202106 实测）

| 列 | 取值集合 | persona 属性（代码） |
|---|---|---|
| `_AGE_CAT` | `Under 40`, `40 to 60`, `Over 60` | age_group（原值直用） |
| `_EDU_CAT` | `High School`, `Some College`, `College` | education_group：`high_school` / `some_college`（旧键沿用） / `college`。注：真实派生列无 postgraduate 区分 |
| `_HH_INC_CAT` | `Under 50k`, `50k to 100k`, `Over 100k` | household_income_band：`under_50k` / `50k_to_100k` / `over_100k`（与合成试点的 4 档不同，均为新增键） |
| `_REGION_CAT` | `Northeast`, `Midwest`, `South`, `West` | region（原值直用，与试点一致） |
| `_NUM_CAT` | `High`, `Low` | numeracy：`high` / `low` |
| `_STATE` | 50 州 + DC 邮政缩写（目标月 8/2531 缺失） | state（原值直用；缺失则不出该属性） |
| `_COMMUTING_ZONE` | 数值编码（约 240 个） | 不进 persona（任务未要求） |
| `Q43` | `1.0`, `2.0`, `3.0` | housing_tenure：owner / renter / other |

白名单执行：persona 属性只由上述列 + Q10/Q43 映射产生；`weight`、`Q8v2`、`Q9_*` 及全部其他回答列**绝不进入属性**（persona weight 固定 1.0；测试 `test_no_forbidden_attribute_keys` 守门）。

## 3. 抽样实现 `scripts/build_sce_population.py`

- 参数：`--months 202105,202106`（默认）、`--n 100`、`--seed 42`、`--out .../population/population_real100.json`、`--housing-window 6`、`--data`。
- panel 模式（默认且唯一模式）：先过滤目标月记录，只保留在所有目标月都出现的 `userid`（Agent 跨月为同一人）；对排序后的交集池用 `random.Random(seed).sample` 无放回抽 n；池不足 n 时打印可用数量并非零退出，**不静默放宽**。
- 输出三件套：PopulationBundle JSON（写出前脚本内 `PopulationBundle.model_validate` 硬校验）、`roster_<name>.jsonl`（step-0 初始态，仿现有 roster：target_month ""、direction ""、point_pct 0.0、q9_valid false 等）、`<name>.sampling_meta.json`（seed、目标月、候选池、来源 SHA-256、抽样时间、各属性分布、住房借用覆盖、面板 tenure 分布、码表映射）。
- `init_state` 与试点完全一致：`{"target_month": "", "direction": "", "point_pct": 0.0, "q9_valid": false}`。

## 4. prompt 映射对齐（`studies/sce_inflation_expectations/model.py`）

`_PROFILE_TEXT` **只增不删**：新增收入 3 档（under_50k/50k_to_100k/over_100k）、教育 `high_school`/`college`、住房 `other`、就业 `on_leave`/`disabled`/`student`/`homemaker`/`other`、新维度 `numeracy`；试点旧键（under_35k、high_school_or_less、bachelors、postgraduate 等）原样保留，试点 `population.json` 不受影响。`_persona_sentence` 仅在属性含 numeracy 时追加一句（旧画像 prompt 字节不变，已实测）。住房/就业缺失时沿用既有 "unknown ..." 回退。

## 5. 正式样本（202105+202106，seed 42，n=100）

候选池：202105 有 1234 行、202106 有 1297 行，两月交集 **1070 人**（≥100，无需 min(n, 池) 回退）。

| 属性 | 分布（n=100） |
|---|---|
| age_group | Under 40: 31 / 40 to 60: 37 / Over 60: 32 |
| education_group | high_school: 10 / some_college: 33 / college: 57 |
| household_income_band | under_50k: 23 / 50k_to_100k: 41 / over_100k: 36 |
| region | Northeast: 18 / Midwest: 30 / South: 32 / West: 20 |
| state | 32 个州+DC；最多 IL 9、TX 7、CA 6、FL 6、NY 6 |
| numeracy | high: 73 / low: 27 |
| employment_status | employed: 64 / retired: 24 / unemployed: 7 / homemaker: 3 / disabled: 1 / other: 1（无 on_leave/student 抽中） |
| housing_tenure | owner: 32 / renter: 9 / other: 1 / 缺失: 58（其中 35 人为 ±6 月内本人回答借用，7 人为目标月原答） |
| 面板 tenure（元数据） | 中位 12 个月（67 人满 12 个月），范围 2–12 |

产物：`studies/sce_inflation_expectations/population/population_real100.json`、`roster_real100.jsonl`、`population_real100.sampling_meta.json`（均通过 `PopulationBundle.model_validate`）。

## 6. 测试

`tests/test_build_sce_population.py`（7 个用例，数据文件缺失时整模块 skip）：
bundle 校验与规模、panel 跨月持久（逐 userid 对照原始数据）、白名单泄漏检查（属性键集 ⊆ 允许集，禁 weight/Q8/Q9 前缀）、同 seed 确定性（与 `random.Random(42).sample` 独立重算一致）、池不足报错（SystemExit）、元数据完整（SHA-256 与文件实算一致、分布计数=样本量）、CLI 写出三件套路由（PopulationBundle 再校验 + roster/meta 命名）。

测试结果（2026-10-03）：`python -m unittest discover -s tests` → **Ran 38 tests, OK**（原 31 + 新 7；新模块因两次完整 xlsx 扫描约 110 s）。

## 7. 修改/新增文件清单

- 新增 `scripts/build_sce_population.py`（抽样脚本）
- 新增 `tests/test_build_sce_population.py`
- 修改 `studies/sce_inflation_expectations/model.py`（`_PROFILE_TEXT` 新增键、`_persona_sentence` 追加 numeracy 句）
- 新增 `studies/sce_inflation_expectations/population/population_real100.json` / `roster_real100.jsonl` / `population_real100.sampling_meta.json`
- 新增本报告 `studies/sce_inflation_expectations/reports/POPULATION_SAMPLING_REPORT.md`
- 未触碰：`population.json`/`roster.jsonl`（试点 20 人合成画像原样）、`scripts/run_sce_local.py`。

## 8. 遗留问题

1. **住房覆盖率 42%**：旋转模块设计所致，±6 月借用已到个人面板存续期上限。若 prompt 需要完整住房维度，须显式扩展白名单（如允许 D 段/Q45new 派生），属协议变更，需主代理/用户决策。
2. household_size 真实不可得（见 §2），已用白名单内 numeracy 替代；若未来要做家庭规模，Q45new 是唯一原始来源（旋转模块，覆盖率同样 ~12%）。
3. 正式 100 人中的 2 个就业全 0 行若被抽中会缺 employment_status（本 seed 下 100 人全有就业代码；机制已处理）。
4. `docs/NEXT_ACTIONS.md` 任务板更新留给主代理统一整合。
