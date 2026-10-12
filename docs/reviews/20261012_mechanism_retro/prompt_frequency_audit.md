# 等价提示与购买频率：实现核查及下一步

核查日：2026-10-12。只读代码、现有产物与一手来源；本轮新增真实LLM调用0，未改配置/计分器，未提交。来源及文件哈希见 `prompt_frequency_audit.sources.json`。以下“已实现”不自动等于“正式采纳”。

## 1. 已做到哪一步

**本轮三种中性等价开场：草案＋实际提示离线准备，未真实交叉运行、未正式采纳。**

- `docs/literature/sce/heterogeneity_and_probability/prompt_template_candidates_20261012.json` 明确是文档草案，`integration_status=not_connected_to_current_provider`。`prompt_variant_plan_20261012.md` 和 `prompt_variation_practice_20261012.md` 是方案。
- 不止占位检查：`studies/sce_inflation_expectations/lifetime_trial_preparation.py:66` 从候选模板抽取三种开场，直接前置于同一完整消息；`outputs/sce_lifetime_trial_draft_20261012_v3/template_probes_private.json` 已有6人×3模板＝18份实际预览。本轮复核：每人三份移除开场后正文逐字相同、事实正文哈希及问卷后缀哈希相同。**这证明受控文本差异，不能凭哈希证明语义等价。**
- 同目录 `trial_manifest.json`：`template_candidate_calls=36`、`new_api_calls=0`、状态为未授权消息草案。早期 `outputs/sce_age_source_followup_20261012_v1/template_validation.json` 只验占位块结构，不能替代完整提示审阅。
- 后续已有真实 lifetime 运行，但 `lifetime_trial.py:54` 读取的是 `main_cases_private.jsonl`，没有读取模板probes。`outputs/sce_lifetime_trial_20261012_v2/trial_manifest.json` 与 `outputs/sce_lifetime_text_trial_20261012_v1/trial_manifest.json` 各登记288次真实调用；相应24个 `outputs/local_runs/<trial>-<month>-<arm>-r<repeat>/llm_calls.jsonl` 各合计288行。前者改变历史事件匹配，后者对比原有/数值/文本历史；**文本压缩会改变信息，不是本轮三模板的同事实措辞试验。**

**旧答题视角改写确实实现并运行过，但不能替代严格等价检验。**

- `experience_mechanism.py:134` 的 `build_mechanism_messages` 修改两个标题，新增“按家庭受访者作答、过去价格并非未来所需答案”的行为说明。保留公共事实及问卷，但同时动了答题框架，不能只称中性格式扰动。
- `outputs/sce-experience-trial-20261006T080038Z-594845/trial_manifest.json` 对应两月五臂200条真实回答；`expression_shared` 臂各20条、合计40条，其两个 `outputs/local_runs/...-expression_shared/llm_calls.jsonl` 和 `run_manifest.json` 均存在。温度0；不是当前温度0.5的模板交叉实验。
- `docs/PRICE_EXPERIENCE_PILOT_RECEIPT_20261006.md:27`：仅答题视角使Q9跨人IQR在5月0.851→0.223pp、6月0.994→0.118pp；个人MAE一月改善、一月略差。旧改写没有解决同质化；不能以“更多模板”预设成功。

**购买频率：Diary日数解析已实现并实际物化；未接入行为组件，未发现真实频率试验或路线B使用。**

- `diary_experience.py:35` 定义 `EXPNSQDY`、`EXPN_QDY`；`:755` 输出 `purchase_day_support`。在同季度精确NEWID连接FMLD/EXPD，仅用正金额、`PUB_FLAG=2`、有效日码1—7及有效标志D/E/T去重。
- 最终 `data/interim/ce_experience/20261006T071002778274Z_ce_diary2020q4_4862a21e/diary_weekly.jsonl` 实际2835个CU-week；本轮重新计数：2455完整可用、136部分日支持、121无正发布金额记录、123无EXPD记录。manifest状态是离线代理；不是空配置。完整可用日数分布1—7分别424/380/399/399/347/293/213周，仅描述样本，未加权。
- 它是**跨全部类别的出现日数**。当前没有按类别日数，不是每天购物几次、交易数、商品数量、真实注意力或全年习惯。现有源码检索 `purchase_day_support`/`distinct_days_with_positive_published_cost_records` 仅命中生产脚本与测试，没有决策读取方。
- `information_exposure.py:34` 用CE Interview的食品/汽油/住房份额归一化抽通道；`...sce_exposure_trial_20261006T150949Z_533cc2be/trial_manifest.json` 与六个真实调用文件合计288行。它检验单通道信息匹配，不是Diary频率。`price_contact.py` 的地区汽油/全国食品补充真实160条，也未输入购物频率。旧 `PRICE_EXPERIENCE_PILOT_RECEIPT` 明示未用Diary。
- 原生QSP5份额模块 `native_spending.py:74` 明示不是购物频率。`outputs/sce_native_spending_trial_20261009_v4/trial_manifest.json` 是 `prepared_not_run`，六job均 `not_run`；32人×2月×3臂192提示已准备，不能称真实QSP5模拟已完成。与之分开的真实SCE支出统计研究已完成。

## 2. 理论如何对应实现

**等价措辞应是稳健性控制。** [FormatSpread一手论文](https://arxiv.org/html/2310.11324v2)检验不改变含义的格式变化，支持报告跨格式敏感性；它的分类任务结果不保证SCE改善，也不能证明现有自然语言开场等价。建议保留一份规范P/E，在独立渲染器只换中性开场/标题。角色、数字、单位、日期、精度、新闻原文、央行信心强度、Q8/Q9原文及档序、输出约束、块顺序逐字锁定；不新增概率取整、人格、情绪或注意指令。

用户此处的RFT指 **rejection fine-tuning**。按 [Llama2 §3.2.3](https://arxiv.org/html/2307.09288v2)，它生成多个候选、评分筛选，并用筛选回答更新权重。当前模板改写与事实一致性筛查都不更新权重，不是RFT；推理时挑“最像SCE”的候选也会改变分布，不能当自然个体差异。真正RFT另需训练集、奖励标准、训练/评价时间隔离及同P/E模型对照。

**购买频率需要另一个观测层。** [D’Acunto等作者稿 §III.C–D](https://eml.berkeley.edu/~ulrike/Papers/paper_DMOW.pdf)用扫描购买数据建立Frequency CPI：基准频率权重是基础期12个月各商品购买总数量，购物行程中购买比例是稳健性替代。它区别于支出金额份额，也区别于CE七天出现日数；不能直接套其系数、把高食品份额解释成每天买菜，或将代理机械乘CPI当必须回答的预期。

[NYFed QSP5问卷第2页](https://www.newyorkfed.org/medialibrary/media/research/microeconomics/interactive/downloads/sce_household-spending-questionnaire.pdf)观测月度九类支出百分比。QSP3是过去四个月是否发生某类大额购买，也不提供日常食品/汽油购物次数。当前未取得联结SCE个人的交易级数量、价格、购物责任或价格注意力。论文扫描数据不是项目已持有的数据。

[BLS官方指南](https://www.bls.gov/cex/pumd-getting-started-guide.htm)说明Diary/Interview来自不同样本；Diary是连续两周、逐周权重。不得把Diary NEWID接成既有Interview donor或SCE真人身份。当前2020Q4代理的可得证据是 [2021-09-09发布稿](https://www.bls.gov/news.release/archives/cesan_09092021.htm)“不晚于此日已可用”，非首次发布日期；本地文件含 [2022-03-10修正](https://www.bls.gov/cex/pumd_errata_2019_2020.htm)。用于2021-05/06只能明确标A事后合成代理；路线B须另取截止前资料及版本证据。换旧年本身也不自动通过可得性验收。

## 3. 最便宜的下一项：同人×模板交叉，36次候选调用

**建议方案；本轮不执行，也不把现有草案称可直接运行。** 使用已封存6人（202203三个年龄组各2人）×3中性开场×2独立生成＝36次冷启动；P/E和所有既有模块逐字相同。先人工审阅18份完整预览，若开场隐含新态度则在调用前淘汰/重写并重新封存，不按真实答案淘汰模板。

需补一个独立decision adapter，复用 `SCEDecision` 的请求/解析/费用审计，只在 `build_llm_messages` 前置冻结开场，并验证生成正文与封存正文一致；或做独立冻结消息回放入口。**当前lifetime runner不读probes，旧reuse/model-counterfactual runner又钉死240/40条与模型，不能伪装现成命令可执行。** 新入口先替代客户端/规则干跑，明确输出case_id、person_id、template_id、repeat、事实/问卷/message哈希及真实返回模型。

调用按“人×轮次”分块，三模板顺序按登记种子随机化；冷启动防前一模板回答影响后一模板。模型/目的地、温度0.5、max_tokens1024、无自动重试一致；轮次不假称供应商采样seed。用同批新生成，不能拿旧温度0或旧历史消息补作基线。个人是6个，模板/重复副本不是新增人口。

现有draft manifest按历史输入$0.30、输出$1.20/百万token与保守字节上界登记36次预留$0.1243206；这是旧费率工程预算，不是当前报价/账单。建议新上限$0.25，执行前复核实际费率、上下文与发送范围并另登记授权；如预留超过上限先缩设计或重新讨论，不能消耗旧授权。本轮新增费用0。

**测量/验收与停止标准（建议工程阈值，非文献估计）：**

1. 开跑前18/18正文、所有数字及问卷/输出文本一致；人工语义审阅全部通过；干跑36/36映射与格式有效。任一事实漂移停止，不能“近似相同”放行。
2. 真调用任一输入漂移、返回模型变化、未知费用或格式错误即暂停；无自动重试、不择优回答。预算达到预留界停止，保留所有原包；未完成不报完整比较。
3. 主检验先不看SCE真值。逐人比较模板均值差、同模板两次差；报告Q9中心、原始通缩概率和个人密度宽度的全部差异。设Q9中心逐人跨模板最大差的中位数≤0.25pp，六人群体中位数跨模板范围≤0.25pp；同时对比同模板重复差，不以比率在零方差时除零。
4. 若模板变化大于同模板重复波动，且超过上述阈值，判为格式敏感，停止把模板当异质性来源；若均在阈值内，仅说明这一小样开场差异有限。两次生成统计功效有限，不报告“证明等价”。完整结果后才用同计分器补看SCE误差，展示所有模板，不以最接近真值选赢家。

**固定个人模板与交叉随机化的识别差别：** 给每人固定模板并跨月沿用能减少月间重抽，但模板效应与个人固定效应混在一起，可能制造持久但无现实依据的差异。上述同人交叉能分开格式变化与个人事实，重复生成提供噪声参照；之后若保留多模板，按与P/答案无关的预登记种子分配，并用多次独立分配评估敏感性。模板比例是实验约定，不能称美国表达风格分布。主结果无需靠随机模板扩大方差。

## 4. 购买频率的可行路线：先零API补测度，再单独小试

最先可执行的是离线数据扩展，而非写“你更关注经常买的东西”：从现有Q4 EXPD和官方UCC映射输出 **居家食品/外食/家用日用品/个人护理** 的 `recorded_days_7d`，保留D/E/T与金额发布口径、缺失状态及全部源行哈希；类别无有效正支出行与已确认未消费分别解释。仅在源支持完整时报告精确数，部分支持报告下界/缺失，不填成零。验收每类0—7、每类日集合是总日集合子集、全类别并集复现旧总日数；各类可能同日发生，所以分类日数之和可以超过7。不得将周数据乘52变年度购买频率，不把EXPD行数当交易数。

随后用Diary自身人口字段建立带权联合供体分布，按现有画像支持匹配整条“分类金额＋出现日向量”，保留供体池大小、回退、缺失、不确定性和两周相关性诊断。它仍是另批CU的合成代理；不能把Interview篮子和Diary日数按ID拼成一户实测，也不能给每个人自动指定真实购物责任。总日数不足以决定食品/汽油/住房三通道路由；住房付款日尤其不是天天看房租的频率。

若离线支持足够，另登记12人×2开发月×（不显示代理/条件匹配代理/同库存固定置换代理）×2独立生成＝144次的小试。所有组保留共同宏观/新闻，新增代理单独侧车及明确合成说明，**该试验有意改变代理输入，不属于等价措辞**；不固定“频率→注意力”系数，不改问卷/概率风格/计分。主要比较匹配与置换的Q9中位数误差、W1、IQR差距，原始通缩概率/Q8次要；每个重复独立报告。建议只有两个月两重复的前两项均改善、且IQR差距不恶化才登记新时期确认；若只增加分散、匹配不胜置换或数据支持不足则停止升级。这里只检验合成接触线索是否有用，不能宣称真实购买频率的因果效应。144次设计尚无配置、预留/新预算/发送范围或独立留出登记，不运行。

本轮只新增本报告和来源JSON。15份待审保护文件核查仍为15/15原哈希；公共文档与现有运行不修改。
