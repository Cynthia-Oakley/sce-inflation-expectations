# 水上挽月｜SCE生成式社会模拟研究包 v03

SocioVerse Challenge 2026，赛道A“历史重建与未来预测”，本地开发。本包遵循 `studies/sce_inflation_expectations/` 标准布局。它是已独立验收的**提交候选研究包**；论文、视频、数据逐源放行及最后文件命名仍待收束，不表示已向赛事提交。

研究对象是纽约联储消费者预期调查（SCE）：Q8为未来12个月通胀点预期，Q9为同期限十档概率。我们研究居民如何回答问卷，而非把未来实际CPI当作同一真值。真实LLM生成使用本地冻结消息执行器；官方Core用于接口装配与离线验收，不能把整个付费生成说成官方引擎在线运行。平台核心未随本项目修改或打包。

## 评审先运行这一条

Python 3.11+；新环境先安装依赖（安装需要网络，后续默认运行不联网）：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python studies/sce_inflation_expectations/run.py --mode all
```

输出写入一个全新 `outputs/reproduction_<UTC时间>/`，打印目录路径。打开该目录 `index.html` 阅读核对结果。`receipt.json` 同时记录来源清单校验、规则干跑和真实聚合缓存重算。默认没有模型密钥也能执行；Python网络连接被阻断，**不会意外产生API费用**。

默认运行包括：

1. 官方Core装配20个手工合成家庭、两步、种子42；产生40次规则决策和60条DuckDB面板记录。此项只验证工程流程。
2. 新旧A82与旧B11的真实聚合重算；A逐年、早48月拟权/后34月评价均校验。
3. 最新A Core＋Normal、最新B Core及Normal、月度自主递推、47周对应11月的主评测；校验原始值与冻结组合值的精确关系。
4. 重算A的82份已保存W1/IQR月摘要的均值；不是从个人答卷重算W1。
5. 由4,896条已保存的宏观预测核对192组误差和408组配对对照，含循环信贷正向线索及其他负向结果；此项不重新拟合下游回归，样本内R²也不重新计算。

只想核查文件：`python studies/sce_inflation_expectations/run.py --mode verify`。
只跑工程示例或缓存：分别使用 `--mode dry-run`、`--mode replay`。可用 `--out outputs/<全新目录>` 指定输出，禁止覆盖。

## 从哪里读研究

- [study README](studies/sce_inflation_expectations/README.md)：P/E/B装配、各研究任务及接口。
- [评审导读](studies/sce_inflation_expectations/reports/REVIEW_GUIDE.md)：理论—机制—对照—结果—边界，以及指标/时间/先验/权重说明。
- [本地视频演示计划](studies/sce_inflation_expectations/reports/LOCAL_DEMO_PLAN.md)：按工作台研究步骤组织约4分40秒展示。
- [论文整合计划](studies/sce_inflation_expectations/reports/PAPER_INTEGRATION_PLAN.md)：8页布局与图表预算，本轮不重写论文。
- [公开仓库准备清单](studies/sce_inflation_expectations/reports/PUBLIC_RELEASE_CHECKLIST.md)：赛事后公开前的资料、版权、历史提交与复现检查。
- `experiment_logs/registry_public.{json,csv}`：选定实验收据索引；实报费、未知预留、token估费分列，非全项目发票总额。

## 最值得先核对的结果

A个人截止T0，2019-01—2025-10共82个月，原始Core全国MAE0.298407pp；统计扩展后0.301422。2021仍是主要难点，改进不等于打败持续性。早48月MSE拟合的Core组合在后34月MAE0.184125，原参考0.194118；信息时点更严格匹配时优势减弱，后期历史也参与过开发。

最新B，2025-11—2026-09，512户Core原始MAE0.348509、公开历史持续性0.172727；冻结组合0.144277。Normal扩到1300后为0.346169/0.143964。A扩展组合权重0.134964，B和周度沿用原Core权重0.133976，两者谱系不同。

月度自主递推排除共用起点后10月MAE0.305751/持续性0.190000，后期发生向上漂移。周度47个周五，固定300户、公开SCE发布后才重置先验，11份月真值主评原始MAE0.151581/持续性0.172727，原始值未做输出层组合，仍使用已公开历史校准先验。9月漏报上升，不能概括为可靠预警；47点不是47份独立真值。

循环信贷未来1/2/3月RMSE，原始月度模拟相对同结构官方SCE模型改善3.55%/8.17%/1.69%。这是月度A/B Core＋Normal下游用途，与新周度结果分开。其他结局不稳定，历史均值等简单基线仍强，不能概括为普遍优越。

## 真实生成、受控复现与数据边界

`--mode generate` 默认不执行，必须显式指定完整合法工作区、已prepare且经授权的冻结运行包与 `--confirm-paid`。它委托已存在的A/B执行器，不恢复缺失数据、不绕过哈希/预算保护，不假装用缓存完成真实生成。详评审导读的恢复步骤。

本包不含真实人口、问卷行、个人权重/轨迹、逐篇新闻、NYT标题/摘要、GSS/ATUS/CE供体或密钥。完整个体评分、W1/条件分布、匹配和生成的重现，需要按原来源许可恢复受控资料。**包内宏观缓存可独立复算，完整微观复现尚未闭环。**`PRIVATE_INPUTS_REQUIRED.json` 为恢复证据目录，不能把原机器的绝对路径复制过去就说完成迁移。

`DATA_RELEASE_POLICY.json`、`TRUTH_ISOLATION_EVIDENCE.json`记录来源、取得时间、版本和隔离；未知历史版本仍填未知。B/周度使用已公布结果做回顾性时点回测，模型知识、人口可得性假设和新闻字节版本限制保留，不称事前封存的盲预测。

## 版本、测试和交付状态

`DEPENDENCIES.json` 锁定实际运行版本和官方参考commit；`SOURCE_INDEX.json`说明源码、适配层和排除项；`PACKAGE_MANIFEST.json`绑定包内所有文件。选定源码原样导出，不替换旧冻结输入或日志。完整原始账本保留在本地，包内只投影聚合字段。

包内针对性测试：先 `python -m pip install pytest`，再 `python -m pytest -q`。包内测试与主仓库全套不同：主仓库仍存在已记录的旧Core+Normal导入、CPI组件提取及环境fixture测试问题，不能宣称全部测试通过。干净依赖安装与受控微观复现另列验收，当前已有独立解压执行不替代所有操作系统上的全新安装。

官方要求：PDF中英文均可、4–8页含图表；MP4不超过5分钟；study格式和README是复现载体。来源：https://socioverse.fudan-disc.com/challenge/ 。本地视频按用户转交的组委会说明，可用录屏、动画或PPT展示研究过程、关键组件和结果；无需录制整夜API过程。论文/视频不混入本包假称已完成，也不会自动提交或公开仓库。
