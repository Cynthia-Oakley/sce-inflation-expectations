# E（信息环境）构建报告：主窗口 2021-12 步 + 前瞻段 2026-05 步

- 任务编号：T02 收尾（E authoring）；执笔：实现代理（Kimi），核查日 2026-10-03
- 交付：`scripts/build_sce_environment.py`、两套 environment/simulation 配置、34 份归档首发稿、单元测试
- 性质：历史回顾性条件模拟的 E 输入，全部信号为 BLS 归档**首发稿**值（historical official release evidence），非 FRED、非当期 SCE 结果

## 1. 取数通道（核实结论）

| 通道 | 结果 |
| --- | --- |
| 本机直连 bls.gov（curl/无代理） | HTTP 403（Akamai），全部 UA 均被拒 |
| 代理 `http://127.0.0.1:7890` + curl（多 UA） | 仍 403 |
| 代理 + Python httpx 0.28.1 + 完整浏览器头（`sec-ch-ua`、`Sec-Fetch-*`、`Accept-Encoding: br` 等） | **HTTP 200，真实 PDF**（`application/pdf`，约 290KB/份） |

脚本内固化该通道（`BROWSER_HEADERS` + `--proxy`，默认 `http://127.0.0.1:7890`），请求间隔 1.5s、单 URL 最多 3 次重试。注意：Akamai 校验依赖完整浏览器头集合，仅换 User-Agent 不够。

## 2. 发布日期核实依据（未靠猜）

对每个参考期，脚本先按惯例生成候选日（CPI=次月 13 日前后、就业=次月首个周五），再从归档 URL 取稿并用**稿内自证**核验：

1. 首页首行 "Transmission of material in this release is embargoed until 8:30 a.m. (ET) **<Month D, YYYY**>" 必须与归档 URL 日期一致（`published_at = 该日 08:30 美东`）；
2. 参考期（如 "CONSUMER PRICE INDEX – NOVEMBER 2020"）必须在首页出现；
3. 候选日 404 时在同窗口内按距离扫描（CPI：次月 8–20 日；就业：次月 1–12 日工作日），直至自证通过。扫描确实命中了日程偏移（如 2026-04 参考期 CPI 实际 5/12 发布，早于惯常 13 日）。

2026 年参考期的发布日另与 BLS 官方发布日程页交叉一致（[cpi schedule](https://www.bls.gov/schedule/news_release/cpi.htm)：2026-04→5/12、2026-05→6/10、2026-06→7/14、2026-07→8/12、2026-08→9/11；[empsit schedule](https://www.bls.gov/schedule/news_release/empsit.htm)：2026-04→5/8、2026-05→6/5、2026-06→7/2、2026-07→8/7、2026-08→9/4）。所有发布均早于对应 as_of，无"尚未发布"缺口。

## 3. 转录值与原文对照（每月抽查 1+ 值；完整 68 条见各 manifest）

转录自 PDF 首页文本（pypdf 抽取；引文为去空白小写形式，数字与标点未动）：

| 参考期 | 值 | 原文句子（节录） |
| --- | --- | --- |
| 2020-11 | yoy 1.2 / mom 0.2 / u 6.7 / nfr +245k | "...the all items index increased 1.2 percent before seasonal adjustment"；"...rose by 245,000 in november, and the unemployment rate edged down to 6.7 percent" |
| 2020-12 | yoy 1.4 / mom 0.4 / u 6.7 / nfr **−140k** | "...total nonfarm payroll employment declined by 140,000 in december, and the unemployment rate was unchanged at 6.7 percent" |
| 2021-01 | 1.4 / 0.3 / 6.3 / +49k | "The unemployment rate fell by 0.4 percentage point to 6.3 percent in january, while nonfarm payroll employment changed little (+49,000)" |
| 2021-02 | 1.7 / 0.4 / 6.2 / +379k | "...the unemployment rate was little changed at 6.2 percent" |
| 2021-03 | 2.6 / 0.6 / 6.0 / +916k | "...rose by 916,000 in march, and the unemployment rate edged down to 6.0 percent" |
| 2021-04 | 4.2 / 0.8 / 6.1 / +266k | "...increased 0.8 percent in april on a seasonally adjusted basis"（与开发窗 environment.json 逐字段一致） |
| 2021-05 | 5.0 / 0.6 / 5.8 / +559k | "...the unemployment rate declined by 0.3 percentage point to 5.8 percent" |
| 2021-06 | 5.4 / 0.9 / 5.9 / +850k | "...increased 0.9 percent in june on a seasonally adjusted basis"（与开发窗一致） |
| 2021-07 | 5.4 / 0.5 / 5.4 / +943k | "...rose by 943,000 in july, and the unemployment rate declined by 0.5 percentage point to 5.4 percent" |
| 2021-08 | 5.3 / 0.3 / 5.2 / +235k | "...increased 0.3 percent in august on a seasonally adjusted basis" |
| 2021-09 | 5.4 / 0.4 / 4.8 / +194k | "...the unemployment rate fell by 0.4 percentage point to 4.8 percent" |
| 2021-10 | 6.2 / 0.9 / 4.6 / +531k | "...rose by 531,000 in october, and the unemployment rate edged down by 0.2 percentage point to 4.6 percent" |
| 2026-04 | 3.8 / 0.6 / 4.3 / +115k | "...increased 0.6 percent on a seasonally adjusted basis in april"（2026 新语序，已兼容） |
| 2026-05 | 4.2 / 0.5 / 4.3 / +172k | "...total nonfarm payroll employment increased by 172,000 in may, and the unemployment rate was unchanged at 4.3 percent" |
| 2026-06 | 3.5 / **−0.4** / 4.2 / +57k | "Both total nonfarm payroll employment (+57,000) and the unemployment rate (4.2 percent) changed little in june" |
| 2026-07 | 3.4 / 0.1 / 4.1 / **−23k** | "Both nonfarm payroll employment (-23,000) and the unemployment rate (4.1 percent) changed little in july" |
| 2026-08 | 3.4 / 0.4 / 4.1 / +162k | "...increased by 162,000 in august, and the unemployment rate was unchanged at 4.1 percent" |

首发值与后续修订值不同属预期（如 2021-07 非农首发 +943k 后修订为 +1,091k；2021-06 非农首发 +850k 后修订为 +938k）——本项目协议要求**首发稿口径**，与开发窗一致。

## 4. as_of / 时区 / published_at 核验

- as_of = 目标月 t−1 月末 23:59:59 America/New_York，经 `zoneinfo` 按 DST 生成：主窗 step0（2021-01）`2020-12-31T23:59:59-05:00`（EST），step5（2021-06）`2021-05-31T23:59:59-04:00`（EDT）；前瞻段 5 步全为 −04:00。
- published_at = 发布日 08:30（美东，带当日正确偏移，如 2020-12-10 为 −05:00、2021-04-13 为 −04:00）；逐信号断言 `published_at < as_of` 通过（测试覆盖）。
- 参考期 = M−2 全量通过（12/12、5/5）。

## 5. 校验与测试结果

- 两套 bundle 与 simulation 均通过官方 schema：`sys.path` 插入 `socioverse2_repo` 后 `EnvironmentBundle.model_validate` / `SimulationConfig.model_validate` 通过（脚本内建，`--no-validate` 可关）。
- `python -m unittest discover -s tests`：**54/54 OK**（本任务新增 12 个用例：日历/时区、步数、每步 4 信号字段齐全、as_of 与 published_at 顺序、M−2、与开发窗 6 条旧信号逐字段一致、runtime 注入键缺席；raw 缺失时 skip）。
- 转录健壮性：构建中实际命中并兼容了 6 种稿面变体（2026 CPI 语序、was little changed、changed little (+N,000)、edged up/down、Both ... changed little 合并句、USDL 与 8:30 数字粘连）。

## 6. 缺口与边界

- 无取数缺口：17 个参考期 × 2 稿 = 34 份 PDF 全部取回并归档（`data/raw/bls_initial_releases/<ref>/`，18MB，含逐文件 URL/SHA-256/字节数/USDL/发布日核验说明/4 条转录引文）。
- 非农信号为主窗口新增（开发窗仅 3 条），字段结构与旧信号一致；开发窗 `environment.json`/`simulation.json` 未改动（测试守门：重叠月份 6 条旧信号 value/source_version/published_at 与构建结果一致）。
- 归档的 `retrieved_at` 记为构建运行时刻；PDF 内容哈希与首发值不随后续修订变化。
- 未运行任何 LLM；未 git commit。

## 7. 附：纽约联储 SCE 结果公布日规律（顺带核实，供封存段死线推断）

- 已核实（多源一致）：SCE 月度结果在**次月中旬的周一 11:00 a.m. ET** 左右公布。例：2021-04 期结果 2021-05-10（周一）公布（[NY Fed SCE 页面转载](https://softpanica.org/Skeptics/Corporate_skeptics/inflation.shtml)引官方稿）；2026 年 8 月参考期结果现已在 [NY Fed SCE 主页](https://www.newyorkfed.org/microeconomics/sce#/calendar)发布；SCE 信用模块 2026-07-20（周一）11:00 公布（[市场日历](https://x.com/marketsday/status/2078349043076346015)）。
- **待核**：逐月精确公布日以 NY Fed 官网每次的 release calendar 为准（无固定"第几个周一"的公开承诺）；若封存段需要精确到日，建议在临近月查 newyorkfed.org 发布日历，不据本规律直接排死线。

## 8. 文件清单

新增/生成（未 commit）：

- `scripts/build_sce_environment.py` — E 物化脚本（`--targets 2021-01..2021-12 --fetch --out-prefix environment/environment_main2021`）
- `studies/sce_inflation_expectations/environment/environment_main2021.json`（12 步 bundle）
- `studies/sce_inflation_expectations/environment/external_events_environment_main2021.json`
- `studies/sce_inflation_expectations/environment/environment_forward2026.json`（5 步 bundle）
- `studies/sce_inflation_expectations/environment/external_events_environment_forward2026.json`
- `studies/sce_inflation_expectations/simulation/simulation_main2021.json`（n_steps=12，memory_window=12，seed 42，scripted，duckdb）
- `studies/sce_inflation_expectations/simulation/simulation_forward2026.json`（n_steps=5，余同）
- `tests/test_build_sce_environment.py`（12 用例）
- `data/raw/bls_initial_releases/<ref>/{cpi,empsit}_*.pdf + manifest.json`（17 参考期，gitignored）

bundle 关键结构：`provider_args` 含 `targets`（按 conceptual step 索引的 `{target_month, as_of}` 列表，新机制）、`signals_by_step`（键 "0".."11"/"0".."4"，每步 4 信号）、`evidence_class: "historical_official_release_evidence"`、`excluded_sources: [fred, nyfed_sce, nyt_archive]`；不含 persona_by_id/audit_dir/run_id（运行时注入）。layers 3 条与 broadcast 12/5 条沿用开发窗结构（channel `official_bls_release`，ttl=1，audience=all）。
