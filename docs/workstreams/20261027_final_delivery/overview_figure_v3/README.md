# 论文方法框架图 v3

2026-10-27。将方法图与v09报告的实际指标层级对齐，并重排为“人群与信息→问卷行为→指标形成→效果检验”。旧v1/v2和作者原稿保留，论文未自动插图，研究包v05未改。

## 文件

- [预览与下载](index.html)
- [可编辑PowerPoint](SCE_framework_editable_v3.pptx)：原生形状、连接线、曲线及文字；各文字区域拥有自身的富文本，不覆盖独立小标签。
- [论文矢量PDF](sce_framework_paper_v3.pdf)：180×101.25 mm，嵌入楷体与Times New Roman。
- [矢量SVG](sce_framework_paper_v3.svg) · [高清PNG](sce_framework_video_v3.png)

## 口径与图注

主模拟评价为全国中心MAE、跨人W1与IQR；偏差/信念漂移作为路径诊断，RMSE单独列在下游经济预测用途。这与v09实际呈现对齐，不暗示从未计算其他指标，也不把下游RMSE当作原始SCE模拟MAE。

图中人口与环境分别汇入模型；个人模拟状态通向月度/周度研究，月度全国指标通向经济用途。统计扩展与冻结组合明确分列。近期日期只进一步限制环境，P和先验按月准备；近期不报告缺失真人微观真值下的W1准确率。

Q9小图使用已封存2025-06匿名真实答卷的十档概率和既有Beta参数，仅说明计分；未新增密度拟合，不代表模拟结果或全国分布。主论文另有完整的同例说明，本小图可按篇幅缩减。

> 家庭画像与已有信念、截止前个人可见信息共同驱动问卷作答；Q9拟合个人密度均值后按人口权重取中位数，Q8独立汇总。原始、统计扩展和历史组合分别评价；月度递推、周度校准更新和下游经济用途为独立拓展。箭头为数据/分析依赖，不表示因果识别。

## 字体与编辑

中文楷体（Kaiti SC），英文/数字Times New Roman。在线PPT渲染器可能回退中文字体，权威外观见嵌入字体的PDF/PNG；PPT已经指定相应中西文字体。图片与字体已检查，不宣称已在桌面PowerPoint完成编辑验收。

方法图仍为作者审阅稿，插入后须重新检查Word/PDF图号和8页限制。未更改任何实验配置、模拟输出或统计结果，0新增模型调用。

## 源码

`studies/sce_inflation_expectations/reports/final_delivery_figures/build_overview_v3.py`生成scene、PDF/SVG；`apply_overview_scene_v3.mjs`用于Artifact Session生成原生PPT。`scene.json`是文字/坐标/曲线的共同数据源；`text_fit.json`及manifest记录交付检查。
