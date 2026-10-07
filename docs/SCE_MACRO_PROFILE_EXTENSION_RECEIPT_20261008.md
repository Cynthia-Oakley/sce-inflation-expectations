# 就业与收入人口更新：数据补齐和滚动回测

日期：2026-10-08。**新增数据已落地，回测已完成；没有更新正式 P 或运行新 LLM。**

## 1. 这次解决什么问题

路线 B 在预测当月时，拿不到当月 SCE 人口画像。本次检验能否利用较及时公布的宏观就业、工资和收入变化，将旧 SCE 画像的就业/收入比例更新得更准确。预测对象是**调查人群的比例**，不是每个人的真实收入，也不是通胀预期答案。

结果没有支持直接升级：新增就业变量没有稳定超过已有失业率模型，收入模型总体没有超过旧画像。经济直觉可以支持候选机制，但仍需用数据决定是否采用。

## 2. 实际补齐了什么

- BLS 就业首发发布稿 **91 份**，观测期 2019-01..2026-08（2025-10 CPS 缺月保持缺失）：就业人口比、劳动参与率、失业率、私人非农平均时薪/周薪。
- BEA 收入发布稿 **92 份**，参考月份 2018-01..2025-09：名义个人总收入、工资与薪金总额。每份表 1 的两行、八个月金额，**共 1,472 个单元格与官方 Excel 全部一致**。
- 总计 **2,473 条带日期的观测版本**：BLS 1,001 条（含发布稿里的旧工资列），BEA 1,472 条。每条保留观测期、实际发布时间、发布版本、页码/列、原文、URL、文件哈希。
- 2018-12 没有单独对应的标准页面，保留 404 审计；其数值由 2019-01 的合并发布稿历史列恢复，采用实际 2019-03-01 发布时间。2019-02 同样采用官方合并发布，2022-08采用含年度更新的页面。

就业资料复用原来下载的 PDF；收入 PDF/Excel 与文本缓存集中追加到 `data/raw/sce_macro_population/`。BLS HTML 批量下载遇到 403，**没有称已完成独立网页逐项核验**：91 份详细表与摘要表/正文对账通过，已有独立核过的失业率一致，就业人口比与参与率/失业率恒等关系在舍入容差内通过。2023-04 PDF 缺摘要 A，用正文的两个明示数值交叉核对。

Excel 对账确实发现并修复了一处机械转录风险：2018-06 PDF 的 `17, 434.8` 带逗号后空格，旧提取会误读成 `434.8`；现在规范化千位分隔符后与 Excel 对上。发布时间也按原文读取：部分 BEA 发布为 **10:00**，没有一律假定 8:30。

主要官方依据：[BLS 就业报告](https://www.bls.gov/news.release/archives/empsit_05072021.htm)、[BEA 收入报告](https://www.bea.gov/news/2021/personal-income-and-outlays-april-2021)、[2019 合并发布](https://www.bea.gov/news/2019/personal-income-and-outlays-december-2018-personal-income-january-2019)、[2022 年度更新发布](https://www.bea.gov/news/2022/personal-income-and-outlays-august-2022-and-annual-update)。

## 3. 怎么比较

固定小模型后运行，没有根据本次结果搜索参数：

1. 所有方法共同评价 **2022-10..2025-10，37 个月**；构造特征使用 2020-01..2025-10 的 70 个月。
2. 每个预测月按纽约时间上月末截止选宏观资料；人口和可训练标签仍采用 `t−10` 的保守可得性假设。至少有 24 个已可用月才训练，逐月更新，标准化也仅用训练资料。
3. 对照：最新旧画像、过去 12 个旧月份平均、不加宏观的历史变化。就业候选：失业率变化、就业人口比变化、就业人口比＋参与率。三项 CPS 比率不作为三份独立信息堆入回归。
4. 收入候选：周薪、时薪、周薪＋个人收入、BEA 工资薪金＋个人收入。采用过去 12 个月窗口相对旧画像窗口的名义变化。BEA 季调年率除以 12 后累加 12 月，得到年内总量；工资则取年内均值。宏观总量不直接填成家庭收入档。
5. 收入有答案的三个档条件比例分别建模；缺失比例沿用旧画像，单独评分。原始样本比例和官方加权比例都做相同回测。
6. 回归在比例的对数比上拟合，转换回合法分布；双变量用固定 Ridge 惩罚 1，单变量最小二乘。没有以测试结果选惩罚或挑年份。

就业采用**首发方案**以便与上次回测直接对比；收入选截止前最新的**已归档版本**。归档旧列并不覆盖完整年度修订史，所以这仍不是完整历史 vintage 回测。SCE 微观资料的历史上线日也尚无逐期证据。已有评价期曾被检查过，本次是探索性滚动检验，不能称新盲测。

## 4. 看到了什么效果

**就业（官方加权比例，MAE，百分点）：**

- 就业占比：旧画像 **1.466** → 原有失业率更新 **1.323**；新增就业人口比 **1.349**，就业人口比＋参与率 **1.359**。
- 失业标签占比：旧画像 **0.786**；三种宏观更新分别 **0.816 / 0.876 / 0.872**，均没有改善。
- 原始样本就业占比：旧画像 **2.051**；上述宏观模型 **2.061 / 2.060 / 2.174**，没有改善。

因此新增变量有经济解释价值，但没有提供稳定的额外预测收益。原有失业率方法也只是就业一项的候选，不能因为这一项更好就替换整个 P。

**收入（官方加权比例，MAE，百分点）：**

- 低收入档：旧画像 **1.169**；周薪更新 **1.843**；周薪＋个人收入 **1.560**。
- 中收入档：旧画像 **1.593**；周薪更新 **2.042**；周薪＋个人收入 **1.660**。
- 高收入档：旧画像 **0.794**；周薪更新 **0.751**，有局部改善，但其他档变差；周薪＋个人收入 **1.244**。
- 整体分布距离（TVD，越小越好）：旧画像 **0.0190**；四个收入候选依次 **0.0244 / 0.0271 / 0.0235 / 0.0262**。
- 原始样本收入整体距离：旧画像 **0.0359**，过去一年平均 **0.0336**；宏观模型 **0.0375..0.0386**，也未改善。

逐年和滚动 12 月结果完整保存。局部年份收入更新有收益，但不能掩盖总体和其他年份的恶化；2022 年仅含 10–12 月，不把三个月称完整年检验。这里的误差全部是**人口比例误差**，不是 SCE 通胀预期误差。

## 5. 下一步怎么推进

1. **保留新增指标，不直接启用新人口回归。** 它们仍可作为 E 和同信息基线的候选公共信息；未改正式 E/运行配置。
2. 优先检查 SCE 轮换、官方权重及年龄/退休构成对就业和收入变化的贡献。全国平均工资不能直接代表调查家庭全年收入，宏观相关性也无法替代联合结构。
3. 新候选应先预测旧联合画像的合理权重变化，约束年龄/教育/地区，保持就业×收入关联；不要独立随机改每个家庭的就业或收入。具体模型另登记，不能在这 37 月反复调参后当作独立验证。
4. 通过人口分布验证后，再做固定 E/B 的旧 P vs 更新 P 行为对照，判断是否真的改善通胀预期。更早模型试验仍按此前明确的数据发送/预算确认要求推进。

历史宏观 2017–2018 就业前置资料、完整年度修订和 BEA 2026 新发布形式的金额版本尚待补齐；未假装它们已可用于完整前瞻预测。

## 6. 路径与复算

项目根：`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/`。

- 原件与文本缓存：`data/raw/sce_macro_population/`（就业原 PDF 继续保留在 `data/raw/bls_initial_releases/`）。
- **最终来源包**：`outputs/sce_macro_profile_sources_20261008_v7/`：`observations.jsonl`、`audit.json`、`summary.json`。v1–v6 是解析/下载修复过程，不用来引用最终结果。
- **最终回测包**：`outputs/sce_macro_profile_backtest_20261008_v1/`：`plan.json`、总 `summary.json`，四个 employment/income × weighted/raw 子目录各含特征、逐月预测、来源时点、训练审计、摘要和缺月清单。
- 小型可版本保存摘要：[sources/sce_macro_profile_extension_20261008.json](sources/sce_macro_profile_extension_20261008.json)。
- 唯一源码：`studies/sce_inflation_expectations/macro_profile_sources.py`、`macro_profile_extension.py`；入口在 `scripts/prepare_sce_macro_profile_sources.py`、`backtest_sce_macro_profile_extension.py`。

```sh
conda run -n socioverse python scripts/prepare_sce_macro_profile_sources.py \
  --macro-pool outputs/sce_e_B_through_2026_10_draft_v2_20261007/source_observations.jsonl \
  --out outputs/sce_macro_profile_sources_REPLAY \
  --pdf-only-bls --bea-end 202509 --verify-bea-xlsx
conda run -n socioverse python scripts/backtest_sce_macro_profile_extension.py \
  --population-stats outputs/sce_b_readiness_population_v5_20261007/monthly_profile_stats.json \
  --macro-observations outputs/sce_macro_profile_sources_REPLAY/observations.jsonl \
  --out outputs/sce_macro_profile_backtest_REPLAY --include-bea
conda run -n socioverse python -m pytest -q \
  tests/test_macro_profile_extension.py tests/test_sce_macro_population.py
```

输出目录须不存在。重放使用本地原件缓存，无 `--fetch` 就不联网；2018-12 的缺标准页面仍会留审计，其值已经由合并发布的旧列覆盖。

验收：**10 项测试通过**；962 份分布预测均合法，时点/训练标签门通过，原有四套加权就业对照的结果误差 <1e−12；15 个 Kimi/用户未审文件哈希保持不变。新增 LLM、付费 MCP 调用均为 **0**。研究决策另记本文，未改待审的 `DECISIONS.md`。
