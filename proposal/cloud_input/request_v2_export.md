# 发给现有 SocioVerse study 的导出请求

**状态：已发送并获回复。** 平台报告托管工作台暂不支持下载完整 ZIP/二进制附件。下一步改用[原始 JSONL 分块请求](request_v2_raw_jsonl.md)；以下原请求留作记录。

v2 scripted 两月流程已运行。请提供**可下载的完整原始导出包或逐文件下载方式**，让我在本地独立核验；不要重跑模拟，也不要新建版本。请列出云端 `study_id`/UUID、version ID、run ID、导出时间，以及导出文件的相对路径、大小、SHA-256；若平台不能打包或不能给下载链接，请说明界面中具体的导出入口和文件名。

请确认包中包含：study/environment/population/simulation 的配置与版本快照、`model.py` 和其他 scripted B 代码、20 个物化 persona 与初始 roster、两个月实际进入 `observe_batch` 的 E 观察和 BLS 来源审计、40 条未经聚合的 Q8/Q9 JSONL、轨迹与 run summary、事前费用确认卡及事后实际调用/费用记录。请特别标明 Q8 的 1.43%/2.31% 使用了哪段聚合代码和哪些原始字段。若某项无法导出，请明确缺项；不要用截图或总结替代原始 JSONL。
