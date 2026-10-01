# SocioVerse 云端 v2 两月 scripted 首试记录

记录日：2026-09-30。**证据级别：平台 Agent 的运行报告，以及已取回并核对 SHA-256 的 40 条原始 JSONL、`model.py`、`environment.json` 和 `simulation.json`。回答结构、统计量、配置与本地 P/E 对照、scripted 公式均已独立复核；历史运行真正传给 `decide_batch` 的 Observation 未被平台持久化，独立 roster、运行 ID 和费用流水也未取得。**

## 任务与版本

- 云端 study：`sce_inflation_expectations`；平台称已创建 v2，并保留 v1 快照。平台说明未持久化独立 run ID；尚无 study UUID 或下载地址。
- 实验标签：**真实历史 BLS E + 合成 P 的两月流程试验**。
- 目标月：2021-05、2021-06；分别以 2021-04-30 和 2021-05-31 的纽约时间月末为 `as_of`。
- 当前任务仅验证 P/E/B 的导入、时点隔离、模拟和导出流程，不是 SCE 全国预测效果试验。

## 平台报告的执行情况

| 检查项 | 平台报告 | 本地验收状态 |
| --- | --- | --- |
| E | 6 条 BLS 首发 CPI/就业信号；step 0/1 每步 3 条，`ttl=1` | **`environment.json` 已取回并核对哈希**；六条配置与本地源 JSON 的关键字段逐一相同，发布时间早于相应 `as_of` |
| E 实际进入 B | `sce_inflation_expectations.environment` 已注册；平台先前展示过 `smoke_001` 两步的 `observe_batch` 检查输出；FRED 当前快照被排除 | 代码、配置和回答相互吻合；**平台承认未保存真实运行时传给 `decide_batch` 的 Observation，无法直接验收该调用的原始轨迹** |
| P | 20 个固定合成 Agent、8 列、4 地区各 5 人；两个月复用同一批 ID；不调用 Population MCP | 环境配置含 20 个画像，逐字段与本地合成 CSV 相同；回答中 20 个 ID 跨月复用；**独立 roster 待取回** |
| B | `sce_inflation_expectations.scripted_b`；`deterministic-scripted-v1`；`sce-q8-q9-scripted-v1`；seed 42 | **`model.py` 与 `simulation.json` 均已取回并核对哈希**；配置与 40 条回答的模型、prompt、seed、step 相符 |
| 运行 | 20 人 × 2 月 = 40 条原始 Q8/Q9 记录；Q9 十项均在范围内且合计 100 | **40 条原始 JSONL 已本地逐行复核** |
| 诊断量 | Q8 带符号等权中位数：2021-05 为 1.43%，2021-06 为 2.31% | **两值按原始 `point_pct` 等权中位数独立复算一致** |
| 调用/费用 | `run_summary.json` 记真实 LLM、Population MCP、v2 运行中新 Event/FRED 调用均为 0 | 这是平台保存的**摘要计数**；未持久化独立调用/费用流水，不能独立核实账单或总费用 |

平台曾报告已导出 study、环境和人口配置、BLS 来源审计、roster、simulation 配置、scripted model、原始 JSONL、轨迹指标和 summary。用户随后粘贴了平台的 `experiment_log_v2.md` 和 `run_summary.json` 文本；二者是摘要。现在另取得原始 JSONL、`model.py`、`environment.json`、`simulation.json` 与进度记录文本，存于本地 `data/raw/cloud_exports/2026-09-30/sce_inflation_expectations_v2/`；其余云端文件未全部取回。平台本次明确费用流水和独立 run ID 未持久化，不能将先前“已导出”的笼统表述当作实际账单已保存。

平台称托管工作台没有 ZIP/二进制下载按钮，观察面板只读；对话可逐段输出文本文件。原始 JSONL 已通过此法取回。**平台声明原文件 26,520 字节、SHA-256 `bd94c7ae0cbb847a54172e0d923c63689dcf3da07f4459766176d7c8c6669ace`；本地从粘贴文本提取 40 行，补回被粘贴界面省去的末尾换行后，字节数与哈希完全匹配。**原始整段粘贴留存为 `user_pasted_text.txt`，本地校验结果为 `local_raw_audit.json`，均在上述被 Git 忽略的云端归档目录。可复跑命令：`python3 scripts/audit_cloud_v2_raw.py data/raw/cloud_exports/2026-09-30/sce_inflation_expectations_v2/raw_q8_q9.jsonl`。

逐行检查：两个目标月各 20 条、无重复 Agent-月，20 个 `smoke_001`–`smoke_020` ID 与本地合成 CSV 匹配且跨月相同；`as_of`、step、E/P 快照 ID、模型/prompt/seed 字段一致；Q8 方向与正幅度一致；所有十档概率在 0–100 且总和为 100。两个月 Q8 等权中位数复算为 1.43% 与 2.31%。**所有 40 条 Q9 都只在第 4、5、6 档有正概率，第 6 档恒为 20%；40 条理由文本完全相同。**这符合简单 scripted 模板的性质，不提供真实行为模拟效果的证据。

## v2 `model.py` 独立审计

用户粘贴的云端 `model.py` 还原后为 9,534 字节、199 行，SHA-256 为 `c6029c9460583aff85f239b4f1e4ff5263b5ce83abb1e65a412575adc8e6cc23`，与平台所报完全一致；Python 语法解析通过。原始粘贴和还原文件均保存在上述本地归档目录，未直接覆盖本地 study。独立公式复算可在仓库根目录运行 `python3 scripts/audit_cloud_v2_model.py`，结果保存在归档目录 `local_model_replay_audit.json`：40 条不一致数为 0，去掉失业率项后改变两位小数回答的条数也为 0。

- 环境代码从 `provider_args.signals_by_step` 按 step 载入信号，经 `observe_batch` 放进 `macro_information.signals`；B 代码确实读取该字段中的 `12-month` CPI 与 `unemployment rate`。用**本地**六条 BLS JSON、20 人合成 CSV 和该公式重算，40 条 `point_pct` 与 Q9 十档全部同原始 JSONL 一致。**这证明回答与该公式及这些输入数值相容；云端配置已取回，但实际运行时 Observation 无原始日志。**
- Q8 规则为 `round(max(0, CPI同比×0.55 − (失业率−6.0)×0.03 + 人/月份哈希扰动 + 收入档调整), 2)`。本次 6.0%→6.1% 的失业率变化在两位小数舍入后对 **40 条回答均没有实际影响**；不能称其贡献已由实验验证。CPI 环比 0.6%/0.8% 虽在 E 中，B 从未读取。
- 20 人画像里只有收入档参与 Q8 公式；年龄、教育、地区、住房、就业等尚未进入 B。环境虽然在 Observation 中提供上一期回答，B 也没有读取 `prior_answer` 或 `memories`，所以没有实际跨月信念更新。Q9 完全不读取 E 或 P，只由 agent ID、目标月与 seed 的哈希决定三档概率；第 6 档恒为 20%。固定理由文本不能作为逐人证据解释。
- `TARGETS` 和 `as_of` 被硬编码为两个月，超出两步时会静默重复第二个月。此为两月 smoke 专用结构，扩展月份前必须改为配置驱动并显式拒绝未知 step。
- CPI/失业率缺失时分别静默回退到 2.0/6.0；即使 E 注入失败仍可产出 `valid` 回答，且 `e_snapshot_id` 由目标月字符串拼出，不能当作 E 真实进入 B 的证据。下一版应在必需 E 缺失或字段重复时失败并记录原因。
- 代码中未见真实 SCE 答案/全国 headline 的直接引用，也未见模拟 LLM 调用；但 `0.55` 等系数在事后写入、来源未说明，不能把本次结果当作无前视的预测表现。`q9_density_eligible_count` 目前仅等于结构校验通过人数，**没有执行个人密度拟合**，命名须在正式结果中纠正。

### v2 `environment.json` 独立审计

平台提供的原文件为 10,718 字节、318 行，SHA-256 `765c926a5405203cebc271d827ee64bbee96bc653f8bad5e8cd6d8fc13995479`；本地按原始字节还原、解析并核对完全一致。可复跑 `python3 scripts/audit_cloud_v2_environment.py`。

- `provider_ref` 指向 `sce_inflation_expectations.environment`。`signals_by_step` 只有 step 0/1，分别对应 2021-05/06；每步 3 条。六条的 ID、指标、数值、单位、参考月、发布时间、首发版本、来源 URL 与 eligibility 均与本地 BLS E JSON 相同，发布时间早于各自月末 `as_of`。
- 两条 BLS broadcast 分别位于 step 0/1，`ttl=1`。`persona_by_id` 的 20 个画像逐字段与本地合成 P CSV 相同。配置的实际信号列表中没有 FRED 或 SCE 真值；`excluded_sources` 也列出了 `fred`、`nyfed_sce` 和 `nyt_archive`。
- 这些事实证明**已保存的云端环境配置正确**。平台随后澄清：此前显示的 `observe_batch` 是重新调用的检查输出，历史运行实际交给 `decide_batch` 的 Observation 并未持久化。不能将其写为已取得运行时观察轨迹；这一证据缺口应在下一版本加记录机制解决，不再反复要求平台贴不存在的 v2 原始 Observation。

### v2 `simulation.json` 与进度记录

平台粘贴的 `simulation/simulation.json` 原文为 **497 字节**、SHA-256 `91ba5ce6b291f363d78b23381c1269cbf74b63fb298f081123c5136363561dee`，本地按原始字节还原、解析并核对完全一致。配置为 `n_steps=2`、`seed=42`、`warm_start=null`、`decision_ref=sce_inflation_expectations.scripted_b`、`model_version=deterministic-scripted-v1`、`prompt_version=sce-q8-q9-scripted-v1`、`collector_ref=sce_inflation_expectations.collector`、`interaction_rounds=1`、`store_ref=duckdb`。40 条原始回答的 runtime step、模型、prompt、seed 均与该配置一致。

用户另粘贴 `trajectory/progress.jsonl` 的三条进度记录；其 step 0/1/2 的 panel size 为 0/20/20，step 1/2 的 Q8 诊断中位数为 1.43/2.31，与原始回答复算一致。时间戳换算为 **2026-09-29 16:19:01 UTC**（北京时间 9 月 30 日 00:19:01）附近的三次进度写入；它们不是独立的 `started_at` / `finished_at`。进度文本未附平台原文件字节数或哈希，本地归档标记为**对话转录，未验原始文件哈希**。

平台还给出 `versions.json` 摘录：v2 的 parent 为 v1、`warm_start=null`、`fork_step=null`；未给完整文件或哈希。`run_summary.json` 报告真实 LLM、Population MCP、v2 新 Event/FRED 调用均为 0；没有独立调用或账单流水。run ID、完整开始/结束时间与费用明细均为 `not_persisted`。`q9_density_eligible_count=20` 只对应结构合格，不代表进行了官方个人密度拟合。

配置正确和回答相容仍不能替代历史运行时 Observation 的直接证据。下一次运行须在 `decide_batch` 前记录实际输入摘要与哈希。

## 实际结论与边界

v2 的已保存配置、代码及回答相互吻合，支持托管平台完成了 BLS E、固定合成 P 和 deterministic B 的两月流程，并保存了原始问卷回答；运行时 Observation 未留原始日志，故该环节的证据仍是间接的。它不能证明合成样本有全国代表性、scripted 预测准确、真实 LLM 有效，或十档概率已按官方个人密度拟合成 SCE headline。v1 没有运行过 synthetic E 基线，不能作为性能对照。

## 接下来本地验收

1. **v2 取件阶段到此结束。**原始回答、模型、环境与模拟配置已取回并核对；run ID、费用流水和历史 Observation 明确未持久化。其余 roster/轨迹二进制文件可在平台提供正式下载后补档，但不阻塞研究下一阶段。
2. 当前转向官方 Q9 个人密度拟合、历史 P/E 与基线。v2 不作为预测效果证据；不得据此选择最佳参数。
3. 下一次实际运行前修复静默 E 回退，记录每个 Agent、step 传入 B 的 Observation 摘要、信号 ID/值/发布时间、输入哈希、模型身份和费用；给运行分配不可覆盖的 ID。若平台仍无法导出这些原始证据，评估转本地运行。
