# Case 6 与数据 MCP 对 SCE 项目的适用性

核查：2026-09-28。读取官方论文、文档与公开代码；没有调用用户账号下的远程服务，没有验证实际数据响应或扣费。当前会话没有暴露 Event/Population MCP 工具。

2026-09-29 更新：云端预配置服务可优先用于小样验收，路线见 [云端方案](CLOUD_PILOT_PLAN.md)。上传/导出 FAQ 与前端代码存在冲突；尚未验证用户账号下的实际能力。前次关于免费读操作的判断不构成当前部署的计费保证。

## Case 6 的启发

目标是美国 ISM Manufacturing PMI。论文 5.4.2 描述 300 家异质企业，先用结构模型更新经营状态，再由 LLM 模拟经理回答五项问卷；状态与记忆跨月保留，信息截止为每月 21 日。适合参考“状态更新—问卷响应—聚合”的分层设计。[论文](https://arxiv.org/html/2609.24911#S5.SS4.SSS2)

这与企业 BIE 的人口和经营环境建模相近，但测量对象不同。PMI 主要衡量本月相对上月经营方向；BIE 核心询问未来一年本企业单位成本的概率分布。PMI 的价格分项不在 headline 的五项中；BIE 也不等同于企业售价或全国 CPI 预期。[ISM 方法](https://www.ismworld.org/supply-management-news-and-reports/reports/seasonal-adjustment-factors/)、[BIE FAQ](https://www.atlantafed.org/research-and-data/surveys/business-inflation-expectations/faq)

动态状态和记忆并不自动证明已经建立企业—居民双向市场反馈。论文描述的 PMI 模型仍主要由外生信息驱动，不能把它作为闭合宏观市场已经重建的证据。论文报告的后截止窗口 MAE 为 0.892，对持续性基线 0.894；这是小幅差异，不能据此承诺企业模拟效果很强。未在本轮复现实验。

公开 GitHub main 在本轮解析为 `fa678ff6aea0e5a6497a7ffac15459123200a150`；递归目录未发现名称含 PMI 的实现，也未见 studies 下专门 PMI study。结论限于这个公开版本，不代表组内或托管平台不存在该案例代码。

## Event MCP 能提供什么

官方目录包含 FRED、BLS、Treasury、NYFed SCE、市场/信用/住房、USTR 和 NYT archive；另有可选 GDELT、人口数据等采集器。注册某个来源并不证明部署端已经具备相应密钥、年份覆盖、连续缓存或全量字段。[服务文档](https://socioverse.fudan-disc.com/docs/guides/data-services/)

公开客户端确实按来源与年月调用 `get_source_detail`；不指定来源则调用默认集合。`query` 只记录用途，不驱动一个自动理解研究要求的检索器。应明确列出来源，SCE 主实验尤其不要无条件加载默认集合中的 `nyfed_sce` 结果。[固定版本客户端](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/socioverse/external_events.py)

### 时间保证的边界

论文对 vintage-safe 的概括较强，当前服务文档则明确将保证限定为 **observation date**。文档举例为 FRED `observation_end` 截至请求月末，并承认后续修订取决于上游。

需要分别核查：

1. 数据参考月份是否不晚于研究月份。
2. 数据实际发布日期是否不晚于研究截止日。
3. 值是否为截止日已公开的历史版本。

前者不能替代后两者。缓存保存 `2022-06.json` 可保证重跑同一文件，却不能证明它含的是 2022 年 6 月当时已知的数据。`fetched_at` 是取数日，也不能冒充原始发布日期。

客户端在核查版本中只向服务传 `source/year/month`，未见逐日 `as_of` 参数或逐条发布/修订过滤。因此 Case 6 的每月 21 日截止，不能仅凭这个通用接口就推定自动实现；需要专门的信号库和过滤层。没有服务端采集器源码与返回样本，本轮不能进一步断言具体来源必然合规或必然泄漏。

### 历史新闻

- `nyt_archive` 有历史月份入口，值得先抽样；NYT 官方 Archive API 提供文章元数据，不应默认等于新闻全文或完整初始版本。[NYT 官方说明](https://github.com/nytimes/public_api_specs/blob/master/archive_api/archive_api.md)
- `search_web` 是实时检索回退接口，官方明确不属于历史 vintage 查询路径。
- `gdelt`、`news_alt` 的实际时间覆盖、正文和发布时间字段待部署抽样；不能只因目录里有名字就承诺 2020–2024 全期覆盖。

## Population MCP 对本项目的作用

当前文档注册池包括 X、RedNote、Nemotron USA、MatrAIx、PersonaHub；没有把真实 SCE 面板列为现成子池。Event MCP 的 `sipp` 人口采集器与 Population MCP 的 persona 池也不是同一个东西。

建议仍由历史 SCE 构造首版 P，并通过框架 `file.personas` 输入。公开 `FilePopulationProvider` 可读 CSV/Parquet，要求 `agent_id`，可附权重和人群属性；使用自有微观数据是框架原生路径。[人口 provider 代码](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/socioverse/providers.py)

若之后比较 MCP 人口：先检查字段与索引，明确历史人口适配；保留联合分布、缺失单元和合成属性来源。能力注册说明默认独立抽样及虚拟补人选项会影响结构，应显式配置并核验返回样本，而不是认为人口规模足够大就代表 SCE 户主人群。[能力注册代码](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/resources/capabilities.yaml)

## 接入与下一步

公开框架包含客户端，不包含两项托管服务本身。README 说明托管工作台预配置服务；本地需要单独的服务地址和认证，GitHub/Hugging Face 登录不替代它们。是否能公网访问、账号额度及部署源可用性尚未验证。[仓库说明](https://github.com/sii-research/SocioVerse2)

下一步先做有限的服务验收，而不是先建设全套爬虫：

1. 检查来源目录和健康状态，确认服务调用额度；不运行付费人群问卷模拟。
2. 抽取 2020-04、2022-06、2024-12 的 FRED/BLS/NYT 数据；检查原始值、参考期、发布时间、版本、新闻 ID/正文范围及错误清单。
3. 与官方历史发布交叉核验；能通过的来源直接复用，缺少 vintage 的宏观数据由官方历史发布/ALFRED 补，新闻覆盖或文本不足再动用学校档案。
4. 将取数结果固化成文件和来源清单，经本项目可得性过滤后再进入 E；不在每次模拟时重新抓取。

这样保留 SCE 主线，同时把通用取数工程尽可能交给平台。当前结论为“有可复用能力，实际覆盖与历史可得性待验收”，不是“已拿到完整回测数据库”。
