# 千问续跑与模型规模对照（2026-10-08）

状态：本轮调用与离线评价已完成。Qwen2.5-72B完成40份；Llama3.3-70B和Llama3.1-8B分别只有4份、1份有效回答，触发格式门槛后暂停。正式模拟模型不切换。

## 用户授权与执行范围

用户同意继续千问及相对类似型号。沿用原40个开发案例（2021-05/06各20个）、原画像/公开E/逐字相同标题摘要消息、temperature=0.5、max_tokens=1024，真人问卷答案和原始ID不进入请求。目标是比较不同模拟模型的水平、分散度、概率表达与跨月变化，不是新的全国指数验证。

本轮三组分别为 Qwen2.5-72B / Llama3.3-70B / Llama3.1-8B，每组计划40份，实际完成情况如下。OpenRouter转接、DeepInfra固定托管；不允许fallback。原Llama3.1-70B的40份回答直接复用，不重复调用。总预算累计不超过$0.50，含此前$0.0414368；每模型不超过$0.25。任何一次调用前预留保守费用；账务未知或返回身份不符时停止该模型。

Qwen是阿里巴巴开发的模型，DeepInfra是本次部署/推理服务提供者，OpenRouter是转接与计费入口。[官方模型卡](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct)。此次性能降级状态属于指定服务端点，不据此推导阿里巴巴模型本身的能力或具体服务故障。

## 预检修订与验收

旧预检默认只允许status=0，保持原行为；新增调用入口显式使用v2预检，允许status=-2且最近30分钟成功率为80%–100%的路由进行原固定案例前两份探针。状态-5、-10、未知状态和其他未明确放行状态继续阻断；缺JSON参数或涨价仍阻断。消息、预算、实际返回模型/provider验收不变。通过探针才继续40份小试；格式失败最多同消息重试一次，不动态改提示词。

13项定向测试通过；新增入口离线检查120份请求与旧结果账务/哈希；旧Llama3.1-70B的Q8/Q9主结果用新评价入口复算逐项不变。原15份用户/Kimi待审文件保持不变。

新入口：`scripts/run_sce_model_followup.py`。固定替代与账务校验：`studies/sce_inflation_expectations/model_followup.py`。原入口/正式study配置不变。评价入口扩展为按每次实际请求快照核查并使用唯一模型标签，防止多个Llama的指标相互覆盖；分别拟合真人与模型，用共同有效样本比较。

## 路径

- 原输入：`outputs/sce_model_counterfactual_20261007/`。
- 原Llama结果：`outputs/sce_earlier_model_trial_20261008/`。
- 新三组运行：`outputs/sce_model_followup_20261008/`；`run_plan.json`为冻结条件，`run_summary.json`与`llm_calls.jsonl`是实际进度/调用记录。
- Llama3.3第一次续跑：`outputs/sce_llama33_resume_20261008/`。免费目录查询连接失败，0真实模型调用，因此没有`llm_calls.jsonl`。
- Llama3.3第二次续跑：`outputs/sce_llama33_resume2_20261008/`；只请求尚未成功的案例，不重复已完成回答。
- 最终共同评价：`outputs/sce_model_followup_analysis_20261008_v3/`；`summary.json`含完整模型效果、不完整模型计数及每次运行新增费用，个人对账文件仅留本地。
- 旧结果独立复算：`outputs/sce_followup_reference_recheck_20261008/`。
- 可提交的汇总及证据哈希：`docs/sources/sce_model_followup_final_20261008.json`。首次运行封存记录：`docs/sources/sce_model_followup_first_attempt_20261008.json`。原回答、请求及真人记录不进Git。

Qwen2.5-7B的40份同输入方案也已离线检查，但当前指定Phala托管，属于新增接收方，需另获明确授权后才能调用；已向用户发出异步确认。本次三组运行不包含Phala。Qwen3-32B因非思考开关与较晚知识窗口，暂作更后候选，不混入本轮。

## 实际执行与费用

- **Qwen2.5-72B：**40次请求、40份有效问卷，无格式重试；API返回费用合计$0.03831376。目录status=-2未阻止本次有效回答，但不能据此保证长期服务稳定。
- **Llama3.3-70B：**首次5次请求得到3份有效回答；一个案例先填概率总和99%，同消息重试遇HTTP429后停止。第一次续跑在免费目录阶段连接失败，未调用模型；第二次续跑新增3次请求和1份有效回答，下个案例两次总和均为99%，触发前两案例验收门。合计8次请求、4份不同案例有效回答，不比较拟合效果。
- **Llama3.1-8B：**3次请求得到1份有效回答；第二案例两次概率总和分别105%和101%，前两案例验收未通过。未擅自归一化这些无效回答，不比较拟合效果。

含前轮Llama3.1-70B，共92次请求、85份不同模型/案例的有效回答，91次HTTP200及1次HTTP429。API已返回的费用总和为**$0.08185786**；另对429保守预留**$0.00137398**，累计预算占用**$0.08323184**。预留不是已确认支出，API回包费用也不是独立账户账单。本轮所有成功API回包的型号与DeepInfra身份通过验收；没有新增Event/Population调用，也没有Phala调用。

续跑沿用同消息、同temperature、同预算，只补缺失案例；加入最小3秒间隔，免费目录连接错误最多重试3次。服务错误与问卷格式错误分别保存，不把被门槛截断的小样本当作模型能力排名。

## 效果与研究决定

Q9先用同一冻结近似计分器分别拟合真人和模型十档概率，再比较个人派生均值。5/6月共同有效样本分别为18/19人；这是同案例等权开发诊断，不是全国headline，两个独立月样本也不是同一持久面板。

- **5月：**Qwen个人MAE为2.479pp，DeepSeek参考为2.911pp；Qwen中位数2.704%，真人3.372%。Qwen月内IQR为0.893pp，DeepSeek为0.605pp，真人为2.405pp。
- **6月：**Qwen个人MAE为3.544pp，DeepSeek参考为2.965pp；Qwen中位数2.217%，真人5.534%。Qwen月内IQR为1.997pp，DeepSeek为1.106pp，真人为3.670pp。
- 原Llama3.1-70B个人MAE为2.421/3.084pp，月内IQR两月都约0.036pp；数值与此前封存结果一致。
- Qwen的原始十档向量分别有10/11种（每月20份），比高度集中的旧Llama更有差异。但Qwen中位数由5月2.70%降至6月2.22%，真人由3.37%升至5.53%，没有复现该样本的上升方向。
- Q8点预测为另一口径：Qwen两月中位数均3.5%，个人MAE为5.184/5.500pp；不能把Q9某项改善推广成所有指标改善。

**本轮决定：不替换正式模型。** 千问部分缓解回答集中，未解决跨月水平和趋势偏差；新增Llama样本不完整。仅两个月、每月20人、每案例一次有效生成，还不能判断长跨度优劣。2021可能在所有模型训练窗口内，本轮不能证明没有记忆影响；模型、托管量化与生成随机性也未单独识别。DeepSeek参考回包名称为`deepseek-flash`，不升级称已核实的V4.1权重版本。

## 下一步与复算

1. 先单独登记问卷概率表达实验：统一校验与纠错协议，对各模型使用相同规则；检验能否减少99%/101%等错误。当前无效回答保持原样，不事后归一化、不追加挑选更好答案。格式问题解决后再补模型对照。
2. Qwen2.5-7B如获新增Phala接收方授权，可沿同40案例完成规模对照，继续计入累计$0.50；未收到回复前不调用。Qwen3先核实非思考开关，再另登记。
3. 对完整候选再冻结更长时期的共同P/E、随机重复与评价窗口，同时检验水平、分散度和趋势；本轮小试不用于宣布最终选型。

离线复算（输出路径必须不存在；不读API key、不调用模型）：

```bash
python scripts/analyze_sce_model_counterfactual.py \
  --inputs outputs/sce_model_counterfactual_20261007 \
  --run outputs/sce_earlier_model_trial_20261008 \
  --run outputs/sce_model_followup_20261008 \
  --run outputs/sce_llama33_resume_20261008 \
  --run outputs/sce_llama33_resume2_20261008 \
  --out outputs/sce_model_followup_analysis_recheck_new
```

验证命令：`python -m pytest -q tests/test_sce_model_followup.py tests/test_sce_model_counterfactual.py tests/test_model_comparison_analysis.py`。续跑时使用有付费记录的最新父运行及封存receipt；0调用目录失败仍独立保留审计，不假造调用日志。`DECISIONS.md`属用户待审批次，本次决定记录在本页，未混改该文件。
