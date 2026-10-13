# Codex个人概率填法：离线验证进度

2026-10-13。状态：离线实现、执行、独立复核与阅读交付完成。先保存[codex_mapping_protocol.json](codex_mapping_protocol.json)，后计算新结果。[结果与解释](codex_mapping_results.md)、[无个人行汇总](codex_mapping_summary.json)。新API调用0，费用$0。

- [x] 确认四期各12人、两次生成、三组模型回答；384配对行包含四种指标，Q9实际96行，不能当384份问卷。
- [x] 冻结历史参考、概率守恒、本人/置换对照、五个种子与评价；当前真值仅用于评价。
- [x] 实现独立mapping模块和复算入口，保持旧输入与计分器。
- [x] 独立检查历史截止、算术、随机分配守恒和计分。
- [x] 执行并报告全部种子、误差差值区间与映射局限。
- [x] 保存阅读页和聚合汇总，同步主任务板。

主种子本人先验臂：中心MAE1.318→1.222pp、W1 3.102→3.027pp、IQR1.060→1.081pp/真人6.249pp（统一经验分位数）；打乱中心1.227pp、W1 3.039pp，无清晰身份增量。主要改善区间均跨0，中心平均有符号偏差向上移动0.260pp；刻度和填0比例更接近真人，但没有恢复信念差异。五个种子均保存，不选最优刻度，不自动升级为主机制或新付费实验。

有效集：96条Q9配对中94条、47人月，三模型臂共282问卷；1个真实无效人月在两遍均排除，映射额外失败0。原始回答、Q8、旧配置及15保护文件保持。12项定向测试通过（新6/原6），48项真实当前/未来答案扰动分配差0，与旧历史预测47项对账差0；Scipy独立评分差≤4.44e-16、映射算术差0。

输出：`outputs/sce_reporting_mapping_20261013_v1/`，个人画像/映射变体仅在该目录；阅读`outputs/sce_reporting_mapping_reading_20261013_v2/index.html`，三图视觉检查。v1阅读保留为排版初稿；分析结果没有覆盖。下一项将本结果与Kimi更新机制候选汇合。

源码范围：`studies/sce_inflation_expectations/reporting_behavior/mapping.py`、`scripts/analyze_sce_reporting_mapping.py`、`tests/test_sce_reporting_mapping.py`。输出必须新建目录；逐人记录不提交。Kimi代码/文档、旧P/E/运行/计分与15待审文件只读。
