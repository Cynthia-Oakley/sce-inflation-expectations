# 实际输入：人口、先验、环境与Prompt

本目录为v12新增的保密评审输入层；模型答卷与评价数据仍在相邻micro目录。这份快速输入投影不含API Key或目标期真值；原始SCE匿名编号、内部代码及供体/匹配资料另在portable层保留。保留来自公开SCE数据、且原Prompt实际使用的调查派生日期。匿名家庭编号沿用micro，可直接连接。

## 文件与数量

- `prompt_templates.jsonl.gz`：四个最终任务66,822个请求位置的实际消息。A/B/月度/周度均完整原样，无遮蔽占位符。
- `complete_prompts.jsonl.gz`：可原样重发的66,822份A/B/月度/周度完整输入；原始哈希和交付消息哈希一致。
- `population_belief_environment.jsonl.gz`：同66,822位置的人口、合成支出/价格、新闻、政策/时间、先验和问卷格式分块，方便阅读实际模型所见内容。
- `one_complete_prompt_example.json`：默认入口选用的一份完整真实历史输入。
- `generation_settings.json`：固定模型/供应商、温度、格式、token和价格上界。
- `manifest.json`、`source_projection_manifest.json`、`acceptance.json`：交付清单、投影来源指纹与全量连接验收。
- `POLICY_SOURCES.json`、`SCE_DATA_NOTICE.md`、`NEWS_REVIEW_NOTICE.md`：政策来源、SCE声明及新闻保密使用范围。

A41,970＋B5,632＋月度5,120＋周度14,100＝66,822位置。月度根月复用B另512状态，不重复导出为新的输入请求。模型回复共67,147条，含技术补跑和历史复用，所以不是一对一行数。连接字段为run、period、household和original_prompt_sha256（回复中的prompt_sha256）。

新闻是当时实际送给模型的标题、摘要/片段及公开日期，本目录保存选中摘录，完整候选新闻快照和标签另在portable源资料层；没有抓取过的文章全文不伪造补写。来源为The New York Times；版权属于原权利人，仅按作者要求供赛事保密评审，勿公开再分发。详NEWS_REVIEW_NOTICE.md。

## 从包根预览输入：0API

```sh
python studies/sce_inflation_expectations/simulation/reviewer_request.py --candidate-dir studies/sce_inflation_expectations/reproduction_data/inputs
```

默认不读取Key、不联网，只显示完整输入、消息哈希、模型与单次费用预留。在自己的终端配置OPENROUTER_API_KEY后，显式增加 `--confirm-paid --out reviewer_generated_01` 才发送一次。输出目录不得存在。可同时给出 `--run B --period 202511 --household <匿名编号>` 选择任意任务中的其他完整输入，A无需额外恢复日期。

固定OpenRouter→SiliconFlow FP8的DeepSeek V3.2、温度0.5、JSON、关闭思考、最多1024输出token。无自动重试或供应商回退；本地保守预留超过$0.01则拒发，配有单价和token上界，但不是服务端美元硬限额。某些较长Prompt可能被这一演示门槛拒绝。未来模型/路由/价格可能变化。完整Key步骤及故障处理见包根EXTERNAL_MODEL_AND_API.md。本入口已离线验收，未使用作者Key做新调用。

## 三种复现不可混称

1. 历史答卷和指标复算：默认all/micro，完全离线。
2. 给定历史先验的一次新模型回答：本单次入口，使用自己的Key，随机输出可能不同；原文独立存档，正式评分另走原流程。
3. 新的自主月度/周度链：须由本次新生成的前态重渲染后继输入。封存后月Prompt中的旧模拟状态不能充当新链的前态。A的历史请求同样完整提供；此入口负责条件单次生成，不代替新的自主链重渲染。

P/E日期、历史版本、合成分配和预训练知识等限制沿用论文及REPRODUCIBILITY.md。已附原始Prompt哈希便于忠实性检查，不因保密提交就升级为严格事前预测资格。

## v12公开日期保留

按作者明确要求，A路线不再额外遮蔽公开SCE数据中已经存在、且实际进入原Prompt的调查/截止日期。原始公开匿名SCE编号及内部代码映射在portable/evidence提供，Key等账号秘密不提供。公开日期按原字节保留，因此全部66,822份消息均可与原哈希核对。`prompt_templates.jsonl.gz`为兼容旧入口保留的文件名，本版其内容也已是完整消息，并不包含缺失模板。

### 列出、预览、重新询问：无需回填输入

在包根先列出A路线某月的完整样本（0API）：

```sh
python studies/sce_inflation_expectations/simulation/reviewer_request.py --candidate-dir studies/sce_inflation_expectations/reproduction_data/inputs --list --run A --period 201901 --limit 5
```

复制其中一个household编号，再把命令中的--list/--limit去掉，补上--household及该编号，即可预览该份完整输入；仅在决定付费时，再加--confirm-paid和全新的--out目录。A、B、monthly、weekly都走同一入口，无需联系作者恢复日期或提供Key。
