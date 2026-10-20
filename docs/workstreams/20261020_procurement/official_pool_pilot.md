# 官方人口问卷MCP：10人技术试测

2026-10-20。用户已明确批准10人试测及$0.10上限。已发起一次模拟工具请求，服务端返回问卷校验错误，**逐人回答为0，SCE答题兼容性未通过**。没有自动重试、扩样或切换模型，实际扣费未返回。技术结果见[核查摘要](official_pool_pilot_result_v1.json)，本页保留配置与失败原因。

## 本次结果：连通成功，当前开放题格式被拒绝

服务端原文：`questionnaire[0].options must contain at least two options.`，错误类型`ValueError`。虽然MCP外层`isError=false`，正文明确为`status=error`，不能把HTTP成功或收到回包记为模拟成功。

本次Q8/Q9用`options=[]`开放题载体，实际部署额外要求至少两个选项。目录schema的问卷条目只声明通用object，没有写出这项内部限制，所以离线参数检查可以通过，远端仍拒绝。6项离线测试验证的是授权、哈希、预算、文件保护与档位顺序，并未验证远端开放题能力。

用户质疑后已[补查使用规范](platform_gpt_requirements.md)：Q9的十个真实通胀区间可以作为非空`options`，正文要求分配概率；此候选尚未试测。当前不能断言服务只能单选或GPT无法完成概率题。已准备正式字段候选，不伪造选项、不改旧失败结果，新增付费调用仍为0。

没有10份回答，因而没有Q8/Q9合法率、拟合误差或GPT行为表现可报告。不能通过给Q9十个区间做单选来替代概率分配；也不添加无意义选项绕过校验。其他数值/开放题模式是否支持仍须官方确认，不能据这一条错误断言所有模式均不支持。

执行记录：v1在免费的能力查询阶段连接中断，模拟工具调用为0；免费连通性恢复后，原封不动复制已批准的协议/输入至v2，只发送了首次、也是唯一一次模拟工具请求。v2原始回包及`inspection.json`保存在本地，两个现场均保留。没有付费补发。$0.04是原计划估算，回包未带账单，不能记成实际消费或保证零扣费。

## 1. 这次能回答什么

检查官方人口问卷服务能否返回逐人Q8点预期和合法Q9十档概率，以及能否保存原始回答、辨认实际模型和计费信息。**不以10人结果评价拟合好坏，也不当作原SCE样本的GPT对照。**

目前免费能力返回的服务端模型是`gpt-4o-mini`，而非可直接假定的GPT-4o。工具没有模型、温度、逐人本地P/E或本人历史参数。若执行前模型配置变化，程序在付费调用前停止。

## 2. 具体配置

- 人口：平台`nemotron_usa`合成人口池。能力目录登记59,994个可索引persona，来源NVIDIA Nemotron-Personas-USA，CC-BY-4.0；保留署名与来源，不公开原始persona。
- 数量：10人，一次MCP请求。仅设男女各50%的技术抽样目标，不宣称代表全国SCE。使用`preserve_joint`，禁止虚拟人口回退；实际抽样比例以回包为准。
- 抽样种子：20261020；并发2。它控制抽样，不等于模型生成随机种子。接口未暴露生成温度。
- 输入：2022年6月10日已发布的BLS食品价格背景和Q8/Q9题目；没有任何真实SCE个人资料、历史回答、当期答案或权重。
- 问卷：Q8/Q9合在一个开放题载体，`options=[]`，请求返回一个JSON对象。Q9档位顺序读取现有模型常量。此结构通过公开schema检查，但本次已被服务端额外的选项数校验拒绝；不要按此配置重复提交。
- 时间边界：历史情景，仅用于兼容性测试；没有排除服务端模型训练中的后来知识，不称严格事前预测。
- 调用限制：一次付费工具请求，无客户端自动重试、不扩样、不换模型。服务内部是否重试不可见，不能声称服务端也零重试。

价格事实来自本地已核首发：2022年5月在家食品同比11.9%、未季调环比1.3%，发布于2022-06-10 08:30纽约时间，USDL-22-1113。题目明确这是食品类别，不能等同于整体未来通胀。来源：[BLS首发PDF](https://www.bls.gov/news.release/archives/cpi_06102022.pdf)。本批不重新读取或发送SCE微观记录。

## 3. 费用及权限

按组委会既有邮件所述每受访者$0.004，10人预计$0.04，本批申请上限$0.10。费率依据见`docs/LOCAL_RUNTIME_ACCEPTANCE.md`及`docs/LOCAL_HARNESS_RUN_PLAN.md`；**未取得新的服务端报价或账单，未核到账户Sim余额。**

接口没有硬预算参数；本地只能限制为10人、一次请求，不能承诺远端强制美元限额。估算与实际账单分别记录，未知费用不写成零。连接错误可能已经计费，保留现场、不自动补发。按AGENTS.md第11条，具体预算需用户明确确认后执行；不使用平台Chat。

## 4. 已完成与待确认

- 已完成：复用同日能力证据；额外免费核查性别标签Female/Male及对应索引数；准备一份合法请求、冻结协议和价格来源；6项关键离线检查通过。
- 已完成：复用已有MCP客户端和脱敏方法，直接保存完整RPC内容，避开便捷`call_tool`对非JSON文本截断至2,000字符的行为。使用独占写入标记防重发；批准须绑定协议哈希，修改请求/预算/代码均需重新准备。
- 已完成：用户具体预算批准、一次真实工具调用和原始回包核查；问卷校验错误，未获得逐人回答，Q8/Q9合法性无法检查。
- 原始回复和persona仅保存在本地忽略目录；有条件公开的仅为技术摘要。无效概率原样保留，不归一化，不因一条无效自动重试。
- 下一步：先确认数值开放题及概率分配的正式参数/示例，再确认同一人接本地P/E与历史、模型选择及原答/费用接口。未明确支持前不为“跑通”追加选择题试测，不把其他人口/题型的成功冒充SCE兼容。

## 5. 文件与执行

实际请求与回包：`outputs/sce_platform_survey_pilot_20261020_v2/`。v1是免费预检失败现场；两包同一协议/输入/预算，不覆盖旧包。

```text
python scripts/run_sce_platform_survey_pilot.py prepare --folder outputs/<fresh_pilot>
python -m pytest tests/test_sce_platform_survey_pilot.py -q
```

以下是本批历史执行命令，**已执行并停止，不得再次运行或复制造成付费补发**：

```text
python scripts/run_sce_platform_survey_pilot.py run --folder outputs/sce_platform_survey_pilot_20261020_v2
```

免费标签证据：`data/raw/mcp_checks/2026-10-20_population_pilot_free_v1/field_values.json`。原同日服务能力：`data/raw/mcp_checks/2026-10-20_procurement_free_v1/evidence.json`。以上证据和运行包不进Git。

官方说明：[数据服务](https://socioverse.fudan-disc.com/docs/guides/data-services/)、[Sim与Agent计费](https://socioverse.fudan-disc.com/docs/zh/hosted/quotas-and-billing/)。数据署名：[NVIDIA Nemotron-Personas-USA](https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA)。模型别名列表不能代替实际运行身份。
