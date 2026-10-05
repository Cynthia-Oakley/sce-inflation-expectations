# 原文阅读指南：先看与当前瓶颈最有关的部分

核查：2026-10-05。先读[综合综述](literature_review.md)和[改进方案](research_design.md)，无需一口气读完全部论文。下面的顺序服务当前“偏低、过窄”问题；论文结论不能直接充当 Agent 响应参数。

## 第一组：最直接的五篇

### 1. 价格体验：D’Acunto 等（2021）

*Exposure to Grocery Prices and Inflation Expectations*。[作者稿](https://eml.berkeley.edu/~ulrike/Papers/paper_DMOW.pdf)；[本地 PDF](../../../data/raw/literature/sce/20261005/household_price_experience/dmow_author_2020.pdf)。期刊发表于 2021 年，本地作者稿日期是 2020-08-03。

读摘要、数据与指标、购买频率和支出权重比较、局限。重点问题：一份全国物价信息，怎样变成不同家庭接触到的价格？该文使用购买扫描数据，我们只有公开消费支出资料，两者不能当作相同数据。

### 2. 信息实验：Cavallo、Cruces、Perez-Truglia（2017）

*Inflation Expectations, Learning, and Supermarket Prices: Evidence from Survey Experiments*。[期刊全文](https://www.hbs.edu/ris/Publication%20Files/Cavallo_Alberto_J5_Inflation%20Expectations%20Learning%20and%20Supermarket%20Prices_ac98a304-ebe4-426c-93c7-ba7d6f92aae1.pdf)；[本地 PDF](../../../data/raw/literature/sce/20261005/expectation_formation/cavallo_etal_published_2017.pdf)。

先读实验设计与美国结果，再读记忆价格实验。重点问题：官方统计、熟悉商品和可回忆的价格信息，是否引发不同更新？随机供给信息与自然购物经历仍不同；不能直接要求 Agent 模仿某个系数。

### 3. 不确定性与更新：Armantier 等（2016）

*The Price Is Right: Updating of Inflation Expectations in a Randomized Price Information Experiment*。[纽约联储稿](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr543.pdf)；[本地 PDF](../../../data/raw/literature/sce/20261005/expectation_formation/armantier_nyfed_sr543.pdf)。本地稿为 Staff Report 543，2012 年发布、2013 年 1 月修订，非 2016 年期刊排版版。

读随机化、先验概率分布、更新结果与题目措辞比较。重点问题：同一个信号，为何有人不更新、有人明显更新？它也提醒我们分开“个人不确定性”和“人群分歧”。

### 4. 合成调查的风险：Bisbee 等（2024）

*Synthetic Replacements for Human Survey Data? The Perils of Large Language Models*。[期刊页](https://doi.org/10.1017/pan.2024.5)；[本地 PDF](../../../data/raw/literature/sce/20261005/agent_simulation/bisbee2024_synthetic_replacements.pdf)。

先读摘要、模拟与真实调查的分布/回归比较、提示词与时间稳定性。重点问题：为什么总体均值接近仍可能不是合格的社会模拟？其政治调查证据支持评价原则，不证明我们的通胀机制。

### 5. 框架参照：ConsumerSim（2026）

*Uncovering Salience-Driven Dynamics in Consumer Confidence with Generative Social Simulation*。[论文 v1](https://arxiv.org/html/2606.30395v1)；[本地 PDF](../../../data/raw/literature/sce/20261005/socioverse_cases/consumer_sim_v1.pdf)。

重点 §4.2–4.6 与 Appendix F：人口、信息解释、Core/Normal、聚合与校准分别做什么。先辨清原始 LLM 回答与包含校准的最终效果；CCI 回答类别与 SCE 的个人概率密度不同。公开 clean rewrite 也不是原论文全部实验的完整复现，详见[案例笔记](themes/socioverse_cases.md)。

## 第二组：准备体验变量与长期状态时再读

### 6. 长期经验：Malmendier、Nagel（2016）

*Learning from Inflation Experiences*。[作者稿](https://eml.berkeley.edu/~ulrike/Papers/InflExp_4.pdf)；[本地 PDF](../../../data/raw/literature/sce/20261005/expectation_formation/malmendier_nagel_author_2011.pdf)。本地稿首页是 2011 年 3 月；2016 年是期刊发表年。

看经验学习与出生队列比较。重点问题：过去的价格经历怎样留下信念？不能将此直接解释为受访者记住上个月自己的问卷答案，也不能用一年 E 序列冒充终身经验。

### 7. 公开数据桥梁：Johannsen（2014）

*Inflation Experience and Inflation Expectations: Dispersion and Disagreement Within Demographic Groups*。[美联储稿](https://www.federalreserve.gov/econresdata/feds/2014/files/201489pap.pdf)；[本地 PDF](../../../data/raw/literature/sce/20261005/household_price_experience/johannsen_feds201489.pdf)。

重点 §2.2 和数据限制。它用 CE 与 CPI 构造固定篮子指数，是公开数据路线的参照；我们拟议的对数加权代理须单独标明。论文比较人口组，未把同一个人的消费与预期逐笔联结。

### 8. 主体状态与问卷：SocioVerse2（2026）

*SocioVerse2: A Longitudinal Dynamic Social Simulation Framework under a Human-AI Co-evolutionary Paradigm*。[报告 v1](https://arxiv.org/html/2609.24911v1)；[本地 PDF](../../../data/raw/literature/sce/20261005/socioverse_cases/socioverse2_v1.pdf)。

重点 PMI 的 §5.4.2 / Appendix A.7，再看汽车案例 §5.4.3 / Appendix A.8。借鉴“环境 → 主体状态 → 问卷”及对照方式；不要把企业状态、人数或参数直接搬到家庭。校准参与的重建与独立预测分别评价。

## 更完整的主题与来源

- [预期形成](themes/expectation_formation.md)：经验、新闻扩散、信息刚性与随机信息干预。
- [家庭价格体验](themes/household_price_experience.md)：篮子、食品/汽油、住房、家庭分工、数理能力与公开数据。
- [Agent × 经济学方法](themes/agent_simulation.md)：Homo Silicus、实验复刻、概率采样、个体模拟与不确定性评价。
- [平台案例](themes/socioverse_cases.md)：ConsumerSim、消费者信心、PMI、混合舆论、汽车与公开代码的边界。
- [统一来源目录](sources/catalog.json)：28 条来源，保留每篇的读取层级、原文定位、版本和局限。
- [实际归档清单](sources/archive_manifest.json)：本地成功副本、路径和 SHA-256；也保留初次失败记录。

全文受限的两篇预期研究、澳大利亚超市研究和汽油实验的页面预览，已在主题笔记注明证据层级；后续若要依赖详细估计或复刻实验，应补读相应完整版本。现在不能把摘要结论延伸成未经核对的数值算法。
