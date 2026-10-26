# Kimi接入契约：四维Core＋Normal小试

2026-10-23，接口v1.1。方法模块由Codex维护；Kimi可接月度历史/P/E组装与新运行目录。不要修改旧82月封存包，也不要另写一套抽样、Normal或分位数。

**本次补充：**已读Kimi的[可得性清单](../20261021_fullperiod/kimi_availability_inventory_20261023.md)及[接口映射](../20261021_fullperiod/kimi_interface_map_20261023.md)，接受其作为接线依据；没有重复全量审计或实验复跑。第5—8节确定本次三月小试的工程接口，最终生产规模、Normal是否采用及付费授权仍未确定。机器可读规格见[pilot_interface_v1.json](pilot_interface_v1.json)，它是接线规格，不是已可执行的运行包。

**后续规模补充（同日）：**用户要求Core比例按本项目实际框架商榷。新[规模对照提案](scale_pilot_design.md)准备共用256／384／512三档回答，名单已生成，最多1728个位置；本页原256＋64／960及相应机器规格保留为旧单档提案，不是当前最终运行人数。权重分工、隐私和角色隔离沿本页；共用审计参考池改为所有Core名册并集之外，不能套用旧256的审计名册或pi。新方案仍未准备完整提示、未授权。

## 1. 可直接使用的名册

项目根下`outputs/sce_core_normal_pilot_preparation_20261023_v1/`：202109、202206、202506三个月，每月：

- `population_private.json`：`month`与`people`。每人`id`为**本地真实userid字符串**，仅供内部连接；`weight`为原始调查权重；`entry`为newcomer/returner/unknown；education/numeracy/age/income/gender为规范化分组，缺值None。
- `core_roster_private.json`：`selected`256人，含id、cell、weight、inclusion_probability、design_weight、poststratified_weight；`allocation`为完整分配审计。
- `audit_roster_private.json`：从Normal中抽64人，字段相同；其π是**给定已选Core后，在剩余Normal框架中的条件抽中概率**，用于Normal审计评价，不可冒称无条件原人口π。

API提示前必须使用既有匿名ID映射，把原始userid留私有链接；权重、性别与原始ID不因出现在本地分析帧就自动外发。原有API授权不覆盖这批新对象与新范围。

## 2. Kimi可以推进的输入接线

1. 按上述固定Core＋审计两份名单，连接既有当期白名单画像、严格更早的本人历史和近期匿名供体起点；保留新/老/间断/部分缺失标记。**审计也用同一套真实输入机制，但其当前LLM回答最终只给评价，不给Normal拟合。**
2. 复用现有V3.2、温度0.5、直接Q8/Q9、食品角色可见价格、随机3/8/20新闻和原50/50主题。不要改动提示措辞或增加心理标签。新闻先在完整月框架分配，再取Core/审计子集，避免Core规模变化重新随机。
3. 初始信念的校准目标沿已登记的严格过去参考；不得用本月真实Q8/Q9校准或选择供体。若既有初始化依赖旧512份名单，应调用共享函数为这批新ID准备，不通过改旧manifest或静默丢人解决。
4. 输出沿现有月度准备／官方引擎需要的selected、resolved、baselines和逐槽日志，另保存本次实际抽样概率/原权重/校准权重与角色。需要调整现有固定六格入口时用新适配器，冻结文件不覆盖。
5. 完整提示准备后交Codex核对精确prompt哈希复用、token/预算与冻结干跑；没有新明确预算之前不调用模型。

## 3. 给扩展器的回答格式

人口与Core文件可直接使用上述本地格式；传输或公开演示另做匿名映射，三文件ID必须一致。经既有评分器归一化并计分后，Core回答输入为：

```json
{
  "month": "202206",
  "answer_origin": "llm_model_output",
  "scorer_provenance": {"source_run_id": "实际运行ID", "scorer_version": "实际冻结版本与哈希"},
  "answers": [
    {"id": "与本地Core名册同一ID", "q9_bins": ["十个已经归一化的数值"], "q9_mean": "已计分数值或null", "q9_iqr": "已计分数值或null", "q8": "合法点预期或null"}
  ]
}
```

上述是字段说明，不是可直接执行的虚假数值例子。真实`q9_bins`必须为十个非负有限数、和为100，mean/IQR来自原冻结评分器；失败/缺失字段保留null，不能手工修分数。扩展入口不再次拟合Q9。

`answers`只允许Core，审计答案一旦混入会拒绝；不存在向扩展器传当期真人真值的参数。模型缺失Q9而Q8合法时，Q8仍进入独立库。若整个入组池没有有效Core，报告不支持，不自行跨新人/回访者借答卷。

## 4. 执行与输出

```sh
python scripts/expand_sce_core_normal.py --population <人口.json> --core <Core名册.json> --answers <Core计分.json> --tau 24 --out outputs/<新目录>
```

输出：`summary.json`（人口/字段覆盖、Core/Normal质量、总体中位数与分布）、`joint_atoms_private.json`（联合答卷和积分质量）；可选`--normal-seed`生成带`source=statistical_Normal`的微观展示，不能用展示样本数构造独立样本置信区间。

τ24只是本轮开发期选择的候选，不是新实验已授权或最终生产参数。正式试验前固定其主/敏感性地位与评价规则。同一批Core输出可离线重算，不需要按τ另发API。

## 5. 对Kimi八项待定接口的决定

### 5.1 网格与manifest

- 本次使用`grid_version=education_numeracy_age_income_54_v1`，字段顺序固定为education、numeracy、age、income。已知水平分别为`high_school/some_college/college`、`Low/High`、`under_40/40_60/over_60`、`under_50k/50k_100k/over_100k`。格键用`|`连接；人口缺一项时抽样格为`unknown`，不删除其余已知特征。
- **抽样格54＋未知池，分布估计另按entry分池。**不把54格再乘新老类型后要求每格保底；也不把无本地Core的细格说成已有直接观察。人口覆盖、有效Core覆盖和借用父池质量分开报告。
- 新manifest用`schema_version=2`和`kind=core_normal_monthly_pilot`。每月记录`population/core_roster/audit_roster`相对路径与sha256，`core_allocation/audit_allocation`沿用`plan_core()`现有输出：`cells[cell].frame_n/selected_n/population_mass/population_fraction/inclusion_probability`。不要把`selected_n`静默换成旧`allocated_n`。
- 名册是当前小试的唯一选人依据，manifest登记已有文件，不再从交付目录重新抽一次。增加Normal时也不改Core名单。

### 5.2 保底和预算

- 三期小试固定202109、202206、202506，每月Core256、细格保底4；不足4人的细格全取。未知池使用同样保底，**计入256**。余量沿既有`plan_core()`按格人口质量分配、受格人数上限约束。
- 64名审计者从Core以外人口中按同细格规则抽取、保底1，**计入Normal，不计入256 Core**。三期共960个LLM位置，尚未扣精确缓存复用，不是960个额外扩展人口。
- 384/保底6、512/保底8只是已检查的未来候选；本次不一起运行，也不据小试结果自动扩大。原始权重缺失者不填1：源P保留，本次加权框架另登记不支持记录。三期名册的正权重框架已经固定。

### 5.3 明确三层权重

- **Core-only参照、条件分布估计：**主用`poststratified_weight`；`design_weight=w/pi`另报敏感性，不互换名称。格内校准只恢复已知人口格质量，不保证中位数无偏。
- **Core＋Normal总体：**保留有效Core原始`weight`，为每个Normal分配其原始`weight`对应的预测质量；无效Core字段的预测后备也只占其原始质量。不得再加一遍Core的`w/pi`。
- **审计留出分布：**用`weight/audit_inclusion_probability`估计剩余Normal框架的分布。此处pi为给定Core已选后的条件概率；不把它当原整波无条件概率，也不向Core分布库传审计权重/答案。
- recipe必须分别声明`core_estimation_weight`、`target_population_weight`、`audit_evaluation_weight`。面板的单一`analysis_weight`无法代表三个对象，应由各视图明确读取。

### 5.4 抽样排序

- 使用当前`draw_core()`的SHA256排序，Core种子20261023，审计种子20261024。输入字符串严格为`seed:YYYYMM:local_userid`，格内按digest、再按userid排序，无放回。
- 已有名册保留；匿名映射只用于连接/发送，不重新计算排序。交付的旧`stable_priority`留作旧六格追溯，不混用或覆盖。新sidecar记录算法名、种子、名册哈希即可，不必重写原交付采样文件。

### 5.5 Normal输出与未知画像

- **主统计产物：**扩展器现有`summary.json`及`joint_atoms_private.json`。后者的Q9原子保留完整十档概率、冻结均值/IQR、配对可用Q8及供体ID；Q8另有独立合法值库。`weight`是原始目标人口质量，不是归一化到1的概率，也不是独立人数。
- **新增接线产物，尚待实现：**`conditional_distributions_private.json`按`entry + 四维实际画像`登记目标人数/原始质量、供体原子质量、local有效人数/ESS、parent质量及缺失后备；由同一`JointExpansion`实例导出，不能另算一套收缩。`unknown`抽样池内不同已知画像仍须区分，不能揉成同一个未知分布。
- 可选`normal_visualisation_private.json`只用于微观展示，标`source=statistical_Normal`；主中位数/W1用精确原子质量积分，不靠反复随机生成Normal碰到好成绩。
- Normal不伪装成LLM的`cases_private.json`行。Core和审计保留实际模型回答、标不同角色；Normal统计摘要与实际回答并列。实际总人数、LLM调用人数、有效Core数、供体有效数分开显示。

### 5.6 前期波次、初始化与网格

- 前期供体仍取最近1—3个月、本人历史严格早于目标月；新老身份、缺失字段和实际来源分别记录。人口网格不替代既有供体匹配，Normal也未因此获得本人历史依赖。
- 新适配器在**完整当月有效权重框架**上准备角色无关的起点和新闻配额，再投影到固定Core/审计名单；起点校准只用严格更早资料和原始人口权重。审计者不单独重新校准或换供体。若实现受限，先报差异，不静默退回两份不同初始化。
- 前期容差带需要的抽样设计用同样54格、256/保底4从前期P及合法权重构建，并登记帧、配额和种子；通过现有分位数/初始化函数计算，不能引用旧六格512方案的容差带。此处为过去资料的抽样容差，不是国家置信区间。
- 本小试只需202108、202205、202505的前期设计。未来201901需要201812前期设计时，由同一适配器生成并登记，**当前不声称已完成**。不为三月小试提前重建全部82月输入。

### 5.7 面板兼容

- 实际回答cases增加可选`grid_version`、`profile_cell`、`simulation_role=core|audit`。保留旧`stratum`语义供旧批次读取；新面板优先显式`profile_cell`，缺版本的旧批次继续旧六格，不重新解释旧结果。
- 新Normal视图读独立摘要及预测原子，展示总体/Core-only/Normal审计三个对象；四维网格可以筛选，稀疏格继续标记n和ESS，不强画54格小图。
- 面板接入可以后置，小试评价先输出规范聚合JSON。不能为了让旧面板接受Normal而给其制造模型轨迹或当期真人答卷。

### 5.8 recipe与技术检查

- 新运行包的`evaluation_recipe.schema_version=2`，声明字段独立有效性、三层权重、总体/Normal/真实相邻回访支持、未知池和稀疏展示规则；旧schema1不改。主候选τ24，τ0/8为离线敏感性，不按新评价结果重新挑主候选。
- 后续运行卡拟使用包含在960位置内的前32次技术检查、最多8并发；归一化并经现有评分后至少31份Q8/Q9可用，才继续，随后最多64并发。仅按格式/接口判定，不看拟合成绩。存在致命错误仍按冻结运行器停止规则处理，不为凑31份补发。
- 允许用户已确定的非负、有限、正总和Q9等比例归一化，保留原始总和/合法率和派生版本；负数、非有限值或总和0不修成合法答卷。Q8和Q9后续评价独立，不能因Q9失败删除合法Q8。
- 此处只是**离线接线要求**。完整prompt、发送范围、逐提示token/费用预留、冻结来源、具体停止规则与新授权完成后，才形成可启动运行包；不存在自动继承旧预算的授权文件。

## 6. 对A包的接纳与B线阻塞项

93月清单可用作文件级索引；逐月实际新闻索引优先于旧`coverage.json`的缺标签快照。接受30条原权重缺失、2019年历史深度不足和停摆例外的显式登记。未在本轮重新下载、审计或认证来源。

82月实际微观可用于A线条件重建；其中三期可先做上述接线。2025-11—2026-09的11月只有合成延伸P/E，尚缺合成起点及发布时间规则，不能视作完整模拟就绪。当前`micro_published_at=null`及最后公开全国SCE值未登记，意味着**SCE人口/信念输入的严格B资格尚未认证**，不等于已经证明每份环境资料不可用。

## 7. 接下来验收什么

1. 输出三期新manifest/选人映射、全框架起点来源与校准审计，再投影Core及审计；检查两角色不重叠、没有换名册、无当期答案进入提示。
2. 复用原P/E/价格/政策/新闻模板，做官方Core离线干跑及精确prompt/模型/供应商/参数缓存匹配。旧相同回答只复用一次，不补旧失败。
3. 冻结评价支持/成本与具体发送范围后报本次小试预算。实际LLM Core与审计结果到齐后，分别评价LLM误差和Normal近似误差，再决定Core规模及是否采用扩展。

**暂不做：**全量付费运行、重跑126套网格选择、重做Kimi数据审计，或为尚未完成的11月起点假设虚构B线认证。

## 8. 版本与状态

v1.1只冻结三月小试接线选择。已实现的抽样、扩展与26项测试沿原源码/收据；新增manifest适配、条件分布导出、全框架起点和schema2面板接入在完成前均为待实现。未修改源方法、旧封存结果或生产默认配置。当前新增API=0。
