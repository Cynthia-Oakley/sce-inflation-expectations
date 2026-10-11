# 新闻语义审核标准 v1

日期：2026-10-11。状态：开发期候选标准，未替换任何运行输入。

## 研究问题与审核范围

审核现有2021年5、6月主实验实际收到的30+30篇NYT标题和摘要：这些文字是否适合帮助美国普通家庭判断未来12个月的总体物价变化？只依据保存的文字，不能补入后来发生的事实、SCE答案或自己的通胀预测。审核的是选入文章的适切性，不是完整新闻库的召回率，也不是媒体政治偏差。

本轮是Luna与主Agent的研究辅助审核，不称为真人专家标注或已验收的金标准。所有实际可得性、原始文本版本、家庭曝光规则另行判断；语义纳入不自动取得预测路线B的资格。

## 逐篇决定

- `include`：标题/摘要提供明确的价格、成本、供应、需求、政策或未来物价解释，保存为价格判断的候选新闻。
- `context_only`：明确属于美国经济/生活背景，但摘要没有足够的物价机制或新进展；可入背景库，不默认占用每个家庭的核心价格消息名额。就业/收入消息不因未出现“通胀”而一律排除。
- `needs_fulltext`：语境或地域/机制缺失，不能仅靠摘要确定纳入价值；保留待核，不自动进入核心消息。
- `exclude`：摘要清楚显示只是词面误中、无经济/价格联系的事件，或与本研究人群不适用且没有可见关联。

不能用“预计会把模型答案推高/推低”“有助于拟合真实SCE”作为入选理由。不能人为使上涨/下降消息各半，也不能只留官方乐观解释、只留悲观解释或统一改写为专家结论。弱机制宁可标背景/待核，不能自行补上证据。

## 内容标签（可多选，主类只选一项）

- `living_prices`：居民购买/支付的价格；租金与房屋售价区别，能源批发与零售区别，涨幅减慢与价格下跌区别。
- `supply_costs`：供应链、运输、原料、产能与企业成本；生产成本变化不能直接等同居民通胀。
- `demand_labor_income`：复工、消费、需求、工资、就业、收入，按原文判断是否有具体价格机制。
- `monetary_policy`：央行实际行动、沟通、利率与经济判断；观点必须保留说话者。
- `fiscal_trade_energy_policy`：财政、税收、关税、政府能源政策；承诺不等同已生效，不等同有效。
- `expectations_narratives`：对涨价持续性、未来走势、原因的明确解释或分歧；主张不等同事实。
- `non_price_context`：与居民经济处境有关的背景，尚没有上述价格机制。
- `unrelated`：摘要已足以排除相关性。

## 每篇必须记录的内容

`target_month`, `event_id`, `decision`, `primary_category`, `categories`, `reason_zh`, `evidence_snippet`, `scope`, `affected_groups`, `claim_type`, `horizon`, `explicit_price_direction`, `confidence`, `event_group`, `duplicate_candidates`, `needs_fulltext_reason`, `presentation_note`。

- `evidence_snippet`：从原标题/摘要原样摘录至多12个英文词；无支持时为空，不编造。
- `scope`：`us_national / us_local / us_and_global / global_only / non_us / unspecified`；`affected_groups`仅写原文明示或有清楚机制的群体，不从画像猜政治立场。
- `claim_type`：`fact / attributed_forecast / opinion / mixed / unclear`。
- `horizon`：`current / near_term / one_year / longer_term / unspecified`，取明确文字，不把没有时间描述的事件强认成一年期。
- `explicit_price_direction`：`up / down / mixed / not_stated`；没有明说价格走向就填`not_stated`，不是让审核者预测。
- `confidence`：`high / medium / low`只指审核判断的把握，不代表消息真实性。
- `event_group`：简短主题与事件字符串，仅供同事件检查；`duplicate_candidates`列同批其他event_id，不能仅因题材相同就认成重复。
- `presentation_note`：保留的限定、归属、地域或需突出信息；不生成通胀数值答案。

原始`pub_date`、`selection_cutoff`、`text_vintage_status`保持不动；检查日期不等于核验了历史首版文字。

## 分工与复核

两个Luna分别审两个开发月；第三个Luna在不知道首审标签的情况下，审固定种子42抽出的每月10篇。主Agent读全部60篇并裁决差异，保留首审、二审与最终候选决定。20篇随机复审只用来发现标准歧义和记录一致程度，不是衡量相对于人类真值的准确率。

这60篇都来自旧关键词筛选后的输入，不能据此证明漏选很少。后续须从同一截止范围内的未入选新闻另抽样查漏；任何批量LLM分类器应另留月份检查，不能仅用这两个月开发成绩验收。
