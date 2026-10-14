# 提示词与输入/输出审阅包（v1 基线运行）

运行：`sce-local-openai-20261003T055121Z-1dc7cd15`（73 人 × 2021 全年 12 月，deepseek-flash，temperature=0.5，thinking 关闭，JSON 模式）。
提示词模板代码：`studies/sce_inflation_expectations/model.py`（当前**已是全英文**）。本文内容均从 `llm_calls.jsonl` 原始存档逐字复制。

## 1. 完整提示词原文（2021-01，40–60 岁、大学、东北区、租房、在职、低数理能力的家庭）

```text
You are a U.S. household head, age group 40 to 60, with a college degree, household income between $50,000 and $100,000, living in the Northeast region, renting your home, currently employed. Your score on the survey's numeracy assessment was low.

It is 2021-01. You only know information that was publicly available by 2020-12-31T23:59:59-05:00.
The most recent official U.S. Bureau of Labor Statistics releases available to you:
- CPI-U all items 12-month percent change, not seasonally adjusted for 2020-11: 1.2% (initial release published 2020-12-10, source USDL-20-2218)
- CPI-U all items 1-month percent change, seasonally adjusted for 2020-11: 0.2% (initial release published 2020-12-10, source USDL-20-2218)
- Civilian unemployment rate, seasonally adjusted for 2020-11: 6.7% (initial release published 2020-12-04, source USDL-20-2184)
- Total nonfarm payroll employment 1-month change, seasonally adjusted for 2020-11: 245 (initial release published 2020-12-04, source USDL-20-2184)

Question 1 (point estimate): Over the next 12 months, what do you expect the rate of inflation to be,
in percent? Give a single signed number (negative means deflation).

Question 2 (density): What is the percent chance that the 12-month-ahead inflation rate will fall in
each of the following ten ranges? Give each a probability from 0 to 100; the ten probabilities must
sum to exactly 100.
  "bin1": probability that inflation will be 12% or more
  "bin2": probability that inflation will be between 8% and 12%
  "bin3": probability that inflation will be between 4% and 8%
  "bin4": probability that inflation will be between 2% and 4%
  "bin5": probability that inflation will be between 0% and 2%
  "bin6": probability that inflation will be between -2% and 0%
  "bin7": probability that inflation will be between -4% and -2%
  "bin8": probability that inflation will be between -8% and -4%
  "bin9": probability that inflation will be between -12% and -8%
  "bin10": probability that inflation will be -12% or less (deflation of 12% or more)

Reply with ONLY a JSON object of the form:
{"point_pct": <number>, "q9": {"bin1": <0-100>, "bin2": <0-100>, ..., "bin10": <0-100>},
 "reason": "<one or two short sentences>"}
```

## 2. 对应的原始回答

```json
{
 "point_pct": 2.0,
 "q9": {
  "bin1": 1,
  "bin2": 2,
  "bin3": 5,
  "bin4": 12,
  "bin5": 38,
  "bin6": 28,
  "bin7": 8,
  "bin8": 4,
  "bin9": 1,
  "bin10": 1
 },
 "reason": "With recent CPI inflation around 1.2% and a weak pandemic economy, I expect modest inflation near 2%, with most probability around 0-2% and some chance of mild deflation."
}
```

## 3. 另外两个月度样例

### 2021-06（agent sce_u70121762）

```json
{
 "point_pct": 4.1,
 "q9": {
  "bin1": 3,
  "bin2": 9,
  "bin3": 22,
  "bin4": 30,
  "bin5": 22,
  "bin6": 9,
  "bin7": 3,
  "bin8": 1,
  "bin9": 0.5,
  "bin10": 0.5
 },
 "reason": "April 2021 CPI came in at 4.2% with strong 0.8% monthly momentum, so I revise my 12-month-ahead expectation up to about 4.1%, with the distribution centered on 2-4% and 4-8% as base effects and reopening pressures fade gradually."
}
```

### 2021-12（agent sce_u70120988）

```json
{
 "point_pct": 5.0,
 "q9": {
  "bin1": 4,
  "bin2": 16,
  "bin3": 34,
  "bin4": 26,
  "bin5": 12,
  "bin6": 5,
  "bin7": 2,
  "bin8": 1,
  "bin9": 0,
  "bin10": 0
 },
 "reason": "With CPI inflation running at 6.2% and broad price pressures still elevated, I expect inflation to moderate only gradually over the next year, centered near 5%."
}
```

## 4. E 输入信号结构（2021-01 步，来自 environment_main2021.json）

```json
[
 {
  "signal_id": "bls_cpi_u_all_items_yoy_nsa_2020_11_initial",
  "measure": "CPI-U all items 12-month percent change, not seasonally adjusted",
  "value": 1.2,
  "unit": "percent",
  "reference_period": "2020-11",
  "published_at": "2020-12-10T08:30:00-05:00",
  "source_version": "USDL-20-2218",
  "source_url": "https://www.bls.gov/news.release/archives/cpi_12102020.pdf",
  "eligibility": "eligible"
 },
 {
  "signal_id": "bls_cpi_u_all_items_mom_sa_2020_11_initial",
  "measure": "CPI-U all items 1-month percent change, seasonally adjusted",
  "value": 0.2,
  "unit": "percent",
  "reference_period": "2020-11",
  "published_at": "2020-12-10T08:30:00-05:00",
  "source_version": "USDL-20-2218",
  "source_url": "https://www.bls.gov/news.release/archives/cpi_12102020.pdf",
  "eligibility": "eligible"
 },
 {
  "signal_id": "bls_unemployment_rate_sa_2020_11_initial",
  "measure": "Civilian unemployment rate, seasonally adjusted",
  "value": 6.7,
  "unit": "percent",
  "reference_period": "2020-11",
  "published_at": "2020-12-04T08:30:00-05:00",
  "source_version": "USDL-20-2184",
  "source_url": "https://www.bls.gov/news.release/archives/empsit_12042020.pdf",
  "eligibility": "eligible"
 },
 {
  "signal_id": "bls_nonfarm_payroll_change_sa_2020_11_initial",
  "measure": "Total nonfarm payroll employment 1-month change, seasonally adjusted",
  "value": 245,
  "unit": "thousands",
  "reference_period": "2020-11",
  "published_at": "2020-12-04T08:30:00-05:00",
  "source_version": "USDL-20-2184",
  "source_url": "https://www.bls.gov/news.release/archives/empsit_12042020.pdf",
  "eligibility": "eligible"
 }
]
```

每个目标月 4 个信号（CPI 同比/CPI 环比/失业率/非农），均为 as_of 时点最新一期首发稿单点值，无历史序列——这正是 v2 要改的地方。

## 5. 逐月分布对照（模拟 vs 真实）

| 月 | 模拟点估计中位 | 真实点估计中位 | 模拟密度中位 | 真实密度中位 | 模拟月内std |
|---|---|---|---|---|---|
| 2021-01 | 2.00 | 4.55 | 0.73 | 3.05 | 0.34 |
| 2021-02 | 2.20 | 4.58 | 0.99 | 3.09 | 0.27 |
| 2021-03 | 2.50 | 4.92 | 1.10 | 3.24 | 0.27 |
| 2021-04 | 2.80 | 4.62 | 1.24 | 3.36 | 0.34 |
| 2021-05 | 3.20 | 5.26 | 1.80 | 4.00 | 0.38 |
| 2021-06 | 4.10 | 5.48 | 3.18 | 4.80 | 0.60 |
| 2021-07 | 4.50 | 5.41 | 3.18 | 4.84 | 0.65 |
| 2021-08 | 4.80 | 5.82 | 3.05 | 5.18 | 0.55 |
| 2021-09 | 4.50 | 5.52 | 2.94 | 5.31 | 0.49 |
| 2021-10 | 4.50 | 6.82 | 3.06 | 5.65 | 0.64 |
| 2021-11 | 4.80 | 7.23 | 3.18 | 6.00 | 0.72 |
| 2021-12 | 5.00 | 7.03 | 4.05 | 5.99 | 0.80 |

真实月内 std（官方 Q9_mean，全样本）约 5.5–7.5pp，见 POPULATION_WAVE_STATS 2b 节。

## 6. 审阅入口

- 全部 876 条提示词+原始回答：`outputs/local_runs/sce-local-openai-20261003T055121Z-1dc7cd15/llm_calls.jsonl`
- 提示词构造代码：`studies/sce_inflation_expectations/model.py`
- E 配置：`studies/sce_inflation_expectations/environment/environment_main2021.json`
- P 配置：`studies/sce_inflation_expectations/population/population_main2021_a73.json`