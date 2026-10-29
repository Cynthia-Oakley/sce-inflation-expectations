# 输入来源与再使用说明

核查日期：2026-10-29。该说明针对候选层实际保留的文字/数值，不为整个原始资料库作一揽子授权声明。

- **SCE：**来源为 Federal Reserve Bank of New York, Survey of Consumer Expectations。问卷有改编，人口与历史字段做了重新编号、分组和合成分配等处理。遵循 [NYFed Terms of Use](https://www.newyorkfed.org/privacy/termsofuse)；保留所附 `SCE_DATA_NOTICE.md` 的来源与非背书声明。新合成人口/信念不代表纽约联储官方调查。
- **价格、消费与时间使用：**BLS 数值以及 CE/ATUS 派生的模拟属性，按 [BLS Linking & Copyright Information](https://www.bls.gov/bls/linksite.htm)注明来源。没有复制另有版权的照片/图形，也没有输出原受访者 ID 或匹配对应表。
- **货币政策：**实际 Prompt 含 Federal Reserve Board 官网政策声明摘录。按 [Board Disclaimer](https://www.federalreserve.gov/disclaimer.htm)使用并注明来源；候选文件 `POLICY_SOURCES.json` 给出官方 URL、已登记发布时间及来源哈希。政策句子不能全部标为项目自行创作。仅适用于未另作版权标注的官网资料，不包括第三方资料或标志。
- **合成支出、采购责任与美联储信心：**这是模型输入中的匹配/合成赋值，不是模拟家庭本人的实测。保留输入值及其合成性质，不提供原供体键表、调查个体记录、第三方新闻/PDF全文。总体资料的历史版本与时间资格限制沿用原研究声明。
- **新闻：**NYT 官方 [Archive API specification](https://github.com/nytimes/public_api_specs/blob/master/archive_api/archive_api.md)要求遵守 API 条款及署名规则；目前未确认批量文字再分发许可。因此，标题、摘要与片段均从候选层的新闻块移除，以明确槽位替代。持有 API 访问权限不自动等于可再分发。今后获得相应授权或合法资料后，须另行评估恢复与分发范围。

此前 `candidate_manifest.json` 的简略 `rights_basis` 未单列 Fed 政策摘录；本说明补足其来源依据，首次投影清单不改写。输入层在法律来源和隐私处理之外，仍保留原研究关于旧人口、文本版本、模型知识和非严格事前回测的限制。

真实 A 路线个人完成/截止日期采用额外隐私遮蔽；这是本项目的公开层取舍，不称其一概受法律禁止。B 的合成作答日期及周度公开截止日期可以保留。身份映射、供体映射、API Key 和访问凭证均不随候选发布。
