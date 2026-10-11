# 为什么居民不同，为什么概率答案不同

核查日：2026-10-12。只使用原始论文、作者原文和调查机构资料。以下“发现”是文献证据，“项目启发”是本项目的推论，不代表已验证模拟机制。

## 一、先分清我们的三个问题

1. **人和人之间的看法差异：** 有人预计涨2%，有人预计涨7%。这是当前模型最明显的缺口。
2. **每个人对自己的判断有多确定：** 两人都预计涨3%，其中一人很确定，另一人觉得0%至8%都可能。
3. **怎样把看法写进问卷：** 一人愿意填1%、3%、7%等细数，另一人习惯填0%、5%、10%。这也会改变计分结果。

已有四时期实验中，模型个人中心的人际中间50%跨度约0.72个百分点，真人约5.78；模型个人不确定程度在人群间的跨度约0.40，真人约4.25。模型一般填写8—10个非零档，真人中位数4个。但真人平均通缩概率高于模型，不能靠删掉所有通缩尾部来“修好”。详见[已有诊断](../belief_proxies/confidence_response_diagnostic_20261012.md)。这些是机制研究样本，不是全国普遍规律。

## 二、生活经历影响预期：与你的想法最直接相关

### L01 — Malmendier & Nagel：Learning from Inflation Experiences

发表：2016，*Quarterly Journal of Economics*，131(1)，53–87；[作者论文](https://eml.berkeley.edu/~ulrike/Papers/InflExp_44.pdf)为2013-04-04草稿，[发表目录](https://eml.berkeley.edu/~ulrike/research.html)核验期刊信息。

**发现：** 研究美国密歇根消费者调查的长期数据。个人一生经历过的通胀有助于解释预期差异；年轻人的经历较短，近期冲击在其中占比更大。论文用随年龄变化的学习更新率描述这种机制。

**项目启发：** 年龄不应只有“45—60岁”标签，也可以对应此前经历过的物价环境。它提供了扩展P的理论依据。

**边界：** 全国历史CPI只能代表年代环境，不能还原每个人的购物、移民或家庭经历。不能由此规定老年人的预期必然更高，也不能只靠年龄解释同龄人的分歧。

### L02 — D’Acunto, Malmendier, Ospina & Weber：Exposure to Grocery Prices and Inflation Expectations

发表：2021，*Journal of Political Economy*，129(5)，1615–1639；[作者论文](https://eml.berkeley.edu/~ulrike/Papers/paper_DMOW.pdf)为2020-08-03草稿。

**发现：** 将购物记录、价格与个人预期联结。购买频率比单纯支出占比更能解释价格体验的作用；涨价与降价的影响也不对称。

**项目启发：** 这支持保留家庭价格体验方向，但CE支出份额不能自动替代购买频率。需要区分“买得贵”和“经常看到这个价格”。

**边界：** 论文的细购物记录不是我们已取得的数据。它并不证明给模型一句“更关注经常购买的商品”就能复现居民，也不能为任意的频率、涨价权重提供数值依据。

## 三、人格可能影响同一信息的解释，但需要数据

### L03 — Roderweis & Toplitsch：From traits to rates: How personality shapes inflation expectations

2026-01-20，OeNB Working Paper 272；[央行原文](https://www.oenb.at/dam/jcr:5d1a8cce-c813-40e2-8a6a-b62535ea3321/wp-272.pdf)。使用2023奥地利HFCS，调查在2023-03至2024-02进行，净样本2,849份，以25个项目提取大五人格。

**发现：** 人格解释了部分常规人口特征之外的预期差异；开放性较高者与较高通胀预期相关，不同人格对政策信息的反应也有区别。论文的“增加70%”是相对于人口特征模型的已解释方差增加，**不是解释了全部差异的70%**。

**项目启发：** 人格不只是让答案更分散的修饰词，可能影响对历史物价与政策的理解。我们可以提出可检验的假设。

**边界：** 这是奥地利观察性工作论文，不能证明改变人格标签会因果性改变美国居民预期，更不能把回归系数直接当作美国P的加减分规则。

### D01 — 美国Understanding America Study：可核查的数据候选

[UAS1调查目录](https://uasdata.usc.edu/index.php?ssid=UAS+1&type=4)列有人格、概率理解、数理能力和金融素养部分，并提供人格/数理能力计分说明。[综合文件说明](https://uasdata.usc.edu/index.php?pid=Comprehensive+File&type=3)也列出人格、认知和人口信息。

**能做什么：** 注册并满足使用协议后，可检查同一个人的人格、数理能力和人口特征是否联合有效，再为合成人口提供参考。

**尚缺什么：** 本轮只核验目录；没有登录、下载微观数据、计算联合样本数或核验历史版本。也没有证明存在可直接联结的同人SCE式通胀答案。不能称“美国人格分配数据已准备好”。

已有GSS2018 HAPPY/SATFIN联合数据可继续作幸福/财务满意状态候选，**不是大五人格或经过验证的乐观量表**。原心理属性目录与已做实验继续保留，不重新随机贴标签。

## 四、概率作答是单独的测量问题

### L04 — Manski & Molinari：Rounding Probabilistic Expectations in Surveys

2010，*Journal of Business & Economic Statistics*，28(2)，219–231；[摘要与正式出处](https://pubmed.ncbi.nlm.nih.gov/20368764/)。

**发现：** HRS概率调查存在取整，而且不同人取整程度不同；可借助同一人在多道题中的作答模式推断报告精度。数字答案应考虑其所代表的概率范围，而不总是当作精确信念。

**项目启发：** 低numeracy标签不一定足以改变模型的填表习惯。可以单独研究概率表达精度，而不是让模型故意算错。

**边界：** 本轮核验摘要及出处；没有逐页审读该文。HRS不是SCE，不能照搬人群比例。

### L05 — Giustinelli, Manski & Molinari：Tail and Center Rounding of Probabilistic Expectations in the Health and Retirement Study

期刊卷期：2022，*Journal of Econometrics*，231(1)，265–281；2020在线发表、2018工作论文是不同日期。[作者原文](https://molinari.economics.cornell.edu/docs/GMM_Rounding_Paper_Final.pdf)、[作者发表目录](https://molinari.economics.cornell.edu/publications.html)。

**发现：** 在HRS2002—2014中，个人取整模式跨期较稳定；许多人在接近0或100时反而比中间区域更精细。

**项目启发：** 概率作答习惯可以作为跨月相对稳定的个人特征，但不能简化成所有人统一按5%取整。

**边界：** 该文主要研究多道0—100概率题，不是十档概率加总为100的SCE分布题。跨题迁移、合计约束都需要独立检验。

### L06 — Bruine de Bruin, Parker & Maurer：Assessing small non-zero perceptions of chance: The case of H1N1 (swine) flu risks

2011，*Journal of Risk and Uncertainty*，42(2)，145–159；[作者稿存档](https://pmc.ncbi.nlm.nih.gov/articles/PMC4267538/)，DOI：10.1007/s11166-011-9113-5。

**发现：** 0%中既有真正认为没有可能，也有将很小概率取整成0的回答。进一步追问细概率有助于区分它们。

**项目启发：** 我们观察到的真人零概率较多，可能部分来自表达习惯，并非模型只要删除所有小概率即可恢复真实信念。

**边界：** 研究的是健康风险；本轮核验公开索引摘要，直接打开存档遇到验证页，未归档全文。不能用它规定SCE的零通缩比例或具体阈值。

### L07 — Tversky & Kahneman：Advances in Prospect Theory: Cumulative Representation of Uncertainty

1992，*Journal of Risk and Uncertainty*，5，297–323；[大学保存的原文](https://psych.fullerton.edu/mbirnbaum/teaching/psych466/articles/Tversky_Kahneman_JRU_92.pdf)。

**发现：** 用决策权重描述风险选择，权重不等同于主观概率本身。

**项目边界：** “人会非线性看待概率”不能直接成为对Q9十档概率进行前景理论变形的理由。我们应优先使用概率调查的测量研究，避免混淆选择偏好与报告信念。

## 五、模型是否真的听懂画像，需要验证

### L08 — Hu & Collier：Quantifying the Persona Effect in LLM Simulations

2024，ACL，10289–10307；[论文与原文](https://aclanthology.org/2024.acl-long.554/)。

**发现：** 在研究中的主观语言任务上，画像提示带来有限但有统计证据的改善，真实属性与回答关联越强，画像越可能有帮助。

**项目启发：** 增加字段之后要验证模型是否稳定响应，不能以“提示里写了”代替机制已经生效。

**边界：** 任务不是SCE，也没有承诺某种人格提示必然恢复真实人群方差。

### L09 — Dominguez-Olmedo, Hardt & Mendler-Dünner：Questioning the Survey Responses of Large Language Models

2024，NeurIPS；[正式论文](https://proceedings.nips.cc/paper_files/paper/2024/hash/515c62809e0a29729d7eec26e2916fc0-Abstract-Conference.html)。

**发现：** 模型调查回答会受选项顺序、标签等表面形式影响。

**项目启发：** 同义改写应作为检验“提示格式有多大影响”的对照。不能把改写带来的差异直接解释为不同居民的差异。

**边界：** 研究的分类调查任务不等同Q9。主实验仍应保持官方题意、档位身份和顺序，避免改写改变了实际问题。

## 六、RFT与我们要做的事有什么关系

### L10 — Touvron等：Llama 2: Open Foundation and Fine-Tuned Chat Models

2023；[原文](https://arxiv.org/abs/2307.09288)，本轮核验§3.2.3。

如果指的是**rejection sampling fine-tuning（拒绝采样微调）**，通常是对一个提示生成多个候选，用奖励模型筛选，再利用选中的答案更新模型权重。它不等于只把提示词轻微改动。

**本项目建议：** 当前先研究有数据依据的不同经历与作答习惯，验证一个基础模型能否响应。若依据当期真实SCE答案挑选候选输出，会把评价目标用于选择结果，不能算独立模拟；格式无效的处理也应另记，不能与按拟合效果挑答案混在一起。

## 本轮结论

你的方向有文献依据，但人格标签、随机措辞、概率表达并不是同一种机制。优先研究“长期经历改变预期”与“报告习惯改变概率答案”；在美国人格数据的联合支持检查后，再决定是否加入人格。下一步具体构造与检验见[讨论方案](discussion_proposals_20261012.md)。
