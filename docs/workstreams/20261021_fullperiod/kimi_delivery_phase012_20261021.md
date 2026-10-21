# 全时段数据交付：阶段0–2 完成记录（Kimi，2026-10-21）

对应交接约定 `kimi_data_contract_v2.md`。**状态：coverage + 三样例月已交付，待 Codex 对齐后再批量物化 93 个月。**

## 阶段 0：来源核查与补抓（免费，无付费调用）

1. **SCE 微观实际截止 = 2025-10**（实证，非推断）：重下 `frbny-sce-public-microdata-latest` 与 chart.xlsx 至 `data/raw/sce_micro_refresh_20261021/`（含 manifest）。micro_latest 与 2026-09-28 旧件 sha256 逐字节相同，实测行范围 202501–202510。chart.xlsx 已更新（新哈希），全国 headline 至 **2026-09**。→ 微观真值段 2019-01..2025-10；近期无微观段 2025-11..2026-09（11 个月，仅汇总级评价）。
2. **NYT 原始缓存补齐 2018-12..2019-11**（12 个月，`data/raw/nyt_archive/`，含 meta 与 sha256；现连续 2018-12..2026-09）。关键词选中事件 360 条存 `outputs/nyt_gap_events_2019_v1/events.json`。
3. **BLS 首发证据**：
   - **ref 2025-10 的 CPI 与就业报告被 BLS 因政府停摆永久取消，不可能补抓**（[BLS 停摆影响页](https://www.bls.gov/cpi/additional-resources/2025-federal-government-shutdown-impact-cpi.htm)；[Reuters 2025-11-21](https://www.reuters.com/world/us/us-cancels-release-cpi-report-october-because-government-shutdown-2025-11-21/)）。target 2025-11 的 as_of 回退至 ref 2025-09 CPI（2025-10-24 发布），已在 coverage 逐月标注。停摆期发布日历实测：ref 2025-09 CPI 延至 10-24、empsit 延至 11-20；ref 2025-11 两份延至 12-16/12-18。
   - 补齐 ref **2018-06..2018-12** 的 14 份首发 PDF（httpx+完整浏览器头+本机代理；裸 curl/缺头均 403）。
   - `scripts/backfill_bls_release_manifests.py` 为 22 个缺 manifest 的月份生成 manifest：sha256、USDL 号、published_at_et 均由 PDF 首页 embargo 行重验，全部与文件名日期一致。**例外**：cpi ref 2018-10 为自定义字体编码（字母 −3 偏移、数字字形丢失），仅月名可验，记 partial；release_id 缺失。
   - 旧文件 retrieved_at 不可知，manifest 记 null 并注明 LEGACY，未编造时间戳。

## 阶段 1：coverage.json（93 月，2019-01..2026-09）

`outputs/sce_fullperiod_data_20261021_v1/coverage.json` + `coverage_summary.md`，脚本 `scripts/build_sce_fullperiod_coverage.py`（内置 10 项验收全过）。状态汇总：**82 月 ready（有微观）、11 月 ready_no_micro、0 partial、environment_ready 93/93**。

实证结论（供 Codex 引用）：

- **tenure 编码**：同一 userid 跨连续月 tenure 恒 +1（106,351/106,351 对零例外），tenure==1 ⇔ 首次出现；首次出现但 tenure>1 者为 2017-01 前入组的左删失，不算新入组。
- **新闻窗口 = M-1 全月 + M 月 1 日至 as_of 日**（从历史试验 environment 实证，与 D050 一致）。
- **标签 id 口径**：labels.jsonl 的 article_id 来自 `coverage_preparation.build_news_pool` 流水线（与 build_nyt_events 的 event_id 不同）；coverage 用同一流水线复刻候选池。
- **新闻 LLM 标签总缺口 43,512 篇**（窗口选中但无标签），集中 2020 下半年与 2025 年（单月最多 2025-05=952）；0 缺口月恰为历次已标注试验月。**此差额待用户审批后再申请付费分类（建议 DeepSeek API），未执行。**

## 阶段 2：三个样例月全套交付

目录 `outputs/sce_fullperiod_data_20261021_v1/{201906,202303,202606}/`，每月 8 类文件（population.json / population_state_private.json / belief_state_private.json / sampling_private.json / environment.json / news_label_index.json / evaluation_truth/ + 根 sources.json、README.md）。脚本 `scripts/build_sce_fullperiod_sample_environments.py`、`scripts/build_sce_fullperiod_sample_data.py`；`tests/test_sce_fullperiod_data.py` **15 项全绿**。

| 样例月 | 角色 | 关键实测 |
|---|---|---|
| 2019-06 | 历史有微观 | personas=1330（entrant 161/returning 1075/gap_return 94）；评价真值加权中位 3.0298 = 官方 chart；环境 66 信号、CPI/失业率/食品 y/y 历史 11/11 |
| 2023-03 | 入组高峰 | personas=1254，entrant=172 与 coverage 一致；新闻池 524 篇标签缺口 0；真值 5.9134 = 官方 |
| 2026-06 | 近期无微观 | 1300 合成 personas（2025-10 波次按权重 PPS 整行抽样，联合结构保真，逐字段合成标记，`pit_risk_unverified`）；评价真值 aggregate_only；belief 全 simulated_previous 不预填 |

- 供体初始化：池严格早于目标月（2019-06 池 201701–201905 共 4,978 人；2023-03 池 11,796 人），Q8×Q9 十档联合整体保留，逐人种子与匹配层级登记，未用目标月中位数校准。
- 泄漏扫描：全部交付文件对 13 万 userid 零泄漏；匿名盐只在 private 文件。
- 全部环境信号通过 `published_at < as_of` 硬守卫；PopulationBundle/EnvironmentBundle 过官方 schema 校验。

## 已知缺口（批量物化前需处理）

1. **components_cpi.jsonl 只覆盖 2020-01..2021-11 与 2026-04..08**——批量阶段 2019 与 2021-12..2026-03 的 CPI 分项需从首发 PDF 补抽（driver 已有 table_a_pct 解析器与 handoff 护栏，可复用；不可抽的逐条 handoff 不猜值）。
2. EIA 汽油周度序列 2018-12 才起步 → 2019 年前几个月汽油历史/yoy 结构性省略（数据本身不存在）。
3. 微观文件 published_at 历史首发日未验证 → 近期段 B 线严格时点合规存疑（`pit_risk_unverified`），需 Codex 决定口径。
4. 新闻标签 43,512 篇缺口待付费审批。
5. 2026-06 环境的 ref 2025-10 BLS 全族缺口为数据从未采集（PDF 明文），非可得性问题。

## 复算入口（无密钥，约 6–8 分钟）

```
python scripts/build_sce_fullperiod_coverage.py
python scripts/build_sce_fullperiod_sample_environments.py
python scripts/build_sce_fullperiod_sample_data.py
pytest tests/test_sce_fullperiod_data.py -q
```

（NYT 补抓需 `.env` 的 NYT_ARCHIVE_API_KEY；BLS 补抓需本机代理。）
