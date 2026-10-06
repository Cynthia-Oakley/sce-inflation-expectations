# 家庭价格体验机制：使用入口

更新：2026-10-06。第一版已接入本地 SocioVerse2，完成离线工程验收；尚未证明能改善真实 LLM 的模拟效果。

## 1. 它具体做什么

原先所有家庭看到一样的经济指标和新闻。现在增加一个有来源、可检查的中间环节：

**SCE 家庭画像 → 分配合成消费篮子 → 形成个体信息视图 → LLM 回答原来的 Q8/Q9 → 用现有计分和评价流程比较。**

- **P：** 保留当前真实画像，按住房、收入、年龄、地区、教育，从 CE 中找相近消费单元，带权抽取一整条记录。食品、汽油、住房份额来自同一家，保留它们的联合关系。
- **E：** 继续使用当前两月的经济指标历史序列和新闻标题＋摘要。三个价格渠道与篮子独立留档；不计算一个“必须回答的通胀值”。
- **B：** 可以给模型展示这份合成消费背景，也可以只按篮子调整价格趋势和新闻的先后顺序。模型自行回答，不加入人为答案偏移、噪声或上月自己的问卷答案。

这里的“体验”是**外部调查分配的支出相关性代理**，不是个人真实买价或感受到的物价，也不是购物频率。是否能解释 SCE 预期差异，需要后续对照检验。

## 2. 五种可比较的设置

原基线 `sce-q8-q9-v2-abstract` 继续可用，新设置通过独立配置选择：

1. `expression_shared`：只改成家庭问卷的表达；经济事实、新闻顺序、问卷完全相同。
2. `basket_shared`：在第 1 组上展示合成支出份额；信息顺序不变。
3. `focus_only`：在第 1 组上按篮子排列价格趋势和新闻；不展示篮子。
4. `basket_focus`：同时展示篮子、调整顺序。

四个新组都使用 `sce-q8-q9-experience-v1`。配置文件在 `studies/sce_inflation_expectations/mechanism/`。**这版的“聚焦”只调整顺序，全部新闻保留，不是在模拟有人只能接触一部分新闻。** 新闻相关性由明示词表标记，份额只是排序代理；它不是文献估计出来的真实注意力系数。

四组共享所有公共事实和相同问卷，篮子显示本身是新增的合成 P 条件。第 1 组与旧基线比较表达；第 2/3 组与第 1 组分别比较消费背景和顺序；第 4 组检查二者的共同效果。

## 3. 数据与分配规则

已下载 [BLS 官方 CE 2020 CSV](https://www.bls.gov/cex/pumd/data/comma/intrvw20.zip)，选一个明确波次 `intrvw20/fmli204.csv`。5,205 行中 5,203 行通过支出/权重检查，两条异常记录的原因保留在构建摘要里。

每个家庭的食品、汽油及机油、现金住房支出分别按 `PQ+CQ` 求和，再除以总报告支出；剩余为 other。总报告支出包含捐赠、养老金等，因此**不是 CPI 消费篮子权重**；本版不据它生成加权“个人 CPI”。食品含居家和外食；汽油与机油不完全等于汽油 CPI；现金住房支出不同于 CPI 的租金等价。对应限制也写进模型实际提示词。

优先保留住房和收入，再是年龄、地区、教育。精确条件下不足 25 条 donor 时，从后往前放宽条件，记录每人实际匹配条件、候选数量和加权有效数量。25 是防止极小候选池的工程初值，不是统计功效保证；这套优先级也只是待检验设计。缺失属性不硬填，州、就业、性别、numeracy 不作 CE 匹配，也不据它们猜购物/开车角色。

按 `seed + agent_id` 固定抽样位置；同一候选池内不会因就业、numeracy 等无关字段改变而重抽篮子。若匹配条件变化，候选池可变化，donor 也可能变化；所以这仍不是已实现的跨月消费状态学习。画像哈希另行绑定输入，防止错配到别人的画像。

**当前只支持 A 线历史重建。** 2020 全年 PUMD 于 2021-09 的发布材料中确认可得，当前网上包还含后续修订；不能当作 2021-05/06 的事前数据。B 线必须另选截至预测时点可得的历史人口/CE 版本，不能直接复用本包。

## 4. 本地路径

以下均相对于研究仓库 `/Users/wushuyue/Documents/科研/DISC/socioverse_challenge`：

- 原始资料：`data/raw/ce_experience/20261006/`。包含官方 ZIP、官方当前字典、来源/哈希记录；原始数据不推送 Git。
- 构建入口：`scripts/build_sce_price_experience.py`。
- 机制实现：`studies/sce_inflation_expectations/price_experience.py` 和 `experience_mechanism.py`。
- 配置/码值：`studies/sce_inflation_expectations/mechanism/`。
- 当前可用输入：`outputs/price_experience_20261006_v1/n300/202105/` 与 `202106/`。
- 每月的 `experience.json` 是运行侧车；`assignment_summary.json` 是来源、支持度和回退统计。
- `prompt_preview_<arm>.jsonl` 是每人的实际提示词与 Observation，适合检查输入，而不是输出回答。
- `source_snapshot/` 和 `manifest.json` 保留构建时的代码、配置及文件哈希。

详细工程证据见 [验收记录](PRICE_EXPERIENCE_ACCEPTANCE_20261006.md)，下一轮设计见 [真实对照运行卡](PRICE_EXPERIENCE_RUN_CARD_20261006.md)。早期无快照输出与中途调试运行不作为后续实验输入。

## 5. 如何使用

在仓库内启用 `socioverse` 环境。更换人口、环境时重新构建一份新目录，不复用不匹配的侧车：

```bash
python scripts/build_sce_price_experience.py \
  --ce-data data/raw/ce_experience/20261006/intrvw20.zip \
  --member intrvw20/fmli204.csv --wave 2020Q4 \
  --source-url https://www.bls.gov/cex/pumd/data/comma/intrvw20.zip \
  --release-date 2021-09-09 \
  --release-evidence-url https://www.bls.gov/news.release/archives/cesan_09092021.pdf \
  --population outputs/monthly_inputs_20261005T044602Z_f8c1a697/n300/202105/population.json \
  --environment outputs/monthly_inputs_20261005T044602Z_f8c1a697/n300/202105/environment.json \
  --output outputs/my_new_experience_package
```

原运行入口已增加 `--mechanism` 和 `--experience`，`--population/--environment/--simulation` 仍能自由切换。P/E/simulation 路径按原入口规则：**绝对路径**，或相对导出的 study；两项新参数相对研究仓库或为绝对路径。每个月分别运行，侧车 ID 必须与该次 P 完全相同。

只有在批准新的付费实验后，真实模式才使用 `--llm openai --prompt-version sce-q8-q9-experience-v1`。新提示词和新机制必须一起选，不能默默忽略机制。规则式模式可验证输入经过框架、轨迹和记录是否完整，**其答案不会检验消费背景是否有效**。

## 6. 尚未做的事情

未运行新机制的真实 LLM；未校准 SCE 水平；未修改计分器或 Normal 扩展；未把消费份额当真实购买频率。购买频率、个人价格经验的跨月更新、差异化新闻接触、人际传播、心理状态和模型知识泄漏实验仍需分别立项。

同月公共截止点仍沿用当前开发 E，不等于每位真人在作答日的可见信息；新闻文本历史版本限制也保留。此机制不能自动修复这些限制，更不能把 A 线变成事前预测。
