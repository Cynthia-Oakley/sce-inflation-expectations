# CE Diary 2020Q4 字段审查

日期：2026-10-06
范围：确认 Diary 2020 Q4 的日序字段、同波次 FMLD/EXPD 连接、类别 UCC 映射和发布标志口径。

## 输入版本

- 官方 Diary 年度 ZIP：`data/raw/ce_experience/20261006/diary/diary20.zip`，SHA-256 `4862a21ef2b9de25c88a4efbdd4f3905aeaf68d942abc9acc31b33644f84db1a`。此次只处理 `fmld204.csv` 和 `expd204.csv`。
- 官方 Interview/Diary 字典：`data/raw/ce_experience/20261006/ce_pumd_dictionary_official.xlsx`，SHA-256 `613810d32de105bcd32fa9030d378472afb4dab23d1922be7b71b0c522d0334c`。
- BLS 2021-09-09 年度发布稿说明 1980–2020 年度 CE PUMD Interview 和 Diary 文件已可用，因此记录 `known_available_by=2021-09-09`，见[发布稿](https://www.bls.gov/news.release/archives/cesan_09092021.htm)。这只是“不晚于该日已可用”的证据，不是首次发布日期或当前本地文件版本证明；不据此认证 2021 年 5/6 月 PIT 可得性。
- 字典和字段用法参考 BLS [PUMD Getting Started Guide](https://www.bls.gov/cex/pumd-getting-started-guide.htm) 与[官方字典下载页](https://www.bls.gov/cex/pumd_doc.htm)。当前 ZIP 是官方可下载的更正后文件；BLS [2019–2020 errata](https://www.bls.gov/cex/pumd_errata_2019_2020.htm) 记录了 2022-03-10 的 Diary 修正。该版本不能证明是 2021 年预测时点可得的版本。

## 明细字段与连接

Q4 FMLD 有 2,835 条唯一 `NEWID`，即 CU-week 记录；其中 `WEEKI=1` 有 1,426 条，`WEEKI=2` 有 1,409 条。脚本保留每条自身的 `FINLWT21`，不把两周合并，也不将周金额年化。

Q4 EXPD 有 93,058 条明细，覆盖 2,712 个 FMLD `NEWID`。脚本在同一个 Q4 内按精确 `NEWID` 连接；没有 EXPD 孤儿记录，123 个 FMLD CU-week 没有匹配 EXPD 明细行。无明细行单独标记，不解释为家庭实际支出为零。日记 `NEWID` 与 Interview/SCE 受访者 ID 不连接。

EXPD 表头直接包含 `EXPNSQDY` 和 `EXPN_QDY`。字典将 `EXPNSQDY` 定义为日记周中的顺序日（1–7）；BLS 指南将 `EXPN_QDY` 的 D/E/T 标作有效值（未调整、分配、封顶或受抑制）。因此无需从 DTBD、ALLOC 或行数推断购买日。Q4 DTBD 的表头为 `NEWID,UCC,AMOUNT,AMOUNT_,PUB_FLAG`，对应年度详细收入，不提供日序。

Q4 EXPD 的日字段标志计数为 D=91,249、B=1,776、A=33。B/A 表示缺失或无效响应状态，不能当成有效日码。对 81,266 条正金额、`PUB_FLAG=2` 明细，1,739 条没有有效日支持。输出日数是每个 CU-week **跨所有类别合计的不同顺序日**，不是按类别拆分的频率；2,455 周为 `available`，136 周为 `partial_day_support`，121 周没有正金额发布明细，123 周没有 EXPD 行。它不表示交易次数、精确日历日期、年度习惯或个人消费频率。

## 类别范围及独立字段核对

2020 有效 UCC 范围按官方字典递归解析：food at home 106 个码（`FOODHOME`），household supplies/services 8 个码（`HOUSKEEP`），personal care 11 个码（`PERSPROD` 8 个加 `PERSSERV` 3 个）。字典中的 `FOODAWAY` 公式文本被截在 255 字符，故 food away 使用所有有效 `DIARY/EXPD` 的 `190` 前缀码（29 个），并与 FMLD `FOODAWAY` 独立核对。其它有效码放入 `other_known_ucc`，不在有效字典的码放入 `unknown_ucc`。

金额输出仅累加用于 BLS 发布统计的 `PUB_FLAG=2` 明细。`PUB_FLAG=1` 明细本身仍在公开 PUMD 文件中，但 BLS 发布统计不使用这些值；本次将其排除在类别金额之外并单独核对。每周的核对字段及汇总都写在 JSONL 与 manifest 中：

- `FOODHOME`：2,835/2,835 周发布明细精确相等。
- `HOUSKEEP`：2,835/2,835 周发布明细精确相等。
- `FOODAWAY`：仅发布明细时 2,834/2,835 周相等，唯一差额为 -$1,000；该周排除的 190 前缀 `PUB_FLAG=1` 明细恰为 $1,000。加回排除行后 2,835/2,835 周都相等。
- `PERSPROD + PERSSERV`：仅发布明细时 2,595/2,835 周相等；240 周的差额逐周都等于被排除的 `PUB_FLAG=1` 个人护理明细，累计 $17,644.39089，未知发布标志金额为零。加回排除行后 2,835/2,835 周都相等。

因此 food-away 的 $1,000 与个人护理差异均由发布标志范围解释，不是公式截断或漏掉 UCC 的证据。输出仍保留发布金额口径，不用未发布值替换；这些类别金额也不用于推断类别购买频率或个人消费权重。

## 输出及验证

完整机器处理结果：[`20261006T071002778274Z_ce_diary2020q4_4862a21e`](../data/interim/ce_experience/20261006T071002778274Z_ce_diary2020q4_4862a21e/README.md)。目录内 README 记录源文件哈希、字段支持、范围、对账结果和局限；manifest 保留每周和总计的确定性核对值。处理过程只运行本地 Python 代码，不将完整 JSONL 或住户记录交给 LLM。

验证命令 `python3 -m unittest discover -s tests -p 'test_ce_diary_experience.py'`：7 项通过；官方 ZIP 端到端运行成功，产出 2,835 条周记录。
