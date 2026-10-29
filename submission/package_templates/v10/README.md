# 水上挽月｜SCE通胀预期模拟研究包 v10

SocioVerse Challenge 2026，赛道A。本包研究家庭如何回答通胀预期问卷，不是直接预测实际CPI。论文和视频单独提交；包版本独立于论文版本。

## 本地开发与外部模型：评审请先读

本研究通过OpenRouter→固定SiliconFlow FP8调用DeepSeek V3.2，未使用平台MCP托管的问卷模拟服务。Q8是数值回答，Q9是十档概率JSON，由study适配器校验并计分，不依赖在线单选问卷模式。

**默认复算不需要API Key、不会产生模型调用费用。**若希望重新生成，请使用评审者自己的OpenRouter Key；作者密钥不提供、不嵌入代码。本版新增实际P/E/先验输入与选中新闻摘录；B、月度、周度的24,852份完整输入支持自备Key单次条件再生成，A的41,970份保留真实日期遮蔽。真实生成前置条件、Key配置、参数与回答契约、现有委托命令见[EXTERNAL_MODEL_AND_API.md](EXTERNAL_MODEL_AND_API.md)。

**分发范围：本ZIP仅供赛事保密评审，包含第三方新闻摘录，不随GitHub公开发布。**来源及边界见 `studies/sce_inflation_expectations/reproduction_data/inputs/NEWS_REVIEW_NOTICE.md`。赛事保密安排不代表已取得新闻的公开再分发许可。

## 从真实答卷复算主要结果

Python 3.11+，在解压后的包根执行：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python studies/sce_inflation_expectations/run.py --mode all
```

安装依赖需要网络；之后默认禁止Python网络连接，不需要密钥，不调用模型。它分别执行20人两步工程示例、封存全国聚合复算、正式批次逐答卷复算。**20人示例是接口检查；真实研究答卷在微观数据层，不要把示例当作实证生成。**每次输出到新目录，打开其中 `index.html`。

只复算答卷：

```sh
python studies/sce_inflation_expectations/run.py --mode micro
```

默认按精确概率向量查用冻结密度拟合缓存，再从逐人值重新计算权重中位数、W1、IQR、条件指标及全国误差。可额外执行 `--mode micro --refit-density`，从十档概率重新运行原冻结数值拟合器；这会增加CPU时间，但不会调用LLM或重新估计机制参数。提供缓存是为了方便审查，不用预先保存的MAE代替微观计算。

## 先读什么

1. `DIRECTORY_GUIDE.md`：目录职责。
2. `studies/sce_inflation_expectations/README.md`：研究与运行边界。
3. `studies/sce_inflation_expectations/reproduction_data/micro/MICRO_DATA_GUIDE.md`：实际答卷、模型原文、失败/补跑与评价数据的对应关系。
4. `studies/sce_inflation_expectations/reports/report.md`：各任务结果与限制。
5. `studies/sce_inflation_expectations/reports/PAPER_METRIC_GUIDE.md`：论文指标、组合权重、样本支持及费用范围对照。

v10保留v06的全部逐答卷数据及按职责整理的study目录，保留A82、最新B11、月度递推和47周的模型输出/有效答卷，以及A/B Normal统计扩展。开发期小实验保留源码及日志索引，不把四个最终任务冒称全项目所有API调用。

## 复现边界

本包可以查看脱敏模型回复，检验原始概率到归一化答卷的处理，重新计算个人密度与全国/微观指标，并以冻结τ=8重建Normal后验质量。Normal随机人口行是展示抽样，主指标用精确后验原子CDF；没有增加独立LLM信息。

近期B、月度与周度没有真人微观真值，因此只评价全国中心，群体分歧仅作描述。全波次真人参考提供冻结的标量分数与权重；不含每一份原始真人十档答卷。已选A样本另有合法来源的最小配对评价层。

本版 `reproduction_data/inputs/` 包含66,822份实际Prompt/人口/先验/价格/政策/选中新闻摘录的脱敏输入；24,852份B/月度/周度输入完整且哈希与原始一致。A输入只遮蔽真实个人关联日期。未提供身份编号、私人交叉表、密钥或完整原始新闻数据库。完整样本可通过 `simulation/reviewer_request.py` 默认离线预览，再显式自备Key发送一次。缓存复算、条件单步生成和新递推链分别说明。

SCE数据来源、衍生处理与使用条件见微观数据目录的 `SCE_DATA_NOTICE.md`；纽约联储不参与或背书本研究。不要把本地评审包准备或运行成功当作赛事已提交或已获奖。

v10在v09上补入实际输入、选中新闻摘录和便携单次入口；v06的八份冻结微观数据和既有研究结果不变。论文与视频另交，不将包内报告导读当作正式论文。

## 提交要求与可复现性声明

[REPRODUCIBILITY.md](REPRODUCIBILITY.md)集中说明种子、模型、调用与费用、真值取得时间及隔离措施、可离线复算和付费再生成的区别。取得时间的原始元数据在包根TRUTH_ISOLATION_EVIDENCE.json；未知时间与历史版本仍明确保留为空，不用目录名代替。

本版没有重新调用模型，既有研究答卷、密度缓存和结果保留。原v09继续存档。我们参加赛道A；本包通过锁定的SocioVerse2依赖和study适配器运行，没有把平台核心改动纳入提交。

## 预览和自备Key重新询问一份完整输入

```sh
python studies/sce_inflation_expectations/simulation/reviewer_request.py --candidate-dir studies/sce_inflation_expectations/reproduction_data/inputs
```

该命令默认0API、不读取Key。选择真实付费请求时才加 `--confirm-paid --out <尚不存在的新目录>`，并在当前终端设置自己的 `OPENROUTER_API_KEY`。每次最多一次、不自动重试；本地保守预留不超过$0.01，不是服务端美元硬限额。可用 `--run B --period 202511 --household <匿名编号>` 指定完整样本；三个选项需同时给出。详细步骤见EXTERNAL_MODEL_AND_API.md。A日期缺口未恢复时拒绝发送；后月/后周封存先验的单步生成不是新自主递推链。
