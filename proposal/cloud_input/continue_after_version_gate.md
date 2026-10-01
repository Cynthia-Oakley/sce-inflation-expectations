# 发给现有 SocioVerse study 的下一条消息

我确认版本选择：请在当前 `sce_inflation_expectations` study 中按版本门创建**新 version**（如需使用 `/sv-iterate`，请执行），把 E 从原先的 synthetic 方案改为已核验的六条 BLS 首发新闻稿信号。保留旧方案记录；旧版尚未生成环境快照或运行结果，因此**不要称它为 synthetic E 基线，也无需先跑合成基线**。这一步不新建 study，不使用 branch 回放。

四份 PDF、JSON、六条时点与哈希已经核查完毕。请直接推进，不要重新逐份阅读文件或再次查询 Event/FRED。首先物化两个 Environment 快照：step 0 对应 2021-05、step 1 对应 2021-06；每步只向 Agent 提供该月三条 BLS 信号，确保 `ttl=1`，原 FRED 当前快照继续隔离。显示实际环境配置和一名 Agent 在两个 step 的观察内容，证明文件已进入 B 输入。

然后确认 20 条合成 P 已实际物化且两个月复用同一批 `agent_id`，完成 Q8 点预测和 Q9 十档概率的确定性 scripted 流程，预期导出 40 条逐人逐月回答、P/E 快照、脚本与配置、校验/失败记录、study/version ID 和费用。运行前按平台要求展示费用确认卡；本轮不使用真实 LLM，也不调用新的付费 MCP。若某个构建步骤失败，请给出具体文件、字段或 provider 错误并停在该处，不要退回 synthetic E。

本轮结果名称：**真实历史 BLS E + 合成 P 的两月流程试验**。不要把它称为已完成 SCE 全国预测效果验证或官方 Q9 headline 复现。
