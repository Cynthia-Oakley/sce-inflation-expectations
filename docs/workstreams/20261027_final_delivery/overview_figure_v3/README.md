# 论文方法框架图 v3

2026-10-27。将方法图与v09报告的实际指标层级对齐，并重排为“人群与信息→问卷行为→指标形成→效果检验”。旧v1/v2和作者原稿保留，论文未自动插图，研究包v05未改。

## 文件

**作者手调版已同步（2026-10-27晚）：**以当前PPT为源，经本机WPS导出PDF，再由同一PDF生成3840×2160 PNG。保留设计依据上移、P/E位置调整、供应商并入B框以及真值、周度和下游措辞；未改动原PPT。已检查字体嵌入、全文和最终图版，新增B框行没有溢出。此次来源与输出哈希见[同步收据](author_export_receipt.json)。


- [预览与下载](index.html)
- [可编辑PowerPoint](SCE_framework_editable_v3.pptx)：原生形状、连接线、曲线及文字；各文字区域拥有自身的富文本，不覆盖独立小标签。
- [当前作者版PDF](sce_framework_paper_v3_author.pdf)：原生16:9页面，保留矢量文字，嵌入楷体与Times New Roman。
- [当前作者版高清PNG](sce_framework_author_v3.png)：3840×2160，与上方PDF一致，便于插入论文或视频。
- 手调前快照：[旧PDF](sce_framework_paper_v3.pdf) · [旧SVG](sce_framework_paper_v3.svg) · [旧PNG](sce_framework_video_v3.png)。旧scene、manifest与text_fit仅记录手调前状态，不能据此重建覆盖当前PPT。

## 口径与图注

主模拟评价为全国中心MAE、跨人W1与IQR；偏差/信念漂移作为路径诊断，RMSE单独列在下游经济预测用途。这与v09实际呈现对齐，不暗示从未计算其他指标，也不把下游RMSE当作原始SCE模拟MAE。

图中人口与环境分别汇入模型；个人模拟状态通向月度/周度研究，月度全国指标通向经济用途。统计扩展与冻结组合明确分列。近期日期只进一步限制环境，P和先验按月准备；近期不报告缺失真人微观真值下的W1准确率。

Q9小图使用已封存2025-06匿名真实答卷的十档概率和既有Beta参数，仅说明计分；未新增密度拟合，不代表模拟结果或全国分布。主论文另有完整的同例说明，本小图可按篇幅缩减。

> 家庭画像与已有信念、截止前个人可见信息共同驱动问卷作答；Q9拟合个人密度均值后按人口权重取中位数，Q8独立汇总。原始、统计扩展和历史组合分别评价；月度递推、周度校准更新和下游经济用途为独立拓展。箭头为数据/分析依赖，不表示因果识别。

## 字体与编辑

中文楷体（Kaiti SC），英文/数字Times New Roman。已在本机PowerPoint和WPS查看作者版；最终PDF来自WPS，字体均已嵌入，PNG直接从该PDF渲染。在线PPT渲染器可能回退中文字体，外观以当前作者版PDF/PNG为准。

方法图仍为作者审阅稿，插入后须重新检查Word/PDF图号和8页限制。未更改任何实验配置、模拟输出或统计结果，0新增模型调用。

## 源码

`studies/sce_inflation_expectations/reports/final_delivery_figures/build_overview_v3.py`生成手调前scene、PDF/SVG；`apply_overview_scene_v3.mjs`用于Artifact Session生成原生PPT。作者后续手调不回写旧scene，因此当前源文件是`SCE_framework_editable_v3.pptx`；重新同步应从该PPT导出。
