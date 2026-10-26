# 初稿来源与待补说明


正文唯一编辑源：studies/sce_inflation_expectations/reports/final_report_draft/manuscript_v04.json。PDF、HTML和文字稿由同一内容生成。仅引用已有A82/B11聚合结果、运行账本和4月离线诊断；不新增API、Q9拟合或回归。两段只在图上按时间接续，分开报告成绩；旧v0.3与冻结运行不覆盖。


## 页与证据

- 第1页（研究问题与理论路径）：纽约联储FAQ；Mankiw–Reis；D’Acunto等；Malmendier–Nagel；ConsumerSim。

- 第2页（真实Q8/Q9示例与计分）：SCE 2025年6月实际答卷；已有truth/scoring_cache及原始微观投影交叉核对；冻结beta_fit_kernel.py，图形来源与参数见sce_research_report_figures_20261024_v03/figure_data.json。

- 第3页（网格依据）：outputs/sce_grid_dimensions_20261023_v1/summary.json；sce_grid_oversampling_20261023_v2/summary.json；grid_dimension_selection_20261023.md。

- 第4页（信息机制与实验取舍）：SCE专项关注文献；ATUS匹配原型；新闻8期直接共同支持；EXPERIMENT_STATUS_20261018.md。

- 第5页（A82/B11全国曲线与分段评价）：sce_fullperiod_analysis_20261024_v1与sce_recent_b_readout_20261025_v2冻结聚合；figures_20261025_v04b仅拼接展示、不合报成绩。

- 第6页（微观差异与更新）：同上fixed_roster/genuine_previous_only/update_summary/variance_summary/groups/regression；近期B无真人微观真值，仅描述模拟IQR。

- 第7页（2021低估与2026-04高估诊断）：sce_2021_environment_blend_diagnostic_20261024_v2与sce_recent_b_april_context_20261025_v1；原始输入/模型理由及官方4月首发。

- 第8页（运行、边界与后续）：A最终receipt＋B generation_receipt；近期人口/先验推定可得性和54格权重接口；研究包/视频尚待验收。


## 当前未完成，不作虚假确认

- Kimi新闻匹配机制与独立测试尚未完成；未来结果另版纳入，不覆盖A82/B11回答。

- 研究包许可清单、独立解压验收、全开发成本总账和演示视频待完成。

- B微观可得性基于显式九个月规则推定，历史字节版本/新闻版本/模型知识截止尚未认证，不能称严格事前预测。

- A/B均512人全LLM和分层权重，无Core＋Normal扩样或连续信念递推；B权重代表旧源人口，近期人口边际不获保证。

- 组合仍冻结早48月λ=0；不据后34月或近期11月重选权重。


## 复建

```sh
python scripts/render_sce_research_report.py --manuscript studies/sce_inflation_expectations/reports/final_report_draft/manuscript_v04.json --out docs/reports/final_report_draft_v04 --pdf-name SCE研究报告_初稿_v04.pdf --canonical-pdf-name sce_research_report_draft_v04.pdf
```

需要本机可嵌入楷体和Times New Roman、ReportLab，以及索引中的已有聚合图。解释图的来源与生成方式见本版图形说明；只在明确登记的示例中单独绘制密度，不改写冻结评价。该排版依赖不是最终独立研究包已经通过验收的声明。

## 本版图形更新

新增图5由figures_v04.py读取两份已冻结汇总，A82与B11合计93个连续调查月。2025-11虚线与阴影区分两种输入制度，模型线不跨边界连接，另放大B11；不计算混合口径总MAE，不作个人递推声明。其余7图复用v0.3，真实Q9示例不重新拟合。population_weight_check.json记录512人直接LLM及54格加权口径核对。
