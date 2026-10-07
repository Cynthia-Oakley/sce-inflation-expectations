# 2019 CPI 分项失败解析复核

核查日：2026-10-07。只读检查 `outputs/sce_e_extension_20261007T084913Z/components_handoff.jsonl` 的 14 行及对应 BLS 首发 PDF。现有脚本为 `scripts/extract_cpi_components.py`；未修改脚本、配置或数据。以下数值均为**未季调、同比百分比**，每条采用 handoff 中所列 `reference_period` 的对应月，不以发布日期或发布月替代。

## 14 条失败及原始证据

| reference_period | signal_id | 值 | 来源与可复核证据 |
|---|---|---:|---|
| 2019-01 | `cpi_shelter_yoy` | 3.2 | [2019-01 首发 PDF](../../../../data/raw/bls_initial_releases/2019-01/cpi_2019_01_released_2019_02_13.pdf) p.3，Table A，Shelter 行末列。 |
| 2019-02 | `cpi_gasoline_yoy` | -9.1 | [2019-02 首发 PDF](../../../../data/raw/bls_initial_releases/2019-02/cpi_2019_02_released_2019_03_12.pdf) p.2，Table A，Gasoline (all types) 行末列。 |
| 2019-03 | `cpi_shelter_yoy` | 3.4 | [2019-03 首发 PDF](../../../../data/raw/bls_initial_releases/2019-03/cpi_2019_03_released_2019_04_10.pdf) p.8，Table 1，Shelter 行，“Unadjusted percent change”下 `Mar. 2018–Mar. 2019` 列。 |
| 2019-03 | `cpi_gasoline_yoy` | -0.7 | 同上 p.8，Table 1，Gasoline (all types) 行，同一同比列。叙述 p.3 也写明能源过去12个月降0.4%，紧接着汽油指数降0.7%。 |
| 2019-04 | `cpi_food_at_home_yoy` | 0.7 | [2019-04 首发 PDF](../../../../data/raw/bls_initial_releases/2019-04/cpi_2019_04_released_2019_05_10.pdf) p.2，Table A，Food at home 行末列。 |
| 2019-04 | `cpi_shelter_yoy` | 3.4 | 同上 p.2，Table A，Shelter 行末列。 |
| 2019-04 | `cpi_gasoline_yoy` | 3.1 | 同上 p.2，Table A，Gasoline (all types) 行末列。 |
| 2019-05 | `cpi_food_at_home_yoy` | 1.2 | [2019-05 首发 PDF](../../../../data/raw/bls_initial_releases/2019-05/cpi_2019_05_released_2019_06_12.pdf) p.3 原句：“The food index rose 2.0 percent over the past year, with the food at home index increasing 1.2 percent.” |
| 2019-05 | `cpi_shelter_yoy` | 3.3 | 同上 p.4 原句：“The shelter index rose 3.3 percent over the year …” |
| 2019-06 | `cpi_food_at_home_yoy` | 0.9 | [2019-06 首发 PDF](../../../../data/raw/bls_initial_releases/2019-06/cpi_2019_06_released_2019_07_11.pdf) p.2，Table A，Food at home 行末列。 |
| 2019-06 | `cpi_shelter_yoy` | 3.5 | 同上 p.2，Table A，Shelter 行末列。 |
| 2019-07 | `cpi_food_at_home_yoy` | 0.6 | [2019-07 首发 PDF](../../../../data/raw/bls_initial_releases/2019-07/cpi_2019_07_released_2019_08_13.pdf) p.2，Table A，Food at home 行末列。 |
| 2019-07 | `cpi_shelter_yoy` | 3.5 | 同上 p.2，Table A，Shelter 行末列。 |
| 2019-09 | `cpi_shelter_yoy` | 3.5 | [2019-09 首发 PDF](../../../../data/raw/bls_initial_releases/2019-09/cpi_2019_09_released_2019_10_10.pdf) p.2，Table A，Shelter 行末列。 |

表内共 14 个数值格，对应 14 条 handoff；2019-03 的两条由同一报告支持。Table A 页面使用 pypdf `extract_text(extraction_mode="layout")` 后可读出相同行列，例如 2019-04 的 `Food at home ... -.1 .1 .3 .1 .4 .4 -.5 .7` 和 `Gasoline (all types) ... 2.7 -5.2 -5.8 -5.5 1.5 6.5 5.7 3.1`。2019-05 的 Table A 页未被 pypdf 提取出可用文本，故该月只采用报告正文中明确带年度语境的短句。

## 对现有解析器的判断

1. `_extract_from_table_a` 当前假设：目标行标签后会先出现至少三个 `>=100` 的指数水平数，再取其后的数值。实测 Table A 的 pypdf 默认线性提取不按视觉行列排序；Table A 的目标行标签后直接是七个季调月变动值和一个未季调同比值，较大的指数水平可能排在行标签之前。因此当前 `>=100` 条件和列序假设与这些文件的实际抽取结果不符。
2. `PATTERNS` 多要求“over the last/past 12 months”紧跟目标值。2019 年报告还使用 “over the year / past year / over the span”，有时年度时间窗写在前句或同段首句，分项随后用 “over the span” 承接；若不约束同段目标月语境，简单放宽正则会误取月度变化或上一期值。
3. pypdf 的布局模式在本批可读 Table A 行；默认模式将列串接，也有数值空格断裂（如 `-5. 2`）。不建议在默认扁平文本上靠“第几个数字”补丁取值。

## 建议的确定性规则

1. **优先读取表格并校验表头。** 对 PDF 页面使用 pypdf `extract_text(extraction_mode="layout")`；先定位 `Table A. Percent changes in CPI ...`，确认该表标题/页眉对应 `reference_period`，并确认列头为 `Un-adjusted 12-mos. ended <month year>`。仅在目标行名精确匹配后读取该行。2019 年这些 Table A 行在行名之后有 7 个当月及前月季调变动格，最右第 8 个一位小数数值是未季调 12 个月变化；Food at home 的行尾脚注 `1` 不是数据格，应仅接受小数格并校验恰有 8 个。遇到列数异常、标签歧义或数字断裂未能无损正规化时，失败并交人工复核，不猜列位。
2. **记录审计证据。** 结果保留 PDF 相对路径、SHA-256、页码、表名/列头、目标行原文、提取值和解析方式。原 `components_handoff.jsonl` 已含每条 PDF 的 SHA-256，可用于确认审计的是同一文件版本。
3. **Table A 缺失时仅用有明确年度范围的窄回退。** 先在正文同段内要求出现目标组件名与年度锚点（`12 months`、`past year`、`over the year`）。允许 “over the span” 仅在同段先有明确截止目标月的 12 个月表述时，并确保中间未换到别的组件。值须是该分项句中的数值；若上下文仅说全能源年度变化、没有同段分项值，则不由总项反推分项。
4. **2019-03 特例优先用 Table 1。** 该首发稿没有可用的 Table A 文本行，但附录 p.8 的 Table 1 可用布局读取；先校验表题为 March 2019，再按 `Unadjusted percent change` 下 `Mar. 2018–Mar. 2019` 列读取，而不是取行末值（行末是另一种月度列）。正文可以作为交叉核对。不同表的列规则不可混用。
5. **禁止跨期回填。** 若目标 PDF 或截止月列未匹配 handoff 的 `reference_period`，或只有前月/相邻月份值，继续隔离失败；不得用当月发布日月份、最新 CPI 快照或下一期值替代。保存每个有效值独立于下游合并，先保留原 PDF 与来源哈希。

## 独立辅助解析器验证

随后按上述列约束新增独立模块 [`scripts/sce_cpi_layout.py`](../../../../scripts/sce_cpi_layout.py) 与测试 [`tests/test_sce_cpi_layout.py`](../../../../tests/test_sce_cpi_layout.py)，未改动 `extend` 或既有解析器。`extract_annual_component(pdf_path, signal, reference_period)` 先按 Table A 精确行名及已核验截止月表头读取恰 8 个小数格的末格；Table A 不可读时，Table 1 仅在报告月/年度范围及列组头匹配后取未季调同比列（行内第 5 个数字，不取行尾）。正文回退限于目标分项与年度后缀同句、方向明确的句式；food-at-home 仅接受已核验的同句 food 指数年度范围承接句。结果保留页码、原文行/句、表头、模式和提取方式。月度短句、核心能源中的 “all items less food and energy” 等反例有拒绝测试。

用 `/Users/wushuyue/anaconda3/envs/socioverse/bin/python -m pytest -q tests/test_sce_cpi_layout.py` 验证：13 项通过。2019 年 handoff 的 14/14 项可提取，值与本报告上表相同；2019-03 两项及 2019-05 两项均通过 Table 1 的同比列读取。另对 2025-09 汽油 handoff 实测命中 p.8 Table 1，表头为 `September 2024–September 2025`，同比列为 -0.5（行尾月度列为 4.1）；对应首发 PDF 为 [2025-09 CPI 新闻稿](../../../../data/raw/bls_initial_releases/2025-09/cpi_2025_09_released_2025_10_24.pdf)。这只是上述本地文件的验证，不证明其余月份或版本覆盖率，也未做独立 HTML 核对。
