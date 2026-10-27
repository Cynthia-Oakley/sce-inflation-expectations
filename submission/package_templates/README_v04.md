# 水上挽月｜SCE生成式社会模拟研究包 v04

SocioVerse Challenge 2026，赛道A，本地开发。**先运行、再看结果、按需查算法**。此包是提交候选版；最终论文、视频和完整微观数据的合法复现安排仍需收尾。

## 三分钟开始

Python3.11+，在解压后的包根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python studies/sce_inflation_expectations/run.py --mode all
```

安装需要网络，默认运行不需要密钥，Python网络连接被阻断，**不产生API费用**。命令打印全新输出目录：打开其中 `index.html` 阅读本次重算，`receipt.json`查看核验。不会覆盖旧数据。

它实际完成两件不同的事：官方Core运行20人两步的合成规则示例；再用封存真实LLM聚合结果核对A/B、Normal、月度/周度和下游误差。前者不是实证拟合成绩，后者不是再次询问模型或从个人数据重建全部分布。

## 只需要先看这些

1. [目录导航](DIRECTORY_GUIDE.md)：每个路径的用途、哪些是入口、哪些只是参考。
2. [study说明](studies/sce_inflation_expectations/README.md)：研究对象、P/E/B、主任务和统计边界。
3. [研究依据与方法](studies/sce_inflation_expectations/reports/REVIEW_GUIDE.md)：为什么这样匹配、设定时间、扩展与评价。
4. [结果图表导览](studies/sce_inflation_expectations/reports/index.html)：封存图表；本次执行所得数字另看命令输出的index.html。

无需逐个阅读Python文件。主包只保留明确研究入口和静态依赖；**其余专题/历史/开发辅助源码在 [补充源码归档](archive/README.md)**，默认不用解压。归档不是删除，也不意味着其中每项代码都已失效。

## 研究和证据

SCE是纽约联储的月度家庭预期调查。Q8问未来12个月通胀点预期，Q9要求给十档通胀区间分配概率。研究目标是重建居民的回答，不是预测实际CPI。Q9先拟个人密度均值，再取跨人设计加权中位数。

- **A82历史重建**：新版原始Core MAE0.298407pp，Normal后0.301422；2021有所改善，仍未在全期胜过持续性。
- **最新B11**：原始/冻结组合MAE0.348509/0.144277，持续性0.172727；Normal后0.346169/0.143964。
- **自主月度链**：排除共用起点10月MAE0.305751/持续性0.190000，后期上偏。
- **周度**：固定300户47周、11份月真值，原始MAE0.151581/持续性0.172727；没有输出层组合，仍使用已公布历史SCE校准先验，9月漏报。不是47份独立真值。
- **下游用途**：原始月度模拟相对同结构官方SCE模型，循环信贷1/2/3月RMSE改善3.55/8.17/1.69%；其他结局混合、简单基线强。不是新周度指标的下游分析。

各任务分开评价，不拼一个93月总分。原始、线性组合、宏观修正分别标识；A Normal组合权重0.134964，B/周度沿用原Core权重0.133976，不在近期11月重拟。完整方法、实验记录、负向结果和限制见reports与experiment_logs。

## 可复现范围与数据边界

支持 `--mode verify` 文件核对、`--mode dry-run`工程示例、`--mode replay`聚合复算。默认all将它们组合。所有输出必须用新目录。

包内能核对A的48/34组合、微观W1/IQR**月摘要均值**、4,896条下游宏观预测的192组误差和408对照。没有从真人答卷重新计算W1/拟合密度，也没有重训下游回归。完整个体重现仍需合法恢复受控资料，具体步骤见REVIEW_GUIDE。

不包含原始调查、个人模型轨迹、供体链接、权重、逐篇新闻和密钥。真实生成通过 `--mode generate` 显式委托合法完整工作区及冻结执行包，要求范围/预算授权，绝不默认收费。主付费生成来自本地冻结消息适配器，官方Core承担接口/离线验收，不冒称所有主批由官方引擎在线执行。

B和周度是回顾性时点模拟；历史人口可得性、新闻字节版本、模型知识及探索性开发边界保留。`DATA_RELEASE_POLICY.json`、`TRUTH_ISOLATION_EVIDENCE.json`、`OFFICIAL_REQUIREMENTS.json`为来源与提交说明。

## 验收、日志及其他交付

安装pytest后可运行 `python -m pytest -q` 检查包内定向测试。主仓库旧测试仍有已登记问题，不能据包内测试宣称全套通过。依赖锁含已有模块初始化所需pypdf/requests；对应版独立解压与全新环境验收另留收据。

`experiment_logs/`为22项选定实验，不是全项目发票总额；实报费、未知预留和token估费分列。`SOURCE_INDEX.json`列主包源码、依赖选择与归档，`PACKAGE_MANIFEST.json`绑定全包文件；旧ZIP及原运行不改。

论文规划：[8页整合](studies/sce_inflation_expectations/reports/PAPER_INTEGRATION_PLAN.md)。视频规划：[本地4分40秒](studies/sce_inflation_expectations/reports/LOCAL_DEMO_PLAN.md)。官网要求PDF4—8页含图表、MP4≤5分钟、标准study及README；本地可用录屏/动画/PPT展示研究过程、组件与结果。官方来源：https://socioverse.fudan-disc.com/challenge/ 。当前包不表示已完成论文、视频或赛事提交。
