# Codex统一行为评价：进度

2026-10-13。离线实现、运行与验证完成。先保存[codex_comparison_protocol.json](codex_comparison_protocol.json)，既有LLM结果已看过，新增基线未选优。任务：评价工具、同样本过去信息基线、后续结果判断规则；新增API0/$0。

- [x] 核对48人月、两次生成、旧三组回答与数据哈希。
- [x] 登记同计分、共同有效集、经验分位数和两种只读历史基线。
- [x] 实现新回答接入、主指标和按人配对区间。
- [x] 同批复算旧LLM与简单基线，核验算术及未来答案隔离。
- [x] 整理结果和Kimi接入规范，更新主清单。

文件范围：新建`evaluation/behavior_comparison.py`、`scripts/analyze_sce_behavior_comparison.py`、定向测试和本目录`codex_comparison_*`。Kimi源码/文档、现有输入、计分器、正式运行配置及15待审文件只读；公共任务板由Codex整合。原始/逐人结果只在新建outputs目录。

两种基线：本人上期照抄；本人过去Q9均值的0.5部分回归。后者借用已存在的训练参数，但去掉当月真实共同变化，且所有人统一使用冻结近似计分，所以不与Kimi原C1混称。同样本消除人群/时期口径差，不表示简单基线获得LLM的所有新闻和价格信息。

结果：[说明/统计解释](codex_comparison_results.md)、[阅读页](codex_comparison_results.html)、[聚合记录](codex_comparison_summary.json)、[Kimi接入规范](codex_comparison_input_spec.md)。主输出sce_behavior_comparison_20261013_v2（v1初算保留，数值相同）；离线导入验证sce_behavior_comparison_import_check_20261013_v1，96份旧回答复放，不是新Simulation。

同样本本人先验LLM/照抄/个人锚：Q9总体MAE1.318/.850/.974、人群W1 3.102/1.704/1.435、变化W1 1.786/2.955/2.224pp。保留差异与合理更新要同时评价；不能仅比旧LLM好就采用。30定向/评价回归测试；独立SciPy/ECDF最大差5.33e-15；48真实历史时点扰动不变、96导入指标/自身区间差0、15待审哈希保持；阅读页30选择组合及链接逻辑验过，未做真实浏览器截图验收。

下一项由Kimi修订并离线验收运行输入；Codex接新JSONL后统一评价、复核，再讨论独立月份和规模。当前未启动新付费请求，不改变正式全国指标或宣称已采用新机制。
