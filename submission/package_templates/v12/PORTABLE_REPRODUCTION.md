# 在评审自己的设备上重新运行

本入口用于原始公开资料→人口/先验与环境匹配→模型作答→连续递推→评价/统计扩展→下游回归。它和默认的封存结果复算并列：默认复算检验旧结果；自备Key运行产生一批新回答。两者不会覆盖原研究。

## 1. 环境与安装

推荐 macOS 或 Linux；Windows 请用 WSL。需要 Python 3.11+、建议20GB以上空闲空间。包内ZIP压缩较高，解压后的公开新闻、微观源文件和独立工作区会占用更多空间。

在**解压后包根目录**执行；下列命令不依赖作者电脑的目录：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python studies/sce_inflation_expectations/run.py --mode all
```

最后一条复算封存的真实答卷、权重、密度、MAE/W1/IQR和Normal后验质量，0API，不需要Key。20人Core例子只是平台接口验收，不是本文实证生成。

另建立一个干净的原工程工作区：

```sh
python review.py install --workspace ./review_workspace
```

`review.py`是包根短入口，调用同一study内的 `simulation/reviewer_pipeline.py`。该命令核对哈希，恢复原代码和公开源快照，保留实际目录间的依赖。不需要作者的外部资料目录、个人账号文件或任何身份信息回填。`review_workspace`须为新目录。

## 2. 检查真实运行链路与重建输入（0API）

```sh
python review.py check --workspace ./review_workspace --out ./review_check
python review.py prepare --workspace ./review_workspace --out ./review_workspace/outputs/reviewer_preparation
```

还可从原始真实回包逐期推进状态，重建并核对全部66,822份实际输入（0API）：

```sh
python review.py audit-inputs --workspace ./review_workspace --out ./review_archived_input_audit
```

这个审计读取封存的真实原始回包并运行原状态更新函数，验证由前一期回包渲染的后继Prompt，而不是读取已保存的有效状态代替递推。它是原运行溯源回放，不冒称一批新模型回答。

`check`用明确标注的注入回答检验四条程序链路，包括“改变前一期回答，后一期Prompt随之改变”、恢复不重复发送、预算停止。这些是工程验收，不作为LLM拟合成绩。

`prepare`使用包内原始公开快照及冻结分类标签，运行原工程的资料整理、人口/先验、时间资格、新闻匹配与提示构造。标签是既有模型分类的中间结果，原始文章、分类结果和来源哈希一并提供；重建相同资料不需要再次为相同文章付费分类。该步骤不是复制封存模型回答，也不重新优化机制参数。完整源资料重建可能以数十分钟计；只需快速验证自己的API时，可在后文workflow命令加 `--use-prepared-inputs`，使用已提供的完整原样准备结果。

原始匿名SCE编号、公开作答日期、内部Agent编号映射都保留。它们是数据溯源编码，不是真实姓名映射。原始数据可能同时含问卷答案，生成函数只读取白名单人口字段与严格过去的信念；评价层另行读取目标答案。不能把“源文件在包内”理解为“目标答案进入Prompt”。

## 3. 先规划少量调用，再用自己的Key运行

```sh
python review.py plan --workspace ./review_workspace --scope smoke
```

默认选每条链路前两期、每期两户；A、B、月度、周度共16个逻辑位置，B首月新生成的两份回答可供月度链初始化，因此通常14个主请求。这里只检验工程通路，不用于估计论文全量误差。

设置评审自己的OpenRouter Key；它只留在当前进程环境中，不写入文件。不要使用作者Key，也不要把Key粘进脚本、README或聊天：

```sh
read -s OPENROUTER_API_KEY
export OPENROUTER_API_KEY
python review.py run --workspace ./review_workspace --scope smoke --out ./review_smoke --budget-usd 0.20 --confirm-paid
```

`read -s`后粘贴Key并回车。实际目的地为 `https://openrouter.ai/api/v1`，模型 `deepseek/deepseek-v3.2`，固定 `siliconflow/fp8`，禁止供应商回退；温度0.5、JSON对象、关闭思考、最多1024输出token。该API不要求平台MCP的单选问卷格式：Q8数值与Q9十档嵌套JSON直接由原适配器校验。

也可用一个命令自动串联“准备→真实生成→独立评价”；完整A/B时再自动接原训练/宏观拟合与下游回归，不需要编码Agent逐批参与：

```sh
python review.py workflow --workspace ./review_workspace --scope smoke --out ./review_pipeline --budget-usd 0.20 --confirm-paid
```

默认首次从源资料重建；已有通过核对的准备结果就直接使用。若只想快速验证API通路，可加 `--use-prepared-inputs`，明确使用包中原样提供的P/E/先验/匹配缓存。完整运行改为 `--scope full` 并自行设置预算；中断时保持其余参数加 `--resume`。少量演示没有足够训练月份，因此不会伪造组合/回归拟合；完整A/B才能自动完成这些步骤。

所有输出保存在新目录。逐条保存原始Prompt、派发意向、原始回复、供应商request ID、时间、usage、成本和字段选择。网络暂错有界冷却，只续从未派发位置；已知技术失败最多补一次；未知在途不会擅自重发。成功字段不因补跑被覆盖。

`--budget-usd`是本地调度的共享“已花费＋未知/在途保守预留”上限，不是OpenRouter服务端美元硬限额；到限保存停止。评审应同时设置自己的服务端Key限额。实际费用取决于服务端费率与可用性。

恢复同一个中断任务，完整保留原命令参数并加 `--resume`：

```sh
python review.py run --workspace ./review_workspace --scope smoke --out ./review_smoke --budget-usd 0.20 --confirm-paid --resume
```

不能在恢复时悄悄改模型、范围、输入或预算。原始主研究没有新增模型调用；以上付费命令只有评审明确执行后才产生费用。

## 4. 四条正式任务和全量范围

`--tasks A B monthly weekly`选择任务；`--scope full`保留原始名单和全部时期：

- A：2019-01至2025-10，82个月、41,970个合格个人月。本人严格更早问卷；缺历史者使用近期匿名联合供体。本人作答日前一天截止，四档新闻4/8/16/32篇、CPI相关度1.5、警示权重1。
- B：2025-11至2026-09，11个月、每月512户，先验按截至该时点已公开SCE全国值校准，月份之间独立初始化。
- 月度个人模拟信念传递：同一批512户，2025-11全新生成根状态，随后10个月使用**评审新生成**的本人上月回答，不用作者旧后续回答。和B同时运行时复用该次新生成的11月根。
- 周度：2025-11至2026-09，47个周五、固定300户。周内沿用本人新模拟信念；新SCE公开后按原规则校准先验。周度目标仍是未来12个月通胀预期。

完整四任务共67,334个有效状态；B首月与月度根共享后，主请求上界约66,822。各任务可以分别运行，不要求一次付出全部成本。请先看 `plan --scope full`，再自行选择预算；不足时程序保存停止，不承诺某个固定美元数必定跑完。

```sh
python review.py plan --workspace ./review_workspace --scope full --tasks A
python review.py run --workspace ./review_workspace --scope full --tasks A --out ./review_A --budget-usd 50 --confirm-paid
```

“50”是示例预算，由评审自行决定。全量耗时通常以小时计，取决于网络、供应商并发和设备；不需要编码Agent逐批操作。

## 5. 新回答的评价、贝叶斯扩展与下游拟合

生成结束后用独立进程评价，评价不能反馈修改同批答案：

```sh
python review.py evaluate --workspace ./review_workspace --answers ./review_smoke/answers.jsonl --out ./review_smoke_evaluation
```

A重新计算同口径全国误差和真人配对/全波次分布比较。B、月度和周度没有同期真人微观数据，不能宣称其W1/IQR拟合经过真人验证。Normal仅在完整Core名单就绪时，从**本次新模型回答**构建τ=8的联合后验；不会用作者旧回答填满少量演示。小演示缺足够Core时明确标记不可用。

如需检查组合与宏观基线的参数从何而来，可实际重跑原拟合，而不是只读已有系数：

```sh
python review.py calibrate --workspace ./review_workspace --out ./review_calibration
```

它重估A早48个月的MAE/MSE组合；宏观模型沿用原来的前36个月训练、后12个月验证选参，再以早48个月重拟、后34个月评价。带 `--fresh-evaluation ./review_A_evaluation` 可改用本次新生成A及A_Normal的完整82个月序列，保存新参数，不改变论文已冻结的旧指标。少量演示不够训练长度时，不伪造这一步。

无需Key也能从公共经济序列重新构建面板、重新估计原扩展窗口回归：

```sh
python review.py downstream --workspace ./review_workspace --out ./review_downstream
```

这一步实际重新拟合OLS，不是读取已保存预测再算RMSE。提供参考数据时核对4,896条预测、192组模型指标、408条配对对照。

如果已全量生成A和B，可将评价输出的A/B月度CSV经 `--a` 和 `--b` 传入同一命令，用新的模拟值重新估计下游回归；不会把新结果强行与旧表相等校验。

## 6. 能复现什么，不能承诺什么

能核查和重跑：资料快照/标签→人口、先验、环境匹配→真实API请求→递推→概率归一化/冻结密度拟合→权重中位数、MAE/W1/IQR→Normal→固定组合与下游回归。原始输入输出、调用凭证和路径哈希支持逐层对账。

不能承诺每次新LLM回答逐字一致或误差恰好等于论文；温度0.5、提供商版本和服务状态都会影响结果。固定模型/供应商若未来不可用会保存错误并停止，不自动换模型冒充复现。本次封包验收没有新增付费API调用，真实外部服务连通性需由评审的Key验证。

本包只供赛事保密评审，包含第三方新闻和公开问卷源快照；不得随GitHub公开再分发。作者Key、账号密码、认证头、付款凭证始终不包含。
