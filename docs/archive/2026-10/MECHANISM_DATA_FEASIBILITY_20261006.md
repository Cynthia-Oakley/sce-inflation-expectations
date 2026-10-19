# SCE 个人价格体验机制：CE 数据可行性核查

核查日：2026-10-06。范围仅为公开 Consumer Expenditure Surveys（CE）与当前 SCE 人口画像能否共同支持“消费篮子 → 类别价格暴露 → 预期回答”的回顾性检验；不是个人真实购买记录，也不是已验证机制。

## 结论与历史边界

2020 CE Interview 的 `FMLI` 家庭级微观记录同时含参考人年龄、教育、住房 tenure、地区、家庭年收入和多个支出类别。它比按人口组发布的 CE 均值更适合作为**联合篮子捐赠样本**：可从同一条 CU 记录保留食品、租金/住房、汽油等类别之间的相关性，再按 SCE 可观察字段作带权条件抽样。当前 v1 只生成基于家庭支出份额的 **spending-salience proxy**，没有将类别金额与 CPI 变化相乘；它不是个体 CPI 或已验证的体验机制。BLS 当前公开 CSV 归档 `intrvw20.zip` 已取得，SHA-256 为 `de226eaf9b18eb4721e8aca385c94101b8061a74decc5b9f52667c29cf01ba8a`，大小 53,895,332 bytes；`intrvw20/fmli204.csv` 有 5,205 行、5,205 个唯一 `NEWID`，且本次抽查行均为 `QINTRVYR=2020`、`QINTRVMO=10–12`。本地副本：`data/raw/ce_experience/20261006/intrvw20.zip`。

这只支持“匹配到一个与画像相容的**合成家庭篮子**”，不表示 SCE 受访者本人买过这些东西、由其本人购物/开车/做饭，或在本地实际支付过对应价格。CE 是 consumer unit（CU）/家庭级支出，SCE 是个人回答；两者没有可联结的共同受访者 ID。公开 CE 均值表只有人口组均值，无法恢复个体篮子、联合分布或协方差；不可把一个组均值复制成组内每个人的事实篮子。

2020Q4 仅供 A 线**回顾性重建**：BLS 2021-04-29 的 midyear 发布稿说当时 Interview PUMD 覆盖 2020Q2/Q3，并称年度 PUMD 计划于 2021 年 9 月发布；BLS 2021-09-09 年度发布稿首页列明发布日期，第 8 页明确称 1980–2020 年年度 PUMD 已可获取。因此完整 2020 数据的公开发布时间在 2021 年 5/6 月目标月之后。当前 BLS 在线 2019/2020 文件还应用了 2022-03-10 公布的修订；本次下载是当前修订副本，不是 2021 年首发快照。可用于 A 的后验约束，不能称为目标月当时已知的 P；B 线或任何严格 PIT 主张须另有当时可得的人口/数据 vintage 证据。当前 SCE 2020–24 工作簿来自 2026-09-28 下载，项目 manifest 未确认其历史首次发布时间；同样不能包装为 2021 年 PIT 画像。

## 字段交叉表

当前 SCE persona 读取的是项目白名单（`studies/sce_inflation_expectations/monthly_population.py`），不是问卷的全部字段。SCE 画像当前可用 `_AGE_CAT`、`_EDU_CAT`、`_HH_INC_CAT`、`_REGION_CAT`、`_STATE`、`_NUM_CAT`、`Q10_1…Q10_10`；`Q43` 只在出现住房回答、且没有后续搬迁时映射为 owner/renter/other。当前数据实测分类及缺失说明见 `studies/sce_inflation_expectations/reports/POPULATION_SAMPLING_REPORT.md`。

| 维度 | SCE 当前画像字段 | CE 2020Q4 FMLI 字段/码 | 可匹配程度与边界 |
|---|---|---|---|
| 年龄 | `_AGE_CAT`: `Under 40`、`40 to 60`、`Over 60` | `AGE_REF`：CU reference person 年龄（岁） | 可按 SCE 分档将 CE `AGE_REF` 合并成三组；SCE 是问卷个人、CE 是家庭参考人，非同一概念。分档边界以原 SCE 派生代码核实后固定。 |
| 教育 | `_EDU_CAT`: `High School`、`Some College`、`College` | `EDUC_REF`：00 未上学；10 小学/1–8年级；11 高中9–12年级未毕业；12 高中毕业；13 部分大学未获学位；14 副学士；15 学士；16 硕士/专业/博士 | 码表有效期 2013Q2 起。三档跨调查映射是**合并规则**，不是标签同义：可暂按 00/10/11/12、13/14、15/16 合并，需保留替代边界敏感性；SCE `College` 无研究生细分。 |
| 收入 | `_HH_INC_CAT`: `<50k`、`50k–100k`、`>100k` | `FINCBTXM`：过去12个月税前 family income，已收集或插补；`FINCBTAX`：过去12个月收集到的税前 family income | 2020Q4 两列均存在。`FINCBTXM` 的组成变量按插补迭代均值合成；适合作条件变量时仍应查收入插补标记并作敏感性分析。它是 family income，不是严格等同的 SCE respondent/household income；且不含 meals/rent-as-pay。BLS FAQ 指出完整定义需另加 `JMLPAYQV`、`JRTPAYQV`，字典将它们列在 Interview 其他文件（XPA/RNT），不在 `fmli204.csv` 这一行内。 |
| 地区 | `_REGION_CAT`: Northeast/Midwest/South/West | `REGION`: 1 Northeast、2 Midwest、3 South、4 West | 粗地区可匹配；本次 FMLI204 中 REGION 缺失 152/5,205，缺失必须显式保留/处理。不可把地区平均汽油价称为家庭个人价格。 |
| 州 | `_STATE`: 州邮政缩写 + DC | `STATE`: 2010 FIPS 州码 | 字典列出该变量，但 FMLI204 中缺失 487/5,205；需先 FIPS/缩写映射和支持度审计，不建议主匹配使用精细州层。 |
| 住房 tenure | `Q43` → owner/renter/other；回答只在特定波次可得，代码在未观察到搬家时才沿用 | `CUTENURE`: 1 有按揭业主、2 无按揭业主、3 按揭状态未报业主、4 renter、5 无现金租金居住、6 student housing | **家庭实际报告的 tenure 标签可用**；可保留六类后再与 SCE 三类对照（1–3 owner、4 renter、5–6 other）。它仍不能判定谁承担购物/开车/做饭。Q4样本中 tenure 码 1/2/4/5/6 均出现，码3未见。 |
| 就业 / 性别 / 数理 | 就业由个体 `Q10_1…Q10_10` 多选优先规则派生；`_NUM_CAT` 为 High/Low numeracy；当前 persona 不含 sex | FMLI204 有 `SEX_REF`（CU reference person 性别），未发现可与 SCE Q10 等价的当前个人就业状态列 | 单人问卷就业 vs CU 层面不能硬配；CE 的参考人性别也不表示购买/驾驶责任。不可按性别、就业、地区或年龄确定谁买菜/开车/做饭；numeracy 在本批 CE FMLI 字段中没有共同指标。 |
| 支出篮子 | SCE profile 无家庭食品、租金、汽油/购物频率或实际成交价字段 | `FOODCQ/PQ`（food at home + away）、`RENDWECQ/PQ`（rented dwelling）、`SHELTCQ/PQ`、`HOUSCQ/PQ`（广义 housing）、`GASMOCQ/PQ`（gasoline and motor oil）、`TOTEXPCQ/PQ` | FMLI204 观察的是家庭金额而非数量/单价/购买人。`RENDWE` 是 renter 的租住支出；`HOUS` 不是租金专属指标。零汽油金额不能辨认无车、未加油或他人承担。 |

## 当前 v1 与后续版本边界

1. 当前 `studies/sce_inflation_expectations/price_experience.py` 把一个 `FMLI204` CU 记录的 `FOODCQ/PQ`、`GASMOCQ/PQ`、`SHELTCQ/PQ` 相加，并用 `TOTEXPCQ/PQ` 归一化为 food/gasoline/shelter/other 支出份额；同一 donor 行保留类别共变，使用 `FINLWT21` 作条件带权抽样，并将结果标为 `estimated_proxy` / `conditional_weighted_synthetic_donor`。这是支出显著性代理，不是价格指数，不包含价格变化或购买频率。
2. 当前分母 `TOTEXP` 的字典公式包含 `CASHCO`（现金捐赠/贡献）与 `RETPEN`（退休/养老金）等非日常 CPI 购买量项目。因此 v1 份额不能称为 CPI 消费权重或个人通胀率；`other` 是由总额残差得到的混合类别。本轮不把它乘 CPI、不拟合回答系数，也不据此预设人口组的回答高低。
3. 如以后单独设计 CPI exposure 版本，先预注册 CPI 可比类别集合 K，用同一 donor 的相应支出构造 `s_ik = x_ik / sum(x_ij for j in K)`，再乘公开类别价格变化；把结果称为项目合成近似而不是个人实付价格或对某论文公式的直接复现。需单独处理 renter rent、owner housing cost、食品内外食、燃油类别，并报告缺失/零支出、调查 vintage 和类别映射敏感性。该方案是后续方向，不是当前 v1 功能。
4. 画像匹配仅使用双方可观察且语义足够接近的字段；条件抽样的层级和 fallback 是统计分配假设。保留 donor ID、源文件哈希、匹配字段、fallback、随机种子、pool 有效样本量和 `synthetic` 标签；以多次 seeds/draws 检查 donor 分配敏感性，不把组均值回填为个体篮子。
5. SCE 没有购物者/驾驶者/做饭者标记，CE 的支出为 CU 总额，日记（Diary）与 Interview 还是不同抽样样本，BLS 明确不可用 `NEWID` 跨调查联结。因此外部证据若提供角色与收入/教育等联合分布，可以用带标签的条件概率作**合成角色分配**、反复抽样作敏感性分析；但当前两库不能把角色当观测、不能按性别分派，也不能强行让某组对通胀回答更高或更低以增加方差。
6. 独立检查应先比较 CE 原始加权的宽组篮子均值与 BLS 已发布 CE 表（仅总体/组水平合理性检查，不作个体赋值），检查 SCE×CE 联合 cell 覆盖、州/地区缺失、收入插补和 donor 重复。若后续引入价格指数，固定相同 B/E 做“无个人价格暴露 vs 加入合成暴露”对照；将 donor 抽样不确定性、个人价格暴露差异、问卷回答不确定性、群体答案分歧及 Q8/Q9 报告形式/圆整分别诊断。人口关联可被检验，不能先验断言人口没有作用。

## 来源、日期与版本

- [BLS PUMD 数据文件页](https://www.bls.gov/cex/pumd_data.htm)列出 2020 CSV Interview ZIP（当前页显示 52.6 MB），并说明自 2020 年起 Interview 包含当年 Q2–Q4 和次年 Q1；[官方归档 ZIP](https://www.bls.gov/cex/pumd/data/comma/intrvw20.zip)已于 2026-10-06 经普通浏览器官方链接下载。BLS 页面被直接命令行请求时曾回 403，浏览器正常官方链接可取；未尝试绕过访问限制。
- [BLS PUMD 字典/样例代码页](https://www.bls.gov/cex/pumd_doc.htm)链接 [官方 Interview/Diary XLSX 字典](https://www.bls.gov/cex/pumd/ce-pumd-interview-diary-dictionary.xlsx)。该官方当前字典于 2026-10-06 经同源浏览器取回：`data/raw/ce_experience/20261006/ce_pumd_dictionary_official.xlsx`，1,355,152 bytes，SHA-256 `613810d32de105bcd32fa9030d378472afb4dab23d1922be7b71b0c522d0334c`；镜像副本仍保留作码值交叉核对，education codes 与官方表一致。两份都是当前代码本，不是 2020 年历史码本。获取记录见 `official_dictionary_manifest.json`、`dictionary_mirror_manifest.json`。
- [BLS 2021-04-29 Midyear Update](https://www.bls.gov/news.release/archives/cesmy_04292021.htm)的 Data Products 节说当时 Interview PUMD 是 2020Q2/Q3；2020 年年度发布/公开微数据计划在 2021 年 9 月。 [BLS 2020 年年度发布 PDF](https://www.bls.gov/news.release/archives/cesan_09092021.pdf)首页给出 2021-09-09 10:00 ET，正文第 8 页明确列出 1980–2020 PUMD available。
- [BLS 2021 CE 使用论文](https://www.bls.gov/osmr/research-papers/2021/pdf/ec210100.pdf)附录 A.2（PDF p.38）列出 2020 `FMLI` 人口、收入、权重和支出字段，并明示参考期 `CQ+PQ`。 [CE Getting Started Guide](https://www.bls.gov/cex/pumd-getting-started-guide.htm)§3.2 与 §6.3 说明问卷回忆期、CQ/PQ、`NEWID`、`FINLWT21` 和全年权重计算；[CE FAQ](https://www.bls.gov/cex/csxfaqs.htm)说明完整收入与总支出口径。
- [BLS 2019/2020 PUMD Errata](https://www.bls.gov/cex/pumd_errata_2019_2020.htm)说明 2019/2020 文件与关联 summary variables 在 2022-03-10 修订，已替换网站旧版；本地文件因此登记为 2026 下载的当前修订副本。
- SCE 当前公开源由 `docs/sce_source_manifest.json` 记录：NY Fed 2020–24 microdata 工作簿，2026-09-28 下载；该 manifest 未记录历史首次发布时间。本文确认的是现有代码白名单及本地画像快照，而非证明这些 P 字段在 2021-05/06 已首次公开。

## 候选来源与获取方式补充（2026-10-06）

本节原为获取前的候选比较。随后用户同意落地：Diary ZIP、收入分组年表已本地归档，完整人口篮子已生成，准确路径与当前验收见 [消费数据入口](../../CE_CONSUMPTION_DATA_INDEX.md)。下文“本次未下载”等表述保留为当时状态，不再代表最新进度；购买频率合成仍未接入模拟。

Diary 是 CE 的日记调查部分，与 Interview 访谈调查共同构成 CE，不是另一个独立供应商。

- **主篮子建议采用 Interview 微观记录。** FMLI 为家庭汇总支出及人口背景；需要拆分更多类别时，可在同一调查内连接 MTBI/月度分类支出或详细问卷分项。带权抽取整户记录，保留组内差异与类别组合；当前已接入的是一个 FMLI 波次，不等于所有详细文件均已处理。
- **购买频率作为后续 Diary 分支。** 两周日常消费记录可研究有购买记录的天数等短窗口代理；不能把明细行数直接当购物次数，也不能把两周记录视为全年稳定频率。Interview 与 Diary 是不同样本，无法用 NEWID 跨调查联结；联合合成需另有匹配假设与敏感性检验。本次没有宣称已完成 Diary 数据获取或频率构建。
- **CE 已发布分组表作独立合理性检查及组均值对照。** [官方表格](https://www.bls.gov/cex/tables.htm)提供 Excel/HTML 等格式；组均值本身不足以恢复个体方差、联合分布。
- **NielsenIQ Consumer Panel 为可选增强来源。** [Kilts 官方说明](https://www.chicagobooth.edu/research/kilts/research-data/nielseniq)介绍家庭购买面板及部分配套预期调查；[获取流程](https://www.chicagobooth.edu/research/kilts/research-data/nielseniq/processes)要求机构订阅及研究者审批，通过 Globus 获取压缩数据。它可更直接研究商品购买/价格接触，但不是无条件开放数据，也不能完整替代住房等全口径支出。学校授权与复旦当前可得性尚未核实。

**文件与 token：** [PUMD 官方下载页](https://www.bls.gov/cex/pumd_data.htm)同时提供 Interview/Diary 的 CSV、Stata、SAS 压缩包；[文档页](https://www.bls.gov/cex/pumd_doc.htm)提供 XLSX 字典。家庭原始记录采用批量下载，不从 [BLS Public Data API](https://www.bls.gov/bls/api_features.htm)逐户检索；该 API 面向已发布历史时间序列，可用于相应宏观指标。主要处理对象是结构化数据，无需把大规模数据或扫描件交给 LLM。问卷/方法 PDF 用于理解规则，只提取必要章节；模型仅接收每人的简短合成消费背景。下载、CSV 清洗及抽样程序本身不调用 LLM。

Luna 子 Agent 另核查了 [BLS 2019 Diary 表格 PDF](https://www.bls.gov/cex/ced/2019/ced-diary-form.pdf)，该文件有可提取文字，无需 OCR；不据此断言所有历史 PDF 均为文字型。官方指南的 Diary 时间字段可用于研究调查周内有记录的不同天数，但隐私处理后不能恢复精确购买日历日期。详细文件和历年字段需在实际获取时再次核对；本次未下载 Diary ZIP。

建议采用 **Interview 主篮子 + CE 分组表核查 + Diary 后续频率对照**；NielsenIQ 不设为项目完成前提。具体年份、类别映射及预测线 vintage 合同仍需分别登记，本节不修改运行配置或冻结参数。
