# B｜SCE 一年期通胀问卷与计分边界

核查：2026-09-29。用途：给 SocioVerse Agent 的 B（问卷作答）与本地计分器提供同一份短规范。**官方事实**来自文末纽约联储原始资料；**本项目规则**是尚待实现的接口约定；**已核验**仅指现有本地数据审计，不代表完整流程已经运行。研究目标和预测时点仍以 [研究协议](RESEARCH_PROTOCOL.md) 为准。

## 1. 测量对象和作答顺序

SCE 核心调查询问美国 household heads 的未来十二个月**通胀率**，不是未来实际 CPI，也不是受访者个人购物篮价格。Q8v2 → Q8v2part2 是直接点预测；其后 Q9 让同一人分配十种未来通胀/通缩结果的主观概率。两种回答可以不同，官方同时公布两条不同的跨人中位数序列。[官方核心问卷，第 7–8 页][Q]；[FAQ，median expected inflation 与 median point prediction][F]

| 字段 | 官方题意 | B 的结构化表达 |
| --- | --- | --- |
| `Q8v2` | 未来 12 个月会是 inflation 还是 deflation；选项 inflation=`1`、deflation=`2`。 | `direction` 仅为两者之一。 |
| `Q8v2part2` | 按所选方向，给未来 12 个月通胀或通缩**幅度**的最佳估计，单位 `%`；问卷指示输入 `≥0` 的数。 | 分别保留 `direction`、`magnitude_pct`，再生成一个带符号的 `point_pct`：通胀为正、通缩为负；零仍是零。 |

**字段口径提醒：**上述 `point_pct` 是本项目输出契约，不等同于要求在已发布微观数据上再次变号。现有本地 `micro_2020_2024.xlsx` 的 `Q8v2part2` 已以带符号数值存储：抽查前 3,000 行时，`Q8v2=2` 的 430 个非零样本为负值。导入微观数据时按其已存数值读取，并对方向和符号做一致性审计；不可再把通缩值乘以 −1。[本地数据审计][A]

## 2. Q9：十个概率选项

Q9 问的是未来 12 个月每种**通胀率或通缩率区间出现的 percent chance**；每格填的是概率百分数，如 `20` 表示 20% 的机会，**不是**预期通胀率 20%，也不是 `0.20`。官方题面按下表顺序列示。表中的“通缩”是下降幅度，不要把它当作正通胀率；程序在拟合时再映射到带符号轴。中间档的端点包含关系不由这张人类问卷表推定，浮点边界和开放尾部应由经验证的计分实现处理。[Q，第 7–8 页]

| 顺序/公开微观列 | 官方选项的中文直译 |
| --- | --- |
| `Q9_bin1` | 通胀率 12% 或更高 |
| `Q9_bin2` | 通胀率在 8% 与 12% 之间 |
| `Q9_bin3` | 通胀率在 4% 与 8% 之间 |
| `Q9_bin4` | 通胀率在 2% 与 4% 之间 |
| `Q9_bin5` | 通胀率在 0% 与 2% 之间 |
| `Q9_bin6` | 通缩率在 0% 与 2% 之间 |
| `Q9_bin7` | 通缩率在 2% 与 4% 之间 |
| `Q9_bin8` | 通缩率在 4% 与 8% 之间 |
| `Q9_bin9` | 通缩率在 8% 与 12% 之间 |
| `Q9_bin10` | 通缩率 12% 或更高 |

官方页面显示 `TOTAL 100`，H4 指示十数相加为 100；空答触发 E1，总和不为 100 会显示当前总和并触发 E3 要求修改。问卷没有给出可随意宽免的总和误差或自动归一化规则。[Q，第 8、42–43 页] **本项目输入校验**：要求恰好十个有限数值，每项在 0–100，单位为“百分数点”，合计 100；负数、越界、缺格、比例/百分数单位混用及非 100 总和记为失败，按有限次数显式请求修正并保存原输出。若实现使用二进制浮点，仅允许为表示误差设置事先记录的极小容差，不以此容忍实质不合计。不得静默大幅归一化，也不得将点预测强制改成概率分布均值。前两句是官方问卷规则，后面的机器校验与修复策略是本项目约定。

## 3. Q9 到官方 headline：哪些已证实

官方统计链是 `十个概率 → 每个人的参数化主观密度 → 个人密度均值 Q9_mean → 跨人中位数`。个人密度四分位数、方差、IQR 和通缩概率也以派生列发布。FAQ 明确：媒体所称 *median expected inflation rate* 是**个人密度均值的中位数**；点预测另取直接回答的**插值中位数**。[F] [Q，第 8 页] [M，§5.2–5.3]

2017 方法论文附录 C 给出的拟合分支如下，**尚未由本项目逐人复现**：[M，附录 C]

1. 三个或更多正概率区间（不要求相邻）：以广义 beta 密度拟合；文中说明最小距离拟合，支持区间端点通常由正概率档决定，落在开放尾档时端点参与估计，并有论文写明的边界约束。这里不从摘要反推目标函数细节或自行指定尾部代表值。
2. 恰好两个**相邻**正概率区间：等腰三角密度；宽度不等和涉及开放尾部时有另外的支持区间规则，不可套用简单的两个区间中点。
3. 只有一个正概率区间：均匀密度。开放尾档的可复现处理仍须在逐人对照时落实，不凭区间中点或自定尾部上限填补。
4. 两个正概率区间却**不相邻**，或概率总和不为 100：论文明确说不拟合密度。B 输出若有这类情况，应保留失败状态；不能把无拟合者的近似均值混入官方口径。

**已经验证的范围：**2026-09-28 本地审计使用下载文件自带的个人 `Q9_mean` 与当期 `weight`，以加权经验中位数（累计有效权重首次达到 50% 的取值）复核 2020–2024 全部 60 个月官方 chart 主序列；同时用 `Q8v2part2` 的加权 mid-distribution 插值中位数复核点预测序列。两条序列的聚合规则在该版本数据中不同；主序列用插值反而会产生差异。这个 60/60 **只验证“已有个人派生值 → 跨人统计”**，没有从 `Q9_bin1`–`Q9_bin10` 重建过任何人的 `Q9_mean`，也没有验证所有分组/不确定性序列。[A] [M，附录 B] [F]

**待实现/验收：**按附录 C 写个人拟合器；用真实 Q9 原始概率逐人对照官方 `Q9_mean`、四分位数和 `Q9_iqr`，覆盖单档、相邻双档、三档及以上、开放尾与无效回答；再复核月度 headline。区间中点加权和、平均所有人的十档概率后再拟合、普通未加权 median 都不能冒称官方 headline。聚合时按目标分别剔除不可用的派生值或权重，在有效样本内归一权重。[A] [M]

## 4. B、Y 与 20 人 × 两开发月首试

**隔离契约。** B 只接收在 `as_of` 时已经可得的 P 画像、E 信息、问卷题意、自己的过去模拟状态；真实目标月 Q8/Q9、`Q9_mean`、当期权重、官方月度 headline 仅在 Y/评价层。历史已公布 SCE 数值若用作输入或基线，须单列并带发布时点；未知历史可得日先隔离。目标月 `t` 的建议初始 `as_of` 为 `t−1` 月最后一天 23:59:59 `America/New_York`，开发月具体选择需经过 P/E 时点验收。[研究协议](RESEARCH_PROTOCOL.md)

**给 SocioVerse Agent 的精简说明，可直接粘贴：**

> 对每个模拟 household head 和目标月，先读取获准的 P/E 快照及 `as_of`。按 SCE 一年期题序先回答：未来 12 个月通胀还是通缩、幅度多少百分比；保留方向与非负幅度，同时输出带符号的 `point_pct`。再按本文件 Q9 表的固定顺序，给十种未来通胀/通缩结果分配概率百分数，合计恰好 100。输出十个原始概率、证据 ID、模型/prompt/种子、校验状态与失败原因。不要读取目标月真实 SCE 回答、权重或 headline；不要把十档概率解释为跨 Agent 的频率。

**首试可行范围（项目建议，非官方 SCE 样本设计）：**取两个相邻的**开发月**、每月 20 个事先固定的合成/历史可得画像，共 40 个 Agent-月；先用 scripted 确定性回答跑通 P/E → B → 导出 → 本地重算，记录输入、题序、校验失败和版本。20 人规模只检验流程，不能据此声称重建全国约 1,200 人的代表性或预测性能。[F] [今日执行计划](archive/2026-10/TODAY_PEB_EXECUTION_PLAN.md)

若个人密度拟合器尚未通过逐人对照，首试可以**降级为**：完整生成并校验 Q9 十数、保存原样供日后拟合；暂时只对带符号点预测做独立的演示聚合/副目标计分。此时不得计算或宣称官方主目标 `median expected inflation rate`，不能用区间中点近似代替。正式改变主目标须按研究协议记录决策，不能凭首试/测试效果临时改名。即使点预测插值算法通过，20 人合成人口权重也只是试验权重，非当期真实 SCE 权重。

## 官方来源与本地证据

- [Q｜纽约联储 SCE 核心公开问卷，Q8v2/Q9、H4/H9、E1/E3](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-survey-core-module-public-questionnaire.pdf)。本地下载快照日期 2026-09-28；SHA-256 见[源文件清单](sce_source_manifest.json)。
- [F｜纽约联储 SCE FAQ，median、point prediction、样本与微观发布](https://www.newyorkfed.org/microeconomics/sce/sce-faq)。网页核查 2026-09-29。
- [M｜Armantier 等，2017，*An Overview of the Survey of Consumer Expectations*，§5、附录 B/C](https://www.newyorkfed.org/medialibrary/media/research/epr/2017/epr_2017_survey-consumer-expectations_armantier.pdf)。本地下载快照日期 2026-09-28；SHA-256 见[源文件清单](sce_source_manifest.json)。
- [纽约联储 SCE 总入口、图表与下载](https://www.newyorkfed.org/microeconomics/sce)；[官方 chart 工作簿](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-data.xlsx)；[2020–2024 官方微观工作簿](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-public-microdata-20-24.xlsx)。下载快照和哈希同见[源文件清单](sce_source_manifest.json)；实际聚合结果见[A｜本地 SCE 数据审计](SCE_DATA_AUDIT.md)。现有下载版可用作事后 Y，不自动成为历史预测日已公开的 P/E。

[Q]: https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-survey-core-module-public-questionnaire.pdf
[F]: https://www.newyorkfed.org/microeconomics/sce/sce-faq
[M]: https://www.newyorkfed.org/medialibrary/media/research/epr/2017/epr_2017_survey-consumer-expectations_armantier.pdf
[A]: SCE_DATA_AUDIT.md
