# 新闻关键词机制 v1.2（待试标草案）

日期：2026-10-11。用途：从本地 NYT 档案找出值得内容打标的文章。尚未接入生产筛选器，不改变旧 E、研究截止点或模拟配置。

## 现在实际怎样筛

[原代码](../../../../scripts/build_nyt_events.py)在标题、摘要、snippet 中匹配强词和宽泛词，按“头版＋强词 → 强词 → 头版＋宽泛词 → 其他头版”排序。第一层不封顶，其他层填至30篇；同层优先命中不同关键词更多、时间更新的文章。部分 E 入口还会将两个月已选列表再次合并限量。

旧正则只设左词边界，`wage` 会匹配 `waged`；固定短语 `price increase` 不会识别 `increase prices`。命中词多、位于头版也不能证明文章更适合居民。库存与旧输入核对见[库存检查](inventory_audit_20261011.md)。

## 新版入口：满足任一条件进入候选池

### 入口1：较明确的经济词或短语

- 总体价格：`inflation`, `deflation`, `consumer price`, `consumer prices`, `cost of living`。
- 能源：`gasoline`, `gas price`, `gas prices`, `prices at the pump`, `oil price`, `oil prices`, `crude oil`, `OPEC`, `fuel costs`, `utility bills`, `electricity prices`, `natural gas prices`。
- 生活支出：`food prices`, `grocery prices`, `rent`, `rents`, `rental assistance`, `home prices`, `housing market`, `mortgage`, `mortgages`。
- 供给：`supply chain`, `supply chains`, `chip shortage`, `meatpacking`, `meat plants`, `food processing`, `producer prices`, `wholesale prices`。
- 就业消费：`jobs report`, `jobless`, `unemployment`, `unemployment benefits`, `wage`, `wages`, `retail sales`, `retail spending`, `consumer spending`, `household spending`, `hiring`, `layoffs`。
- 政策与前景：`Federal Reserve`, `interest rate`, `interest rates`, `monetary policy`, `fiscal policy`, `stimulus`, `relief payments`, `spending bill`, `infrastructure bill`, `tariff`, `tariffs`, `trade war`, `economic recovery`, `economic rebound`, `recession`。

这是候选词典，不是已经证明完整的词典。顺带提及房租、外国通胀和隐喻价格仍可能命中，随后作内容判断。

### 入口2：经济栏目

`section_name` 为 `Business Day`、`Business`、`Your Money`，或 `news_desk` 为 `Business`、`BusinessDay`，进入候选，无须命中上述词。2021-05原始档案已核实 `Business Day` 栏目和 `Business` desk；其他名称是待检查实际出现值的别名。

`Food`、`Real Estate`、`Technology`、`Opinion` 不整栏自动保留：菜谱、住宅参观和产品评测不当然是经济信息，但相关报道可通过其他入口。一般经济背景不必来自头版。

### 入口3：商品或生产对象＋变化语境

在同一文本字段内，两类词之间最多隔12个词，两个顺序均可。

- 对象：`beef`, `meat`, `poultry`, `grain`, `wheat`, `grocery`, `groceries`, `supermarket`, `household goods`, `clothing`, `apparel`, `appliance`, `appliances`, `electricity`, `natural gas`, `pipeline`, `factory`, `factories`, `plant`, `plants`, `shipping`, `port`, `ports`, `semiconductor`, `semiconductors`, `lumber`, `used cars`。
- 语境：`price`, `prices`, `cost`, `costs`, `supply`, `production`, `shortage`, `shortages`, `closure`, `closures`, `closed`, `shut`, `shuttered`, `disruption`, `disrupts`, `disrupted`, `outage`, `outages`, `raise`, `raises`, `increase`, `increased`, `rise`, `rising`, `cut`, `cuts`, `fall`, `falling`。

用于发现工厂停产、管道中断等没有标准通胀词的消息。这层故意较宽，`plant` 也可能指植物，不把命中当作相关性证明。

### 入口4：价格变化的不同表达

`price/prices/cost/costs` 与 `rise/rose/rising/increase/increased/increasing/higher/raise/raised/hike/hikes/fall/fell/falling/decrease/decreased/lower/drop/dropped/cut/cuts/surge/surged` 在同一字段内最多隔4个词，两个顺序均可。于是 `prices rose` 和 `increase prices` 均能找到。

### 入口5：一般经济背景

`economy/economic/pandemic/covid/coronavirus/reopening/reopen/shutdown/vaccine` 与 `employment/jobs/hiring/wages/spending/business/businesses/shops/factories/supply/production` 在同一字段内最多隔12个词，两个顺序均可。普通疫情人情故事不会仅因提及疫情自动入选。

以上4词、12词均是待检验的工程参数，不是居民注意力参数，也不是理论证明的最优距离。未召回抽查用于发现词表或近邻限制的遗漏。

## 匹配与后续处理

- 统一大小写、空白和词间连字符；`supply-chain` 与 `supply chain` 等价。
- 单词与短语使用左右词边界，复数与必要形式显式列出，不作任意前缀匹配。`wage/wages` 不包括 `waged/waging`。
- 标题、摘要、snippet 各自匹配，不在字段交界制造虚假短语或近邻。
- 记录文章ID、文本哈希、命中规则与词、栏目和来源记录。头版及命中词数作辅助资料，不再主要决定谁入选。
- 合并研究窗口内候选、按文章ID去重后，按[v1.2提示词](llm_label_prompt_v1_2.md)打标；随后整理事件重复与新进展，最后控制数量和长度。主题相同不等于同一事件。
- 公共库先试40–60篇、目标50篇，尚未冻结。不是每户阅读量，也不是已验证的最佳数量；主题不均分、涨跌不配平、不为凑数填满。保留因预算落选的标签供审计。
- 时间和文本历史版本由程序及来源证据单独检查，沿用各研究方案。打标不能把未知vintage升级为合格；历史抓取日也不能代替发布日期。

## 验收与状态

同一原始窗口比较旧规则、改进规则、规则＋模型；同时检查未召回、模型保留和模型排除的文章，并用未参与调整的月份复查。当前120篇助审不是人类金标准。本文没有实现新筛选代码或新增付费调用。
