# 原生SCE支出模块：数据、理论与使用边界

核查日：2026-10-09。对应[进展与小试](../../../SCE_NATIVE_SPENDING_20261009.md)。原始数据及论文统一归档于`data/raw/sce_spending_20261009/`，无个人记录的来源与聚合结果封存于`docs/sources/sce_native_spending_20261009.json`。

## 一、为什么优先这套数据

[SCE Household Spending Survey](https://www.newyorkfed.org/microeconomics/sce/household-spending)是核心SCE的四个月轮换模块。其[微观Excel](https://www.newyorkfed.org/medialibrary/media/research/microeconomics/interactive/downloads/sce-household-spending-microdata.xlsx)包含`userid`、`date`和`qsp5_1`至`qsp5_9`。[问卷](https://www.newyorkfed.org/medialibrary/media/research/microeconomics/interactive/downloads/sce_household-spending-questionnaire.pdf)QSP5要求把月度家庭支出分成九类并使份额合计100。第九类Other自2015年4月加入。

九类分别为住房、水电、食品、衣着个人护理、交通、医疗、娱乐、教育育儿、其他。这是金额占比，不是购买数量、价格涨幅或购物次数。“其他”还可能包括礼物、慈善捐赠等，不能直接套入CPI项目。原表没有支出模块单独作答日期、调查权重或可独立核对的人口字段。

当前下载版覆盖2014-12至2024-12，2020—2024年与核心文件重叠的15,931个人月全部匹配。Briand作者稿也明确连接核心和支出模块的同一家庭。组合证据支持本项目关联；仍须保留表版本和键一致性检查，不能仅凭两个文件都有相似ID就连接。

[2023年修订说明](https://www.newyorkfed.org/medialibrary/media/research/microeconomics/interactive/downloads/sce_jan2023_note_household-spending-series.pdf)指出部分未来分项支出预期记录错误并修订历史序列。它不是本项目QSP5实际支出份额全面受影响的证明，也不能据此声称QSP5完全没有任何修订。我们记录当前下载版用于A回顾研究，不把它当成过去公开的版本。

## 二、三条可操作的文献启发

### 1. 接触价格的频率与幅度需要单独研究

D’Acunto、Malmendier、Ospina、Weber，*Exposure to Daily Price Changes and Inflation Expectations*，2019年NBER工作论文26237，[官方来源](https://www.nber.org/papers/w26237)、[PDF](https://www.nber.org/system/files/working_papers/w26237/w26237.pdf)。研究结合购物与预期，强调日常价格变化的频率与大小，而非直接按支出权重形成预期。

**项目用途：**QSP5先约束家庭消费结构；购物频率和价格接触另找观测或明确代理。不能从“食品占比高”直接推断“每天买菜”，也不能把问卷九类份额乘CPI后称为人类感知通胀。当前统计增量很小，与篮子不能代替全部经历的解释相容，但不证明它是误差的唯一来源。

### 2. 信息干预和问卷措辞都会改变回答

Armantier等，*The Price Is Right: Updating Inflation Expectations in a Randomized Price Information Experiment*，纽约联储Staff Report543，[官方PDF](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr543.pdf)。价格信息实验显示，针对自身所购物品的提问与总体通胀提问，受信息影响的方式不同。

**项目用途：**保持官方Q8/Q9目标和题面，用对照组检验加入个人消费背景的作用。不能为提高拟合而将目标换成个人篮子通胀。完整统计简报可能让模拟成为信息干预，但是否是本项目偏差来源，须用保持事实与题目不变的呈现对照检验。

### 3. 家庭资源约束也可能影响信息需求

Etienne Briand，*Rational Inattention and Real Heterogeneity*，2025年3月作者工作稿，[PDF](https://ei.cerge-ei.cz/pdf/events/papers/Briand_paper.pdf)。该稿合并核心SCE与支出模块，并以收入损失下的支出/储蓄/借款选择研究家庭资源约束与预测误差。

**项目用途：**收入、资产与就业可通过财务约束影响信息需求，而不是必然与通胀预期无关。这提供下一步经济学机制候选；本轮不同时加入该问卷字段或强制注意力函数。该稿是工作论文，代理分类也有假设，不能把家庭类型视为无误测标签或从其理论模型直接移植LLM参数。

## 三、A与B怎么使用

**A回顾重建：**原生QSP5可用于同户验证、先前一至四个月的个体消费线索或同月结构研究。原生篮子优于CE供体的一点是无跨调查家庭匹配，但仍有自报误差、缺失选择和日期精度限制。5/6月小试均用4月份额，不称当月实测篮子。

**B实时预测：**只用截止前确实公开的版本估计“人口特征→联合消费份额分布”，从该分布抽取整个向量并保留不确定性。不能直接使用预测月的真实ID、真实画像或未公开支出。2024-12以后没有此文件的真实篮子观测，稳定性需跨波次验证，不能凭四个月频率断定永远平稳。

## 四、下一项机制开发的判断顺序

1. 先核验原生篮子三组小试：正确匹配是否优于错配；不要先改模型或调整答案偏移量。
2. 如果只增加数字而没有匹配增益，优先研究共同背景与价格接触的表达，不扩张Core数量来掩盖机制问题。
3. 如果出现匹配增益，追加独立月份与重复生成，同时检验分组差距、全国层面拟合和样本缺失处理。
4. 后续个人信息视图应允许共同背景、多个消费品类和不同更新频率。上次单品类遮罩提高分散但未改善准确度，因此不直接再次采用“一人只看到一类信息”。

证据分层：官方文件决定字段与时点；真实微观统计检查相关模式；理论提出机制；LLM对照检验模型是否响应。四者不能相互替代。
