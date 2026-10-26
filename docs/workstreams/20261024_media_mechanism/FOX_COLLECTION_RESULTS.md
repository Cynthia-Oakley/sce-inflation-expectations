# Fox 官方 sitemap 采集结果（sce_fox_news_20261025_v1）

2026-10-25，Kimi。任务依据 `NEWS_MECHANISM_PLAN_V3.md` 第 3 节（Fox 官方
sitemap 完整枚举、NYT 相容关键词初筛、正式六字段标签、Wayback 核对）。五个缺失窗口
已在后续续跑中完成公开采集；早期“未完成”状态已被本节实际结果替代。

## 1. 状态总览（实际采集结果）

| 月份 | sitemap 扫描 | 原始抓取 | 候选 eligible | 旧启发式 keep/background | Wayback |
|---|---:|---:|---:|---:|---|
| 2019-05 | 114 页 | 216 篇 | 210 | 210 / 0 | 209 有快照，1 未核实 |
| 2020-09 | 89 页 | 219 篇 | 206 | 203 / 3 | 205 有快照，1 未核实 |
| 2021-09 | 72 页 | 219 篇 | 206 | 206 / 0 | 206 有快照 |
| 2021-12 | 68 页 | 401 篇 | 385 | 385 / 0 | 385 有快照 |
| 2023-12 | 36 页 | 126 篇 | 125 | 125 / 0 | 125 有快照 |
| 2021-06 | 既有小样＋英文原文补齐 | 26 篇（排除1篇SCE后） | 26 | 沿用人工标签 | 26 有快照 |
| 2022-06 | 既有小样＋英文原文补齐 | 21 篇（排除1篇SCE后） | 21 | 沿用人工标签 | 21 有快照 |

- NYPost 一律未导入、未抓取（robots 与计划决定）。
- 所有窗口定义与 NYT 一致（上月 1 日至当月 as_of，取自
  `outputs/sce_monthly_fine_full_assembly_20261023_v3/prompts/<month>/environment.json`）。
- 五个新窗口共 1,132 篇唯一候选，已形成 142 批六字段补标包；旧 `keep/background`
  只是关键词初筛，不能替代正式标签。Wayback 的“有快照”只表示找到 HTTP-200 存档，
  不等于已逐字比较当前文本，未核实项始终保留 `unverified`。
- 两个旧月份已补齐英文标题/导言，CJK 检查为 0；原始 HTML 与旧人工标签分别保存。

## 2. 漏斗（逐月，来自各月 candidates.json）

2019-05（窗口 2019-04-01..2019-05-10）：sitemap 窗口内条目 13,194 → slug 初筛 216
→ 抓取成功 216 / 失败 0 → 发布时间在窗 216 → SCE 报道排除 0 → 全文关键词无命中
6 → eligible 210（keep 210）。来源：Fox Business 169 / Fox News 41。

2020-09（窗口 2020-08-01..2020-09-11）：窗口内 10,635 → slug 219 → 抓取 219/0 →
在窗 219 → SCE 排除 0 → 无命中 13 → eligible 206（keep 203，background 3）。
来源：Fox Business 161 / Fox News 45。

每月完整漏斗存于 `outputs/sce_fox_news_20261025_v1/<month>/candidates.json` 的
`funnel` 字段；HTTP 原始记录（每次 GET 的 URL/状态/大小/错误）在
`<month>/raw/http_log.jsonl`；sitemap 与文章原始响应（gzip）在
`<month>/raw/sitemaps/`、`<month>/raw/articles/`；断点状态在 `<month>/state.json`。

## 3. 方法与已知限制

- 召回：sitemap 条目无标题/摘要，预筛打 URL slug（连字符转空格），与 NYT 共用
  `news_keyword_rules_v1_2.json` 强词表；抓取正文后用同一 RecallRules 跑标题+导言。
- **lastmod≠发布时间**：候选按 lastmod 落在窗口内召回，发布后又被修改的文章会漏
  （继承 2021-06/2022-06 小样方法）；抓取后以页面 JSON-LD 的 published_at 复核，
  不在窗者剔除（本次实际剔除 0 篇，说明 lastmod≈发布时间占绝对多数）。
- **关键词假阳性未二次剔除**：如 2020-09 一篇犯罪报道 slug 命中 `rent` 被判 keep。
  NYT 管线靠后续 LLM 标签层处理同类噪声；本批标签为确定性启发式
  （`label.label_method = heuristic_keyword_v1_pending_llm_verification`），
  主 Agent 统一补标/复核时应过滤此类条目。tone/persistence 本批一律未生成。
- **fb 尾页缺口**：foxbusiness sitemap 页内条目非严格按 lastmod 排序，第 18 页
  min=2019-02-19 但 max=2019-05-02（跨窗口）。旧停止条件导致 2019-05 一度漏掉该页
  106 个 slug 命中；已修复（改为“整页 newest lastmod 低于窗口起点才停”），并用
  缓存离线重建补齐 201905/202009。fb 第 19 页及以后（更老）从未抓取，其跨窗口
  逃逸条目仍会漏；修复后真跑会继续翻页直到整页低于窗口。
- scope/topics 为关键词映射启发式（us_unspecified 为默认），非 LLM 判断。

## 4. 文件清单

- `studies/sce_inflation_expectations/fox_news_archive.py` — 采集库（断点续跑、
  限速/超时/UA、原始响应记录、Wayback CDX 核对、既有月份 Fox-only 导入）。
- `scripts/prepare_sce_fox_news.py` — CLI：`collect [--month|--all]`、
  `wayback [--month|--all]`、`import-existing`、`report`。
- `tests/test_sce_fox_news_archive.py` — 20 个离线测试（fixtures 假网络），全绿。
- `outputs/sce_fox_news_20261025_v1/` — `<month>/{candidates.json,state.json,raw/}`、
  `existing_months/{202106,202206}.json`、`summary.json`、`collect.log`（约 104MB，
  主要是 gzip 原始响应，不入 git）。

## 5. 验证

- `python -m pytest tests/test_sce_fox_news_archive.py -q` → **20 passed**（采集前
  亲见因模块缺失失败，TDD 实现后转绿；断点续跑、SCE 排除、标签枚举、CDX 解析
  均有覆盖）。
- 201905/202009 的重建完全离线（OfflineFetcher 拒绝一切网络），候选集与
  state/raw 缓存一致（216/219 篇全部来自本地缓存，0 新增 GET）。
- 未改 `media_mechanism_trial.py`、`news_label_compat.py` 及任何公共配置/评分/宿主。

## 6. 后续执行记录

1. 五个缺失窗口已用 `collect --all` 完成；201905、202009、202109 的 Wayback
   分别有 209/210、205/206、206/206 篇找到快照。其余月份继续按同一命令核对。
2. 新候选的 1,132 篇六字段补标已获 $0.46 独立授权。前两批分别返回 ID 索引对象、
   `articles` 数组而非 `labels` 数组，保留原错误与费用，只对这两种结构做确定性
   归一化恢复，不重发这些批次；其他结构仍会停止。
3. Wayback 更新使候选文件哈希变化后，v2/v3 准备包改为以 `pending_public_articles`
   和请求字节验证正文不变，存档状态不再被误当正文变化；各版请求哈希必须一致。
4. 正式运行前仍需完成 Fox 标签质量复核、全部 Wayback 核对、最终冻结包和
   70-job 官方 Core 干跑；6,720 次模拟没有因补标获批而自动获得授权。
