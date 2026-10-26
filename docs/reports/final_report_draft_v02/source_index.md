# 初稿来源与待补说明


正文唯一编辑源：studies/sce_inflation_expectations/reports/final_report_draft/manuscript_v02.json。PDF、HTML和文字稿由同一内容生成。仅排版与引用既有汇总，不运行API、Q9计分或新回归。


## 页与证据

- 第1页（研究问题与理论路径）：纽约联储FAQ；Mankiw–Reis；D’Acunto等；Malmendier–Nagel；ConsumerSim。

- 第2页（Q8/Q9教学与计分）：官方FAQ/Armantier2017；scoring/sce_q9_frozen.py；虚构教学例保存在figure_data.json，不进入提示或成绩。

- 第3页（网格依据）：outputs/sce_grid_dimensions_20261023_v1/summary.json；sce_grid_oversampling_20261023_v2/summary.json；grid_dimension_selection_20261023.md。

- 第4页（信息机制与实验取舍）：SCE专项关注文献；ATUS匹配原型；新闻8期直接共同支持；EXPERIMENT_STATUS_20261018.md。

- 第5页（全国与组合结果）：outputs/sce_fullperiod_analysis_20261024_v1/summary.json；冻结48/34月组合。

- 第6页（微观差异与更新）：同上fixed_roster/genuine_previous_only/update_summary/variance_summary/groups/regression。

- 第7页（2021定向诊断）：outputs/sce_2021_environment_blend_diagnostic_20261024_v2/summary.json及原始输入核查。

- 第8页（执行、边界与后续）：主批scope/quality/receipt；现有A/B时间证据；近期B明确暂缓。


## 当前未完成，不作虚假确认

- 近期11个月B线暂停，是否使用Kimi新新闻机制待定；未启动新调用。

- 研究包许可清单、独立解压验收、全开发成本总账、视频未完成。

- Kimi媒体拓展/新测试和六项微观事实关键回归未在本轮复核，不拿未复核系数校准或写为已证实机制。

- 全82月主结果与48/34月权重评价保留，后期不是全机制未见盲测。

- 外部CE/ATUS固定年资料作A线合成机制，不认证历史当时可得；模型参数知识另列。


## 复建

```sh
python scripts/render_sce_research_report.py --manuscript studies/sce_inflation_expectations/reports/final_report_draft/manuscript_v02.json --out docs/reports/final_report_draft_v02 --pdf-name SCE研究报告_初稿_v02.pdf --canonical-pdf-name sce_research_report_draft_v02.pdf
```

需要本机可嵌入楷体和Times New Roman、ReportLab，以及索引中的已有聚合图。新解释图另由同目录figures_v02.py读取冻结缓存生成，不调用API或重跑统计模型。该排版依赖不是最终独立研究包已经通过验收的声明。
