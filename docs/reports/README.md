# 项目汇报入口

后续实验阅读页及汇报沿用用户认可的[图文风格](STYLE.md)：高对比配色、图数结合、分层展示，中文楷体/英文Times New Roman。

## 近期11个月结果：2026-10-25

- [运行、全国误差与人群差异](20261025_recent_b_v2/index.html)：5632份全部补齐，API报告$4.0745；模型MAE0.241/持续性基线0.173pp。3幅图＋逐月CSV＋交互Canvas，近期微观结构仅描述。
- [结果解释与零API复算](../workstreams/20261025_recent_b/results.md)。原评价漏登2026-09已补官方首发来源恢复，原始运行与配置保留。报告v0.3仍未修改，近期结果待合入正式稿。

## 当前研究报告：2026-10-25 v0.4

- [8页阅读版](final_report_draft_v04/index.html) · [PDF](final_report_draft_v04/SCE研究报告_初稿_v04.pdf) · [来源与复建](final_report_draft_v04/source_index.md)。沿用楷体/Times New Roman与首行缩进；旧v0.3保留。
- 新增A82/B11的93月时间图，2025-11用虚线/底色区分，并放大B段；成绩分开报告，不冒称个人连续递推。第3页说明512人全LLM与权重，无贝叶斯扩样；第7页加入2026-04新闻风险外推诊断。
- 只是工作稿；研究包、完整开发成本、许可及视频仍待完成。Kimi旁线结果以后另版补充，本次0API/0Q9拟合。

## 上一版研究报告：2026-10-24 v0.3

- [打开v0.3阅读版](final_report_draft_v03/index.html) · [PDF](final_report_draft_v03/SCE研究报告_初稿_v03.pdf) · [文字稿](final_report_draft_v03/manuscript.md) · [来源与复建命令](final_report_draft_v03/source_index.md)。8页/8图，中文楷体、英文Times New Roman。
- 本版强化“理论依据—操作化—检验—取舍”：补SCE/Q8/Q9真实答卷示例图、人口移除重拟合/MCA与54格依据、新闻/购物价格两条路径及新闻量对照。统计支持与因果解释分开；原82月结果保持。
- 正文源final_report_draft/manuscript_v03.json；scripts/render_sce_research_report.py读取正文排版，--manuscript等参数见复建命令。正文和图表分别缩小5%/8%，自然段首行缩进两字；图1使用2025年6月真实去标识答卷，1次示意曲线拟合与旧缓存完全一致，0API/0新评价拟合；B线按用户要求暂缓。
- [v0.1初稿](final_report_draft_v01/index.html)及其PDF保留，未覆盖。研究包/全项目费用/许可及近期结果仍待补。

## 最新全量结果：2026-10-24

- [82个月历史重建效果（正式v2）](20261024_fullperiod_v2/index.html)：总体/组合、时期差异、微观/更新、分组与增量回归，六张科学图。与10月19日阶段PPT分开，是当前主结果入口。
- [结果解释与复算](../workstreams/20261024_fullperiod_analysis/results.md)、[分析框架](../workstreams/20261024_fullperiod_analysis/README.md)。本轮分析0 API、0 Q9重新拟合、配置不变；主分析是A线，近期11月尚需独立推进。
- `20261024_fullperiod/`保留图文初稿；正式v2将残余中位数敏感性严格对齐主共同支持。原始模拟和主指标均不变。

## 最新汇报：2026-10-19

- [打开汇报阅读版](20261019/index.html)：16页正文＋4页附录；可进入演示模式。
- [下载PDF](20261019/SCE项目进展汇报_20261019.pdf)：用于汇报、转发和打印。
- [查看逐页提纲](20261019/汇报提纲.md)。

沿用原版楷体、Times New Roman和横向布局，更新十二期主结果、六期新闻对照、Kimi初步发现和采购角色研究计划。各批不同支持分别报告；Kimi关键回归解释列为待复核，未复现实验或新增模拟。

最新入口也可直接打开本目录的[index.html](index.html)。

## 最新实验：2026-10-23新人起点小试

- [图文阅读页](../workstreams/20261021_fullperiod/entry_pilot_results_v2/index.html)：近期供体、新人与真实回访者分别评价；Q9中心有局部收益，分布仍收缩，Q8单列。
- [完整说明与复算](../workstreams/20261021_fullperiod/entry_pilot_results_20261023.md)：144个人月/288尝试、281可用/7连接失败，API报告$0.1827，82月仍暂停。此页不是最终全量报告。

## 旧版保留

本目录仅保存明确选入备份的汇报成稿，不批量纳入自动运行产物、真实微观记录或原始新闻。

- `sce_progress_report_20261015_v2.pdf`：15页主讲、6页附录，已按用户首轮反馈改为中文楷体、英文数字Times New Roman，补SCE背景、A/B边界、八期图及模型知识诊断。与本机`output/pdf/`同名文件逐字节相同。
- 文稿、聚合数据和制作入口：`studies/sce_inflation_expectations/reports/progress_20261015_v2/`及`scripts/{prepare,render}_sce_progress_report.py`。

这是研究进展汇报，不是最终参赛报告。GitHub备份不涵盖被忽略的原始数据、完整轨迹与待用户审定的旧改动；最终研究包仍须独立验收。

- 上一版保留：[v0.2](final_report_draft_v02/index.html)。
