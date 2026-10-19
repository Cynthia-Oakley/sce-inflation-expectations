# 温度对照：增加的是随机波动，还是有用的人际差异？

2026-10-19。**本批已授权并完成1152次调用，全合法，估$1.2875/$6；主比较未过筛选，参考温度仍0.5。**[结果与复算](temperature_results_20261019.md)。下文保留执行前设计与预算，待授权/调用0描述的是准备时状态。评价复算需使用新`evaluate_sce_temperature.py`补齐四遍事实索引；不重调API。

## 配置与目的

2020-04、2021-05、2021-11、2022-03，每月沿用原24人；温度0.5／0.8／1.0三组，每人每组回答4遍，共1,152请求。模型仍为DeepSeek官方Flash，关闭思考，最多1,024输出token，无自动重试。三组使用完全相同的直接Q8/Q9提示、人口、本人真实上期回答、历史摘要及环境，唯一差别是API温度参数。每组人人用相同温度，不把某种人口特征直接指定为高温。

四个旧开发月包含疫情、上涨与高通胀阶段，用于小样机制筛查，不是独立验证。采用4遍是为了估计同一虚拟人的重复波动，不能算成4倍真实人口。0.5组同期新生成以保留对照；既有答案仅供历史参照。旧数据、新闻和提示均复用，无新增抓取或新闻打标。

DeepSeek官方文档说明温度范围0—2，高温增加随机性，思考模式下不生效；本轮明确关闭思考，不同时改top_p。来源：[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)，核查2026-10-19。实际回包仍可能只返回可变模型别名，不能宣称固定权重；逐次登记返回模型、指纹及有效温度，轮换三组任务次序。

## 看哪些结果

1. **拟合质量**：同支持Q9群体中位数MAE、跨人W1、IQR及照抄上期；Q8另报。Q9沿用原调查权重作敏感性，不称本次24人代表全国。
2. **同一个人的摇摆**：固定画像和信息，比较4遍回答的方差。
3. **不同人的稳定差异**：比较各人4遍均值之间的方差，并用“均值间样本方差−平均人内样本方差÷4”估计扣除重复噪声后的差异；负估计原样报告。该修正依赖近似独立重复，有限遍数和API共同变化可能影响估计，不是人类心理参数。
4. **合法性**：十档概率是否仍在0—100且合计100，解析/计分覆盖、输出截断和接口错误。全量保存，不靠删掉坏回答提高成绩。

有限样本还保留精确方差恒等式：全部输出的总体方差＝个人重复均值的总体方差＋平均人内总体方差。分解按人等权；不能与加权中心分数直接拼成一个全国指标。真人每月只观察一次，无法据此推断其真实重复波动。

主要比较预先固定为**1.0对0.5**，0.8为辅助敏感性；不在两个温度中事后挑最优并称确认有效。主配对区间位于评价结果`additional_paired_intervals.temperature_10_minus_baseline`，默认`paired_intervals`对应0.8对0.5，不混用。探索性继续条件为主W1差95%上界低于0、Q9中心点值不差、模型合法率≥99%；不自动升级默认。按人重抽样保留月份及四遍，未覆盖换月份风险。

**IQR扩大本身不算成功。**若只有同一人重复波动增加，或中心、W1变差，就只记录温度敏感性；有希望也须另期验证。数理、心理、新闻量和购物信息不同时改。

## 工程、预算与现场

共用`run_sce_frozen_trial.py`增加可选的逐组温度映射；旧协议仍使用原标量温度。官方引擎、解析器和Q9计分器不变；只新增准备适配及重复方差分解，未另造运行器。旧Q8已完成批次的三个共享源码修改前副本保存于`outputs/sce_shared_runtime_snapshot_20261019_temperature_v1/`；需要重算旧批次时使用对应冻结源码，不改旧manifest。

配置：[temperature_config_v1.json](temperature_config_v1.json)。有效准备包`outputs/sce_temperature_trial_20261019_v1/`；干跑结果见其`engineering_checks.json`。23项定向测试已通过。新数据发送范围仍需本批确认；授权文件目前`approved=false`。

按已核峰时输入$0.30／百万、输出$1.20／百万估算：预计$1.361，保守预留$5.289，拟定硬上限$6；余额和旧实验额度不自动视作本批授权。费用按回包usage记账，最终不等同厂商账单。

```text
python scripts/run_sce_frozen_trial.py prepare --config docs/workstreams/20261019_advisor_followup/temperature_config_v1.json --folder outputs/<fresh_trial>
python scripts/run_sce_frozen_trial.py dry-run --folder outputs/<fresh_trial> --workers 4
python scripts/run_sce_frozen_trial.py run --folder outputs/<authorized_trial> --workers 4
python scripts/run_sce_frozen_trial.py evaluate --folder outputs/<completed_trial> --out outputs/<fresh_evaluation>
```

prepare/dry-run不重复覆盖本次目录；run须本批明确授权，出现接口错误保留现场并停止，不自动续跑。公开只保留聚合与协议，不发布逐人提示、原问卷或回包。
