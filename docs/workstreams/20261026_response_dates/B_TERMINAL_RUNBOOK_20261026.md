# B线个人日期版：本机独立后台运行

本批：2025-11—2026-09，11期×512代理，一遍，共5,632主请求；技术失败每个位置最多补一次，最多11,264次物理尝试。用户明确要求由Codex代启动；预算采用此前B线提案的保守总帽$8，预计主批$5.5634。不会自动增加预算或换供应商。

**已于2026-10-26 19:36（北京时间）全部完成。**主5632＋补16，最终5632份Q8/Q9均可用；报告费$4.68201、未知预留$0.06013。后台已正常退出，不需要再run/resume。原始MAE .348509，持续性.172727，固定MSE组合.144277。结果见正式目录evaluation/index.html及fixed_model_comparison.json。

**原启动记录：已于2026-10-26 19:13（北京时间）启动。**用户对明确列出的资料范围、OpenRouter／SiliconFlow目的地、5632主请求及$8主补总帽回复“同意”；`human_approval.json`与协议授权绑定。独立后台PID 22562，实际完成状态以`progress.json`／`worker_receipt.json`为准。此前自动审批拦截另存保留，不能把旧“未启动”状态用于本次判断。不要再开第二个生成器。

## 固定配置

- OpenRouter → SiliconFlow FP8 → DeepSeek V3.2；温度0.5、JSON、关闭思考、最多1024输出token。
- 前一年同月的完成日频率、日期种子20261026，为代理抽取合成作答日；个人环境截止=min(合成作答日前一天，原全局D)。全局D不动。
- 四档4/8/16/32新闻、CPI相关度1.5、个人警示1。January使用Kimi修复快照与增量基础标签。人口、设计权重、公开历史锚及合成联合Q8/Q9先验不变。
- 独立月一步预测，不增加出入、Normal或连续递推。不把预测日期随机化称成模拟完整月末信息。较晚抓取的新闻文本与模型知识边界仍保留限制，属于回顾性时点回测。

## 入口与存档

正式目录：`outputs/sce_recent_b_sampled_terminal_20261026_v1/`。

完整输入：`outputs/sce_recent_b_sampled_dates_complete_20261026_v1/`。

源码为`studies/sce_inflation_expectations/experiments/recent_b_sampled_terminal.py`。运输层直接复用既有full-A冻结消息容错调度器，未改写旧A/B模块；先进行11个官方Core离线单元/5632提示验收，再由本地冻结消息适配器调用API。执行后端不是平台Chat或官方MCP。

在项目根目录查看进度：

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/run_sce_recent_b_sampled.py watch \
  --run-dir outputs/sce_recent_b_sampled_terminal_20261026_v1
```

Ctrl+C只退出观察。Codex退出或额度耗尽不影响已启动的独立后台进程。`caffeinate`运行期间防止空闲系统休眠；断电、强制睡眠、关机或长期断网仍会影响本机程序。

启动（本轮由Codex代执行，不要再开第二个生成器）：

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/run_sce_recent_b_sampled.py run \
  --run-dir outputs/sce_recent_b_sampled_terminal_20261026_v1 --confirm-scope-and-budget
```

仅在已确认进程结束且主批或补批未完成时，保留原账本续跑：

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/run_sce_recent_b_sampled.py run \
  --run-dir outputs/sce_recent_b_sampled_terminal_20261026_v1 --confirm-scope-and-budget --resume
```

未知在途请求不重发；已完成主批不重跑。生成已完成但评价失败时不能用resume再调用API，应使用离线`_evaluate`并另存失败评价目录。

## 容错与费用

前32请求最多8并发；正常回包至少16、其中至少95%格式合法后进入主批32→64并发。零星连接、超时或5xx只记失败，不立即停整批；429、Retry-After、连续3次传输失败或滚动32回包至少8次失败触发有界冷却。连续无进展/不健康段及总冷却1800秒仍有限制。

主批完成后，只针对传输、截断或结构失败补一次；原成功字段不被补答覆盖。原始主答/补答、发送意图与费用逐条存档；发送前fsync意图，防止崩溃后重复扣费。认证、余额、供应商/模型不符及费用异常保存停止。SDK自动重试和供应商回退均为0。

主批和补批共享$8；账本以实报费＋未知请求保守费＋在途满输出预留控制发送。到限提前停止。全部旧运行和原始资料保留。

## 自动评价

生成与评价分离进程。全国Q9与官方headline比较，按原冻结计分算法计算MAE、RMSE、bias和胜出月份；同时列截止前最后公开SCE基线。组合MSE权重0.133976257来自A早48个月；MAE拟权0。公平SCE＋CPI与再加模拟的模型参数已在A冻结，B不重估。

近期无真人微观数据，因此Q8、模拟人群IQR及分组只描述输出，不称真人W1或微观准确率。完成后查看`evaluation/index.html`、`evaluation/monthly_comparison.csv`和`evaluation/fixed_model_comparison.json`。`worker_receipt.json`给出最终状态，`generation.log`/`evaluation.log`分别保存诊断。

验收证据：24项定向测试；全5632位置假回包回放，注入2次传输失败并仅各补一次，0API、未开真值。正式包在源码冻结后重新准备并校验哈希。


## 首次B与新版B的公平比较（2026-10-26离线复算）

首次B为sce_recent_b_overnight_20261025_v3，评价源sce_recent_b_readout_20261025_v2；新版为sce_recent_b_sampled_terminal_20261026_v1。逐月目标、官方发布版本、全局D、历史全国锚一致；44个P/先验/篮子/全局E文件逐字节一致，人口及先验来源目录相同。LLM可见的逐人环境改变。全部复算0API、0拟参，旧结果保留。

- 原始全国Q9 MAE：首次0.240815→新版0.348509pp，增加0.107694pp、44.72%。RMSE0.296171→0.432837；bias从−0.114437转为+0.258760。主要增加来自202603与202606高估，202608/09改善。
- 同一A早48 MSE权重λ=0.133976257：首次答卷离线组合MAE0.159907→新版0.144277，RMSE0.200121→0.174003。共同持续性MAE0.172727。旧报告当时λ=0、组合等于持续性；不能直接用旧0.172727对新0.144277，宣称全是机制收益。
- 同一A冻结宏观模型：无模拟MAE0.160025；加入旧模拟0.149295，加入新模拟0.142174。参数保持不变。MAE拟合的凸组合λ仍为0，不隐去这一结果。
- 每月模拟跨人IQR均值首次2.324981→新版2.545613pp；近期没有真人微观，只能描述输出，不能称微观误差下降。

两次均每月512个全LLM代理，使用54格小格过采样与权重校准，**均未进行Core＋Normal贝叶斯式扩展**。权重代表声明旧源框架；B缺目标期微观人数/边际，不能称已补到同期实际1300人。源框架约989—1099人，不等于同期真实人数。若后续离线扩展，应明确扩至旧框架还是固定代理规模，并与未扩展结果并列；不得为凑人数声称增加独立信息，也不能直接套A的扩展权重与组合参数。

新版同时改新闻数量、CPI相关度、逐人信息截止，并补January原文；不是单因素随机对照。两次均单遍、独立月、公共历史锚校准的合成先验，无人口出入/连续递推。11期回顾性结果已知，历史文本/模型知识边界仍待披露；不称严格事前封存预测。正式报告和研究包尚待纳入这份公平比较。
