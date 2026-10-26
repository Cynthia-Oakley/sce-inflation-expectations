# 初稿来源与待补说明


正文唯一编辑源：studies/sce_inflation_expectations/reports/final_report_draft_v05/manuscript_v05.json。PDF、HTML和文字稿由同一内容生成。本版按冻结计分器复核既有A T0回答并引用聚合结果；报告排版未触发API。评价来源包含9,262个新Q9回答向量的离线密度估计与13个冻结后备值。


## 页与证据

- 第1页（研究问题、理论路径与摘要）：正文理论参考；本版摘要更新为A T0与未刷新的B11结果。

- 第2页（真实Q8/Q9示例与计分）：既有SCE答卷示例；冻结beta_fit_kernel.py与计分器说明。

- 第3页（网格依据）：outputs/sce_grid_dimensions_20261023_v1/summary.json；sce_grid_oversampling_20261023_v2及grid_dimension_selection_20261023.md。

- 第4页（机制与T0信息时点）：既有新闻/采购角色研究；outputs/sce_full_a_t0_terminal_20261025_v1/protocol.json。

- 第5页（A82新旧全国曲线、B11旧结果与组合）：outputs/sce_full_a_t0_readout_20261026_v1/summary.json、monthly_national.csv、yearly.csv；outputs/sce_recent_b_readout_20261025_v2/summary.json；组合读数见同一readout summary。

- 第6页（同支持微观W1/IQR、Q8与真实上期比较）：outputs/sce_full_a_t0_analysis_20261026_v1/summary.json：same_roster、genuine_previous_only、initial_reference_comparison。

- 第7页（2021全年与异向偏差解释）：outputs/sce_full_a_t0_readout_20261026_v1/yearly.csv及figures/a2021_levels_errors.png；旧2021环境诊断与旧B11 April context。

- 第8页（运行账本、评分和边界）：outputs/sce_full_a_t0_terminal_20261025_v1/protocol.json、generation_receipt.json；outputs/sce_full_a_t0_analysis_20261026_v1/manifest.json；B11仍引用v0.4。


## 当前未完成，不作虚假确认

- B11结果沿用v0.4，未以新版A配置重新生成或评价；A+B不计算合并MAE。

- A T0与旧A的比较覆盖探索性时期；2021及后34月已进入此前机制开发，不能称盲测或独立验证。

- 历史公开全国基线沿用共同月中锚，与T0的个人日期窗口不完全同一as_of；模型知识截止及部分历史字节版本未认证。

- 报告是可修改工作稿；赛事提交前仍需复核许可、数据访问/分发与最终材料。


## 复建

```sh
python studies/sce_inflation_expectations/reports/final_report_draft_v05/render_v05.py --manuscript studies/sce_inflation_expectations/reports/final_report_draft_v05/manuscript_v05.json --out docs/reports/final_report_draft_v05 --pdf-name SCE研究报告_初稿_v05.pdf --canonical-pdf-name sce_research_report_draft_v05.pdf
```

需要本机可嵌入楷体和Times New Roman、ReportLab，以及索引中的已有聚合图。解释图的来源与生成方式见本版图形说明；只在明确登记的示例中单独绘制密度，不改写冻结评价。该排版依赖不是最终独立研究包已经通过验收的声明。

## 本版图形更新

本版图5把82月旧A与新版T0、官方值及旧共同月中锚放在A面板，旧B11放在独立B面板；不跨制度连线或合并成绩。图6由同支持W1/IQR汇总直接绘制。图7复用readout已生成的2021逐月图。图5/6的源图和数据哈希见本目录figure_data_v05.json及manifest。
