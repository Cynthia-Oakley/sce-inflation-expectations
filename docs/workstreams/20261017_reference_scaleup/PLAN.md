# 12月扩大验证：执行接力计划

2026-10-17。用户已同意12月×192人×两遍、一套共同参考配置；**新API预算须另报另批**。没有新范围/金额许可前，只做本地准备、公开资料获取和离线检查。

## 固定方向

- 月份：202003/09、202103/09、202206/12、202306/12、202404/10、202503/09。
- 原4月：202206/202306/202410/202509；其余8月为新增当前配置月份。
- 4608次，Flash/.5/关闭思考/max1024/无重试；只reference臂，没有Q1/认知实答/频率新块。
- 官方SocioVerse2引擎；P从完整合格回访者池按年龄×收入分层抽192，权重只评价；本人真上期Q8/Q9与更早摘要，A条件重建，不是B递推。
- 同192真实回答和完整SCE波次两类中心分别评价；旧4/新增8/全12分报；预设48/96子样本0额外API。
- 旧48样本不强保，原轨迹只作历史参照；完整新192同批生成。不用新输出调当前提示、换月或选种子。

## 分工与文件归属

1. 主Agent：新闻包准备/预算确认，reference_validation_preparation.py、分层/权重/子抽样、P/E整合、协议、文档。
2. finance_runtime：reference_validation_runtime.py、run_sce_reference_validation_trial.py、运行定向测试。source pin新/旧runner+export与study非evaluation源码；复用旧dispatch/gate但新无Q1worker。
3. finance_evaluation：evaluation/reference_validation.py、analyze_sce_reference_validation.py及评价测试；完整24真实完成后才读当前真值；支持同样本/完整波次/returner差异分解、基线和子样本。
4. finance_incremental：policy_sources.json、confidence_sources.json、source_receipt.json及data/raw/reference_scaleup_20261017，只下载免费官方资料，不调用模型。

公共DECISIONS与15保护文件不得改动；只主Agent更新NEXT/handoff，所有提交scoped add。旧冻结源不改，不提交个人记录/原轨迹/密钥，不自动push。

## 执行顺序及停点

1. 本地覆盖核查已完成：12月宏观/新闻原档齐，缺4316条新闻标签、8政策简讯、3目标月信心来源。源收据见../20261017_finance_validation/scaleup_coverage.json。
2. 准备新闻缺口请求，沿原8条/批提示和白名单，验证各包无API，报精确文章数/批数/总cap。等待该批明确授权后才分类。
3. 同步补政策/信心，构建人口/严格历史先验/时间标记，目标答案不进入准备和运行。无新闻标签时只可保存draft，不能称完整可运行。
4. 新协议id=sce-reference-scaleup-v1。每月population/environment/simulation_reference/preview_reference/past_private/eligible_ids_private/nested_subsamples_private；links全体2304人月，只评价有userid/weights。
5. 全输入物化后固定来源/实际提示/模型/预算/种子/主评价，跑24官方引擎scripted单元；再给本批4608次范围和预算卡，等待用户明确答复。
6. 授权记录绑定protocolhash/cap/calls，真实运行不重试/不重启已发任务。故障保留现场，若未获新授权则停止补发。
7. 离线复算、原回包核验、定向聚合核对、图表/结果报告及taskboard/handoff；本地保存，不将结果称全国事前预测。

## 当前估价与状态

最近实际调用线性估模拟$5.195688，**不是已冻结cap**。新闻4316条/540批/12包已准备并通过离线检查，保守预留$2.829956、上限$3；用户已明确批准新闻范围和上限，正在运行，无自动重试。模拟仍未授权、真实模拟0。

详细研究方案见../20261017_finance_validation/scaleup_plan.md。若中断，先查看本目录最新receipt与output目录，不重跑已经执行的新闻/模拟请求。

## 执行检查点（2026-10-17）

- 完整192人口/严格历史先验已冻结：outputs/sce_reference_population_20261017_v1，2304人月；12月合格回访者795—1053，设计加权有效样本量约108—132。权重不发模型。
- 8份新增政策/2019、2020原信心来源补齐；source_receipt.json记录免费官方来源和历史版本限制。
- 新reference运行和评价实现完成；38项定向运行/评价检查、3项抽样/协议检查通过。最终物化模块已写好，等待真实新闻标签齐全后生成输入；未冒称已完成24引擎干跑。
- 新闻授权记录：outputs/sce_reference_news_prepared_20261017_v1/authorization.json，用户“同意新闻分类，上限$3”；run_parent=outputs/sce_reference_news_run_20261017_v1。检查每part的state.json，不以进程exit0代替completed。失败保留现场，禁止自动续跑。
- 只允许下一步本地合成/干跑；4608模拟发送范围与最终cap另待用户批准。
