# 水上挽月｜SCE生成式社会模拟研究包 v05

SocioVerse Challenge 2026，赛道 A。本研究包的当前提交候选目录为 **deliverables/research_package/v05/package/**，配套压缩包为 **deliverables/research_package/v05/SCE_research_package_draft_v05.zip**。两者内容对应；旧版 outputs 产物只供历史追溯。

本研究重现居民如何回答纽约联储消费者预期调查（SCE）的 Q8（未来 12 个月通胀点预期）和 Q9（十档通胀概率），不是预测实际 CPI。

## 三分钟开始

Python 3.11+。在解压后的包根目录运行：

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python studies/sce_inflation_expectations/run.py --mode all
~~~

安装依赖时需要网络。默认运行不需要密钥，也不调用模型 API。它完成两项不同工作：

1. 运行官方 Core 的 20 人、两步工程示例，核对接口和执行流程。它不是 512 人正式研究配置，也不是研究结果。
2. 使用包内封存的真实聚合数据复算误差和既有对照。它不是重新生成个人回答，也不能补出缺失的微观分布。

命令会写入新的输出目录。打开目录里的 index.html 查看本次复算，打开 receipt.json 查看核对记录。每次运行都使用新目录，不覆盖旧结果。

只检查文件可运行 --mode verify；只运行工程示例可运行 --mode dry-run；只重算封存聚合结果可运行 --mode replay。真实生成须在受控工作区按独立授权流程执行，不属于默认复现。

## 阅读顺序

1. [目录导航](DIRECTORY_GUIDE.md)：查看包的组成和阅读路线。
2. [Study 说明](studies/sce_inflation_expectations/README.md)：了解研究任务、配置和复现边界。
3. [结果导读](studies/sce_inflation_expectations/reports/report.md)：查看各任务结果；这不是最终 8 页论文。
4. [评审方法说明](studies/sce_inflation_expectations/reports/REVIEW_GUIDE.md)：核对方法、信息时点、基线和限制。
5. [文件导读](studies/sce_inflation_expectations/FILE_GUIDE.md)：按研究问题定位代码。

无需逐个阅读源码。Study 根目录只保留标准元信息和清楚的运行入口；其他代码按职责分目录。原始开发源码在 archive 中按原路径和 SHA-256 校验信息追溯，不进入默认执行链。

## 结果与复现范围

A、B、月度递推、周度和下游任务分别报告，不合并成单一总分。默认运行将工程示例与真实聚合复算分开标识。

包内可复算封存的全国聚合误差、冻结组合和既有下游误差。微观资料不完整，因此默认流程不会重新生成真实个体回答、重算完整个人密度或 W1，也不会重训下游模型。整体复现范围和限制见结果导读与评审方法说明。

本研究包是提交候选复现载体，不是最终论文、演示视频或赛事提交回执；包内材料不代表所有资料许可和提交要求均已完成。
