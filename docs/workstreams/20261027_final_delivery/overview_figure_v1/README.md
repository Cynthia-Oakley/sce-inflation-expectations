# SCE全流程框架图：初版

2026-10-27。依据作者已确认的[文字设计](../overview_figure_brief.md)绘制，供论文与视频迭代。未插入或修改Kimi的论文，未改研究结果/配置，未调用收费模型。

## 先看什么

- [图形预览与下载](index.html)
- [可编辑PPTX母版](SCE_framework_editable_v1.pptx)：一页16:9，51个文本对象及原生方框、连接线；可在PPT中改字、调整和做分步展示。
- [论文矢量PDF](sce_framework_paper_v1.pdf)：180 × 101.25 mm，嵌入中文字体，可缩放；建议正文全宽使用。
- [可编辑SVG](sce_framework_paper_v1.svg)：便于矢量编辑；保留可编辑文本，显示依赖本机中文字体，跨机器定稿优先用PDF。
- [视频/阅读PNG](sce_framework_video_v1.png)：1920 × 1080。

## 阅读顺序与图注建议

从左侧P与E开始，两条输入共同进入家庭代理；再看计分汇总与分层验证。蓝色表示家庭/信念，橙色表示信息通道，灰黑表示统计与检验。Normal与冻结组合使用虚线边框和连接线，动态与用途以独立拓展标出。

可供作者改写的图注：

> 调查约束下的家庭通胀预期模拟框架。人群P与个人可见环境E共同驱动问卷行为B，Q8独立汇总，Q9经冻结近似计分器转换为个人密度均值，再按人口质量求全国中位数。A使用真实历史或近期供体，B以较早框架与已公开历史值构造合成起点。全国与微观评价分开，近期微观真值缺失不作准确率判断。Normal和冻结组合另报；动态与经济用途为独立拓展。箭头表示数据与计算依赖，不是现实居民机制的因果估计。

时间细节仍需正文说明：A以真实完成日前一日限制E；B的P/先验按月全局截止准备，合成个人日期只进一步限制E；周度仅在新历史SCE公开可用后校准。图中的采购角色匹配是已实现操作化，不宣称它单独改善拟合。

## 本轮适合讨论什么

1. 总览中的主干与分支是否一眼可辨，文字密度是否合适。
2. 论文全宽放置时，是否需要进一步简化参数/底部说明；视频则可放大逐段讲解。
3. 动态与用途当前作简写，若需完整递推回环，宜另做视频展开页，不在这张图追加大量细节。

## 源与重建

- `scene.json`是同一内容与几何的中间描述，SVG/PDF和PPT都由此生成；不含个人数据。
- 源码：[build_overview_v1.py](../../../../studies/sce_inflation_expectations/reports/final_delivery_figures/build_overview_v1.py)及[apply_overview_scene.mjs](../../../../studies/sce_inflation_expectations/reports/final_delivery_figures/apply_overview_scene.mjs)。
- SVG/PDF重建需要Python、ReportLab和支持中文的TTF。输出目录须全新，旧版本保留：

```bash
python studies/sce_inflation_expectations/reports/final_delivery_figures/build_overview_v1.py \
  --out docs/workstreams/20261027_final_delivery/overview_figure_rebuild_new \
  --font '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
```

PPT由`applyOverviewScene(presentation, scene)`在Artifact Session中生成原生可编辑对象，渲染检查后导出。也可直接编辑现成PPT母版，不必重跑绘图代码。

本轮仅做图文与导出验证；没有全项目测试或PowerPoint桌面打开验收的声明。初版图件尚未纳入当前封存研究包。
