# 初稿来源与待补说明


正文唯一编辑源：studies/sce_inflation_expectations/reports/final_report_draft_v06/manuscript_v06.json。PDF、HTML和文字稿由同一内容生成。本版只重写文章并复用冻结聚合和既有图，不运行模拟、LLM、Q9计分或新回归。


## 页与证据

- 第1页（研究问题与主结论）：materials_v1/numbers.csv及第01、11主题；摘要同时保留正向结果与失败边界。

- 第2页（问卷、框架与评价）：SCE_EVALUATION_CONTRACT_V1.md；materials_v1第01—02主题。

- 第3页（人口网格、权重与历史状态）：grid_dimension_selection_20261023.md；grid维度与过采样summary；materials_v1第03主题。

- 第4页（环境、行为与机制取舍）：CURRENT_SIMULATION_CONFIGURATION.md；materials_v1第02、10主题。

- 第5页（A82与B11全国结果）：A_T0_readout、B_latest与A82_comparison_summary；不跨任务合并指标。

- 第6页（微观结构与Normal）：A82_micro_monthly_summaries、A82_Core_Normal_tau8及B Normal汇总。

- 第7页（月度、周度与下游）：monthly_autonomous_recursion、weekly47、downstream_contrasts；输入谱系分别说明。

- 第8页（讨论、复现与参考）：deliverables/README.md、clean_release验收与materials_v1/sources.json。


## 当前未完成，不作虚假确认

- 作者、单位与导师署名尚未确认，本版为作者审阅稿而非最终提交件。

- 所有实验均为回顾性证据，不称严格封存实时预测或全研究未触碰盲测。

- 完整受控微观复现、数据许可与全项目费用覆盖仍按研究包清单核查。

- 最终提交前需由独立复核者逐项检查摘要、图表和结论的数字口径。


## 复建

```sh
python studies/sce_inflation_expectations/reports/final_report_draft_v06/render_v06.py --manuscript studies/sce_inflation_expectations/reports/final_report_draft_v06/manuscript_v06.json --out docs/reports/final_report_draft_v06 --pdf-name SCE研究报告_重写稿_v06.pdf --canonical-pdf-name sce_research_report_draft_v06.pdf
```

需要本机可嵌入楷体和Times New Roman、ReportLab，以及索引中的已有聚合图。解释图的来源与生成方式见本版图形说明；只在明确登记的示例中单独绘制密度，不改写冻结评价。该排版依赖不是最终独立研究包已经通过验收的声明。

## 本版图形更新

本版复用materials_v1中已经离线核验的八组PNG图。没有重新拟合、选择性改数或新绘图；图的来源和哈希见manifest及materials_v1/sources.json。
