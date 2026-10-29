# 实际输入：人口、先验、环境与Prompt

本目录为v10新增的保密评审输入层；模型答卷与评价数据仍在相邻micro目录。它不含API Key、原始SCE编号、身份/供体对应表或真实个人作答日，不含目标期真值。匿名家庭编号沿用micro，可直接连接。

## 文件与数量

- `prompt_templates.jsonl.gz`：四个最终任务66,822个请求位置的实际消息。B/月度/周度完整，A仅遮蔽真实关联日期。
- `complete_prompts.jsonl.gz`：可原样重发的24,852份B/月度/周度完整输入；原始哈希和交付消息哈希一致。
- `population_belief_environment.jsonl.gz`：同66,822位置的人口、合成支出/价格、新闻、政策/时间、先验和问卷格式分块，方便阅读实际模型所见内容。
- `one_complete_prompt_example.json`：默认入口选用的一份完整真实历史输入。
- `generation_settings.json`：固定模型/供应商、温度、格式、token和价格上界。
- `manifest.json`、`source_projection_manifest.json`、`acceptance.json`：交付清单、投影来源指纹与全量连接验收。
- `POLICY_SOURCES.json`、`SCE_DATA_NOTICE.md`、`NEWS_REVIEW_NOTICE.md`：政策来源、SCE声明及新闻保密使用范围。

A41,970＋B5,632＋月度5,120＋周度14,100＝66,822位置。月度根月复用B另512状态，不重复导出为新的输入请求。模型回复共67,147条，含技术补跑和历史复用，所以不是一对一行数。连接字段为run、period、household和original_prompt_sha256（回复中的prompt_sha256）。

新闻是当时实际送给模型的标题、摘要/片段及公开日期，不是完整原始新闻数据库或所有文章全文。来源为The New York Times；版权属于原权利人，仅按作者要求供赛事保密评审，勿公开再分发。详NEWS_REVIEW_NOTICE.md。

## 从包根预览输入：0API

```sh
python studies/sce_inflation_expectations/simulation/reviewer_request.py --candidate-dir studies/sce_inflation_expectations/reproduction_data/inputs
```

默认不读取Key、不联网，只显示完整输入、消息哈希、模型与单次费用预留。在自己的终端配置OPENROUTER_API_KEY后，显式增加 `--confirm-paid --out reviewer_generated_01` 才发送一次。输出目录不得存在。可同时给出 `--run B --period 202511 --household <匿名编号>` 选择其他完整输入；不接受A日期缺口模板。

固定OpenRouter→SiliconFlow FP8的DeepSeek V3.2、温度0.5、JSON、关闭思考、最多1024输出token。无自动重试或供应商回退；本地保守预留超过$0.01则拒发，配有单价和token上界，但不是服务端美元硬限额。某些较长Prompt可能被这一演示门槛拒绝。未来模型/路由/价格可能变化。完整Key步骤及故障处理见包根EXTERNAL_MODEL_AND_API.md。本入口已离线验收，未使用作者Key做新调用。

## 三种复现不可混称

1. 历史答卷和指标复算：默认all/micro，完全离线。
2. 给定历史先验的一次新模型回答：本单次入口，使用自己的Key，随机输出可能不同；原文独立存档，正式评分另走原流程。
3. 新的自主月度/周度链：须由本次新生成的前态重渲染后继输入。封存后月Prompt中的旧模拟状态不能充当新链的前态。完整A历史还涉及受保护日期；本入口不承诺一键重建全部原运行。

P/E日期、历史版本、合成分配和预训练知识等限制沿用论文及REPRODUCIBILITY.md。已附原始Prompt哈希便于忠实性检查，不因保密提交就升级为严格事前预测资格。
