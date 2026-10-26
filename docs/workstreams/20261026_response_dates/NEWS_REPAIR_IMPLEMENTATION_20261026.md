# 路线B新闻修复：2026年1月原文与9月基础标签

日期：2026-10-26。任务来源：[Kimi新闻补齐任务单](KIMI_NEWS_REPAIR_TASKS_20261026.md)。本批只使用 NYT 官方来源，不引入 Fox、NYP，不改变人口、先验、权重、全局截止日、新闻参数或旧运行。

## 1. 修复方式

- 旧文件 `data/raw/nyt_archive/2026-01.json` 和 `2026-09.json` 不覆盖、不改名、不移动。
- 两个月均重新请求官方 Archive 月档，原始响应和meta另存于 `data/raw/nyt_archive_repairs/20261026/official_archive_refresh/`。
- 一月刷新仍只有1—7日，因此用官方 Article Search 按日检索1月8—31日。每日独立翻页至源端`hits`所示结果取完，避免长区间分页上限；每页原始JSON、无密钥URL、HTTP状态、抓取时间、哈希和字节数落盘，可断点续抓。官方FAQ写明每分钟5次、每天500次并建议间隔12秒，本批从原13秒调整为12秒，不以并发绕过限制；依据存于 `docs/sources/nyt_api_rate_limits_20261026.json`。末页`docs:null`仅在`offset>=hits`时规范化为空列表，原始响应不改。
- 合并文件是由官方Archive与每日Article Search转换得到的新快照，不冒充未经转换的原始月档。保留原文字段，以来源ID＋标题/摘要/片段指纹去重；同一来源ID出现不同文本版本时阻断并交人工复核，不静默选择。
- 九月不另造原文overlay。其297篇是缺基础标签的经济候选，不是缺原文。
- 基础标签沿用冻结的 slim4：`article_id/decision/topics/scope`，模型为官方DeepSeek Flash；不生成理由、证据摘录、警示或持续性标签，不运行Simulation。

## 2. 最终验收结果

- 2026-01官方月档刷新：694篇，与旧档逐字节一致，仍仅覆盖1—7日。Article Search补抓1月8—31日共3,367条，去除2条重复后与原694篇合并为 **4,059篇**，31天均有文章；新快照SHA256为 `d62a4bd880eba32cfa52969da8c110ab81dc68c88d2519541d57e54c9f66b9eb`。旧档哈希未变。
- 2026-09官方月档刷新：4,367篇，与旧档逐字节一致，覆盖1—30日；无需新原文快照。
- 2026-09基础标签：297篇、38批全部成功，无失败批次；费用记录为 **$0.02676706**，硬上限$0.30。
- 补齐January后，跨January/February窗口去重得到340篇新增经济候选，不是把9月297篇重复计入。43批请求已返回，41批计费成功、2批仅因多余字段未通过格式校验；已从保存的回包做离线四字段投影，分类内容不变、未重发请求，16篇全部恢复，最终无未解决错误。January费用记录为 **$0.03170938**，硬上限$0.60。
- 两批合计 **637个新标签**，费用记录合计 **$0.05847644**，未知计费成功数为0。最终库存显示January、February、September缺标签均为0，原文覆盖阻断为0；manifest schema、绑定哈希及两个旧原档保护哈希全部通过。25项相关测试通过；验收环境的`jsonschema`补装为4.26.0。全程0 Simulation调用。
- 证据：`repair_manifest.json`、`source_reconciliation.json`、`label_receipt.json`、`acceptance.json`及`outputs/sce_recent_b_news_repair_inventory_final_20261026_v1/`。这只是来源与接口就绪验收，不代表11期个人环境已重建，也不代表付费B模拟已运行。

## 3. 文件范围

新源码：

- `studies/sce_inflation_expectations/experiments/recent_b_news_repair.py`
- `studies/sce_inflation_expectations/experiments/recent_b_news_repair_audit.py`
- `scripts/repair_sce_recent_b_news.py`
- `scripts/run_sce_recent_b_news_labels.py`
- `scripts/finalize_sce_recent_b_news_repair.py`
- `tests/test_sce_recent_b_news_repair.py`
- `tests/test_sce_recent_b_news_repair_audit.py`

新数据与交付：

- 原始修复证据：`data/raw/nyt_archive_repairs/20261026/`
- 统一overlay：`outputs/sce_recent_b_news_repair_20261026_v1/repair_manifest.json`
- 来源对账：`outputs/sce_recent_b_news_repair_20261026_v1/source_reconciliation.json`
- 标签与费用：`outputs/sce_recent_b_news_repair_20261026_v1/label_receipt.json`
- 最终离线验收：`outputs/sce_recent_b_news_repair_20261026_v1/acceptance.json`

## 4. 复算入口

```bash
PY='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'

"$PY" -m pytest \
  tests/test_sce_recent_b_news_repair.py \
  tests/test_sce_recent_b_news_repair_audit.py \
  tests/test_sce_recent_b_sampled_dates.py \
  tests/test_news_label_compat.py -q

"$PY" scripts/finalize_sce_recent_b_news_repair.py source-audit

"$PY" scripts/inventory_sce_recent_b_news_repairs.py \
  --repair-manifest outputs/sce_recent_b_news_repair_20261026_v1/repair_manifest.json \
  --out outputs/sce_recent_b_news_repair_inventory_final_20261026_v1

"$PY" scripts/finalize_sce_recent_b_news_repair.py accept \
  --inventory "$PWD/outputs/sce_recent_b_news_repair_inventory_final_20261026_v1"
```

最终交付须同时满足：一月31天均有文章；一月和二月输入窗口均可构造；三个目标窗口新增经济候选标签缺口为0；manifest路径及哈希正确；旧原档哈希不变。较晚抓取只能证明当前官方接口内容，不认证历史网页逐字版本。
