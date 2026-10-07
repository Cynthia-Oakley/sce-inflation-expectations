# E 扩到最新 SCE 节点：资料与路线 B 输入草案

核查日：2026-10-07；本次完成 E 资料扩充，不运行新的 LLM，不修改正式 study/simulation、P 或计分器。

## 1. “最新”分别指什么

本次重新下载[纽约联储全国指标工作簿](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-data.xlsx)，最后一个有值的调查月是 **2026-08**。官方 [SCE 首页](https://www.newyorkfed.org/microeconomics/sce) 也显示 8 月调查；[2026-09-08 发布稿](https://www.newyorkfed.org/newsevents/news/research/2026/20260908) 对应的是 **8 月**，并不是 9 月调查。核查时点尚未核实 9 月结果，不能提前当作可评价真值。

旧微观快照仍到 2025-10，本次没有重下载或更新人口。**2026 年可以进行全国指标预测评价，但不能据此说已有 2026 年逐人真实回答。** 后续人口采用过去已公开的人口信息建模，不能等待当期微观答案再倒填预测人口。

重新下载的全国指标和汽油快照在 `data/raw/sce_environment_latest_20261007/`，都有哈希记录。全国指标只用于核查覆盖月，不进入 E 输入。

## 2. 实际补到了哪里

BLS 发布稿资料池现覆盖 2019-01 至 2026-08 的可用参考月；2025-10 官方缺失单独标记。合并核验 **182 份 PDF**，包括 **455 个 CPI 分项值和 181 个总体 CPI 同比/环比值**，共 **636 条独立官方 HTML 对账一致**。就业数值保留发布稿引文和哈希，不把这些就业值称为全部经第二来源数值核对。

NYT 原始档案连续缓存已补至 **2026-09**。汽油旧侧车实际已到 2026-09-28，重新下载的 91 个重叠周观测逐条相同，因此复用原侧车而不覆盖它。当前快照与真实历史版本仍不是同一个概念。

之前的 69 月 A 候选与实验不覆盖。新的资料池足以支持后续延展至最新节点的 A 环境构建；本次首先交付用于 **B 上月末信息截止** 的独立草案，不能把它接到旧 A 配置后当作同一时点版本。

## 3. 路线 B 输入如何落地

当前唯一最新草案目录：

`outputs/sce_e_B_through_2026_10_draft_v2_20261007/`

目标 2025-10 至 2026-10，共 13 个月。2026-09、10 的 E 输入可以准备，但在本次核查中尚无已验证公布的 SCE 真值，暂不计算效果。窗口只是材料准备范围，未冻结正式测试期或费用。

- `environment_B_full_draft.json`：发布稿＋汽油＋新闻；每月 77 数值、30 新闻。所有内容按纽约时间上月末过滤，汽油和新闻版本不确定性保留，不能称严格历史实时输入。
- `environment_B_bls_only_draft.json`：每月 64 条带初发证据的 BLS 数值；排除未核验历史版本的汽油和新闻。它为可核验来源的对照提供输入，不保证排除 LLM 训练知识中的未来记忆。
- `availability_audit.json`：每月截止、每个指标真正可见的最新参考月及实际历史月份。
- `structural_missing.json`：停摆造成的缺失及口径说明。
- `source_observations.jsonl`：带原始发布日期、参考月、来源、哈希和引文的资料池。
- `independent_value_checks.json`、`bls_manifest.json`、`manifest.sha256`：独立对账和文件验收。

各指标按实际发布日期独立选择，不再假定 CPI、失业率和汽油的最新参考月必然相同。历史序列采用最后 12 个实际已公布观测，保留各观测月份；这与固定连续 12 个日历月不同，跳过缺失月时不伪造数据。过期值仍带其原参考月，不将它重标为当月数据。

例如预测 2025-11（截止 2025-10-31），CPI 可见到 9 月，而失业率只能见到 8 月。预测 2026-10（截止 2026-09-30），CPI 与失业率可见到 8 月。

## 4. 停摆期间的特殊口径

[2025-11 CPI 发布稿](https://www.bls.gov/news.release/archives/cpi_12182025.htm) 明确：10 月未采集常规调查价格，开头的 0.2% 是 **9 月至 11 月两个月累计季调变化**，不能作为 11 月单月环比。本次修复了通用开头句式可能误读这一数值的问题，单月字段为空，两个月值仅进审计。

因此预测 2026-01 时，最新 CPI 同比为 2025-11，而最新可用单月环比仍是 2025-09，二者不能共用一个月份标签。[就业发布稿](https://www.bls.gov/news.release/archives/empsit_12162025.htm) 的 11 月失业率句式也已兼容。该稿还补刊 10 月企业就业数据；本次仅取每份报告的标准目标月主要值，补刊的 10 月新增岗位尚未独立录入。这是资料范围限制，不声称穷尽报告中所有可得信息。

先前失败/旧解析来源批次 `outputs/sce_e_latest_sources_20261007/` 保留；本次采用的来源验收为 `outputs/sce_e_latest_sources_retry_20261007/`。其两个日历缺失提示是官方缺月，不是尚未下载的普通文件。早期 draft 输出保留但由本节 v2 包取代。

## 5. 同信息基线已经有输入，但尚未训练

完整匹配输入：`outputs/sce_shared_e_B_full_through_2026_10_v2_20261007/shared_environment.jsonl`。

BLS-only 匹配输入：`outputs/sce_shared_e_B_bls_through_2026_10_v2_20261007/shared_environment.jsonl`。

分别对应同名 Agent 环境，不能拿完整 Agent 输入与 BLS-only 回归比较后把优势全归于 Agent。导出正确标为 B 草案，未添加 SCE 答案。

因停摆和发布时差，按“参考月滞后几个月”编码的列并非每个月都齐。BLS-only 每月确有 64 条数值，列并集为 79；额外空列反映不同月份和陈旧程度，而不是 15 个下载失败。后续回归应在训练期资料内确定对齐、缺失标记和处理规则，也可采用观测次序＋指标年龄；不能把这些空位一律填零或用测试期资料拟合。

## 6. 验证、下一步与复算

57 项相关测试通过；官方两份 `EnvironmentBundle` schema 均通过，逐条时间检查和输入哈希复核通过。真实 LLM、付费 MCP 均为 0；NYT 使用现有账号获取档案，没有独立核实账号账单。

接下来：

1. 以新资料池构建更新后的 A 历史重建包，并独立固定 A/B 的正式研究窗口。当前旧 A 69 月文件不扩写、不偷偷改变其截止。
2. 在真正运行前改进提示的日期展示：旧模板曾共用 CPI 月份来标失业率，且称历史为连续 12 个月；新输入必须分别显示各指标月份与缺口。另做实际提示预览、人口可得性及白名单验收。
3. 选择完整/只含 BLS 的对照，冻结人口、模型、训练/评价时期和预算，再开展覆盖 2026 年的模拟和匹配基线。
4. 后续每次手动更新重新核实 SCE 工作簿和发布稿，另建输出版本；没有设自动监控或自动付费运行。

离线复算（项目根，`socioverse` Conda 环境；输出必须是新目录）：

```sh
python scripts/build_sce_available_environment.py \
  --source-dir outputs/sce_e_extension_2020_2025_verified_20261007 \
  --source-dir outputs/sce_e_latest_sources_retry_20261007 \
  --template outputs/sce_e_extension_2020_2025_verified_20261007/environment_candidate.json \
  --gas-weekly-csv data/raw/eia_gasoline_support/20261007T085903Z/gasoline_retail_regular_consolidated.csv \
  --targets 2025-10..2026-10 --latest-observed-sce 2026-08 \
  --out outputs/sce_e_B_latest_new_check
```

代码与小型回执可进私有 Git；原始新闻/PDF/快照和自动产物仅留本地。回执：`docs/sources/sce_environment_latest_2026_20261007.json`。
