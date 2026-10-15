# 信念更新与价格体验：这轮设计采用哪些依据？

核查日：2026-10-15。一手论文与本项目推断分开记录。本轮没有新的付费调用。

## 1. 同样的信息，本来就可能让居民回答更接近

Armantier、Nelson、Topa、van der Klaauw、Zafar，*The Price Is Right: Updating of Inflation Expectations in a Randomized Price Information Experiment*，纽约联储Staff Report 543。已核对官方摘要与PDF的更新结果、结论段；主页列初稿2012-01、修订2013-01。

随机提供信息后，预期分布向中心收敛；更新与信息强度、原有信念的精确程度有关。**因此，不能把所有收窄都判为错误。**我们现在提供较完整的统计信息，更接近一次信息处理实验，与居民自然作答时掌握的信息不完全相同。后一句是项目设计的类比，不是对当前同质化原因的因果证明。

设计含义：同时评价总体中心、跨人分布和个人更新；不为了扩大方差而强制保留所有历史差异。不直接把不确定性转成一个固定的“更新权重”。

来源：[官方论文页](https://www.newyorkfed.org/research/staff_reports/sr543.html)；[PDF，特别是更新与先验精度段及结论](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr543.pdf)。

## 2. 同样的事实，也可能被不同居民解释成相反的方向

Andre、Pizzinelli、Roth、Wohlfart（2022），*Subjective Models of the Macroeconomy: Evidence From Experts and Representative Samples*，Review of Economic Studies 89(6):2958–2991。已核对出版社正文引言与情境/线索实验设计。

在相同冲击与历史事实下，家庭和专家的判断仍有显著差别；人们联想到的成本、需求等传导渠道与判断有关。情境线索实验表明，提醒某个渠道可以改变理解。它支持研究“如何理解E”，也提示整段通胀历史未奏效，不等于事件触发的记忆无效。

设计含义：下一候选固定事件、个人起点及价格，只改变一个理解线索。论文的情境回答比例不是可直接迁移到SCE每月的固定人格比例；先做受控情景，不任意给美国人口分配“成本派/需求派”。

来源：[出版社正文，尤其§2与§4](https://academic.oup.com/restud/article/89/6/2958/6531988)；[DOI](https://doi.org/10.1093/restud/rdac008)。

## 3. 购买频率有依据，但频率数字不是完整的价格体验

D’Acunto、Malmendier、Ospina、Weber，*Exposure to Grocery Prices and Inflation Expectations*。本轮复查NBER摘要及作者研究介绍，沿用此前项目对正式论文的核查。

研究把家庭实际购买、价格变化与预期关联起来，强调接触频率和价格变化幅度的作用。它没有证明：给LLM补一个跨年家庭周的购买日数标签，就会降低SCE拟合误差。我们仍缺少具体商品、实际店铺/价格及谁承担采购的信息。

设计含义：继续改善联合匹配，但保留“无频率/匹配频率/置换频率”的干净对照。频率、价格及持续性解释分别变化；不把所有差异混在一段提醒里。

来源：[NBER工作论文26237](https://www.nber.org/papers/w26237)；[正式论文DOI](https://www.journals.uchicago.edu/doi/10.1086/713192)。

## 4. 人口特征匹配得再细，也不等于恢复了个人真实通胀

Kaplan、Schulhofer-Wohl，*Inflation at the Household Level*。本轮仅核对NBER摘要层面的结论，没有声称重现其微观估计。

家庭经历的价格变化存在大量差异，其中很大部分与可观察人口特征并不对应。这支持把“供体匹配可信度”与“恢复个人真实体验”分开评价，不能声称细收入、年龄、家庭规模足以还原真人购物环境。

来源：[NBER工作论文22331](https://www.nber.org/papers/w22331)。

## 5. 信息更新缓慢是合理候选，不能从短面板硬算心理参数

Coibion、Gorodnichenko（2015），*Information Rigidity and the Expectations Formation Process: A Simple Framework and New Facts*。本轮核对AEA摘要/论文信息，未逐页复现原估计。

它为信息处理摩擦与状态依赖提供研究依据。它不直接给出SCE个人应当更新几成，也不能让我们把现有短样本回归系数叫作因果心理权重。

来源：[AEA论文页](https://pubs.aeaweb.org/doi/10.1257/aer.20110306)。

## 对本项目的共同约束

1. 文献帮助提出可检验机制，不替新模拟保证效果。
2. SCE相邻月的未来12个月窗口重叠11个月，但并非同一个预测目标。月间变化同时包含窗口前移及信息更新，不能全部解释成固定目标的贝叶斯修正。
3. “早已公开”不等于这个居民早已知道；时间标签只证明可得性。
4. 真正的改善需要中心、分布和更新共同评价，并在未参与调整的时期复核；不以方差增加代替成功。

落地与复算见：[本轮准备记录](../../../workstreams/20261014_mechanism/belief_update_and_matching_preparation_20261015.md)。
