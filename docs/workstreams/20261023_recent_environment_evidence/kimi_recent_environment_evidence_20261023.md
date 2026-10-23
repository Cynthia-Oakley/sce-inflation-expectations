# 近期环境证据补齐（Kimi，2026-10-23）

任务来源：`docs/workstreams/20261023_main_run/kimi_environment_tasks.md`（Codex 布置的 P0-a/P0-b/P0-c/P1 + 可并行附加项）。
全部离线完成：**new_api_calls=0，new_llm_calls=0**；未修改任何已有文件、旧账本或冻结输入。

## 一句话结论

近期 11 个月（2025-11..2026-09）的环境输入中，BLS 价格类与 EIA 汽油已全部达到「发布有据 + 版本已核」；
新闻文本、政策/信心文本、微观人口仍不满足严格 B（原因各异，见下）；
2025-11 月存在一个规则候选（停摆取消发布时沿原计划日取信息集）可让 SCE 锚升到 2025-10 值，**未冻结，待 Codex/用户决定**。

## P0-a：2025-11 新截止候选（as_of=2025-11-13）

- 背景：生产 as_of=2025-10-24 与实际 9 月 CPI 发布日耦合（停摆延迟）。规则候选「取消发布时仍沿原计划日期（11-13）取信息集」。
- 停摆取证：`sources/bls_lapse_2025.pdf`（FRASER 归档 BLS 官方修订表，sha256 `bbc6c4f9…`）确认：10 月 CPI（原计划 2025-11-13）**Canceled**；9 月就业报告改期 2025-11-20。
- 候选环境已按生产构建器同逻辑重建（`studies/sce_inflation_expectations/experiments/recent_environment_evidence.py`，硬守卫 published_at<as_of，通过官方 schema 校验）：
  - CPI 仍 2025-09 值（10-24 发布，**不捏造新值**）；就业仍 2025-08（9 月报告 11-20 才出，晚于候选截止）；
  - 汽油最新月升 2025-10；新闻窗口扩至 10 月全月+11 月 1-13 日（30 条中 19 条更换）；
  - **SCE 锚升为 2025-10 值（2025-11-07 发布，赶上候选截止）**；政策锚从 9-17 FOMC 升为 **2025-10-29 FOMC（降息 25bp）**；信心波次不变。
- 产出：`outputs/sce_recent_environment_evidence_20261023_v1/202511_candidate_asof20251113/` + `as_of_candidates.json` + `candidate_202511_summary.json`。
- **未覆盖旧 202511**；候选采纳与否不在本任务范围内。

## P0-b：汽油 13 条信号取证（subagent 执行，我已核验交付）

- 发布规律：观测周一 ≤2025-03-31 → 当周一下午 5 点 ET 发布；≥2025-04-07 → **周二上午 10 点 ET**（2025 年 4 月改制，EIA schedule 页 Wayback 快照 + FreightWaves 报道佐证）；周一联邦假日顺延。
- 143/143 实例：数值与缓存周度 CSV 算数平均一致；全部组成观测推断发布时刻早于 as_of（0 违规）；**FRED 免 key realtime vintage 逐周核验，首发与当前快照一致（无修订）**。
- 严格 B：143/143 合格，排除清单为空。应急条款：若 vintage 不可核则 143 实例全排除；备用指标 `bls_cpi_gasoline_yoy_nsa`（指数同比，**不得冒称美元/加仑同一变量**）。
- 仍属 inferred：单条发布精确时刻（EIA 不存档逐次时间）。
- 产出：`gasoline_evidence.jsonl`（143 行）+ `gasoline_summary.json` + `sources/` 下 13 份带哈希存档页。

## P0-c：新闻候选池逐篇资格检查（subagent 执行，我已核验交付）

- 11 个月候选池 5,611 篇：标签齐全（缺 0）；after_cutoff 0 篇（9 篇日粒度保守越界者精确时间戳均 ≤ as_of，UTC 跨日假象）；SCE 泄漏扫描 0 命中（含全窗口原始缓存扩扫）。
- **严格 B 池 11 个月全部为 0 篇**：所有文本 vintage 未核（缓存为 2026-10-07 抓取，无同期快照、无发布方修订时间字段）。远低于共同池 3 / 个人池 17 下限，已如实报不足。
- A 池（回顾用）逐月充足（如 202511：295 篇，共同 A1 18、个人 keep 110）。
- 产出：`news_pool_eligibility.jsonl`（5,611 行）+ `news_pool_summary.json`；审计脚本持久化于 `scripts/audit_sce_news_pool_eligibility.py`。

## 附加项：微观版本公开取证

产出：`outputs/sce_recent_environment_evidence_20261023_v1/micro_publication_evidence.jsonl`（5 条）+ `sources/micro_snapshot_20250702.xlsx`、`sources/micro_snapshot_20261007.bin`。

- **2025-07-02 Wayback 快照**（66,445,529 字节，sha256 `d9714028…e24e90`；原始响应头 last-modified 2025-06-05）：实测覆盖 **2020-01..2024-08**（67,798 行）——彼时公开微观文件滞后约 10 个月。
- **2026-10-07 Wayback 快照**（12,365,907 字节，sha256 `7da4bbcd…5f48`）：与本地 `data/raw/sce_micro_refresh_20261021/micro_latest.xlsx` **逐字节一致**，实测覆盖 **2025-01..2025-10**（10,559 行，滚动近期窗口）。
- **CDX 时间线**：2025-07-02 与 2026-10-07 之间无快照 → 当前版本（max 2025-10）的首次公开时点**不可证明**。
- 结论：严格 B 口径下，近期 11 个 as_of（2025-10-24..2026-09-11）可证明公开的微观数据**止于 2024-08**；202409..202510 微观在这些截止的可得性 = unknown。Codex 此前的提醒成立：字节一致只能证明 2026-10-07 前已公开，不能证明 2026-09-11 前可得。
- 对今晚 82 个真实微观月批次（≤2025-10）无影响。

## P1：11 个月 monthly_readiness 合并清单

- 脚本：`scripts/build_sce_monthly_readiness.py`；产出：`monthly_readiness.json` + `monthly_readiness.md`（逐月×逐项状态表）。
- 状态词汇：verified / inferred_publication / vintage_unverified / excluded / missing_permanent / unknown。
- 逐月结论一致：**严格 B 可用来源 = bls_prices + eia_gasoline**；食品（同 CPI 归档 PDF 抽取，生产保守标 False）、政策/信心（当前文本快照，生产标 False）、新闻（vintage 未核）、SCE 锚（按设计 excluded）、微观人口（unknown）均不满足严格 B。
- 停摆口径：2025-10 CPI 发布永久取消、2025-10 CPS 永久缺失，202512..202609 历史序列相应单元留缺，已在每月 `shutdown_permanent_missing` 标注；不补造。
- 信心波次：注册表最新为 gallup_2025_april。**已查证（gallup_2026_wave_check.md）：Gallup 于 2026-02-11 宣布停测 national leadership ratings，2026 年 4 月 EPF topline 中已无 Fed chair 信心题，该题 2025-04 后未在任何 Gallup 调查中复现——系列实质终结，不是"2026 波次还没出"**。缺口期唯一观测是 2025-12 Governance 的 Powell 任职支持率（3 桶题面不同，只能作独立 stopgap）。维持 gallup_2025_april 反而是真实信息集（真实居民在 2026 年也看不到更新的该题读数）；但 2026-05 主席换人（Powell→Warsh）后，旧读数指涉对象已不在任，2026-06 起需注明此解释性限制。

## 对今晚全量运行的影响

无。A 主候选执行包 `outputs/sce_monthly_fine_full_execution_20261023_v3/` 覆盖 82 个真实微观月（201901..202510），近期 11 个月不在今晚批次；本任务为后续批次的证据准备。

## 复算命令

```bash
PY=/Users/wushuyue/anaconda3/envs/socioverse/bin/python
cd /Users/wushuyue/Documents/科研/DISC/socioverse_challenge
$PY -m studies.sce_inflation_expectations.experiments.recent_environment_evidence   # P0-a，约 56s
$PY scripts/audit_sce_news_pool_eligibility.py                                        # P0-c
$PY scripts/build_sce_monthly_readiness.py                                            # P1
# P0-b 复跑：outputs/sce_recent_environment_evidence_20261023_v1/build_evidence.py（vintage 缓存 /tmp/gasregw_vintage_cache.json）
```

## 文件清单与哈希

完整清单（31 个输出文件，含 bytes/sha256、生成器与关键输入）：`outputs/sce_recent_environment_evidence_20261023_v1/manifest.json`。
本轮新增代码：`studies/sce_inflation_expectations/experiments/recent_environment_evidence.py`（P0-a）、`scripts/audit_sce_news_pool_eligibility.py`（P0-c）、`scripts/build_sce_monthly_readiness.py`（P1）。

## 补充任务：Gallup 2026 信心波次查证（subagent，2026-10-23）

报告：`docs/workstreams/20261023_recent_environment_evidence/gallup_2026_wave_check.md`；证据 PDF（4 份，含 sha256，官网版与 Wayback 存档逐字节一致）：`outputs/sce_recent_environment_evidence_20261023_v1/sources/gallup_*.pdf`。

## 待决策（不在本任务范围）

1. 2025-11 规则候选（沿原计划日取信息集）是否冻结采纳。
2. 食品类别行、政策/信心文本是否升入严格 B（当前生产保守标 False）。
3. 严格 B 线下新闻池为 0 的处置（补同期文本快照取证，或接受严格 B 无新闻）。
