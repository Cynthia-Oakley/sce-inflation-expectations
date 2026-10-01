# SCE 的 P 输入：来源、时点与云端小样建议

核查日：2026-09-29。范围：SCE household-head 画像及其历史可得性；只核查公开官方网页、问卷、方法材料和仓库已存快照。本文不把尚未查明的具体微观文件发布日期推算成事实。

## 结论

- SCE 有公开的个体微观数据、核心问卷和方法说明。适合做 P 的字段包括年龄、教育、家庭过去 12 个月总收入、Census region、住房自有/租住和当前就业状况；性别、族裔、数理能力和家庭构成可作为有明确机制时的扩展。[P1–P5]
- 官方说明核心微观数据按九个月滞后发布。下载清单显示 2013–2016、2017–2019、2020–2024 分段文件及一个 latest 文件；但本次核查没有在官方 Data Bank/FAQ 找到每个文件或每个月的实际首次上线日。不能用调查月加九个月替代实际 `published_at`。[P1–P3]
- 当前已存的 2020–2024 文件含该期同期人口变量，latest 文件含 2025 年样本。它们是 2026-09-28 取得的现行快照；不能将目标月同期 P 或当期权重回填为该月月初已知信息。[P2, P6]
- 今天在 SocioVerse 云端做 20 人 × 两个相邻开发月的 scripted 小试，建议用 **20 条标为 synthetic 的 SCE 风格 household-head 画像**，跨两个开发月复用同一批 Agent、每人等权。该小样只验收人口文件导入、Agent 映射和跨月流程，不代表美国人口，不用于预测准确率结论。

## 官方数据与变量依据

纽约联储 Data Bank 列有 SCE 核心问卷、图表指南、latest 微观数据，以及 `2013–16`、`2017–19`、`2020–24` 三段完整微观数据；SCE 主页面另给出相同下载入口。FAQ 说明主调查从 2013 年 6 月开始，是美国 household heads 的网络轮换面板，约 1,200 人、每人最多参与 12 个月；主页面约称 1,300 人，实际分析应按现存文件逐月人数记录，不能把近似样本量写死。[P1–P3]

2024 年版核心问卷区分新进入面板者和重复受访者。初次问卷包含当前年龄（Q32）、性别（Q33）、西语裔身份（Q34）、可多选种族（Q35）、最高学历（Q36）、当前就业（Q10）、家庭是否有伴侣（Q38）、家庭过去十二个月税前总收入（Q47）、居住州（Q39/Q40）、当前住房自有/租住（Q43）和家庭成员构成（Q45）。重复受访者有 D 系列更新题，例如家庭收入 D6、家庭变化 D1/D2、迁居 D3/D5、伴侣关系 DQ38。问卷还包含数理题。准确字段名及复选题展开列，应以每个工作簿表头和对应期问卷为准。[P4, P6]

仓库现有工作簿的字段核查确认：面板键与权重为 `userid`、`tenure`、`weight`；调查归属月为 `date`，完成日为 `survey_date`；可见原始画像字段包括 `Q32`、`Q33`、`Q36`、`Q10_1`–`Q10_10`、`Q43`、`Q47`、`D6` 等；官方分组字段包括 `_AGE_CAT`、`_EDU_CAT`、`_HH_INC_CAT`、`_REGION_CAT`、`_NUM_CAT`，另有 `_STATE`、`_COMMUTING_ZONE`。官方问卷把 Q39/Q40 的州字段与州代码联系起来；主页面说明调查追踪年龄、收入、教育、住房、就业历史、地区和数理能力。[P3–P6]

| P 用途 | 候选字段/题号 | 处理建议 |
| --- | --- | --- |
| 最小人口分层 | 年龄组 `_AGE_CAT`、教育组 `_EDU_CAT`、收入组 `_HH_INC_CAT`、地区 `_REGION_CAT` | 优先。先采用粗分组，保留问卷原定义；避免把家庭收入误称为个人工资。 |
| 价格/住房差异 | 住房状态 Q43、就业 Q10 | 可作为少量扩展；Q10 是多选题，须先按原始选项编码，不可随意压成“就业/失业”。 |
| 可选差异 | 性别 Q33、族裔 Q34/Q35、数理组 `_NUM_CAT`、家庭构成 Q45 | 首轮不需要；仅在研究问题预先需要、且历史字段有来源时使用。 |
| 时间/核验字段 | `userid`、`tenure`、`survey_date`、`weight`、`date` | 不传给云端 Agent。只留本地做去重、回溯、时间审计或独立计分。 |
| 不得进入 P | Q8/Q9 点预测、概率分配、官方派生预期及其他当期问卷答案 | 一律从 Agent 输入表剔除；完整问卷行不能直接上传或映射为 P。 |

SCE 方法说明称其统计权重根据收入、教育、地区和年龄四项特征，对齐到该日历年的 ACS 人口目标；这说明 ACS 是合理的边际校准来源，但不表示某个调查月的真实 `weight` 在预测截止时已公开。[P5] 主预测以月初为截止，因此应冻结该截止日前实际已发布的画像版本；数据观测月、问卷完成日、文件下载日和首次发布日期是不同字段。

## 历史可得性与当期画像泄漏

SCE FAQ 对核心微观数据给出九个月发布滞后政策；这支持“同月微观画像不可能在该月月初由这份 SCE 文件公开获得”，但不足以给每个旧分段文件补出精确首发日期，也不能证明某个特定版本在某个历史 `as_of` 已上线。官方网页显示的当前下载链接、当前工作簿覆盖范围、仓库的 `retrieved_at` 都不是历史首次发布时间。[P1–P3, P6]

因此，历史预测只在有**该 P 版本的实际公开日期证据**且该日期不晚于 `as_of` 时接纳它。来源发布时间未知时，该行标记 `availability=unknown` 并排除严格回测；不要根据问卷月份、文件名、FAQ 的九个月政策或本次下载日反推。对于 t 月预测，t 月的 SCE 样本画像、同期权重、`survey_date`、住房/就业/收入更新和当期问卷答题都不可用。年龄和学历相对缓慢也不构成向后使用未来调查记录的许可；收入是过去十二个月的家庭收入，住房、就业和地区均可能变化。

后续可验收的 SCE 历史 P 构造：每个 `as_of` 先筛 `published_at <= as_of` 且画像观测时间不晚于截止的版本；按 `userid` 去重，只向未来月份沿用此前已公布画像，遇到后续合格更新再前向更新，绝不由未来访次倒填；固定基期池时先说明画像陈旧误差。`userid` 仅用于本地串联，不暴露给 Agent。权重只作为已发布样本的校准/抽样信息之一，不能先按权重抽样后又不加调整地重复乘权。

本次盘点已有 [SCE 来源清单](sce_source_manifest.json) 和原始快照，没有重复下载大型 2020–2024/latest 文件。2026-09-29 又补下 2017–2019 官方微观工作簿与官方图表指南，见 [补充来源清单](peb_source_manifest.json)。它们是**当前可下载快照**，实际历史首次上线日仍未核实：

| 已有文件 | 官方 URL | 覆盖与现状 | SHA-256 |
| --- | --- | --- | --- |
| [`micro_2020_2024.xlsx`](../data/raw/sce_audit_20260928/micro_2020_2024.xlsx) | https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-public-microdata-20-24.xlsx | 2020-01 至 2024-12；60 个月、71,976 条有效人月；2026-09-28 本地审计 | `1b57ffb75c2170d767f46a001002db8c40c228fe5691f6dd19e39777ffe469c6` |
| [`micro_latest.xlsx`](../data/raw/sce_audit_20260928/micro_latest.xlsx) | https://www.newyorkfed.org/medialibrary/Interactives/sce/sce/downloads/data/frbny-sce-public-microdata-latest | 本次文件实际覆盖 2025-01 至 2025-10；2026-09-28 本地审计；“latest”是下载端点名，不代表文件覆盖到 2026-09 | `7da4bbcd3f23a4434ab5a94c4c93a255c46df7a57c38eef807b39466bf158f48` |
| [`questionnaire.pdf`](../data/raw/sce_audit_20260928/questionnaire.pdf) | https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-survey-core-module-public-questionnaire.pdf | © 2013–2024 核心问卷，变量与跳题依据；2026-09-28 已存 | `e30e2ef1f925cb90aef1d5d6c9b13c6307b1f311e40c5b894ad27ddf69066e93` |
| [`methodology.pdf`](../data/raw/sce_audit_20260928/methodology.pdf) | https://www.newyorkfed.org/medialibrary/media/research/epr/2017/epr_2017_survey-consumer-expectations_armantier.pdf | 官方方法综述；2026-09-28 已存 | `8b2bee5dd67bf28a3423ac4bae8fc9938a1d1720ce2630307debbd4040f99553` |
| [`micro_2017_2019.xlsx`](../data/raw/sce_p_sources/micro_2017_2019.xlsx) | https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-public-microdata-complete-17-19.xlsx | 2026-09-29 新下载；`Data` 表 47,683 行、220 列，首条样本日期 201701；完整覆盖及人口字段还待审计 | `a88e5a225c9a566dd8cdfdd77abef9ac456eb52d1a120c5ec208184a88c745c9` |
| [`chart_guide.pdf`](../data/raw/sce_p_sources/chart_guide.pdf) | https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/glossary/frbny-sce-chartglossary.pdf | 2026-09-29 新下载；13 页，解释 headline、点预测与不确定性图表口径 | `ee5c88618dae047948eaf528999b22d02ba38a80502b4eb5c8346983cbfb2881` |

表内既有 hash 是从本地文件复算值，与现有来源清单一致；新增 hash 见补充清单。FRBNY 使用许可允许免费使用、复制、分发已发布 SCE 数据及其衍生分析，要求发表/展示时附带指定出处与免责声明，并禁止暗示 FRBNY 背书或使用其标志。[P7] 这不替代对第三方云端服务存储/保留条款的核查；本次小试用合成 P 即可，避免把整张真实微观表传入平台。

## 历史画像构造与外部数据的必要性

优先路线是历史已发布 SCE P 池，因其对象、题意与 household-head 目标一致。若每个历史 cutoff 都能还原公开版本，按过去访次抽取唯一 Agent 画像；需要全国代表性时，在清晰报告下用当时可得的 ACS 年度边际校准年龄、教育、收入和地区。若官方历史首发日不能证明，严格回测版暂用**仅由当时已发布 ACS PUMS 构造的合成 household-head P**，记录该 P 的 ACS 年份、实际发布日期、下载时间、权重和字段映射；PUMS 提供个人/住房单元记录与自定义估计所需字段。[P5, P8]

对本次 2021-05/06 两月首试，Census 官方发布记录确认 **2019 ACS 1-year PUMS 在 2020-10-15 已发布**；因此它是后续构造真实历史 P 的候选。今天只下载了 2019 PUMS [变量字典](../data/raw/acs_2019_docs/pums_data_dictionary_2019.pdf)和[使用说明](../data/raw/acs_2019_docs/pums_readme_2019.pdf)，未下载原始 PUMS 人口记录，也未完成 SCE household-head 映射。[文件哈希与来源](peb_source_manifest.json)是当前下载版；不能仅凭 2020 年产品发布日期推定这两份 PDF 的当前版本当时相同。[P9] Census 同时说明标准 **2020 ACS 1-year PUMS 未发布**，做滚动 P 时不可机械假定每年都有同样产品。[P10]

| 外部源 | 首轮必要性 | 何时再引入 |
| --- | --- | --- |
| ACS PUMS | **可选补位；今天的小试不需要。** 是 SCE 权重目标的官方依据，也是构造人口学联合画像的优先外部候选。 | 历史 SCE 文件可得时点缺失，或需校准全国 household-head 年龄×教育×收入×地区结构时。逐个 ACS vintage 核实首次发布日，不能拿后来修订版回填。 |
| CPS | **当前不需要。** Census 提供 CPS/ASEC 微观数据及技术文档。 | 若研究明确需要更细/更及时的劳动状态分组，而 SCE Q10 不足；它不是匹配 SCE 目标人口的第一选择。 |
| SIPP | **不需要。** | 只有加入资产负债、收入/福利项目动态或纵向家庭经济机制才考虑；会显著增加变量映射和历史时点工作。 |
| BLS CE PUMD | **不需要。** | 做价格暴露增量实验时，用历史已发布支出份额估算食品、能源、住房等组别暴露；不把其家庭样本当作 SCE 同一受访者。 |

### 需要 MCP 时的 P 请求清单（今天的合成首试不调用）

SocioVerse 文档把 `census_acs`、`cps_basic`、`cps_asec`、`sipp` 放在 **Event MCP 的 population 类 collector**；它们不是 Population MCP 的 SCE 人物池。对首个真实历史 P 样例，先 `list_sources()` 看可用性与费用，再只选择一个来源调用 `get_source_detail(source="census_acs", year=2021, month=4, use_cache=true)`，要求返回的 ACS **调查年份、具体产品、字段与权重定义、实际发布日、历史版本、来源 URL、抓取日、许可与缺失说明**。这个月份只是测试 2021-05 目标月的接口；不能假定 collector 会自动给出 2019 ACS 或正确历史版本。若数据只含当前边际/没有 household-head 联合记录，就只能作校准候选，不能直接生成有真实联合结构的人物。[P11]

`cps_basic` 仅在需要月度劳动状态分层时单独取样；`cps_asec` 仅在需要家庭收入补充时单独取样；`sipp` 仅在明确加入财富/福利/纵向家庭机制时单独取样。每项都要求同样的调查期、首次发布时间、vintage、人口单位、权重、联合字段和使用限制，缺一不进入严格历史 P。不要请求 Event 的 `default/all`，也不要为了“用上 MCP”而把 Population MCP 的通用 persona 池当作 SCE household-head 面板或心理人格分布。真实服务响应和费用本轮均未验收。[P11]

## SocioVerse 云端最小 P 输入：20 人 × 2 开发月

与 E 文件和主计划保持一致，两个相邻开发月为 **2021-05、2021-06**。预测截止分别为纽约时间 `2021-04-30 23:59:59 America/New_York` 和 `2021-05-31 23:59:59 America/New_York`。两个目标月复用同一份合成 P 文件。本次是合成 schema 测试，不需要声称真实 SCE P 在这些历史时点可得；真实 SCE P vintage 的历史可得性仍待验收。

上传字段与已有 [合成样例 CSV](../data/fixtures/sce_20_synthetic_personas.csv) 对齐：

```text
agent_id,weight,age_group,education_group,household_income_band,region,housing_tenure,employment_status
```

fixture 当前使用的演示值域为：年龄 `18-34 / 35-44 / 45-54 / 55-64 / 65_plus`；教育 `high_school_or_less / some_college / bachelors / postgraduate`；家庭收入 `under_35k / 35k_to_75k / 75k_to_125k / 125k_plus`；地区 `Northeast / Midwest / South / West`；住房 `owner / renter`；就业 `employed / unemployed / out_of_labor_force / retired`。这些值是人为设定的演示标签，**不是 SCE 官方编码或官方人口比例**，不能当作对官方年龄、教育、收入边界的精确复刻。配套字典/元信息写 `household_head=true`、`p_source_type=synthetic`、`p_version=p_pilot_20260929_v1`，不必逐行重复。

云端小样配置建议：

1. 使用固定的 `smoke_001`–`smoke_020` 画像；年龄五组每组 4 人，四个地区每区 5 人，教育/收入/住房/就业类别均有变化。`weight` 每行是 1；**等权**运行，不声称 20 人代表全国，亦不再乘 SCE 调查权重。
2. 两个月完全复用同一批 20 个 `agent_id` 和画像，以便隔离月份环境变化；若平台跨月保留记忆，只允许读取上一个月 Agent 自己生成的模拟状态。
3. 在配套字典/元信息中写 `household_head=true`、`p_source_type=synthetic`、`p_version=p_pilot_20260929_v1`。只用来核验导入、字段映射、流程和导出，不纳入历史人口准确性或预测效果报告。
4. 不上传 `userid`、真实权重、`survey_date`、州/ZIP、原始逐题答案或任何 Q8/Q9 结果。Agent 输入层只白名单映射上述画像字段。

20 人 × 2 月只有 40 个人月，是平台最小流程 smoke，不足以估计统计代表性、样本量收敛或 Agent 效果。通过后再验收真实历史 P vintage 与更大样本；如果 SCE 历史文件 `published_at` 证据仍缺，严格回测主版继续用有历史 release 记录的 ACS 合成 P，公开 SCE 当期 microdata 只放 evaluation。

## 官方来源（均于 2026-09-29 核查）

- [P1｜SCE FAQ](https://www.newyorkfed.org/microeconomics/sce/sce-faq)：目标人群、轮换面板、问卷入口、核心微观数据九个月滞后。
- [P2｜SCE Data Bank](https://www.newyorkfed.org/microeconomics/databank.html)：当前 SCE 下载入口、各历史分段文件及问卷/图表指南链接。
- [P3｜SCE 主页面](https://www.newyorkfed.org/microeconomics/sce)：样本对象、面板与跟踪特征、公开材料入口。
- [P4｜核心问卷 PDF](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-survey-core-module-public-questionnaire.pdf)：2024 版本标记、题号、问卷跳转及重复受访者 D 系列。
- [P5｜SCE 方法综述 PDF](https://www.newyorkfed.org/medialibrary/media/research/epr/2017/epr_2017_survey-consumer-expectations_armantier.pdf)：目标人群、样本和权重设计；权重按收入、教育、地区、年龄对齐对应年 ACS 目标。
- [P6｜已有来源清单](sce_source_manifest.json) 与 [已完成的 SCE 数据审计](SCE_DATA_AUDIT.md)：本地下载时间、文件覆盖、逐月人数及现有 hash。
- [P7｜FRBNY SCE 数据与问题许可](https://www.newyorkfed.org/microeconomics/confirm_download.html)：使用/分发条件、出处、免责声明和不得暗示背书的要求。
- [P8｜Census ACS PUMS](https://www.census.gov/programs-surveys/acs/microdata.html)、[CPS 数据](https://www.census.gov/programs-surveys/cps/data.html)、[SIPP 数据](https://www.census.gov/programs-surveys/sipp/data.html)、[BLS CE PUMD](https://www.bls.gov/cex/pumd.htm)：仅作上表所述条件性补位来源；本次未下载这些大数据。
- [P9｜2019 ACS 1-year PUMS 实际发布公告](https://www.census.gov/programs-surveys/acs/news/updates.2020.html)及[2019 文档目录](https://www.census.gov/programs-surveys/acs/microdata/documentation/2019.html)：产品发布日为 2020-10-15；当前字典和说明书的下载链接在文档目录。
- [P10｜2020 ACS PUMS 文档](https://www.census.gov/programs-surveys/acs/microdata/documentation/2020.html)：标准 2020 ACS 1-year PUMS 未发布。
- [P11｜SocioVerse 数据服务目录](https://socioverse.fudan-disc.com/docs/guides/data-services/)及[公开客户端](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/socioverse/external_events.py)：Event MCP 人口类来源、工具签名和按月请求方式；目录注册不等于本账号服务端成功返回。
