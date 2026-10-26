# 新闻机制小对照：离线准备结果与交接

2026-10-25，Kimi。本文是 `next_trial_design.md` 的实施回执。

**当前状态：已验收的离线提示包，不是可启动执行包。**未调用真实模型、未读取目标答案来分配输入、未修改 A82 或其配置、未产生 API 费用。最终使用 **v5**；v1–v4 是实现过程草稿，不作为交付入口。

## 1. 最终路径

- 提示包：`outputs/sce_media_mechanism_trial_20261024_v5/`
- 设计与材料说明：`docs/workstreams/20261024_media_mechanism/README.md`
- 原始外部材料：`outputs/sce_media_mechanism_20261024_v1/`
- 算法：`studies/sce_inflation_expectations/experiments/media_mechanism_trial.py`
- 准备入口：`scripts/prepare_sce_media_mechanism_trial.py`
- 验收与预算：`scripts/audit_sce_media_mechanism_trial.py`
- 测试：`tests/test_sce_media_mechanism_trial.py`

包内关键文件：

- `summary.json`：共同新闻、外部池排除记录、各组来源/语气曝光、21 项上游输入 SHA-256。
- `protocol.json`：两组月份、四组机制、两遍生成、模型路由、温度、JSON 输出、禁用供应商回退及零重试。
- `acceptance.json`：整包验收、输出与代码哈希、实际不同提示数。
- `budget.json`：估算成本、保守预留与建议预算帽。
- `<month>/<arm>/prompts_private.json`：实际完整提示。
- `<month>/<arm>/contexts_private.json`：个人文章来源和语气记录。

## 2. 材料和共同新闻

两个月各有 30 篇外部候选，覆盖上月 1 日至当月 10 日的完整窗口。每月各排除 1 篇直接报道纽约联储 SCE 通胀预期的文章，因此每月实际合格外部池为 29 篇；原始候选仍保留以便审计。

共同三篇在四组中完全相同：

- 2021-06：
  - Jump in Consumer Prices Raises Stakes in Inflation Debate
  - Soaring Prices Herald Boom Time for Steel Makers
  - Prices Jumped 5% in May From Year Earlier, Stoking Debate in Washington
- 2022-06：
  - Fed Confronts Why It May Have Acted Too Slowly on Inflation
  - Consumer Prices Are Still Climbing Rapidly
  - Inflation Sped Up Again in May, Dashing Hopes for Relief

规则使用当时可见的 A1 位置、标题、发布日期、语义 scope 和最新 CPI 发布日；优先美国国内、标题直接涉及通胀的文章。它在这两个目标月保证了 CPI 当日稿覆盖，但不能据此声称对任意未来月份都有形式化保证。

## 3. 四组与规模

- R0：仅 NYT，现有兴趣权重。
- R1：仅 NYT，兴趣加权部分的警示文章 boost=2。
- M0：NYT＋外部媒体，现有兴趣权重。
- M1：NYT＋外部媒体，警示 boost=2。
- 外部文章在个人新闻中固定占 25%：5 篇取 1 篇、17 篇取 4 篇；0 篇档自然为 0。

每月 96 人、四组、两遍：

- 人×组提示位置：`2×4×96=768`。
- 实际不同文本：483 份；3 篇共同新闻档在四组中内容相同。
- 两遍物理调用上限：`768×2=1,536`。
- 2021-06：46/96 人有个人新闻，50/96 人只有共同新闻。
- 2022-06：51/96 人有个人新闻，45/96 人只有共同新闻。

每月名单独立，agent_id 也按月份隔离；“同 96 人”只指每月内部各组名单一致，不表示跨月配对。未采用跨组复用相同回答来减少调用，避免把不同组的随机生成结果强行视为同一个输出。

## 4. 验收结果

`pytest`：5 项通过。

整包验收全部通过：

- 768 个提示位置及 1,536 次两遍调用上限；
- 每月四组均为相同 96 人；
- 21 项上游输入哈希一致，能够发现准备后输入漂移；
- 非新闻部分逐字不变，共同新闻四组一致；
- 个人文章数与冻结的 3/8/20 档一致；
- 外部来源配额准确；
- 两篇 SCE 报道未进入任何提示；
- R1>R0、M1>M0 的警示曝光确实增加；
- new_api_calls=0。

独立只读复核未发现提示内容、泄漏防护或预算公式的实质错误。复核指出的上游哈希、提示计数和入口版本问题已修正。

## 5. 预算

沿用已登记的 OpenRouter → SiliconFlow/fp8 价格：输入 $0.259/M token、输出 $0.8/M token，温度 0.5、关闭思考、JSON、`max_tokens=1024`。

- 两遍估算成本：**$1.101798**（平均输入按 chars/4、输出按 180 token）。
- 两遍保守预留：**$7.042652**（最大提示 13,516 UTF-8 字节＋1,024 余量，输出按 1,024 token）。
- 建议预算帽：**$8**。

这些只是预算估计，不是价格保证，也不是运行授权。真实调用前仍须重新确认供应商价格和用户批准。

## 6. 复算命令

```bash
cd /Users/wushuyue/Documents/科研/DISC/socioverse_challenge
PY=/Users/wushuyue/anaconda3/envs/socioverse/bin/python

$PY -m pytest tests/test_sce_media_mechanism_trial.py -q

# 准备命令要求一个全新的输出目录；不要在已存在的 v5 上覆盖运行。
$PY scripts/prepare_sce_media_mechanism_trial.py --out outputs/<fresh_media_trial_output>

$PY scripts/audit_sce_media_mechanism_trial.py --out outputs/sce_media_mechanism_trial_20261024_v5
```

验收脚本会就地重写 `acceptance.json` 和 `budget.json`，不是纯只读命令；复算正式包前先复制到新目录。

## 7. 距离真实运行仍缺什么

1. **执行器导出层：**96 人版 environment/population/simulation bundle、执行器格式的 prompts、manifest、16 个 job 格、工程干跑和唯一 run_id。当前 v5 不是 `frozen_batch` 可直接消费的格式。
2. **评价入口：**冻结 signed error、MAE、W1/IQR、先验与新闻量分层、两遍及逐月报告；不能用合并均值掩盖单月或跨遍反转。
3. **来源收尾：**对拟用外部文章做历史快照抽查与许可确认；对 NYT 警示正则做人工小样复核。当前在线文本不等于历史版本认证。
4. **统计与授权：**Codex 复核四组设计和评价门槛，用户明确批准调用范围、外发字段和预算帽，之后才能写 `authorization.json` 并启动。

因此，本轮交付已经完成“材料＋机制适配＋离线提示＋预算”，但**尚未完成执行器接线，也未运行模拟**。
