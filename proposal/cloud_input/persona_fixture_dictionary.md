# 20 人合成 P 样例说明

关联文件：`data/fixtures/sce_20_synthetic_personas.csv`。生成日期：2026-09-29。**全部 20 行人为编排，仅用于云端文件读取与流程验证**；不含真实个人记录，也不表示 SCE、ACS 或美国居民的实际分布。每行假定为一位合成 household head，两个目标月均复用同一行。

| CSV 列 | 含义与校验 |
| --- | --- |
| `agent_id` | `smoke_001`–`smoke_020`；必须唯一，跨月稳定。 |
| `weight` | 每人 1；原始总和 20，聚合前标准化为每人 0.05。不是 SCE 官方权重。 |
| `age_group` | `18-34`、`35-44`、`45-54`、`55-64`、`65_plus`；人为示例标签。 |
| `education_group` | `high_school_or_less`、`some_college`、`bachelors`、`postgraduate`；人为示例标签。 |
| `household_income_band` | `under_35k`、`35k_to_75k`、`75k_to_125k`、`125k_plus`；人为示例标签，单位美元家庭收入区间。 |
| `region` | `Northeast`、`Midwest`、`South`、`West`；每区 5 人。 |
| `housing_tenure` | `owner`、`renter`；合成住房状态。 |
| `employment_status` | `employed`、`unemployed`、`retired`、`out_of_labor_force`；简化合成状态，不能当作 Q10 官方编码。 |

整份文件的元信息：`p_source_type=synthetic`，`p_version=p_pilot_20260929_v1`，`household_head=true`。这些元信息不需要重复填进每一行，但必须与生成的 population 配置一起保存。不得把合成 P 与官方当前微观数据拼接，也不得把任何真实 Q8/Q9 回答、官方派生预期、当期调查权重带入 Agent 输入。

云端 Agent 导入后请报告：实际读取 20 行、8 列；ID 20 个且无重复；缺失数为 0；原始权重合计 20；四个 region 各 5 行；用同一批 ID 生成两个目标月。若平台自己生成了更多家庭、改写了字段或忽略了上传文件，暂停运行并先修正 population 映射。
