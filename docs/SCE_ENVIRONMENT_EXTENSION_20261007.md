# 优先补齐 E：本轮任务与接力入口

2026-10-07。用户确认：新闻情绪难以直接解释通胀，高阶新闻基线优先级降低；先查 ConsumerSim 的披露，再补历史 E。本轮不下载句向量/情绪模型，不训练新闻回归，不修改正式模拟配置，不运行真实LLM。

## 本轮完成与唯一验收包

正式资料验收：`outputs/sce_e_extension_20261007T081207Z/`。2022全年12步，每步77条数值信号、30条标题＋摘要；合计924条数值记录、360条运行输入新闻。已补24份BLS PDF、12个月NYT原始档案；46份所需BLS资料含历史支持全部核验，115条分项与官方HTML Table A全部逐条一致。13个完整新闻月的台账有390条，经过各步截止与合并筛选才成为360条，不是丢失30条。

`environment_candidate.json`通过官方EnvironmentBundle校验；`acceptance.json`保存逐月结构/日期检查，`manifest.sha256`保存文件哈希。新环境仍是候选，未放入默认study、未生成新的正式simulation配置、未运行Agent或训练新基线。当前2021与新增2022输入已具备资料层的跨年衔接条件，尚未证明模拟效果或严格B时点合规。

本轮发现并修复了真实转录风险：旧能源正则可能把“all items less food and energy index”末尾误识别为能源，2022-04至11的8项出现错值。新入口要求明确的能源主语和全年跨度，并以独立网页表格逐条阻止错值进入候选。另补食品/住房年度句式，以及就业稿“remained at”句式；后者仅扩展两个既有BLS解析函数的同义表述，未改变时点/单位/旧配置。此前失败或局部候选批次保留，不作为正式验收。

对旧2021环境涉及的2020-01至2021-11共23个能源输入月另做复查，22项精确主语对账一致，1项用独立官方HTML补核一致；未发现旧2021输入的同类错值。记录为`legacy_energy_final_check.json`，不据2022解析错误追改旧实验结论。可版本管理的小型验收摘要见[sources/sce_environment_extension_20261007.json](sources/sce_environment_extension_20261007.json)。

61项相关测试、9项subtest通过。真实LLM与付费MCP调用均为0；使用了已有NYT账号的数据接口，未核实其账号账单，不将无LLM调用等同于全部接口免费。

## 1. 新闻基线调查的结论

[ConsumerSim核查](literature/sce/news_baselines/CONSUMERSIM_NEWS_BASELINES_20261007.md)：News Semantic FAAR将经济新闻语义压成紧凑代理特征，再结合自回归信息；Macro–Market–News Ridge使用宏观、市场及新闻派生特征，例如经济新闻强度。后者没有明确宣称使用同一语义编码器。

正文未披露编码器、按月汇总公式、降维维数及完整训练清单，因此目前只能参考方法类别。不能把MPNet、PCA或positive-minus-negative说成其原方案。

既有持续性、AR/ARX等保留。E齐备后可先增加一个共享宏观输入的简单回归；新闻的增益也可通过相同Agent有/无新闻对照检验。暂不把实现两个高阶新闻基线作为主线门槛。信息不一致时，仍不能声称优势来自Agent方法本身。

## 2. 补齐 E 服务什么

把原本只有2021全年的新版输入，扩成可以连续跨年比较的资料池；让不同方法读取相同价格历史、就业和新闻。延长跨度可以检查疫情、通胀上行与回落等不同阶段，而不仅评价5/6月。下载更多资料不会自动改善拟合，也不等于已完成长期模拟。

本轮先准备2022全年：所需2021-01至2022-11的BLS参考资料、2021-12至2022-12的NYT原始月档案。沿用现有价格/就业类别、12点历史和新闻筛选规则；只生成独立候选，不替换2021包。

来源盘点：[BLS](literature/sce/environment_extension/BLS_INVENTORY_20261007.md)、[NYT](literature/sce/environment_extension/NYT_INVENTORY_20261007.md)。NYT分工报告记录的是扩展前快照，新增批次以独立summary/验收为准。

## 3. 文件与运行入口

- 新辅助入口：`scripts/extend_sce_environment_sources.py`。
- PDF缓存：`data/raw/bls_initial_releases/<reference_month>/`。
- NYT缓存：`data/raw/nyt_archive/<month>.json`及`.meta.json`。
- 每次独立产物：`outputs/sce_e_extension_<UTC timestamp>/`；含plan、BLS来源清单、分项及handoff、新闻台账、summary；成功构建时另有候选environment和external_events。
- 独立官方网页核对缓存：`data/raw/sce_environment_extension_html/`；直接HTTP取HTML遇到403时，本轮以浏览工具存回官方表格文本，未转用当前修订序列。15份新网页副本与8份既有网页表格合计核验23个月×5项。
- 旧分项/新闻台账、正式环境和simulation配置均不覆盖。失败批次保留；缓存哈希或发布日不一致会阻止候选生成。

默认命令只盘点，无网络：

```sh
python scripts/extend_sce_environment_sources.py --targets 2022-01..2022-12
```

下载缺失源并准备候选（NYT仅从本地`.env`内部读取原有凭证，不打印到命令或产物）：

```sh
python scripts/extend_sce_environment_sources.py --targets 2022-01..2022-12 \
  --fetch --fetch-nyt --build-candidate
```

资料齐备后，纯离线重建使用同一范围加`--build-candidate`，不加两个fetch标志。输出目录必须是新目录。BLS下载按已归档官方日历；不存在对应日历的窗口先补日历，不能试猜日期。新入口串行NYT请求，至少间隔15秒，失败停止后续新认证调用，保留缓存供下一次继续。

## 4. 时点与来源证据

BLS按初始发布稿取值，发布时间由官方日历及PDF相互核对。新闻按发布时间过滤后再选取标题和摘要；API现在返回的文章文本未必是当时版本，保留`unverified_archive_snapshot`。汽油数据沿用已下载周序列，但当前FRED快照的版本、推定发布日期仍未补证。

候选 E 继续标为混合来源证据。A路线可用于明确标注的回顾重建；B路线应另建上月末截止包，给各方法共同采用已核验来源，或共同排除未补证部分。不能把本轮缓存下载或时间字符串校验称为解决全部前视风险。

NYT API文本使用的账号许可范围仍待核实；本轮没有向LLM发送新闻，也不公开原始缓存。来源盘点提供官方API规格和条款入口，不推断未读到的专门条款内容或当前价格。

## 5. 后续顺序

1. 完成2022候选与独立数值/时点验收，确认跨年解析无静默缺失。
2. 补2019–2020历史支持，再接2023–2025-10；2026已有全国指标，可随后补全国评价环境。此为资料建设建议，不自行冻结实验窗口。
3. 同一来源池分别物化A研究包和B截止前包，解决汽油版本证据，登记新闻文本版本边界。
4. 再准备长跨度Agent运行卡及共享输入基线，确定月份、人口、模型和预算后运行；主线仍是解释水平偏差与分布过窄，而非增加模型个数。

以上第1项已完成；下一项是历史支持与后续年份资料扩展。汽油/新闻版本边界仍需另行处理。
