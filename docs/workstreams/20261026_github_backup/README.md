# 2026-10-26 私有GitHub阶段备份

本次按用户要求，将当前项目代码、方法文档、汇总图表和报告草稿保存到既有私有远端。它是研究进展检查点，不代表正式投稿包已验收，也不更改默认分支、仓库可见性或已有运行结果。

远端：`https://github.com/Cynthia-Oakley/socioverse-challenge-2026`。继续使用工作分支 `docs/deepseek-reuse-20261008`，正常快进推送，保留此前72个本地提交，不重写历史。操作前已读取远端；本地没有需要先合并的远端新提交。

## 保存的内容

- 当前P/E/B、抽样、Q9计分、独立评价、Core＋Normal和容错运行代码及测试。
- 已有A/B全时段分析、研究报告草稿、研究包构建工具与实验记录。
- 月度信念递推的[新版图文总结](../20261026_belief_recursion/monthly_results_v2/index.html)：如实列为实验性扩展；连续性改善与转向不足同时披露。
- 周度发布／评分时钟等离线设计，保留“未进行真实周度运行”的状态。

## 留在本机的内容

沿用`.gitignore`及项目数据规则，`outputs/`、原始／受限／评价微观数据、逐人答卷和完整请求日志、密钥与环境文件不上传。费用与实验结果只通过文档和聚合统计记录。GitHub代码备份不能替代对本地数据和运行归档的独立备份。

以下3份已被旧版本跟踪的人口文件，本轮的本地改动不纳入新提交，不删除或改写它们：

- `studies/sce_inflation_expectations/population/population_main2021_a73.sampling_meta.json`
- `studies/sce_inflation_expectations/population/population_real100.json`
- `studies/sce_inflation_expectations/population/population_real100.sampling_meta.json`

它们含画像或匹配ID。本轮保留本地实际输入，避免为整理仓库而改变冻结实验；没有扩大既往的资料发布授权。

## 核查和运行边界

远端元数据核实为private。推送前扫描新增历史中的592个blob以及本次候选工作文件，未发现常见API密钥／GitHub令牌／私钥格式；候选JSON的逐人字段检查识别并排除了上述3份人口文件。检查以文件路径、结构、汇总层级和内容为依据，不依赖“已经去标识就可发布”的假设。

月度递推、周度时钟、研究包实验记录及离线复算相关测试41项通过；这不是全仓所有历史实验的重新复现。提交前另检查Python语法、暂存清单和diff格式。此次不新增模型API调用。

具体文件清单、提交前检验和最终远端提交SHA保存在本机`outputs/sce_github_backup_20261026_v1/`，不把包含本地逐文件审计的运行目录强制加入Git。
