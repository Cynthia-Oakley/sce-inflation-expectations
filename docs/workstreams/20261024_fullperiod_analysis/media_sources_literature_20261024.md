# 新闻来源与叙事差异：文献核查及Kimi交接

2026-10-24。用户希望并行开展来源探索与原定收尾。本轮只查公开资料，0付费API、0新模拟；82月结果与配置保留。下述候选不代表资料已经下载、许可已经核验或历史版本已经认证。

## 1. 可以支持什么判断？

文献支持三条相邻但不相同的机制：家庭与专家解释经济的方式存在差异；报道的数量及负面语气与通胀预期有关；新闻进入社交平台后，会因用户的选择和转发再次改变构成。它们支持探索多来源信息，不能直接证明“NYT导致了本项目2021年低估”，更不能证明更换媒体就必然改善。

主流/通俗、专业/非专业、左右政治立场、负面/正面、夸张/准确，是不同维度。不要预先把所有NYT文章判为安抚、所有小报或Fox文章判为恐慌，也不要将偏高预测都称作不理性。

## 2. 候选来源与受众证据

### New York Post：美国通俗小报候选

适合检验生活成本呈现、强标题和政治归因。News Corp的[2021年报](https://newscorp.com/wp-content/uploads/2021/08/10-K-Q4-FY-2021-as-filed.pdf)单列Post Digital Network流量，说明它有实际数字受众；该网络包含NYPost、PageSix和Decider，跨站/浏览器/设备可能重复，不得把集团流量当作独立美国读者人数或SCE受访者接触概率。

2021年7月22日一篇涉及Biden再次主张价格上涨暂时性的报道，有明确原始URL线索：
`https://nypost.com/2021/07/22/biden-again-rejects-inflation-concerns-claims-its-temporary/`。
本轮原站工具不可访问，仅核到外部引用；尚不能作为已准备好输入的证据，更不能用于早于其发布日期的窗口。媒体风格可先参考[AP对Post的报道](https://apnews.com/article/77404c3052278c3c2086406e2cee28b2)，后续仍须按具体文章判断。

### Fox News / Fox Business：大众电视与评论来源候选

与小报分开分类。已经读到Fox Business的[2021年秋季文章](https://www.foxbusiness.com/economy/consumer-price-index-september-2021)：标题突出能源上涨及较长时期最大涨幅，正文同时保留政策观点及不同判断。这证明该类内容可存在于同一篇报道，不证明报道失实。

[Pew 2021年3月调查](https://www.pewresearch.org/journalism/2021/03/23/large-majorities-of-newsmax-and-oan-news-consumers-also-go-to-fox-news/)显示，43%的美国成年人称过去一周从Fox News获得过政治新闻。政治新闻接触率不能直接当作财经阅读率；Fox News的受众也不能直接赋给Fox Business。

### Daily Mail / MailOnline：补充候选

可以检查较强标题、个人案例和负面表达；下述Watson等研究包含该来源。它是英国起源的媒体，对美国项目必须筛选美国报道，并另查美国受众及历史文章可得性，不能把英国新闻与英国受众比例直接匹配到SCE。

## 3. 最相关的四项研究

### A. 居民与专家的预期差距：直接涉及2021—2022

Kmetz、Shapiro、Wilson，2022，旧金山联储[《Can the News Drive Inflation Expectations?》](https://www.frbsf.org/research-and-insights/publications/economic-letter/2022/11/can-news-drive-inflation-expectations/)。研究估算，2021年6月至2022年6月家庭与专业预测者预期差距的扩大，约四分之一可由负面报道的增加解释。基于密歇根调查及回归估算，不是SCE试验，也没有单独识别小报作用。

### B. 文章到社交曝光：同一新闻会被再次筛选

Watson等，2024，Scientific Reports，[《Negative online news articles are shared more to social media》](https://www.nature.com/articles/s41598-024-71263-z)。其2019—2021年四家媒体样本中，负面文章被分享到社交平台的可能性约为其他文章的1.91倍。这是一般新闻研究，不能直接用1.91作为我们的通胀参数。

作者提供[数据与代码仓库](https://github.com/JoeMarkWatson/negative_news_sharing)。已核README有data目录，但尚未核实字段、是否含标题/正文/URL、文件大小、原文版权与再利用条件，不能称其为可直接接入的新闻库。

### C. 因果解释影响预期：不只是语气变化

Andre等，[《Narratives about the Macroeconomy》](https://academic.oup.com/restud/advance-article/doi/10.1093/restud/rdag014/8489219)，2026正式版。其研究发现家庭叙事更粗、政治归因更多；随机叙事干预影响未来预期。较早[2022年版本](https://www.econstor.eu/bitstream/10419/258961/1/cebi-wp2118rev.pdf)还报告所分析媒体叙事更接近专家。研究没有将NYT固定为降温端，也指出传统媒体只解释部分差异。

复现包：[Zenodo](https://zenodo.org/records/15311300)。本项目以前已使用其新闻关注问卷；此处核查的是叙事及媒体机制，不重新合成人口。论文发表后的整理和分类只能作研究依据，不能将后来叙事倒灌给2021年的agent。

### D. 新闻曝光量影响预期

Binder、Frank、Ryngaert，2025，[《The Causal Effect of News on Inflation Expectations》](https://www.nber.org/papers/w34088)。使用CNN、Fox和MSNBC新闻及日频预期，以工具变量局部投影估计报道增加带来的影响；正向CPI意外的响应更强。它提供财经报道曝光的依据，不说明某一媒体必然夸大或某种措辞必然提高模型拟合。

## 4. 一个反例与对当前选择器的检查

NYT在2021年10月也发表了突出感恩节成本上涨的报道，作者为Kim Severson。NYT原站本轮受robots限制；可核[署名NYT的同文转载](https://indianexpress.com/article/lifestyle/food-wine/thanksgiving-2021-feast-expensive-wallet-food-7591336/)，其中明确署名New York Times。转载页面不替代原始时点的文本版本或再利用许可核验。

所以先做两项小检查：现有NYT池是否已有生活成本和持续上涨叙事；已有文章在筛选、摘要和实际提示中是否被保留。不能先认定问题只在媒体来源，而跳过选择器与模型如何解释文本。

## 5. 怎样把“光谱”变成可检查的设计？

先按文章而非整家媒体记录三个轴：

- 价格内容：具体生活成本/家庭经历，或宏观统计/政策解释；允许兼有。
- 表达语气：警示、安抚、中性或混合。
- 持续性判断：暂时、持续、不确定或未判断；同时记录归因。

另留source、新闻/评论类型、original_url、published_at、observed_at、text_vintage_status。负面语气与事实错误分别判断；不修改真实数字来制造夸张新闻。

每个人可有0—1的来源混合比例，但当前尚无识别该比例分布的证据。若后续模拟，先冻结简单混合规则与分配种子；人数、新闻量、字数预算、价格和先验保持可比，再讨论人口匹配。Pew政治新闻比例和转发研究1.91都不能直接替代财经曝光参数，不按2021真值挑最优“真实比例”。

## 6. 可转交Kimi的任务：小材料包，不搭新管线

**Codex主线：**继续近期11个月合法P/起点/截止及原定总体评测准备，整合最终报告；负责这条探索的统计设计和主结果边界。

**建议Kimi旁线：**先只取2021-06和2022-06两个既有窗口，每窗10—15篇候选文章，优先Fox Business及NYPost；NYT复用本地缓存。按原as_of筛选，交付URL、原标题、可用摘要、原发布日期、正文版本状态及上述三个轴的人工小样判断。同步检查Watson仓库可复用字段和许可；不用立即下载全库，不调用付费模型、不更动主运行文件。原站不可用就登记缺口，不将镜像抓取时间冒充原发布日期。

先判断是否确实补到了当前提示缺少的内容，再决定是否值得另列小试与预算。新小试如开展，属于看过2021结果后的探索性机制实验；不更换82月主成绩，不把同一时期重试当作独立验证。此文件是可转交任务说明，尚未代用户发送到Kimi会话。
