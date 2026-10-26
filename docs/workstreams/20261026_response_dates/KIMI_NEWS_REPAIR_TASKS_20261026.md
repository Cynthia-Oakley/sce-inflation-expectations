# 给Kimi：B线1月原文修复、9月基础标签与完整性对账

2026-10-26。用户会转交本任务；Codex不直接发送消息。Kimi负责公共新闻数据/标签及来源证据，Codex负责B日期抽样、个人环境组装、运行和评价。请不要改共享决策、人口/先验/权重、B截止日、新闻参数、模型和旧运行目录。

用户已经确认：B用**前一年同月（前12个月）**的经验作答日期，不是前24个月。保留原每月全局D，个人环境截止为min(合成作答日前一天,D)。新闻窗口仍为“上月1日—个人截止”。因此2026-01原文缺口会同时影响2026-01及2026-02两期B输入。

## P0：重新核实并补齐2026-01的NYT原始新闻

当前文件`data/raw/nyt_archive/2026-01.json`只有694篇，pub_date仅为1/1—1/7；其meta记载2026-10-07抓取，SHA256为：

`788ab41712e164d6c7cbf0a425a2a899730614e98eb29bd2d62c9d5cd8f58266`

原1/13截止缺1/8—13；2月输入还需要完整January，所以请补至1/31，而非仅补到13日。

1. 重新核实官方月档`https://api.nytimes.com/svc/archive/v1/2026/1.json`。不要因本地文件已存在而直接跳过；现有抓取器可能会复用缓存。
2. 若重新获取仍只到7日，检查接口/缓存/分页/截断；必要时用NYT官方按日期检索来源补查1/8—31。保留每份原始响应及合并过程，不能把其他月份或其他媒体补成NYT。
3. 保存到**新目录**，例如`data/raw/nyt_archive_repairs/20261026/2026-01.json`。消费者需要`response.docs`列表格式；若由多份官方响应合并，保留原分页文件与转换证据，不把合并文件称未经转换的原始月档。
4. 保留headline.main、abstract、snippet、pub_date、_id/uri/web_url、document_type、section_name、news_desk、print_section、print_page等。A1路由依赖版面字段；缺失应保持未知，不虚构头版。
5. 按来源标识＋文本指纹去重，检查每日条数、首末日期、总数与源端数量。`meta.hits == 本地N`本身不能证明整月完整。记录source_url（不含密钥）、fetched_at、HTTP/源端线索、SHA256、字节数与缺口。
6. 用原基础主题分类提示，仅为新增或文本版本改变的经济候选补标签。完全相同article_id/文本指纹的旧标签复用；不重标全部新闻，不修改已成功旧标签。

旧`data/raw/nyt_archive/2026-01.json`及meta必须保留，**不能覆盖、改名或移动**，否则旧B及冻结输入的来源哈希会失效。新模拟从明确overlay读取新版本。

## P1：2026-09原文完整性核验＋297个基础标签

目前`data/raw/nyt_archive/2026-09.json`有4,367篇，日期覆盖9/1—9/30，30天均有记录，SHA256：

`4576d2696b9f8e6254f87beeed400e9041c4aa0f028c51fad2baaa3fef5e472e`

**未发现像January那样的日期断档；297指缺基础分类标签的候选，不是缺297篇原文。**

1. 与官方9月月档的数量、独立来源ID和每日分布再做一次对账。若相同，交审计收据即可；若发现缺文/文本版本差异，同样另存新快照，不覆盖旧文件。
2. 297个去重待分类候选已经导出：

`outputs/sce_recent_b_news_repair_handoff_20261026_v2/pending_public_news_202609.jsonl`

其中全是公开标题、摘要、片段和文章标识等，不含人口或问卷。沿用现有基础decision/topics/scope口径与旧标签JSONL格式；保持24字符article_id原样。个人警示倍数仍为1，**不要求额外重跑警示/持续性标签**。
3. 这些候选在9/11原全局截止之后。保留当前D的本次9月输入不使用它们，但用户要求补齐，供全月时间版或后续复用。优先级低于January。

## 交付接口：新快照＋增量标签＋一个repair_manifest

建议目录：`outputs/sce_recent_b_news_repair_20261026_v1/`。交付：

- `repair_manifest.json`，schema必须为`sce_B_news_repair_overlay/v1`；准确结构见本目录`news_repair_manifest.schema.json`。
- `archive_overrides`：以`2026-01`等月份为键，列项目相对`path`、实际`sha256`；可附meta_path/meta_sha256。未改的September无需为了形式另造override。
- `base_label_overlays`：新增标签JSONL的项目相对路径＋SHA256。记录可为既有wrapper（含label）或原label行，须含article_id、decision、topics、scope。不能静默重写旧文章的既有分类。
- 按日覆盖/重复/源端计数对账、新增与复用标签数量、运行参数、成本和失败记录。凭较晚抓取日期不能认证历史原文版本，相关限制继续保留。

初次可先写只含真实archive_overrides、base_label_overlays为空数组的manifest，复算缺标签清单；分类完成后在**新的**交付版本补标签路径。

从项目根目录运行以下命令仅做离线库存检查，不调用API：

```bash
PY='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
"$PY" scripts/inventory_sce_recent_b_news_repairs.py \
  --repair-manifest outputs/sce_recent_b_news_repair_20261026_v1/repair_manifest.json \
  --out outputs/<fresh_repaired_news_inventory>
```

它检查January、February、September三个完整窗口，去重导出`pending_public_news.jsonl`和9月子集，并报告原文日期覆盖。这样能得到**补齐January之后**真正需要新增的分类数，不把现有297当作最终总缺口。

## 验收与边界

- 旧原始档、旧标签、旧B/A输入和账本哈希不变。
- January完整来源覆盖1/1—31，January＋February窗口都能构造；若来源仍取不到完整内容，明确交缺口，不静默当齐全。
- 全量新增经济候选都有基础标签，文章ID与实际选用文本版本一致；SCE报道泄漏过滤沿用原规则。
- 新manifest内每个路径存在、哈希正确；不发送/保存密钥或原始SCE个体资料。
- 不自行启动Simulation、改变截止或根据预测误差筛新闻。Codex拿到交付后负责重建11期个人环境、官方Core验收、费用/权限范围和Terminal入口。

当前机器清单：`outputs/sce_recent_b_news_repair_handoff_20261026_v2/summary.json`、`archive_coverage.json`。日期映射：`outputs/sce_recent_b_sampled_dates_plan_20261026_v2/`，全部5,632户已准备，原D未变，0API。
