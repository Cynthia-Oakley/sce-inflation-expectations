# SCE 遗漏机制：从属性走到预期形成过程

核查：2026-10-12。性质：证据复核与实现候选，未新增实验、付费调用或正式输入。范围：美国 SCE 一年期 Q8/Q9；不是为恢复 IQR 而任意补人格标签。证据台账见 [sources_missing_factors.json](sources_missing_factors.json)。已读取 AGENTS、交接/任务板、heterogeneity_and_probability、belief_proxies 及既有心理属性、价格体验、政策信任材料；已有年龄、CE 份额、人生 CPI、numeracy、Fed 信心和新闻分配不重复提出为新机制。

**最值得先推进的三项：感知通胀与价格接触、主观因果模型与持续性、近期家庭财务冲击与情绪线索回忆。** 它们连接了“相同客观 E”与“不同主观解释”。按数据准备成本，已有 SCE Q1 的状态审计最快；因果模型可立即做明确标为情景的离线配对；真实购物频率仍要补数据。没有一项已证明能改善当前 LLM 的 SCE 模拟。

下列八类按直接证据与项目增量价值排序。P 指画像/经历，E 指实际可见的信息与信号，B 指注意、解释、更新与问卷作答。A 是披露使用当期观测的后验重建；B 事前预测只能使用 cutoff 前真实已发布的版本。两条线不得混用。

## 1. 感知通胀、购物分工、价格接触频率与注意力

**机制：** 家庭并不直接把公布 CPI 当成自己所见涨价。频繁购买、主动购物、加油或缴账单决定价格接触；近期突出的涨价更容易被回想；局部体验形成“过去一年涨了多少”的感知，再外推未来。消费份额、购买次数、是否本人买东西、感知涨价是四个不同量。

**证据：** D’Acunto 等（2021，JPE）的美国购物记录联结研究表明频率权重和涨跌不对称有解释力，主要是观察关联。Cavallo、Cruces、Perez-Truglia（2017，AEJ Macro）在美国/阿根廷随机给统计与商品价格信息，并操纵价格记忆的显著性，提供“信息/记忆提示改变预期”的直接实验依据；不等于随机改变长期注意力。Aidala 等（2024，JEBO）SCE 实验支持汽油正负冲击不对称，但汽油作用并不异常大，不能把加油设成万能驱动。[JPE 作者稿](https://eml.berkeley.edu/~ulrike/Papers/paper_DMOW.pdf)、[Cavallo 原文](https://www.hbs.edu/ris/Publication%20Files/Cavallo_Alberto_J5_Inflation%20Expectations%20Learning%20and%20Supermarket%20Prices_ac98a304-ebe4-426c-93c7-ba7d6f92aae1.pdf)、[JEBO](https://doi.org/10.1016/j.jebo.2024.01.027)

**P/E/B 实现：** P 单独保存有出处的 household purchase-day frequency、本人购物角色、账单类型；E 只送其接触到的价格变化与 cutoff 前公布的宏观信号。B 先产生内部“过去一年整体涨价感知及主要线索”，再回答未来问卷，内部感知不可用真人同期答案校准。先对照无接触信息、消费份额、频率候选三臂，检查更新方向与引用线索；不要先定涨价加权系数，也不要靠随机加价来制造分歧。

**数据/联合可行性：** 既有 SCE QSP5 是本人家庭份额且已同 ID 审计，仍不是购买频率。CE Diary 的 FMLD/EXPD 可在同 consumer unit 保留人口与逐日开支；BLS 指明可见 EXPNSQDY/EXPNWDY 等日字段，但不能识别谁购买/消费、逐行不必等于独立购物趟数。应先计算“类别购买日数”代理，不能叫 Nielsen trip frequency；两周日记有零购买、记录误差与短期代表性限制。CE Interview 与 Diary 本来是不同样本，不能把前者已有 donor 与后者频率逐人硬连。需要在 Diary 内整行条件匹配共同 X，重新声明合成值；年文件具体首发与历史版本另审，不能直接用 2021 全年日记预测 2021-05。[BLS PUMD 指南](https://www.bls.gov/cex/pumd-getting-started-guide.htm)、[CE 收集方法](https://www.bls.gov/opub/hom/cex/data.htm)

**缺口：** 未取得本人的真实 SKU 价格历史和购物角色；SCE 2023 专题的通胀感知题已见官方汇总，未取得可公开联合匹配的专题微观。[SCE 2023 专题](https://libertystreeteconomics.newyorkfed.org/2023/08/consumers-perspectives-on-the-recent-movements-in-inflation-expectations/)

## 2. 主观持续性、价格水平回落与宏观因果模型

**机制：** 相同价格冲击可被理解成暂时供给阻塞、持久成本转嫁、需求过热或价格将回落。居民可能认为加息提高商家融资成本，专家则先想到抑制需求；这会改变信号的方向、持续时长和个人不确定性。价格水平回落不等于通胀率下降，也不等于衰退。

**证据：** Andre 等（2022，REStud）让美国居民/专家看相同宏观冲击，观察到显著的同信息分歧，随机机制提示能改变被唤起的渠道；这是情景预测实验，不能直接替代正常 SCE Q9。NY Fed SR1037（2022，2023 修订）用 2022/2023 专题发现中长期通缩与价格均值回归信念相关；主要是观察性、三/五年证据，不能宣称一年期因果效应或把所有通缩答案当误解。[REStud 原文](https://doi.org/10.1093/restud/rdac008)、[SR1037 原文，§5/附录B–C](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr1037.pdf)

**P/E/B 实现：** P 若有测量，保存对加息/需求/供给/价格回落的原题信念；E 保持事实完全相同；B 用供给成本、需求、回落等可共存的解释渠道形成预测。无人口分布时只做 unassigned/明确不同渠道的配对情景，标记 synthetic scenario；不得给每人任意抽一个永久经济学派并称全国比例。现有 easing/persistent 离线探针可复用，但需要区分“涨幅持续”与“价格跌回旧水平”。先查看机制响应是否符合情景内容，再看 Q8/Q9 水平、尾部与不确定性，不据真值挑渠道。

**数据/联合可行性：** Andre 作者 [公开复制包](https://zenodo.org/records/5744017) 可核样本、共同 X、原始机制编码与联合支持；2021-11-30 v1 的公开日晚于2021-05/06，当前包也未下载审计，故不能作该两月 B-ready donor。SCE 专题原题/汇总可用于设计，既有项目未取得专题联合微观。同期 Q9c 三年真实答案仍是结果，不能反推一个“持续性参数”放回 P，也不能用真实一年/三年比值初始化。

## 3. 近期家庭财务冲击、流动性压力与情绪线索回忆

**机制：** 相同收入水平下，刚失去收入、付不出账单、遭遇健康开支或家庭预算转差者，可能更关注价格、回想高涨价经历并预测未来更贵。财务压力还改变寻找信息的时间与所用渠道。它是有时间窗的状态/事件；不能直接替换成“此人不幸福”。

**证据：** Taubinsky、Butera、Saccarola、Lian（2026，QJE；早期 NBER32664）将丹麦调查与行政收入联结，收入/财务变化与通胀预测及回顾感知过强地负向共变；补充提示实验支持部分情绪线索回忆路径。行政收入变化没有随机分配，不能写成所有财务压力都有已识别因果效应；丹麦2012–2019主样本与美国疫情年不同。[QJE](https://doi.org/10.1093/qje/qjag032)、[作者原文](https://www.nber.org/system/files/working_papers/w32664/revisions/w32664.rev1.pdf)。本次 NBER PDF 直接抓取403，新增核查只见原机构索引段落；详细样本沿用本仓既有原文读记，未声称重读全文。

**P/E/B 实现：** 首候选为 SCE Q1“目前相较12个月前家庭财务状况”，保留1–5有序原义与 observed_at；健康冲击、债务/应急资金、失业变化须另有真实字段。B 让状态影响检索哪些经历/关注哪些信号，记下被召回的经历；不规定差状况就加几个百分点。比较无状态、真实允许状态、同 X 内置换状态，并对照状态只进注意规则 vs 只作笼统描述，才能检查是否真通过记忆/信息形成差异。

**数据/联合可行性：** 本仓既有 SCE 当期 Q1 与 Q9/X 同行覆盖充分，A 可披露做状态关联与候选；Q2 是未来财务 outlook，属于目标接近的另一项预期，不能包装成固定乐观。SCE core/credit 微观公开滞后9个月，spending等18个月，因此当期Q1、真实欠款概率、同期收入/就业预期都不是 B 事前可见输入。[官方FAQ](https://www.newyorkfed.org/microeconomics/sce/sce-faq)。SHED/NFCS donor 的财务状态、应急能力、债务与共同 X 可同人保留，但不能识别 SCE 的真实冲击。2026 NY Fed 新研究确认2020-05/06曾问食物不足；这证明存在专题，未证明专题微观公开或在2021 cutoff前可得，也不能用2025/26调查倒填2021。[专题说明](https://libertystreeteconomics.newyorkfed.org/2026/05/food-insecurity-and-consumer-pessimism/)

## 4. 实际信息渠道、广播/电视与熟人网络传播

**机制：** 新闻分配决定“给了什么”，还需要渠道习惯决定“接触了什么”、可信度决定“接受了多少”、交流决定“哪些价格故事被重复”。广播/电视是传播载体，并无一般理由硬设其推高/压低通胀。社交同质性可能放大共同经验；重复消息不可被当独立证据无限计权。

**证据：** Cleveland Fed《The Expectations of Others》（2023）用美国2021-02—2023-07 ICIE调查与2016县际Facebook SCI；同类群体网络关系更强，汽油显著信号能经网络传递。作者有全国汽油价格×驾车通勤份额的 shift-share IV 因果解释，但依赖排除共同/直接价格路径等识别假设；不是随机分配朋友、不是逐人真实消息观察。47国2026研究与既有Pew来源材料支持渠道选择关联；不应用其回归系数充当2021美国渠道权重。[Cleveland 原文，§3–5](https://www.clevelandfed.org/-/media/project/clevelandfedtenant/clevelandfedsite/publications/working-papers/2023/wp2322.pdf)、[Meta SCI定义](https://ai.meta.com/ai-for-good/datasets/social-connectedness-index/)

**P/E/B 实现：** P 保存调查原义的使用频率、渠道可信度；E 由实际渠道选择已归档事实，附 source_id 和 published_at；B 保留看见/接受/记忆的区别。网络后续可让已生成、未看真值的 Agent 信号按预登记边与一步滞后传播，比较无网络、相同信息量随机边、同质边；消息必须标为模拟传闻，不能凭空写某受访者朋友说了什么。先处理共同事实重复与传播滞后，不能靠加噪或把真人同月网络均值作为输入“修好”分歧。

**数据/联合可行性：** Pew ATP、ANES 可核共同 X、媒体使用/信任；个体SCE不含已验社交边，合成渠道不等于实测暴露。SCI公开地理边可提供结构参考，却不是每个人的朋友圈；论文 ICIE县数据未取得，本仓SCE公开地理主要state/CZ，不能在没有county映射时直接套县际矩阵。2016 SCI权重用于2021是稳定性假设，当前SCI文件的历史公开日/版本仍待核。2021后研究只可指导今天的机制设计，不可证明历史输入可得。

## 5. 金融/通胀理解、知识自信与更新能力

**机制：** numeracy 衡量计算/概率能力，金融素养还涉及购买力、名义/实际、复利、风险分散；通胀理解包括价格水平和涨幅、统计代表性及政策渠道。客观知识与自信不必一致，知识可能影响选信号与解释同信号两步。

**证据：** Bruine de Bruin等（2010）的美国ALP小样本已有直接通胀关联，客观素养与自信的结果不同。新增 Burke & Manz（2014 JMCB；2011 Boston Fed稿）用实验任务区分选信息和用信息，客观经济素养高者两方面表现较好；素养本身是测量、没有随机给人教育，实验任务也非全国SCE。[原文](https://www.bostonfed.org/-/media/Documents/Workingpapers/PDF/ppdp1108.pdf)、[期刊](https://doi.org/10.1111/jmcb.12144)

**P/E/B 实现：** 保留已有 numeracy，新增知识项必须说明非同义增量；优先让“是否懂代表性/水平与涨幅”影响B对同E的理解，不写“低金融素养→固定高通胀”。客观得分、自信分开；不要给低素养Agent要求故意算错。Cavallo原文显示假设价格数字也能形成虚假学习，所以知识测试的示例数不要直接紧贴通胀问卷当锚。

**数据/联合可行性：** UAS1目录列人格、numeracy、金融素养，是同panel候选，但注册/协议、历史波次、与通胀题联合支持未审。FINRA NFCS2018公开问卷/数据、2019-06报告可查金融知识与财务状态同人共同 X；报告历史发布不等于已取得2019原微观字节。NFCS是网上配额样本，其权重与成年个人总体不能直接替SCE户主权重；不含已验同人SCE通胀密度。先测conditional donor的知识增量与支持，不从教育/收入推定分数。[NFCS 数据入口](https://finrafoundation.org/knowledge-we-gain-share/nfcs/data-and-downloads)、[2018报告](https://finrafoundation.org/sites/finrafoundation/files/NFCS-2018-Report-Natl-Findings.pdf)

## 6. 党派、政府/统计机构信任与表达性回答

**机制：** 政党认同可能影响相信哪种经济叙事、如何评价执政政府、是否接受统计或政策承诺；同时部分问卷回答可能表达政治立场，未必是用于实际支出的信念。Fed信心、政府信任、新闻信任和党派是不同变量，不能互作替代。

**证据：** Binder/Kamdar/Ryngaert（2024）的疫情期美国党派差异与冲击响应是直接通胀证据，但党派没有随机赋值。NY Fed作者2024 JME comment补充SCE，指出党派预测差距的一部分可能归于战略性作答。Binder/Couture/Smit（2025）也报告Fed信任不能充分解释党派差距，2025方向反转可作固定符号规则的反例。[疫情论文](https://www.nber.org/papers/w32650)、[SCE comment](https://www.sciencedirect.com/science/article/abs/pii/S0304393224001120)、[Fed信任论文](https://www.nber.org/papers/w33684)。两份NBER直接访问403，具体结论沿用既有读记与作者/期刊信息，不宣称本轮全文复核；comment仅核查期刊摘要，未审完整识别设计。

**P/E/B 实现：** 只在党派与具体来源联合支持后测试党派×政策来源/内容；未知和independent/leaner保持原题分类。把“对政策的预期”与“问卷表达方式”分成两个候选B路径，不能把党派分歧全当真实宏观信念；也不能给某党固定加减通胀。县/州投票比例只能当地区环境，不能决定个人党派。

**数据/联合可行性与新核查：** ANES官网明确2021-02-11发布2020 pre-election preliminary、2021-03-24发布合并pre/post preliminary，2021-07-19才full release。因此ANES2020不是整体不可用于2021-05；可考虑的是需取得、核字段、留哈希的3月初版。当前2022版不能冒充初版。ANES面向eligible voters而SCE是household heads；公民/选民总体差异和共同X支持必须单列。Pew ATP波次/发布与账户访问继续依既有核查，不能把访谈月当发布时间。[官方历史公告](https://electionstudies.org/updates-announcements/)、[2020数据页](https://electionstudies.org/data-center/2020-time-series-study/)

## 7. 幸福/乐观、人格、风险偏好与主观不确定性

**机制：** 理论上可以影响检索、可信度、关注范围和是否愿意给窄预测；一般乐观并不必然降低通胀，因为对需求旺盛的乐观可抬高预期。风险偏好影响选择，不等同主观概率；健康/幸福状态也不等同长期人格。

**证据：** 新读OeNB WP272（2026）确认奥地利2023 HFCS人格与通胀水平/锚定的直接关联；“70%”是相对于人口模型已解释方差的增量，绝非解释总差异70%。横截面相关、奥地利高通胀背景、不同测量不能移植为美国系数。既有幸福文献更多研究通胀经历→满意；未找到稳定幸福/乐观→美国一年期Q9的可靠独立因果证据。[WP272](https://www.oenb.at/dam/jcr:5d1a8cce-c813-40e2-8a6a-b62535ea3321/wp-272.pdf)

**P/E/B 实现与数据：** GSS2018 HAPPY/SATFIN在本仓已核联合，是当时有序状态，不是大五；无需重做已有幸福 donor。UAS人格候选、HRS50+乐观/心理测量、MIDUS队列需按已有准入规则审历史版本和同人X。若后续做单项增量，保持原量表/有序选项、与近期财务变化分开，并报告分配不确定性。SCE QRA1/2风险意愿只对新入组原答，carry-forward需同ID依据且保持缺失；不得用“风险厌恶”直接扩大/缩小Q9。当前不建议把本类作为首轮新增主轴。

## 8. 宗教参与、文化/社群与代际传播：证据缺口，后置

**机制假说：** 宗教社群可能提供共同新闻、互助及信任网络，文化/家庭可传递价格经验。可检验的对象应是实际交流、社群参与与传播内容；宗教名称本身不能确定其成员对价格、政策或未来的观点。

**证据边界：** Guiso/Sapienza/Zingales《People’s Opium? Religion and Economic Attitudes》（CEPR2002）使用WVS研究宗教与合作、政府、节俭等一般经济态度，属于相关性，未测/识别本项目一年期通胀信念。此次原机构/作者检索未找到可可靠外推到美国SCE的宗教→通胀预期直接证据；这不是证明效应为零。[CEPR原研究摘要](https://cepr.org/publications/dp3588)

**P/E/B 实现与数据：** 当前不加入宗派对应的通胀系数或“信教者更乐观/更信政府”等提示。GSS宗教归属/参与题、WVS信任/态度可以作为未来同人联合支持候选，但GSS2018与HAPPY/SATFIN共同ballot、样本、细宗派稀疏性、历史权重未新增行级核查；WVS跨国波次不是当月美国户主分布。若有实际参与/渠道记录，可把参与影响接触概率，内容经第4类网络机制进入；宗教身份不得用年龄/族裔/地区硬推断，也不能依据真实通胀答案分配。未有直接测量前只留为研究问题。[GSS数据入口](https://gss.norc.org/get-the-data.html)

## 历史可得性纠错与准入条件

**SHED年份证据需纠正后才继续：** 当前Fed数据页中2021-05-07新增state identifier说明在**2018** Survey Documentation下；既有data_feasibility将它用于2019候选，不能继续当2019在2021-05可得的证明。2019页面只见2020-12添加跨年ID说明，当前文件又有2026-06修订。它不证明2019不能用，只说明需找独立2019发布日期/原版本。此次未改既有文档。[Fed原页](https://www.federalreserve.gov/consumerscommunities/shed_data.htm)

每项输入至少登记construct、原题/单位、observed_at/reference_period、published_at、vintage、as_of、scope与observed/synthetic/scenario状态。注册后可下载≠已获取，已获取≠同人联合有效，当前字段存在≠历史月份可得。跨调查合成仅保留 donor 内已观察的相关结构；GSS、CE、ANES、SCE之间未观测的联合结构不能由同年龄/收入匹配识别。

**先做三项小交付：** (1) 在已有SCE文件离线审Q1与Q9分布的增量关联，明确A；(2) 原easing/persistent探针补主观渠道定义和价格水平/涨幅区分，保持人口比例未知；(3) CE Diary仅做purchase-day代理字段/联合X/历史版本审计。之后再决定机制臂，未通过数据准入者留在情景研究层。

冻结评价前不得按目标Q8/Q9选择或估计 persona；不得用同期其他商品预期、Q9c或未来财务预期当“心理知识”倒灌。每次只增加一个机制族，使用相同P/E/模型与生成重复，另留同标签置换/同信息量对照；分别报告水平、个人Q9不确定性、人际分歧和概率报告质量。更宽IQR不是成功判据，固定方向和跨月响应是否合理比标签数量更有诊断价值。
