# 价格体验机制 v1：工程验收

日期：2026-10-06。用户要求按文献方案落地；主 Agent 实现，两个 Luna Max 子 Agent 分别核查数据和已有输出，并独立复审关键接线。**本轮真实 LLM / 付费 MCP 调用均为 0；没有新机制效果结论。**

使用入口：[PRICE_EXPERIENCE_MECHANISM.md](PRICE_EXPERIENCE_MECHANISM.md)。下一轮：[对照运行卡](PRICE_EXPERIENCE_RUN_CARD_20261006.md)。

## 1. 已落地

1. **P 侧车：** CE 联合消费记录条件加权抽样，按固定 ID/seed 保留潜在抽样位置；整套份额、来源、支持度、回退和画像绑定哈希一起保存。当前支持单个月份的 A 线侧车。
2. **E 视图：** 三个价格渠道单独记录；共有指标和新闻完整保留，篮子可控制展示和排列。公共事实集合哈希与实际视图顺序分别保存。
3. **B 接线：** 原问卷不变，增加家庭表达/篮子展示/信息排序。实际 LLM provider 调用新 renderer；错误提示词配对会在 API 前拒绝。没有回应方向系数、随机答案噪声或上月答案。
4. **运行入口：** 新增 `--mechanism/--experience`；原 P/E/simulation 切换继续有效。有效输入、代码快照、机制及公共事实哈希、轨迹、调用计数均留存。规则式运行显式声明不验证机制行为。

源码：`studies/sce_inflation_expectations/price_experience.py`、`experience_mechanism.py`；配置：该 study 的 `mechanism/`；构建及小试准备脚本：`scripts/build_sce_price_experience.py`、`prepare_sce_mechanism_pilot.py`。

## 2. 来源与实际输入

原始资料目录：`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/ce_experience/20261006/`。

- 官方 ZIP `intrvw20.zip`：53,895,332 字节；SHA-256 `de226eaf9b18eb4721e8aca385c94101b8061a74decc5b9f52667c29cf01ba8a`。
- `intrvw20/fmli204.csv`：5,205 唯一记录，实核年份 2020 / 月份 10–12；5,203 可用，2 条因支出一致性或正值条件排除。
- 官方当前字典 `ce_pumd_dictionary_official.xlsx`：1,355,152 字节；SHA-256 `613810d32de105bcd32fa9030d378472afb4dab23d1922be7b71b0c522d0334c`。教育及 tenure 码值按明确有效期核查；作者镜像仅保留为次级核验。
- 普通命令行下载曾返回 403；浏览器官方普通下载/同源读取成功，未使用访问限制绕过。来源记录、镜像记录及先前下载失败记录均保留。

正式候选输入只使用：

- `/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/price_experience_20261006_v1/n300/202105/`
- `/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/price_experience_20261006_v1/n300/202106/`

各 300 份篮子，独立 donor 分别为 286 / 288 个；放宽部分匹配条件的分别为 107 / 103 人，原本没有观测到的字段不计为“放宽”。候选池至少 25 条，最小加权有效数量为 19.48 / 19.28。支持度阈值只是工程初值，不能保证画像间匹配完全或经济因果有效。

两月共有 243 个 ID，221 个画像完整一致、236 个 donor 一致。潜在抽样位置按 ID 固定；无关画像字段变化不会重抽，匹配条件变化仍可能更换 donor。不能据此声称模拟了真实家庭预算的跨月更新。

各月每组 300 条实际 Observation/提示词预览，合计 2,400 条。公共事实和问卷跨组一致；每人的 77 条信号和 30 条新闻均保留。实际序列化提示词最大 10,868 字符，小于运行器 16,000 字符门槛。

已准备的 `n20/202105` 与 `n20/202106` 包从对应 300 人中按 seed=42 无答案抽样。逐 ID 核对篮子与母样本一致，子包 P 哈希重新绑定。两月各组配对比较，不能把两个 20 人包叫同一长期面板或全国代表人口。

## 3. 验证证据

**48 项相关测试通过：** 机制/构建/小试 9，原模型 22，费用门槛 6，导出保护 11。

机制检查包括：手算 `PQ+CQ` / 份额、真实字典教育码、异常/重复记录、整条联合抽样和带权概率、ID/顺序稳定性、匹配回退、禁止画像错配/未来信息、四组公共事实和问卷保留、真实 LLM 路径的替代客户端提示词/审计接线。替代客户端不联网，没有真实模型费用。

**官方框架实跑两月各 300 人：**

- `outputs/local_runs/sce-mechanism-v1-20261006-202105/`
- `outputs/local_runs/sce-mechanism-v1-20261006-202106/`

两次均保存 run manifest、有效 P/E/simulation、完整代码快照、300 条 Observation、300 条有效规则式回答及 DuckDB。成本账本均为 0 次 LLM 调用，`mechanism_behaviour_test=false`。逐条核验实际 Observation 的篮子及渠道状态与对应候选提示词预览完全相同。

**这 600 条规则式回答只证明框架能传递和保存输入。规则式 B 本身不使用消费篮子，不能比较它的数值判断机制好坏。**

机器收据及逐文件哈希：

`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/outputs/price_experience_20261006_v1/engineering_acceptance.json`

独立归档核验脚本：同目录 `audit_acceptance.py`。各输入包的 `source_snapshot/`、`manifest.json` 可追溯到构建时代码和配置。中途初版运行曾在写 manifest 时出现循环变量覆盖错误；已修复，用新 run_id 重跑，初版不纳入通过记录，不称为完整运行证据。其他中间输入/预览也不作为下一轮候选。

## 4. 必须保留的研究限制

- 本版是 A 后验代理：2020 全年 PUMD 的公开时间晚于目标月，当前 CE 包也不是首发版本。单项 E 日期门槛通过，不等于 P 全面 PIT 合规。B 线明确拒用本包。
- `TOTEXP` 含捐赠/养老金等；这是支出相关性代理，不是个人 CPI。真实购物频率、当地买价、角色和注意力均未观测。
- 同期 SCE 与异期 CE 是不同调查对象；收入、教育、年龄含义和住房口径仍有跨调查误差。一个固定 donor seed 不能覆盖这种不确定性。
- 当前新闻文本历史版本限制、公共截止点与真人早期作答日的差别不因机制落地而消失。
- 模型知识可能含历史事件；本轮不验证训练记忆是否导致水平偏离。
- 真实新机制尚未跑；真人/Q9 近似计分差异、旧 Core 的偏低及过窄问题均仍存在。

## 5. 后续行动

先按 [真实对照运行卡](PRICE_EXPERIENCE_RUN_CARD_20261006.md) 确认新数据发送范围、模型/价目及总预算，再跑五组小试。对比总体水平、人群分布和问卷格式，不把标准差上升当成功；若值得扩大，固定设计后换独立月份验证，再讨论 Normal 扩展与校准。当前计分器、原提案与 Kimi 10-03 待审批次未修改、未纳入本轮提交。
