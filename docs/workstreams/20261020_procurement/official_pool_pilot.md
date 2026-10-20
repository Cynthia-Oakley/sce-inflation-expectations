# 官方人口问卷MCP：10人技术试测

2026-10-20。用户要求先试跑官方接口，再考虑切换模型。本页是具体准备记录，不表示真实模拟已经执行。新增付费调用为0；本批预算确认已发送，批准前不调用。

## 1. 这次能回答什么

检查官方人口问卷服务能否返回逐人Q8点预期和合法Q9十档概率，以及能否保存原始回答、辨认实际模型和计费信息。**不以10人结果评价拟合好坏，也不当作原SCE样本的GPT对照。**

目前免费能力返回的服务端模型是`gpt-4o-mini`，而非可直接假定的GPT-4o。工具没有模型、温度、逐人本地P/E或本人历史参数。若执行前模型配置变化，程序在付费调用前停止。

## 2. 具体配置

- 人口：平台`nemotron_usa`合成人口池。能力目录登记59,994个可索引persona，来源NVIDIA Nemotron-Personas-USA，CC-BY-4.0；保留署名与来源，不公开原始persona。
- 数量：10人，一次MCP请求。仅设男女各50%的技术抽样目标，不宣称代表全国SCE。使用`preserve_joint`，禁止虚拟人口回退；实际抽样比例以回包为准。
- 抽样种子：20261020；并发2。它控制抽样，不等于模型生成随机种子。接口未暴露生成温度。
- 输入：2022年6月10日已发布的BLS食品价格背景和Q8/Q9题目；没有任何真实SCE个人资料、历史回答、当期答案或权重。
- 问卷：Q8/Q9合在一个开放题载体，`options=[]`，请求返回一个JSON对象。Q9档位顺序读取现有模型常量。接口schema允许此结构，但服务能否实际处理开放题尚待试测；不能用离线检查代替远端验证。
- 时间边界：历史情景，仅用于兼容性测试；没有排除服务端模型训练中的后来知识，不称严格事前预测。
- 调用限制：一次付费工具请求，无客户端自动重试、不扩样、不换模型。服务内部是否重试不可见，不能声称服务端也零重试。

价格事实来自本地已核首发：2022年5月在家食品同比11.9%、未季调环比1.3%，发布于2022-06-10 08:30纽约时间，USDL-22-1113。题目明确这是食品类别，不能等同于整体未来通胀。来源：[BLS首发PDF](https://www.bls.gov/news.release/archives/cpi_06102022.pdf)。本批不重新读取或发送SCE微观记录。

## 3. 费用及权限

按组委会既有邮件所述每受访者$0.004，10人预计$0.04，本批申请上限$0.10。费率依据见`docs/LOCAL_RUNTIME_ACCEPTANCE.md`及`docs/LOCAL_HARNESS_RUN_PLAN.md`；**未取得新的服务端报价或账单，未核到账户Sim余额。**

接口没有硬预算参数；本地只能限制为10人、一次请求，不能承诺远端强制美元限额。估算与实际账单分别记录，未知费用不写成零。连接错误可能已经计费，保留现场、不自动补发。按AGENTS.md第11条，具体预算需用户明确确认后执行；不使用平台Chat。

## 4. 已完成与待完成

- 已完成：复用同日能力证据；额外免费核查性别标签Female/Male及对应索引数；准备一份合法请求、冻结协议和价格来源；6项关键离线检查通过。
- 已完成：复用已有MCP客户端和脱敏方法，直接保存完整RPC内容，避开便捷`call_tool`对非JSON文本截断至2,000字符的行为。使用独占写入标记防重发；批准须绑定协议哈希，修改请求/预算/代码均需重新准备。
- 待完成：具体预算批准、一次真实调用、原始回答结构核查及Q8/Q9合法性检查。不能提前称接口跑通。
- 原始回复和persona仅保存在本地忽略目录；有条件公开的仅为技术摘要。无效概率原样保留，不归一化，不因一条无效自动重试。
- 若能返回合法逐人答案，下一步仍需确认如何给同一人传本地P/E与历史、选择模型并导出参数；本次成功本身不解决这些接口缺口。

## 5. 文件与执行

准备包：`outputs/sce_platform_survey_pilot_20261020_v1/`，包括`request.json`、`protocol.json`、实际工具schema与`readiness.json`。不覆盖旧包。

```text
python scripts/run_sce_platform_survey_pilot.py prepare --folder outputs/<fresh_pilot>
python -m pytest tests/test_sce_platform_survey_pilot.py -q
```

只有收到明确确认，并将原确认及准确协议哈希存入该包的`authorization.json`后，才执行：

```text
python scripts/run_sce_platform_survey_pilot.py run --folder outputs/sce_platform_survey_pilot_20261020_v1
```

免费标签证据：`data/raw/mcp_checks/2026-10-20_population_pilot_free_v1/field_values.json`。原同日服务能力：`data/raw/mcp_checks/2026-10-20_procurement_free_v1/evidence.json`。以上证据和运行包不进Git。

官方说明：[数据服务](https://socioverse.fudan-disc.com/docs/guides/data-services/)、[Sim与Agent计费](https://socioverse.fudan-disc.com/docs/zh/hosted/quotas-and-billing/)。数据署名：[NVIDIA Nemotron-Personas-USA](https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA)。模型别名列表不能代替实际运行身份。
