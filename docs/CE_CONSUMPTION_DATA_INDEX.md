# 消费篮子数据入口与本轮验收

更新：2026-10-06。用户已同意继续 Interview 主篮子、官方分组表核查、Diary 后续购买频率研究。本页是查找入口；执行顺序见 [本轮计划](archive/2026-10/CE_DATA_BUILD_PLAN_20261006.md)，已有机制见 [机制说明](PRICE_EXPERIENCE_MECHANISM.md)。

## 1. 本轮做了什么

把既有“300 Core 有篮子”扩展为“完整月度人口都有篮子”，再按既有 Core ID 划分 Core/Normal。两类人口使用同一种匹配与抽样方法，没有给 Normal 换成平均篮子。匹配使用画像，不使用真实问卷答案。

- 2021-05：完整人口 1,234 人 = 300 Core + 934 Normal。
- 2021-06：完整人口 1,297 人 = 300 Core + 997 Normal。
- 两月已有 300 Core 的篮子分别 300/300 与上一版一致；没有重新抽选 Core。
- 两月共有的 1,070 人中，1,051 人的匹配特征未变，这些人的 donor 与篮子均不变；17 人因匹配信息变化更换 donor，另 2 人信息变化但抽中同一 donor。结果见运行目录 `cross_month_stability.json`。
- CE 2020Q4 可用 donor 5,203 条。较细匹配池不足 25 时，按既定规则放宽匹配：两月分别 395/414 人使用了回退；这不是删除记录，应在后续敏感性分析中检查。
- CE 以自身调查权重计算参考分布；SCE 调查权重只用于事后审计，不进入 Persona，也不影响篮子抽样。

**本轮没有生成新的 LLM 回答，也没有更新 Normal 答案扩展算法。** Normal 现在有篮子输入，但现行扩展算法仍按原有画像分层。下一步要单独设计如何在扩展中保留篮子差异，再检验效果。

## 2. 原始资料：核查从这里开始

原始目录：[data/raw/ce_experience/20261006](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/ce_experience/20261006)。下载记录和文件 SHA-256 随资料保存；文件不覆盖，数据不进入 Git。

完整归档清单：[archive_registry_complete_20261006.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/ce_experience/20261006/archive_registry_complete_20261006.json)。此前登记的 `download_pending` 仅是保留的初始记录。

- Interview CSV 压缩包：[intrvw20.zip](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/ce_experience/20261006/intrvw20.zip)。主篮子使用其 `intrvw20/fmli204.csv`，不是 PDF 转录。
- Diary CSV 压缩包：[diary20.zip](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/ce_experience/20261006/diary/diary20.zip)；[下载清单](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/ce_experience/20261006/diary/download_manifest.json)。后续周金额和购买日数来自这里，不能按 NEWID 与 Interview 逐户合并。
- 官方字段字典：[ce_pumd_dictionary_official.xlsx](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/ce_experience/20261006/ce_pumd_dictionary_official.xlsx)。这是当前下载字典；处理时选择适用于 2020 的字段与分类定义。
- 官方收入分组年表：[cu-income-before-taxes-2020.xlsx](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/ce_experience/20261006/benchmarks/cu-income-before-taxes-2020.xlsx)。供描述性参照；年度综合统计与单季 Interview 的估计口径不同，不能要求数值逐项相等。

**版本边界：**这些是现在下载的资料，不能证明其内容在 2021-05/06 预测时已经可用。当前用于 A 历史重建的消费背景代理。B 未来预测需另行选择截止日前已发布的 CE 年份与版本，不复用本包的历史可得性声明。

[BLS 2021-09-09 发布稿](https://www.bls.gov/news.release/archives/cesan_09092021.htm)的 Data Products 段明确当时 2020 Interview/Diary 微观文件均已公开。这只能证明“截至该日已可得”，不能证明最早首发日，也不验证本地修订副本的历史版本。现有篮子元信息 `public_release_date=2021-09-09` 按此证据解释，不作为已查明的最早 PUMD 发布日。

## 3. 已生成篮子与 Core/Normal 分工

本轮运行目录：[ce_population_baskets_20261006T063749Z_a8be0d98](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98)。旧 `outputs/price_experience_20261006_v1/` 保留。

### 2021-05

- 全人口篮子：[202105/experience.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/experience.json)。同目录保存构建参数、源码快照和四组实际提示词预览。
- Core 输入：[population.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/roles/core/population.json)、[experience.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/roles/core/experience.json)。
- Normal 输入：[population.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/roles/normal/population.json)、[experience.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/roles/normal/experience.json)。
- 独立审计：[report.md](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/audit_weighted/202105/report.md)、[summary.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/audit_weighted/202105/summary.json)。

### 2021-06

- 全人口篮子：[202106/experience.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202106/experience.json)。
- Core 输入：[population.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202106/roles/core/population.json)、[experience.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202106/roles/core/experience.json)。
- Normal 输入：[population.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202106/roles/normal/population.json)、[experience.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202106/roles/normal/experience.json)。
- 独立审计：[report.md](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/audit_weighted/202106/report.md)、[summary.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/ce_population_baskets_20261006T063749Z_a8be0d98/audit_weighted/202106/summary.json)。

分组文件只划分已生成篮子，保留相同 ID 的消费结构。角色文件的 Population 哈希重新生成，不能把旧配置哈希当作这些新文件的哈希。运行入口与旧实验配置本轮未改。

## 4. 已验收与尚待研究

完整人口覆盖、Core 一致性、画像哈希、donor 选择、份额与候选池均通过独立审计。审计同时保存等权与调查加权分布，不用全国平均消费份额替代每个家庭，也不强制 SCE 与 CE 总体均值一致。

2020Q4 处在疫情期间，其消费结构不一定代表 2021-05/06。后续需比较其他 CE 波次与不同抽样种子；匹配仅依赖共同字段，不代表恢复了该 SCE 家庭真实的消费记录。

### Diary 清洗结果

- [字段审查与对账说明](CE_DIARY_FIELD_REVIEW_20261006.md)。
- [本轮清洗说明 README](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/interim/ce_experience/20261006T071002778274Z_ce_diary2020q4_4862a21e/README.md)、[机器清单 manifest](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/interim/ce_experience/20261006T071002778274Z_ce_diary2020q4_4862a21e/manifest.json)、[家庭周记录 JSONL](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/interim/ce_experience/20261006T071002778274Z_ce_diary2020q4_4862a21e/diary_weekly.jsonl)。早期清洗批次保留，以上是带发布标志对账的最新批次。
- 2,835 条家庭周记录，连接 93,058 条支出明细；无孤儿明细，123 周没有明细，单独标记。
- 2,455 周有完整的购买日字段支持，136 周仅部分支持；另 121 周没有正金额且用于发布统计的明细。1,739 条正金额明细缺有效日字段，不能默默当作“没买”。
- 当前只有**所有类别合计的周内不同购买日数**，尚未生成分商品类别频率。食品、家庭用品与 FMLD 汇总金额全一致；外食和个人护理的差异均由 `PUB_FLAG=1` 排除解释，逐周对账保存。该标志表示是否用于 BLS 发布统计，不表示该明细是否公开。

Diary 提供的是调查周的记录，不是全年稳定习惯，更不是实测注意力。如何给 SCE 人口合成购买频率尚待设计，暂不进入 B 提示词。Interview 与 Diary 是不同样本，不能靠相同编号强行逐户合并。

本轮新增审计与分割测试 10 项、Diary 测试 7 项通过；另用真实原档端到端构建与核对。这证明数据处理和输入一致性，不证明机制改善了模拟效果。

后续顺序：

1. 固定同人、同公共信息，做已有五组小额机制对照；检验水平、分歧、尾部与答案质量，不能把增加方差直接当作成功。
2. 设计 Normal 的篮子条件扩展：依据 Core 的模拟回答，联合画像与篮子选择回答 donor；稀疏时回退到画像层。保持 Q8/Q9 联合记录，检查留出 Core 的扩展误差，再对比现行画像扩展与直接加权基线。不得用真实 SCE 答案训练扩展规则来改善本轮结果。
3. 购买频率作为独立研究分支；只有明确测量与合成规则后才加入机制。
4. 为 B 线另建历史可得的 CE 版本。年度官方分组表的数值比较还需统一年度/季度、总体范围及“平均份额/总额之比”的统计口径；本轮只归档该年表，不声称逐项对账已完成。正式效果检验与调参月份区分。

## 5. 复算入口

在仓库根目录、已配置的 `socioverse` 环境运行。各入口要求新输出目录，保留旧结果。

- [build_sce_price_experience.py](../scripts/build_sce_price_experience.py)：全人口篮子与提示预览；实际输入和参数见运行根目录 `build_recipe.json`、每月 `assignment_summary.json`，源码与输出哈希见每月 `manifest.json`。
- [split_sce_basket_population.py](../scripts/split_sce_basket_population.py)：输入全人口、原 Core、全人口 experience，按 ID 划分；不生成答案。
- [audit_sce_basket_population.py](../scripts/audit_sce_basket_population.py)：读取实际 CE donor，核对完整篮子与原 Core，并接受独立 `--analysis-weights` 做事后审计。
- [prepare_ce_diary.py](../scripts/prepare_ce_diary.py)：离线处理 Diary CSV 与官方字典，默认创建新的中间数据目录。

无需将这批家庭记录直接上传云平台。先在本地验证方法；如需平台实验，另做只含必要白名单输入的版本包与发送范围确认。
