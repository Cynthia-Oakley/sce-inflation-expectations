# v06：真实答卷、模型原文与微观复现

2026-10-29。用户授权补齐已有批量模拟资料与微观复现；本轮无API调用，无机制/参数重选，不改论文或冻结研究结果。

## 当前交付

- [解压包](../../../deliverables/research_package/v06/package/README.md)
- [ZIP](../../../deliverables/research_package/v06/SCE_research_package_draft_v06.zip)，39,093,089字节。
- [微观资料导读](../../../deliverables/research_package/v06/package/studies/sce_inflation_expectations/reproduction_data/micro/MICRO_DATA_GUIDE.md)
- [独立ZIP验收](acceptance_public.json)、[密度重拟合验收](density_refit_acceptance.json)。

旧v05原字节保留，SHA仍为 `28f0866dea240c834f5d50a66b569536e2d5dfb4972bcd82fce597fd9d41804f`。v06不是把旧ZIP重命名：新增逐答卷数据、原始输出、独立入口、版本模板和实际验收。

## 补入什么

四类正式运行共 **67,334个有效状态**：A82为41,970个合格个人月，B11为5,632个家庭月，月度递推为5,632个状态（512个根状态复用B），47周为14,100个状态。

共有 **67,147条模型输出记录**，主请求、错误、补跑分开，A内182条是原提示一致的历史导入。对应历史物理新请求为66,965次，不能把输出记录数或根状态复用再计作新调用；本次整理调用数为0。输出保存原文、原字节哈希、模型/供应商、token/费用、未知费用预留和补跑阶段。没有导出完整提示或请求ID。

有效答卷逐字段连接输出；Q9比例归一化、传输失败保留旧值、数值密度拟合失败后备分别可追溯。A的少量最终密度仍为空时按旧评价的字段支持排除，不删除整个人，也不伪造新的答案。

另有 **112,682个扩展人口行**：A98,382行、B14,300行。主指标使用原算法及固定τ=8重新计算后验原子质量；这些抽样展示行不增加独立LLM信息。A保留Q8边际与Q9联合供体的区别。

提供最小A配对评价数据、完整波次冻结标量/权重、精确向量拟合缓存、Normal人口框架与供体。研究内代理键重新编号；为兼容共享评价器，A配对数据的 `userid` 字段是新的包内顺序号，**不是原始SCE编号**。私人键表不进ZIP。

## 实际复算结果

从逐答卷重新得到全国原始MAE：A82 **0.2984067126pp**，B11 **0.3485087577pp**，月度后10期 **0.3057506013pp**，周度11个月 **0.1515806409pp**；Normal A/B分别 **0.3014219106/0.3461686160pp**。与旧封存结果一致。

A同支持、真实相邻回访支持、完整波次W1/IQR均与原评价核对；六类粗分组及54格按月输出支持/ESS标记。B、月度和周度没有近期真人微观真值，分歧只描述模拟，不称准确率。

默认按完整十档向量调用冻结缓存并重新做所有权重统计，不读取已存MAE充当复算。本轮还对 **32,500种向量**独立重新运行冻结数值拟合器，通过1e-6pp比对，重新得到相同核心结果。独立重拟合使用v2投影，除模型记录新增复用/费用元数据外，七项数值输入与最终v3逐字节相同，绑定见验收JSON。

## 复算命令

在解压包根，装好 `requirements.lock.txt` 后：

```sh
python studies/sce_inflation_expectations/run.py --mode all
python studies/sce_inflation_expectations/run.py --mode micro
python studies/sce_inflation_expectations/run.py --mode micro --refit-density
```

三条均不调LLM；最后一条是CPU数值拟合，会更慢。all另含20人两步工程例和全国聚合/下游预测缓存复算，三者分开标识。结果写新目录，不覆盖旧输出。

原开发工作区重建：

```sh
python scripts/export_sce_micro_reproduction.py --out outputs/<新的投影目录>
python scripts/build_sce_research_package.py --draft-version v06 \
  --out deliverables/research_package/<新的版本目录> \
  --public-log-registry outputs/sce_submission_experiment_logs_20261027_v4/experiment_registry_public.json \
  --a-refresh-readout outputs/sce_full_a_t0_readout_20261026_v1 \
  --micro-data outputs/<新的投影目录>/data
python scripts/verify_sce_research_package.py --archive <新ZIP> --out <新的验收目录>
```

开发工作区需要原始账本和合法来源；生成微观投影不是从ZIP恢复历史输入。v1/v2投影及检查是开发快照，当前封包绑定v3，不覆盖原件。

## 验证与边界

- 独立解压，异地cwd，移除key环境变量并禁止Python联网；159个study模块均从解压包导入，72项包内测试通过。
- 使用2026-10-27新建、无system-site-packages的独立虚拟环境，本轮复用该环境；不冒称今天重新下载安装依赖。
- 原科学主体146份在仅归类/导入适配归一化后AST一致；冻结计分核哈希仍匹配；744个实际输入源文件和旧v05哈希未变。
- 数据模式扫描未发现原SCE代理键、密钥模式或本机路径。它是针对已知模式的检查，不承诺数学意义的不可重识别。
- 官网条款及SCE专节已核，附署名、非背书与衍生处理声明；[来源核查](source_terms_review.json)。新闻全文、实际作答日、原编号和CE/ATUS/GSS原始个人供体不随包。
- 仅四个最终任务和A/B扩展有逐答卷闭环。开发期试验保留源码与公开日志索引，不声称全部探索HTTP回复均已补入；所有项目发票总账也未在本任务对齐。
- 全波次参考提供冻结标量，不提供每一份原始真人十档回答；因此不声称从原始公开工作簿重算了全部真人密度。选定A配对样本支持其十档核查。
- 没有恢复完整历史新闻版本、重新生成随机LLM输出，严格事前资格也不因此升级。PDF/视频最终封版、上传和公开GitHub是后续动作。

文档收敛：首次v06验收后，将旧写作/视频规划移入包内archive，并保留数据投影时的导出器原件；另建当前ZIP再次通过72测试，数值数据未变。首次候选原件保存在deliverables/research_package/_build_history/v06_candidate01_20261029，不作为入口。
