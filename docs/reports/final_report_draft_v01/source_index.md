# 初稿来源与待补说明


正文唯一编辑源：studies/sce_inflation_expectations/reports/final_report_draft/manuscript.json。PDF、HTML和文字稿由同一内容生成。仅排版与引用既有汇总，不运行API、Q9计分或新回归。


## 页与证据

- 第1页（研究背景）：纽约联储FAQ、Armantier2017、ConsumerSim及理论参考，均见正文链接。

- 第2页（P/E/B及权重）：docs/workstreams/20261023_main_run/README.md；mechanism_guide_20261024.json。

- 第3页（计分和时间边界）：scoring/sce_q9_frozen.py；evaluation/fullperiod_analysis.py；最终协议与来源索引。

- 第4页（机制取舍）：docs/EXPERIMENT_STATUS_20261018.md及其逐项实验结果；不跨支持拼接成绩。

- 第5页（全国结果）：outputs/sce_fullperiod_analysis_20261024_v1/summary.json：macro_whole、yearly、official_national。

- 第6页（微观和更新）：同上：fixed_roster、genuine_previous_only、update_summary、variance_summary、groups、regression。

- 第7页（2021诊断）：outputs/sce_2021_environment_blend_diagnostic_20261024_v2/summary.json；专项结果MD。

- 第8页（费用和限制）：主分析scope/quality；原始/两轮修复账本；待补项未预写成绩。


## 当前未完成，不作虚假确认

- 近期11个月B线暂停，是否使用Kimi新新闻机制待定；未启动新调用。

- 研究包许可清单、独立解压验收、全开发成本总账、视频未完成。

- Kimi媒体拓展/新测试和六项微观事实关键回归未在本轮复核，不拿未复核系数校准或写为已证实机制。

- 全82月主结果与48/34月权重评价保留，后期不是全机制未见盲测。

- 外部CE/ATUS固定年资料作A线合成机制，不认证历史当时可得；模型参数知识另列。


## 复建

运行scripts/render_sce_research_report.py；需要本机可嵌入楷体和Times New Roman、ReportLab，以及索引中的已有聚合图。该命令不需要API密钥。该排版依赖不是最终独立研究包已经通过验收的声明。
