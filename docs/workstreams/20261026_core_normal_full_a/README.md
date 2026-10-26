# 已有T0回答的Core＋Normal全月扩展

2026-10-26。用户授权仅离线接入、扩到每月实际调查人数并比较MAE/W1/IQR；新增API、费用和Q9密度重拟合均为0。原A82回答、评价、报告v05及研究包v02未覆盖，B11未运行或改变。

## 最新：真值口径、缩放策略、组合与宏观校准

用户不认可τ约202过强的邻格依赖；不采用该参数，原τ8仍作为本轮固定扩展对照。τ应与格内有效Core量比较，不能把它解释成202个真实邻居或按全月1300人计算占比。

新增[真值与组合说明](macro_calibration_v1/index.html)：全国主MAE及持续性基线均取官方首发全国值，微观评价则采用共同冻结近似算法。真人重算全国值与官方差距的82月MAE为0.026928、最大0.127817pp，包含拟合/样本/权重/分位数/公布精度等差别，不能全部归给密度算法，也不能直接从模型MAE扣掉。同算法真人目标下原Core/扩展中心MAE .289976/.291984，主表官方目标相应.298407/.301422。主结果不换成分数更好的目标。

原512人Core已经使用54格小格保底8、格内抽样及w/pi后格质量校准，即过采样后恢复真实人口比例。Normal条件分布复用校准权重，有限人口整合再按每人原始质量计算一次，避免放大Core与Normal重复加总。

扩展后按早48月MSE拟模拟权重.134964，后34月MAE .184980、RMSE .256700；持续性.194118/.270076，原Core组合.184125/.256272。MAE拟权仍0。新增离线ARX/岭回归探索只改统计后处理，按早36月训练、2022年12月序列验证选正则强度，再用早48月重估、后34月检查。CPI用原月度参考截止前已发布首发值，不使用目标月未来CPI；高CPI≥4%的状态与交叉项事先固定，不调阈值。

后34月宏观不含模拟的MAE .214229，加入扩展模拟 .214883，状态与模拟交叉 .209441，暂不及简单组合；有配对不含模拟控制。仅82个宏观月，不能把Normal行数当额外时间样本；两段历史已查看，个人日期A与共享参考CPI也不构成严格统一截止B预测，不升级配置。

协议为`macro_calibration_protocol.json`；数据和拟合系数位于`outputs/sce_full_a_macro_calibration_20261026_v1/`。4项新增计算/时间边界测试及相关回归通过，0API/0密度拟合，原报告和来源不改。复算输出必须全新：

```bash
"$PY" scripts/analyze_sce_full_a_macro_calibration.py --out outputs/<fresh_macro_calibration>
"$PY" scripts/report_sce_full_a_macro_calibration.py --source outputs/<fresh_macro_calibration> --out docs/workstreams/20261026_core_normal_full_a/<fresh_macro_report>
```

## 后续：扩大τ搜索，并按早期真人全国指标训练

用户追问0/8/24的依据与训练优化上限后，另立[tau_sensitivity_protocol.json](tau_sensitivity_protocol.json)，原τ8结果不改。原三个值只是零/适度/较强收缩的粗网格，并非理论规定。新检验只改τ：早48月全国Q9 MAE训练，候选覆盖0至1,000,000、完全父池极限及两轮训练内局部细搜；共1,681个不同取值。使用训练真人全国指标属于监督统计校准，与原来“仅恢复LLM留出回答”的选择不同，不能混称。后34月目标在新选择文件封存后用于检查；这些历史时期以前已经被查看，不是新的盲测。

搜索范围内训练最小MAE0.356010pp，多个τ并列，按较小值规则选τ约202。对照原Core/τ8/训练选参：早48月0.357760/0.359526/0.356010，后34月0.214613/0.219393/0.220590，全82月0.298407/0.301422/0.299860。训练收益没有保留为后期优势；虽然全期回到0.3以下，也仍比原Core略差，不能据首位数字切换配置。新检验不声称连续参数空间的严格全局最优，不自动采用该参数。

图文见[训练选参敏感性](tau_sensitivity_v1/index.html)，输出为`outputs/sce_full_a_core_normal_tau_20261026_v1/`。零API、零密度重拟；新的快速原子质量曲线在82个月的τ0/8/24均与旧冻结结果一致，5项新增测试及44项相关回归测试通过。项目根目录复算，输出目录必须全新：

```bash
PY='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$PY" scripts/analyze_sce_full_a_core_normal_tau.py --out outputs/<fresh_tau_analysis>
"$PY" scripts/report_sce_full_a_core_normal_tau.py --source outputs/<fresh_tau_analysis> --out docs/workstreams/20261026_core_normal_full_a/<fresh_tau_report>
```

## 原τ8扩展：先看结论

82个月（2019-01—2025-10）已全部扩展。全框架98,382个人月＝41,970个真实模型Core＋56,412个统计Normal，每月实际人数976—1,372。原权重缺失30条保留null、不填1；加权统计支持为98,352个人月。Normal不是新增独立LLM回答，也不代表找回了本人真实先验或完整个人轨迹。

主参数τ=8，只由早48个月已有LLM回答的遮蔽检验确定；后34个月和当期真人答案没有用于选择τ。0/8/24三个候选全部保留敏感性。τ8的遮蔽中心MAE为0.177573，τ0为0.177979，优势很小，不称稳定最优。各月两种固定留出种子，属于抽样/信息留出检查，不是两遍新LLM生成。

全国Q9中位数MAE：512人加权原版0.298407→扩展版0.301422pp，增加0.003015pp；RMSE0.415121→0.414236略降。2021年MAE0.577424→0.565315，改善0.012109pp。整体拟合基本保持，但没有额外的全期MAE收益，仍高于公开历史参照0.223171pp。

统一全波次真人目标下，W1 2.197466→2.194265pp；模拟跨人IQR 2.244954→2.248071pp，真人为5.258538pp。两项改变都很小，微观过度集中仍在。这里的原版W1是“512人估计分布对全波次真人”，不是v05的同名单W1=2.219；二者不交叉混比。

早48月/后34月组合也按原口径重算：MAE拟权仍为0，后34月MAE0.194118；MSE拟得模拟权重0.134964，后34月组合MAE0.184980，较原版组合0.184125略差。没有据真人成绩把主τ改成其他候选。

## 算法与人口口径

沿用学历×数理×年龄×收入54格，缺失画像保留已知特征；新人、回访者、未知类型分池，不静默跨池借答卷。Normal使用同格有效模型回答分布，小格向同入组类型、人口特征匹配最多的其他格借信息。本地有效样本量和τ决定借用比例；使用完整十档Q9答卷原子及其冻结分数，不平均概率造一张标准答卷。这是加权经验贝叶斯式/伪Dirichlet扩展，不宣称精确多层抽样后验或完全复制ConsumerSim。

条件分布估计使用原Core的T0校准权重；有限人口汇总时，每个合法Core只保留自身原始调查权重，其余Normal及字段无效Core的质量按预测分布积分一次，不能再叠加一遍已放大Core权重。主中位数、W1、IQR由精确原子CDF计算，不靠随机抽取Normal凑到好成绩。

每月另物化完整人口JSONL，全部目标都有Core/统计Normal、原始权重/缺失标记、逐字段来源和固定种子抽取；这些逐人抽取只供检查，不作为主指标。Q9联合答卷保留原供体配对Q8，Q8边际另标，不把这两份视图称为已经恢复完整联合行为或连续轨迹。

两组“14”不同：原T0剔除的14份跨标称月完成记录不作为Core，但本次仍在全调查框架中得到统计Normal预测；不能称其已接受个人日期新闻模拟。Core内部另有14个Q9字段（1个原技术后备、13个密度拟合失败）不进入供体库，按统计后备处理；它们的Q8仍保留。实际合法Q9模型供体41,956，Q8模型供体41,970。

## 选参、隔离与核查

在早48个月，按既有Core的入组类型×实际画像分组，固定种子遮住部分合法模型Q9回答，保留训练供体；训练与留出分别恢复相应有效Core组质量，修正小格留出比例不同。单例组不假装已验证，覆盖率另列。选参首先最小化月/种子等权中心误差，W1平手时辅助，再偏好较小τ；协议在新真人绩效评价前保存。历史后期曾参与项目探索，不能再称完全未触碰盲测。

评分投影在评价侧先将逻辑字段逐一核对原始main/repair回复及输入manifest，再从旧混合评分缓存导出只包含模型实际使用向量的评分表。prepare/predict只解析模型专用表，混合缓存仅作来源哈希核验而不作为预测输入。预测封存后才由独立评价器打开真人全波次真值。没有用Normal真人答案估计条件分布。

44项相关测试通过；独立逐行检查82个月的身份、Core保留、字段供体来源、缺权重状态、人口行数和三种τ的质量守恒。最大质量误差3.64e-12，原T0 487项冻结来源全部未变。平均约20.16%的全人口质量由邻格经验先验贡献，约1.47%的质量没有同格Core，需纯邻格后备；这些是近似依赖的诊断，不是精度保证。

## 文件与复算

- 图文结果：`results_v1/index.html`。
- 冻结协议：本目录`protocol.json`。
- 模型专用评分投影：`outputs/sce_full_a_model_score_projection_20261026_v1/`。
- 最终只含人口/模型输入：`outputs/sce_full_a_core_normal_prepared_20261026_v3/`。
- 最终封存预测：`outputs/sce_full_a_core_normal_prediction_20261026_v2/`，含parameter_selection.json、82个月的atoms_private.json与expanded_population_private.jsonl。
- 正式评价：`outputs/sce_full_a_core_normal_evaluation_20261026_v3/`，含summary.json、82行monthly_public.csv、7行yearly.csv及manifest。
- 独立审计：`outputs/sce_full_a_core_normal_readiness_20261026_v1/final_acceptance.json`。

旧prepared_v1/v2、prediction_v1保留并标记工程中间版本：前者做了字段schema适配，后者采用旧混合缓存的模型向量查分，未作为正式研究结果评价；后续加强模型专用投影、原始回复绑定和有效Core留出权重一致性。evaluation_v2与v3数学结果相同，v3另强化原子ESS标注和质量审计字段；原文件未覆盖。

重新评价已封存预测，无需API，输出目录必须全新：

```bash
PY='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
"$PY" scripts/evaluate_sce_full_a_core_normal.py \
  --prediction outputs/sce_full_a_core_normal_prediction_20261026_v2 \
  --out outputs/<fresh_core_normal_evaluation>
```

当前预测可复算为另一个新目录：

```bash
"$PY" scripts/run_sce_full_a_core_normal.py predict \
  --inputs outputs/sce_full_a_core_normal_prepared_20261026_v3 \
  --out outputs/<fresh_core_normal_prediction>
```

统计生成不会凭空增加模型未表达的判断类型，人数补齐不能被当作更多独立信息。当前结果只支持“人口表示完整、误差大体保持”的结论，尚未解决微观分歧不足。完整私人缓存不进入公开研究包；是否纳入最终主报告另版处理，不改写v05。
