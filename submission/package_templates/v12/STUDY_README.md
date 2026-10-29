# SCE study：正式答卷与复现入口

本研究模拟美国SCE一年期通胀预期问卷。Q8为点预期，Q9为十档概率；个人Q9连续密度均值再经人口权重取全国中位数。

在包根运行 `python studies/sce_inflation_expectations/run.py --mode all`。默认0 API，同时包含明确标识的工程示例、全国聚合复算和正式答卷微观复算；`--mode micro`只跑最后一项。

## 正式运行资料

- `reproduction_data/micro/model_outputs.jsonl.gz`：实际模型返回的原文（及失败、补跑记录），带原字节哈希、脱敏状态、模型/供应商、token/费用。不是新生成回答。
- `effective_answers.jsonl.gz`：最终有效答卷，逐字段连接原始输出，保留归一化和输入/前态后备标记。
- `A_paired_cases.jsonl.gz`、`A_full_wave_targets.jsonl.gz`：只供评价的配对/全波次参考，不能进入生成输入。
- `normal_mechanism.jsonl.gz`：冻结参数、无目标答案的框架与模型供体，用原算法重新计算后验质量。
- `normal_population_rows.jsonl.gz`：已物化的人口展示行，不能用它的随机抽样误差冒充精确后验CDF。

数据细节见同目录的 `MICRO_DATA_GUIDE.md`。代码按人口、环境、行为、运行、计分、评价归类，根目录保持清爽；`FILE_GUIDE.md`提供导航。研究配置在 `simulation/research_runs.json`，不从20人脚本示例推断实际研究规模。

## 复现边界

默认用精确向量冻结缓存重算指标，`--mode micro --refit-density`可重新数值拟合密度。两者都不调用LLM，不按目标真值挑选回答、月份或参数。

包含四个正式最终任务与A/B统计扩展，不是全部开发试验逐条输出的全集。近期没有真人微观真值；快速复算参考采用冻结标量；原始公开工作簿与提取脚本另在portable源资料层。本包附实际输入与选中新闻摘录，未重新调用模型；A公开调查派生日期也原样提供，公开SCE匿名编号与内部Agent编码映射在portable/evidence提供。来源声明见 `reproduction_data/micro/SCE_DATA_NOTICE.md`。


实际输入层：`reproduction_data/inputs/README.md`。完整自备Key入口为包根 `review.py`（委托study内reviewer_pipeline）；单步预览仍保留reviewer_request.py。方法与命令见PORTABLE_REPRODUCTION.md。此ZIP包含第三方新闻摘录，仅供赛事保密评审，不随公开GitHub分发。

## v12：从公开源到新模型结果

当前完整命令以包根 `PORTABLE_REPRODUCTION.md` 为准。新增原工程独立工作区，不依赖作者绝对路径或Key。公开源/匿名编号/日期/内部编码映射/候选新闻/标签/实际请求ID均保留；完整Prompt和逐答卷旧结果不变。`simulation/reviewer_pipeline.py`支持准备、计划、自备Key批量、月度/周度新状态递推、评价与下游重估。
