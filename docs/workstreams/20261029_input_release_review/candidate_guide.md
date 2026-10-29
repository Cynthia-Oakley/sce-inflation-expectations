# 实际输入候选层：先预览，再选择是否付费

这是 2026-10-29 准备的候选层，尚未安装进正式研究包 v09。完整输入与有占位槽的模板分别存放；后者不能直接送入模型。

`complete_news_free_prompts.jsonl.gz` 含 1,343 份完整原样周度输入；`prompt_templates.jsonl.gz` 与 `population_belief_environment.jsonl.gz` 覆盖 66,822 个请求位置。字段 `run`、`period`、`household`、`original_prompt_sha256` 可连接 v09 的 `reproduction_data/micro/model_outputs.jsonl.gz`。重复调用或技术补跑可能使一个输入对应多条模型回复。

当前便携入口使用 `one_complete_prompt_example.json` 中的一份完整样本。它保留当时已经形成的先验，是条件单步生成，不是重跑整条周度链。新生成的原文单独存档，不会覆盖历史答卷，也不由这个小入口替代正式 Q9 计分流程。

## 默认只看输入，不调用 API

在本目录运行（Python 3.11 或更新版本）：

```sh
python run_single_request.py --candidate-dir .
```

默认操作只使用标准库，不读取 Key，不联网。屏幕显示完整 Prompt、原哈希、模型路由和一次请求的估算预留。

## 可选：用自己的 Key 发出一次真实请求

只有决定付费重新生成时才安装客户端。研究包锁定环境中的客户端版本为：

```sh
python -m pip install openai==3.24.0 httpx==0.28.1
```

在自己的终端会话安全设置 `OPENROUTER_API_KEY`，不要写入脚本、共享文件或提交包。以下命令需要显式 `--confirm-paid`，且输出目录必须尚不存在：

```sh
python run_single_request.py --candidate-dir . --confirm-paid --out ../reviewer_one_request_01
```

固定 OpenRouter → SiliconFlow FP8、DeepSeek V3.2，温度 0.5、JSON、关闭思考，最多 1,024 输出 token；最多发送一次，不自动重试或切供应商。原输入与参数哈希不匹配、有占位槽、已有同名输出目录时拒绝发送。记录请求前意图、脱敏后的模型原文和费用回执，不记录 Key、请求头或供应商请求 ID。

入口采用保守预留不超过 $0.01、供应商单价上限和 token 上限；**这不是服务端美元硬限额**。真实价格或路由变化可能导致请求失败，失败不自动重发，可能已计费的未知结果仍保留。新输出具有随机性，不承诺复刻历史文本。本入口完成了离线验收和注入测试，未使用作者或评委的 Key 做真实联网测试。

## 有占位槽的输入

`withheld` 中列明新闻或真实关联日期的槽位。新闻仅保存字节数、文章接触数和内容哈希，不携带新闻文字；真实个人日期不携带原值。输入恢复后必须与原始消息 SHA256 一致，才能称原条件再生成。另选合法新闻或合成日期必须标为新变体。

本候选层没有原始 SCE ID、身份/供体映射或 API Key。来源与使用条件见 `SOURCE_AND_REUSE_NOTICE.md`、`SCE_DATA_NOTICE.md`；清单与验收见 `candidate_manifest.json`、`review_addendum_manifest.json`、`candidate_acceptance.json`。
