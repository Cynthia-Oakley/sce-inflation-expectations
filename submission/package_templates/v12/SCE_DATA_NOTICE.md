# Survey of Consumer Expectations：来源与衍生处理

Source: Survey of Consumer Expectations, ©2013-2020 Federal Reserve Bank of New York. The SCE data are available without charge at https://www.newyorkfed.org/microeconomics/sce and may be used subject to license terms posted there. The New York Fed disclaims any responsibility for this analysis and interpretation of Survey of Consumer Expectations data.

Some survey questions were taken or adapted from the Survey of Consumer Expectations, ©2013-2020 Federal Reserve Bank of New York. The SCE questions are available without charge at https://www.newyorkfed.org/microeconomics/sce and may be used subject to license terms posted there. The New York Fed did not participate in or endorse this SCE simulation study, and the New York Fed disclaims any responsibility or legal liability for the administration of the survey and the analysis and interpretation of data collected.

使用条款：https://www.newyorkfed.org/privacy/termsofuse ，2026-10-29核对。条款的Permissible Use、Conditions以及SCE专节一并适用；本研究不对来源数据附加比来源条款更严格的许可。

本目录是本研究生成的最小复现投影，**不是纽约联储原始数据文件**：移除了原编号与身份映射，输入层保留来自公开调查、且实际进入Prompt的日期；人口权重有研究抽样/校准权重与原调查权重之别；个人密度分数使用已声明的冻结近似算法。它们不应被称为纽约联储官方个人拟合算法的输出。全国首发目标与项目同算法微观比较分别标识。

来源变量来自官网公开SCE微观数据及全国指标，原下载来源和哈希由作者来源账本保留。字段选择、匿名编号、权重校准、模型回答、Normal扩展、误差计算和所有解释均由本研究负责。来源内容仍适用上述条款，不暗示纽约联储背书。

本包不附完整新闻原库或GSS/ATUS/CE原始个人供体。已选NYT新闻摘录与脱敏Prompt在inputs目录，仅供赛事保密评审；不授予公开再分发权利。数据再生成与许可恢复步骤见包根 `PRIVATE_INPUTS_REQUIRED.json`。


实际输入层：`reproduction_data/inputs/README.md`。完整自备Key入口为包根 `review.py`（委托study内reviewer_pipeline）；单步预览仍保留reviewer_request.py。方法与命令见PORTABLE_REPRODUCTION.md。此ZIP包含第三方新闻摘录，仅供赛事保密评审，不随公开GitHub分发。


v12另在portable层保留原始公开SCE工作簿、匿名受访者编号/日期、内部Agent编码及匹配来源。仅排除真实账号秘密。快速投影沿用旧别名以保证旧复算字节不变，可用完整映射连接原始资料。
