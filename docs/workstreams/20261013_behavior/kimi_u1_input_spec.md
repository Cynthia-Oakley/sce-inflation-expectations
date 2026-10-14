# U1 输入规范 v2：显式个人信念状态（Kimi 定稿，待汇合评审）

2026-10-13。状态：**v2 定稿草案**，汇合评审通过后转正式冻结。v2 按 Codex 互检（`codex_kimi_u1_review_20261013.md`）修订，逐条对应见文末变更记录。依据：`kimi_results.md`（更新线事实）、`kimi_anchor_results.md`（个人锚规则）、`codex_results.md` / `codex_mapping_results.md`（表达线约束）。实证锚点全部来自已验证结果，无新假设。

## 0. 一句话说明

U1 = 在**已执行过的 U0 本人先验臂**（保留上期 Q8 点值 + Q9 十档原始 JSON，实物见 `outputs/sce_prior_trial_20261013_v2/<month>/preview_own_previous.json`）基础上，**追加**一块标明来源的个人状态摘要；另设一臂再追加一句"更新假设"提示。输出格式完全不变，保证与报告层（R0/R1）正交。

## 1. 两臂设计与对照逻辑（v2 核心变更）

| 臂 | 内容 | 对照含义 |
|---|---|---|
| U0 本人先验（已执行，96 次） | 上期完整回答（Q8 点值 + Q9 十档 JSON） | 既有基准 |
| **U1s（state）** | U0 + 状态摘要块 | 与 U0 比 = 状态摘要的增量效果 |
| **U1g（guided）** | U0 + 状态摘要块 + 更新假设句 | 与 U1s 比 = 更新指导的单独增量 |

v1 的"摘要替换原始 JSON"方案废弃：摘要替换会把"状态指导效果"与"信息压缩效果"混杂（46/48 人的 Q8 点值与 Q9 拟合均值差 >0.1pp，平均绝对差约 4.83pp），v2 保留原始回答、摘要只做增量。

## 2. 个人状态三要素（构造公式锁定）

记本人 t−1 期十档回答经冻结计分器重算的近似均值为 c、四分位 p25/p75 为 L/H，本人全部严格早于 t 的有效回答近似均值的扩张均值为 ā。

| 要素 | 公式 | 数据来源 | 实证依据 |
|---|---|---|---|
| S1 上期中心 | c = frozen_mean(Q9 十档, t−1)，文字标明是**概率回答隐含的近似均值** | 本人上期回答 | 真人 lag-1 排序持续 0.58–0.64 |
| S2 上期不确定度 | L, H = frozen p25/p75(Q9 十档, t−1)，文字表述为"**约 50% 概率落在其间**" | 本人上期回答 | H2 描述关系：高不确定度者修正幅度 2.5 倍 |
| S3 个人长期锚 | ā = mean(本人早于 t 的全部有效近似均值)，历史 <2 条时省略整行 | 本人多期历史（本数据段可见 1–11 期，**非终身信念**） | 锚规则 C1：个人锚显著收窄超额截面 W1 距离 |

构造代码复用 `belief_dynamics/anchor.py::personal_anchors`（mode="mean"，MIN_HISTORY=2，已有无前瞻测试锁定）。**禁止**把任何当期/未来 SCE 汇总统计写入状态块——那是评价侧校准量，入提示即泄漏。

注意口径：S1 的 c 是 Q9 分布的**拟合均值**，与 Q8 点回答是**两个不同的量**（Q8 点值已在 U0 原始 JSON 中保留）；状态块措辞必须标明"probability answers implied"，不得称 "your central expectation was"。

## 3. 提示词 diff（英文，美国居民语境）

在 U0 本人先验臂消息中，原始回答块之后、问卷起始标记之前插入：

```
Your survey history (a summary of your own earlier answers):
- Last survey (2022-02): your probability answers implied an average expectation
  of about 4.1%, and about a 50% chance of inflation between 2% and 4%.
- Over your past 8 surveys, this probability-implied average has typically been
  around 3.6%.
```

U1g 臂在锚行之后**再追加**（仅当 S3 存在时；无锚者整句省略，与 C1 历史不足回退一致）：

```
One hypothesis about how people usually update, which we ask you to consider as
a possibility rather than a rule: people move only partway from their last answer
back toward their own typical level in a single month — roughly halfway — unless
recent information or their own situation suggests a bigger or smaller change.
```

说明：
- "roughly halfway" 是 λ=0.50 的文字化（训练期选定值），**明确标注为待检验假设**，不是已证实的居民习惯；λ=0.50 只是在带真实共同平移条件的预测器中的损失最优参数，不能保证模型实现 50%，也不声称"most people"必然如此——故措辞用 "One hypothesis ... a possibility rather than a rule"。
- 数字示例（4.1%、3.6%、8 surveys）为占位，运行时由构造器逐人逐月填充；一位小数为近似值，措辞保留 "about"。
- 原始回答块自带的免责声明（"These were your reported expectations, not measured inflation..."）已覆盖来源说明，状态块不重复。
- E 环境块（BLS 数据、新闻层、政策简报）与 U0 完全相同，本规范不改 E。

## 4. 冻结参数表

| 项 | 冻结值 | 备注 |
|---|---|---|
| 基座 | U0 本人先验臂消息（逐字复用已执行输入） | 候选 v4 与已执行试验逐字一致（断言） |
| 锚模式 | 扩张均值（C1） | C2/C3 仅敏感性，不入正式臂 |
| 最小历史 | 2 条有效回答 | 不足则省略锚行；U1g 同时省略假设句 |
| 靠拢强度 | λ=0.50，文字 "roughly halfway" | 训练期选定；验证期一次性评价已过 |
| 不确定度呈现 | 十档 p25/p75 转"约 50% 概率区间"文字 | 不给模型数字公式 |
| temperature | 0.5 | 沿用既有冻结 |
| 输出 schema | 与 U0 相同 JSON | 保证 R 层正交 |
| 状态来源（第一轮） | A 线：真实历史初始化 | B 线闭环（状态仅来自本人模拟历史）为第二轮 |

## 5. 样本与请求计数（v2 修正）

- 样本：**每期 12 人 × 4 期 = 48 个人月**（沿用已执行试验的冻结选择）。
- 请求数：一个臂 × 每例 2 遍 = 48 × 2 = **96 次**；两臂合计 **192 次**。
- 旧试验的 384 条配对记录是 4 种指标行，其中 Q9 行 96 条；另有 767 份回答属另一批 48 人实验——两者都不能当作本批次的问卷数。

## 6. 评价与升级决策（v2 取消自动触发）

- 跨人 IQR 主口径统一为**左逆经验 CDF**（与项目评价函数一致；该样本真人约 6.25pp），插值口径（约 5.50pp）仅作敏感性并列。
- v1 的"身份弹性 <0.30 自动升级 U1b"**取消**：旧 0.118 来自本人/置换输入差对应的输出差，本批两臂没有同格式置换状态对照，该量按原口径不可计算。
- 替代：预先登记评价指标（跨人 IQR、ΔW1、截面 W1、中心 MAE、逐人 MAE，与 U0 三臂同口径同有效集），U1s/U1g 跑完后在**汇合评审**上对照 U0 与预登记指标决定是否升级 U1b（规则算基准 + LLM 供冲击）。U1b 详细规范触发后再登记。

## 7. 构建与校验要求（实现时执行）

1. 构造器逐人逐月生成两臂提示，附 prompt_sha256；状态值由独立函数从源数据重算并断言一致。
2. 基座断言：候选 v4 的 own_previous 消息与已执行试验 `outputs/sce_prior_trial_20261013_v2/` 存储的实际发送提示逐字一致（经 evaluation_links 的 ID 映射）。
3. 无前瞻断言：扰动 t 月及之后的回答不改变 t 月状态块（复用锚测试模式）。
4. 输出完整性：summary.json 不含自身哈希；另写 manifest.json（最后写入）登记包括 summary.json 在内的全部输出哈希。输出目录只新建不覆盖。
5. 每个 run 记录：run_id、提示哈希、状态三项数值、原始响应——沿用项目归档纪律。

## 8. 明确不在本规范内

报告层映射（Codex 候选 2，R1，降为离线敏感性）、模型选型与预算（用户决定）、样本与月份范围（48 人月已定）、E 环境改动。

## 9. 待汇合评审确认

- Codex 复核 v2 措辞与两臂拆分；汇合后本文件转正式预登记（改状态、补哈希），随后才可构建 U1 输入批次。
- 执行前另需：运行入口适配（own_state 接入真实运行管线）、请求清单/费用记录、引擎实际收到这些提示的离线验收。

## 10. v1 → v2 变更记录（对应 Codex 互检清单）

| Codex 条目 | v2 处理 |
|---|---|
| A. Q8 点值与 Q9 均值混称 | 基座改回 U0 完整上期回答；摘要标明 "probability answers implied"；§2 口径说明 |
| B. 四分位措辞 | "most likely between" → "about a 50% chance of inflation between" |
| C. "roughly halfway" 措辞 | 明确为待检验假设；无锚者（6/48）关闭该句 |
| D. 0.30 身份弹性触发不可操作 | 取消自动触发，改汇合评审按预登记指标决策（§6） |
| 人数/请求数 | §5 修正：48 人月、96/192 次、384/767 澄清 |
| 分位数口径 | §6 主口径左逆经验 CDF |
| summary 自哈希 | §7.4 manifest 分离 |
| "七成宽度"等旧表述 | `kimi_anchor_results.md`、`kimi_results.md` 已同步修订 |
