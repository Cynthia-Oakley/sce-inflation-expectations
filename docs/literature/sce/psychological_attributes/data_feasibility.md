# 心理属性数据可行性核查

核查日：2026-10-06。仅核查公开问卷、数据说明及 SCE 已归档微观表；没有读取环境密钥、注册受限账号、调用付费服务或下载新的大型微观文件。本文件提供来源与字段候选，不代表已批准加入 P。

**后续实测更新（2026-10-06）：** GSS2018已下载并完成联合支持审计；前次“人口分组全有效”需更正为原始非空记录。清洗后5月教育/收入缺9/14，6月缺6/13。数理/年龄/地区有效全覆盖。已生成五套候选侧车；详见[离线验收](../../../PSYCHOLOGICAL_PROFILES_ACCEPTANCE_20261006.md)。下方保留首次调研状态，已完成项以该验收为准。

## 结论

- **A 后验重建：** SCE 同一受访者月记录可见 Q1（过去一年家庭财务变化）、部分新入组 respondent 的健康、风险意愿和 numeracy；Q1 可作为明确披露的当期回顾状态候选。Q1 不是幸福感或客观财务压力，Q2 是接近目标的未来家庭财务预期。原 baseline 未用 Q1/Q2；需另做变量白名单与目标接近度审查，不能把同期 Q2 当普通心理特征。
- **B 事前预测：** SCE core 微观数据官方说明延迟约九个月发布，所以目标月的 Q1/Q2 不能作为该月 B 输入。必须使用实际已发布的滞后月份，并核实来源文件当时可得。GSS 2018 有官方历史公告证明数据于 2019-03-19 可用，是跨调查心理 donor 的首选**候选**；但尚未从 2018 文件计算 HAPPY/SATFIN/TRUST 与共同 X 的完整案例数，且今天的累计文件可能含后续修订。只有找到当时版本并通过同人联合支持审计后，才可作为 B donor。GSS 2021 的公开数据晚于 2021 年 5 月；其网上自填模式、问卷和 2018 不同，不能用于当时 B。
- **备选：** SHED 2019 的家庭财务体验可作财务状态/通胀冲击代理；官网记录其州字段更新于 2021-05-07，但所需文件的历史快照与精确版本仍需留档。SHED 2020 public-use 微观文件的首次发布日未核实，故不据今天的文件声称它在 2021 年 5 月已可用于 B。
- 跨调查 donor 是依共同 X 进行的**统计合成**，不是 GSS/SHED 心理值与 SCE 居民逐人联结。GSS/SHED 的成年个人样本也不等同 SCE 家庭户主样本，未匹配共同支持不得用全国心理边际补齐。

## SCE：同一 respondent-month 的实测字段

NY Fed 将 SCE 描述为约 1,200–1,300 名美国住户户主组成的每月轮换互联网 panel，核心问卷按月进行；core 微观表约滞后九个月公开。问卷与数据公开可免费下载。[SCE 概览](https://www.newyorkfed.org/microeconomics/sce) · [SCE FAQ](https://www.newyorkfed.org/microeconomics/sce/sce-faq) · [核心问卷 PDF](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-survey-core-module-public-questionnaire.pdf)

在本地既有 2020–2024 文件 `data/raw/sce_audit_20260928/micro_2020_2024.xlsx` 中，按 2021-05 与 2021-06 月份过滤并读取了字段列；文件由 2026-09-28 取得，故下面是**今天可见的当前文件内容**，不是 2021 年当时发布的字节版本。

| 字段 | 问题/解释与编码 | 2021-05 实际有效 | 2021-06 实际有效 | 适用性与缺口 |
|---|---|---:|---:|---|
| `Q1` | 受访者及同住家庭当前财务状况相较 12 个月前；1 明显更差、2 稍差、3 差不多、4 稍好、5 明显更好。是回顾性主观状态，不是一般幸福或客观财务压力。 | 1,234/1,234 | 1,297/1,297 | Core 可观测；A 可作为当期自报体验候选并单独披露。B 需滞后且该月微观文件须在 cutoff 前公开。 |
| `Q2` | 未来 12 个月家庭财务相对当前的预期；1 明显更差至 5 明显更好。 | 1,233/1,234 | 1,296/1,297 | 未来家庭财务 outlook，不是稳定乐观人格；与目标 respondent-month 同波出现，属高 target-proximity proxy。不可作为同波 B 输入；B 仅可考虑公开日已核实的滞后值。 |
| `Q43` | 主要居所住房/产权状态字段；本轮确认列存在并记录类别值 1–3，尚未复核全部选项标签。 | 153 | 162 | 新入组回答覆盖，不可将其余缺失编码成“租房/无房”。 |
| `Q45b` | 自评健康：1 优、2 很好、3 好、4 一般、5 差。 | 153 | 163 | 新 respondent 题项，非每月全样本；更像健康状态，非人格。 |
| `QRA1`,`QRA2` | 分别为金融事项风险意愿、日常活动一般风险意愿，1–7 从完全不愿意到非常愿意。官方问卷图示虽只画出部分刻度，本地数据实见 1–7。 | 各 153 | 各 163 | 新 respondent 子样本；是风险倾向 proxy，不是标准通用人格量表。 |
| `QNUM1,2,3,5,6,8,9` | 新入组者的 numeracy 测试题，原始列为自由数值答案（例如折扣、利息和概率题），不是预先标准化的连续心理分数。 | 各 153 | 各 162–163 | 核心 QNUM 仅新 respondent；各题有效数略有差异。具体题目与评分应以问卷版本重算，不把自由回答直接当分数。 |
| `_NUM_CAT` | 文件中标记为 `High` / `Low` 的数理分类。 | 1,234/1,234 | 1,297/1,297 | 覆盖是实测事实；其派生算法、阈值和跨月更新逻辑本轮未验证。若用，先核算法。 |
| `_AGE_CAT`,`_EDU_CAT`,`_HH_INC_CAT`,`_REGION_CAT`,`_STATE`,`_COMMUTING_ZONE` | 公开人口分组及地区字段。 | 均 1,234/1,234 | 均 1,297/1,297 | 可用于人口匹配；数值标签映射需沿用相应 SCE 字典。 |
| `Q10_1`–`Q10_10` | `Q10` 就业状态的十个分列字段。 | 各 1,234/1,234 | 各 1,297/1,297 | 字段同月均非缺失；本轮未核完整类别标签与多选编码，应用前需按问卷标签逐列验证。 |

两个月每人一条 respondent-month 行；Q1/Q2 与上述画像字段同列。`Q1`/`Q2` 的联合有效例分别是 1,233 与 1,296。健康、风险与原始 QNUM 每月仅约 12% 新 respondent 有答，不能把缺失当 0 或默认覆盖所有住户。FAQ 明确新 respondent 不参加该月补充模块；QNUM 只对新 respondent 提问。[SCE FAQ](https://www.newyorkfed.org/microeconomics/sce/sce-faq) · [问卷 numeracy 与风险题](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-survey-core-module-public-questionnaire.pdf)

SCE `weight` 是月度设计权重；需逐目标月份确认版本和公开日。SCE 样本以家庭户主为单位；`AGE/EDU/HH_INC/REGION`、就业、住房和 numeracy 分组虽同一行可用，仍需与 GSS/SHED 人口定义及分箱对齐。

## GSS：幸福、财务满意度、信任与“未来乐观”核查

GSS 是美国成年个人横截面调查。NORC 提供公开的 Stata/SAS/SPSS 年度文件和 Data Explorer；本轮没有下载 2018 原始 respondent 文件或跑同人完整案例计数。[NORC 数据入口](https://gss.norc.org/get-the-data.html) · [GSS 文件格式与年份](https://gss.norc.org/get-the-data/stata.html) · [2018 问卷 ballots](https://gss.norc.org/get-documentation/questionnaires.html)

| 字段/候选 | 已核实含义 | 解释边界 |
|---|---|---|
| `HAPPY` | 近来总体幸福，自评“很幸福 / 比较幸福 / 不太幸福”，有序 1–3；2021 codebook 有 4,014/4,032 有效。 | 当前幸福状态，不是经过验证的乐观人格量表。 |
| `SATFIN` | 受访者及家庭对目前财务状况满意度，“相当满意 / 还算满意 / 完全不满意”，有序 1–3；2021 有效 4,016/4,032。 | 当前满意度受实际财务状态影响；与 SCE `Q1` 不是同一题。 |
| `TRUST` | 一般人际信任：多数人可被信任 vs 与人交往应小心。 | 2021 codebook 标明该项未纳入；不能用机构信心题冒充普遍人际信任。2018 是否与所有目标变量同 ballot、缺失重叠仍须用历史文件实测。 |
| `GOODLIFE` | 2021 codebook 有一个关于本人/家庭改善生活水准机会的同意度题；属单题、向上的生活机会预期。 | 可作主观前景 item 候选，但它不是多题验证的 disposition-optimism 量表；2018 可用性/完整题项本轮未核，且 2021 版本晚于 B cutoff。ConsumerSim 的 “GSS future optimism” 不能据论文称谓自动映射到此项。 |
| `FINALTER` | 家庭财务在过去几年变好、变差或不变（回顾）；2021 有效 4,021/4,032。 | 明确不是未来财务乐观。 |
| `FINRELA` | 家庭收入相对美国一般家庭的当前高低判断。 | 横截面相对经济地位，不是对未来的预测。 |

2021 codebook 是 NORC Release 4（2024-11-25 编制），其 `HAPPY`、`SATFIN` 和 `GOODLIFE` 等题可见于同一人级文件；我未下载文件计算逐人交集。`TRUST` 不在该年度。2021 GSS 数据收集使用疫情期间 web/self-administered 为主的模式，和 2018 传统面对面方式不可直接视为无模式差异；2021 PUF 发布时间在 2021-05 cutoff 之后，故不适用于那时的 B donor。[2021 GSS codebook](https://gss.norc.org/content/dam/gss/get-documentation/pdf/codebook/GSS%202021%20Codebook.pdf)

**2018 候选与 B 历史可得性：** 官方公告明确 2018 GSS 结果于 2019-03-19 可用，因此它在 2021 年 5 月前已发布。[NORC 2018 发布公告](https://www.norc.org/research/library/results-of-the-2018-general-social-survey-now-available-to-the-p.html) 但今天的 1972–2018 累计码本/当前下载文件不能证明文件 byte-vintage 等于 2019 公开版本；2018 HAPPY/SATFIN/TRUST 的有效答卷交集、ballot 覆盖和跨 X 缺失率尚未核。故 GSS 2018 是首选**待验 donor**，不是已验收 joint donor。历史版权重也要取 2019 vintage；GSS 后续加入 WTSSPS/WTSSNRPS post-stratification 权重（旧年份新版权重为后续构造），不能倒称为 2021 年 B 当时已知。[NORC 后分层权重说明](https://gss.norc.org/content/dam/gss/get-documentation/pdf/reports/methodological-reports/MR135%20poststratified%20weights.pdf) · [GSS 权重 FAQ](https://gss.norc.org/faq.html)

共同 X 候选：`AGE`、`EDUC`、家庭收入字段（2018 可检验 `REALINC` 或原始家庭收入；不可直接等同 SCE household-income 档）、`REGION`、`WRKSTAT`、住房自有/租住项。它们能与心理变量同 person file 匹配的前提是历史 codebook 与非缺失交集实测通过。公开 GSS 通常只有粗 Census region，不提供可直接与 SCE state/CZ 对齐的公开地理；敏感地理要走受限申请。GSS 样本单位是成人个人，不是特选家庭户主。

## SHED：有用的财务状态/通胀经历 fallback

Fed Board 的 SHED 每年针对美国成年人；公开 CSV/Stata 数据、码本和测量题目，不需付费；分析权重面向成年人口。[SHED 数据与版本页](https://www.federalreserve.gov/consumerscommunities/shed_data.htm) · [SHED FAQ](https://www.federalreserve.gov/consumerscommunities/shed-faqs.htm)

2024 码本实核：12,295 名成年 respondent，`B2` 是自评“目前财务管理得如何”，1 难以维持、2 勉强维持、3 还可以、4 舒适；`INF4` 是过去一年所付价格变化对财务状况的影响，1 很大程度变差至 5 很大程度变好、3 无或几乎无影响，12,295 人均答；`I21_a`/`I21_b` 是与一年前相比家庭月收入/支出变少、相同、增加，均 12,295 人有记录。[SHED 2024 codebook](https://www.federalreserve.gov/consumerscommunities/files/SHED_2024codebook.pdf) 这些是当前/回顾家庭经济体验和通胀冲击，不是一般幸福、信任或未来乐观。2024 码本对 `happy`、`optimistic` 关键词无命中，本轮也未确认一般信任量表。

同一成年 respondent 数据行带有可用共同 X：`ppage`（年龄）、`ED0`（教育）、`ppinc7`（家庭收入档）、`ppreg4`（四 Census 区域）、`pprent`（居住住房产权/租赁状态）；就业状态的精确字段名本轮未确认。2024 权重为 `weight`（年度横截面）、`weight_pop`（总体人数估计）；2023–24 panel 子样本用 `panel_weight` / `panel_weight_pop`。SHED 的成人 respondent 不是一定为 SCE household head，且 2024 波次不可用于 2021 B。

历史方面，SHED 页面记载 2019 public data 在 2021-05-07 更新州字段；这使对应 2019 版本有机会满足 2021-05-12 可用条件，但本轮没归档其当时的原文件。2020 SHED 报告发布时间为 2021-05-17，不能以今天网页上的 2020 文件倒推微观数据已于更早日期公开；2020 PUF 首次发布日期尚待官方历史证据。2024 码本最后更新于 2025-05-28，2024 数据最后更新于 2026-02-09，当前版不能作历史 vintage 证据。

## 其他候选仅作准入筛查

- **HRS 2018：** 50 岁及以上为主的老龄化纵向样本，不代表全美成年 SCE 户主；2018 Core early data 官方于 2019-12-18 宣布可用，公开下载要注册。官方 2018 psychosocial codebook 含未来乐观 item `QLB018B`，但只可作 50+ 敏感性/测量效度检查；不做全美成人 donor。
- **MIDUS：** 有成人心理幸福与乐观量表，但它是始于 1995–96 的纵向队列、后续多年追访，不是目标月新横截面；公开访问经 MIDUS/ICPSR 页面，个体匹配支持及 B 历史 vintage 未核。此轮不下载。
- **UAS：** 美国在线 panel，虽可检查问卷/码本，但个体级文件须注册并签署数据使用协议；未获得账户前不能证明文件可立即免费公开下载、字段联合覆盖或目标 vintage。此轮只记录准入门槛，不建议首版依赖。

这三类面板都不能在本轮替代经行级审计的 GSS/SHED donor；HRS 的 50+ 限制尤其不适合外推到全体美国成人。

## 最小操作步骤

1. A 先保留 SCE 当前观察画像；在单独候选列里记录 `Q1` 为“过去一年财务状态”，`Q45b` 为健康状态，`QRA1/2` 为风险意愿，原始 numeracy 题与 `_NUM_CAT` 分开标来源/算法状态。缺失保留 missing；不得默认加进 P 白名单。
2. B 固定 target cutoff，再取 cutoff 前真实已公开的 SCE 滞后波次或归档 GSS 2018/SHED 2019 vintage；保存下载时间、官网发布日期、文件版本和 SHA-256。当前在线文件不得倒推历史可得。
3. 先以 SCE/GSS/SHED 的年龄、教育、收入、粗地区做变量 crosswalk；再核就业、住房标签。只保留同时在两边、同 respondent 有效的 X 单元。比较家庭户主与成年个人总体差异，不把权重差异当作已解决代表性问题。
4. 在 GSS 2018 和 SHED 2019 微观表计算 HAPPY+SATFIN(+TRUST) 或 financial-state+X 的完整记录数、ballot/项目适用性、各组 ESS 及权重版本；若任一关键心理字段无足够共同支持，标 unsupported，不用全国边际随机给 SCE 居民贴心理标签。
5. 统计匹配只形成条件 donor 分布。分别保留 GSS 的幸福/财务满意/信任联合行；SHED 只作为财务体验/通胀冲击替代条件。模型不能据此声称个体 SCE 真实心理记录已被找到，也不能把支持相关性说成因果机制。

## 本轮文件/版本记录

本轮未写入原始文件到 `data/raw/literature/...`。复核 SCE 数据来自既有文件：`data/raw/sce_audit_20260928/micro_2020_2024.xlsx`，官方 URL 与 SHA-256=`1b57ffb75c2170d767f46a001002db8c40c228fe5691f6dd19e39777ffe469c6` 已列在 `docs/sce_source_manifest.json`；问卷 PDF 的 SHA-256 也在该清单。本轮查阅了 SCE 官方问卷、GSS 2021 Release 4 codebook 与 2018 发布公告、SHED 2024 codebook/官方数据页；未下载 GSS、SHED、HRS、MIDUS 或 UAS 微观数据。逐来源访问与核验状态见 [data_sources.json](sources/data_sources.json)。
