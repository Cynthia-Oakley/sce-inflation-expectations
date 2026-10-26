# 初稿来源与待补说明


正文唯一编辑源：studies/sce_inflation_expectations/reports/final_report_draft/manuscript_v03.json。PDF、HTML和文字稿由同一内容生成。仅更新展示示例与排版，不运行API或新回归。示例取自已有真实微观答卷，单独用冻结算法绘制1条密度曲线，并与既有缓存均值/IQR逐项核对；不改写评价、主结果或模型输入。


## 页与证据

- 第1页（研究问题与理论路径）：纽约联储FAQ；Mankiw–Reis；D’Acunto等；Malmendier–Nagel；ConsumerSim。

- 第2页（真实Q8/Q9示例与计分）：SCE 2025年6月实际答卷；已有truth/scoring_cache及原始微观投影交叉核对；冻结beta_fit_kernel.py，图形来源与参数见sce_research_report_figures_20261024_v03/figure_data.json。

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
python scripts/render_sce_research_report.py --manuscript studies/sce_inflation_expectations/reports/final_report_draft/manuscript_v03.json --out docs/reports/final_report_draft_v03 --pdf-name SCE研究报告_初稿_v03.pdf --canonical-pdf-name sce_research_report_draft_v03.pdf
```

需要本机可嵌入楷体和Times New Roman、ReportLab，以及索引中的已有聚合图。解释图的来源与生成方式见本版图形说明；只在明确登记的示例中单独绘制密度，不改写冻结评价。该排版依赖不是最终独立研究包已经通过验收的声明。

## 本版图形更新

新增图1由 studies/sce_inflation_expectations/reports/final_report_draft/figures_v03.py 生成，读取已有真值与计分缓存；对应原始十档、月份、选择规则、来源SHA和一致性检查见 outputs/sce_research_report_figures_20261024_v03/figure_data.json。未输出原始ID、人口特征或调查权重。其余解释图仍复用figures_v02.py的冻结汇总图。
