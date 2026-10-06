# 家庭状态审计与心理画像离线验收

日期：2026-10-06。本轮完成接力计划步骤1–3：已有 SCE 字段诊断、GSS 联合样本核查、五套候选侧车。**没有新增模拟 LLM/付费 MCP 调用，没有修改正式人口、运行配置或 Normal 答案扩展。** 当前仅 A 历史重建探索，不声称心理属性已改善模拟。

## 1. 主要发现

### 财务经历值得单独检验，但不是确定性规则

按当前 SCE 微观文件中的官方 Q9 个人密度均值与当月调查权重：

- 2021-05：家庭财务明显变差者37人，预期加权中位数约8.77%；财务不变者603人，约4.04%。
- 2021-06：明显变差者40人，约8.87%；不变者628人，约4.33%。
- 控制年龄、教育、收入、地区和数理类别的描述性加权线性回归，“明显变差”相对“不变”的个人预期均值差分别约+2.72/+5.01个百分点。完整回归样本1194/1254，设计矩阵均满秩15。没有报告显著性或因果效应；小群体、权重与极端值会影响结果。
- 财务变好组并非每档每月都严格单调；数理 High/Low 的预期排序也随月变化。不要据此给 Agent 编写固定加减通胀的规则。

这些是开发月相关性，不是独立测试。Q1 已经用于诊断，后续不能在相同月份声称盲测有效。问卷的 Q1 是过去一年家庭财务自报变化，不是客观收入冲击或幸福量表；经济学依据见[综述](literature/sce/psychological_attributes/literature_review.md)。

### 数理分组复算通过

[纽约联储官方图表指南](https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/glossary/frbny-sce-chartglossary.pdf) pp12–13 规定五题答对4/5为High，0–3为Low。对应QNUM1/2/3/5/6，正确答案150、242、10、100、5；QNUM8/9不在这五题计分中。

两月有完整五题可复算的新入组者153/162人，分别153/153与162/162同 `_NUM_CAT` 一致。重复出现的1070人分类均未变化。原始题只在新入组时问，所以没有声称从两月原始答题复算全部2531个人月。

### 更正前次“全覆盖”的表述

原始字段有内容不代表是合法画像类别。本轮读取并清洗后：

- 5月教育缺9人、收入缺14人；年龄、地区、数理类别均无缺失。
- 6月教育缺6人、收入缺13人；年龄、地区、数理类别均无缺失。

前次调研中“人口字段全覆盖”的推断过宽，现已更正。缺失保留未知，不按全国比例猜测教育或收入。

## 2. GSS 2018 联合样本

从[NORC年度Stata入口](https://gss.norc.org/get-the-data/stata.html)的2018链接下载，压缩包包含官方 `GSS2018.dta`。当前版2348人；HAPPY有效2344，SATFIN有效2338，两题共同有效2336。共同具备可比年龄、教育、地区者2326；再要求非缺失且不跨SCE阈值的收入代理者1998。

- HAPPY与SATFIN保留三档有序分类，从同一个donor整行抽取，不分别抽取两题。
- 采用当前NORC推荐的WTSSPS。[权重FAQ](https://gss.norc.org/faq.html)。它是当前修订版的A探索选择，不作为2021年B历史权重证据。
- 当前公开版region已经是四大区，按**该变量实际标签**映射，不拿另一个九分区标签表套用。公开文件包含后来的修订，不能当成原2019发布副本。
- GSS是成年个人、收入题是历史family income；SCE是家庭户主、household income。收入单位与参考年份不完全一致，目前只是粗历史收入代理，不是严格同口径当期收入。
- GSS的$90,000–109,999一档跨越SCE的$100,000界限；联合样本中145人落在该档。收入匹配池排除这档，不取中点或随机切分。缺收入记录也排除收入条件池。
- TRUST与两题共同有效1548人，但本版不加入信任；它是一般人际信任，不是美联储信任。

四条件同时匹配时，一些小格有效样本量低；按年龄×教育×收入代理并合并地区后，5/6月非空格最小有效donor数约11.71/17.61。只用年龄×教育×地区支持更宽，但遗漏收入条件，保留为诊断比较，不将其默认作为财务满意主模块。

## 3. 已实现的候选合成规则

算法：[psychological_profiles.py](../studies/sce_inflation_expectations/psychological_profiles.py)；入口：[build_sce_psychological_profiles.py](../scripts/build_sce_psychological_profiles.py)。

1. 优先同年龄、教育、粗收入代理、地区；源内整行按WTSSPS抽样。
2. donor有效样本量不足10时只合并地区，保留年龄/教育/收入条件；关键字段缺失或仍无支持，则心理值unknown。
3. 有效样本量10是本轮**开发参数**，不是论文规定或最终冻结门槛。五套分配同样只是起始敏感性检查。
4. 种子42，draw0–4；人员键和匹配条件决定抽样，月份和Core/Normal角色不改变相同条件下的分配。
5. Q1作为单独的SCE已观察家庭状态保留。它没有用于挑选心理donor。幸福/满意值标外部合成，不说是这位SCE真人的状态。
6. 候选预览的 `candidate_text` 属性文字不含userid、donor ID、权重、真实Q8/Q9；JSON外层agent_id仅供本地定位，不应作为消息内容发送。预览是待接入属性文本，不是完整LLM提示，也没有接入现行model.py。

### 五套分配验收

每套均覆盖两个完整月，共2531条记录；五套共12655条候选侧车。

- 5月1234人：1211人分配心理值，23人未知；361人合并地区。Core 300人中296分配，Normal 934人中915分配。
- 6月1297人：1278人分配，19人未知；388人合并地区。Core 300人中296分配，Normal 997人中982分配。
- 每套1054位跨月重复且实际匹配条件不变、支持有效的人，donor均保持一致。Q1允许随月变；固定两月心理值是合成假设，不证明人格稳定。
- 各套心理组合比例有波动，例如5月“很幸福且财务相当满意”187–229人，6月202–236人，说明分配不确定性仍应保留。
- 原始Stata记录独立核对了12655条侧车的联合值/unknown处理。没有构造原donor不具有的幸福—满意组合。

Normal拥有候选属性，不意味着现行答案扩展已使用它。CE与心理属性分别匹配，没有共同观测消费—心理的个体联合关系；不能声称已还原该关系。

## 4. 准确路径

唯一合格审计目录：`outputs/household_psychology_20261006T133213Z_6de9a161/`。

- [审计summary.json](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/household_psychology_20261006T133213Z_6de9a161/summary.json)
- [人口候选字段，无Q8/Q9](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/household_psychology_20261006T133213Z_6de9a161/profile_candidates.jsonl)
- [清洗donor](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/household_psychology_20261006T133213Z_6de9a161/gss2018_candidate_donors.jsonl)
- [实际值标签字典](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/household_psychology_20261006T133213Z_6de9a161/gss_field_labels.json)

唯一合格侧车目录：`outputs/psychological_profiles_20261006T133319Z_db8c7eb9/`，包含draw_00至draw_04。

- [分配摘要](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/psychological_profiles_20261006T133319Z_db8c7eb9/summary.json)
- [draw_00侧车](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/psychological_profiles_20261006T133319Z_db8c7eb9/draw_00/sidecars.jsonl)
- [draw_00属性文字预览](/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/psychological_profiles_20261006T133319Z_db8c7eb9/draw_00/candidate_text_preview.jsonl)

原始目录：`data/raw/psychological/gss/2018/20261006T131656Z/`；[来源与哈希](literature/sce/psychological_attributes/sources/gss2018_archive_20261006.json)。原始Stata、ZIP、SCE指南、嵌入式字段字典与manifest各自保留。微观记录与自动产物不进GitHub；源码、文档和来源索引可备份。

## 5. 验证与已知缺口

9项定向测试通过：加权分位数、缺失数理题、收入跨界、教育分类、支持ESS、联合donor/跨月稳定、角色/输入顺序不影响分配、预览无ID/目标字段、CLI拒绝错误来源哈希。命令：

```bash
python -m unittest tests.test_sce_household_state_audit tests.test_sce_psychological_profiles -v
python scripts/audit_sce_household_state.py --gss data/raw/psychological/gss/2018/20261006T131656Z/GSS2018.dta
python scripts/build_sce_psychological_profiles.py --profiles outputs/household_psychology_20261006T133213Z_6de9a161/profile_candidates.jsonl --donors outputs/household_psychology_20261006T133213Z_6de9a161/gss2018_candidate_donors.jsonl --source-hash 5816dc11c00b6f19a210d3d8f83fc2bab1a738352636295342dec3ebf71a15f4 --role-root outputs/ce_population_baskets_20261006T063749Z_a8be0d98
```

重新执行另建run_id。完整SCE文件已在最终合格审计中重新读取；中间缓存尝试不作为唯一最终结果。开发期先遇到统计代码/相对路径错误，已修正；一次侧车构建用了错误来源哈希，已标记INVALID_PROVENANCE，不可用于任何模拟。CLI现校验实际源SHA和两个候选文件哈希，合格批次另建；旧尝试保留追溯。

尚未完成：来源调查内部屏蔽留出验证、跨调查迁移效度、历史B vintage、家庭收入跨年/单位可比性更严格处理、实际提示接线和行为有效性、Normal心理条件扩展。当前支持检查与联合值核验不代替这些验证。

## 6. 下一步

先独立检验Q1状态模块；幸福/满意模块随后作为另一对照，避免把二者同时新增后无法归因。制作真实提示预览和具体运行卡，保持现有E、模型和计分不变。先沿用开发月做工程/机制检查，再按冻结方案选未用于调参的月份评价。新API数据发送范围和预算另行确认；本轮没有启动实验，也没有修改旧实验配置。
