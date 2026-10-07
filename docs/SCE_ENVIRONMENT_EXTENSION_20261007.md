# 优先补齐 E：本轮任务与接力入口

2026-10-07。用户确认：新闻情绪难以直接解释通胀，高阶新闻基线优先级降低；先查 ConsumerSim 的披露，再补历史 E。本轮不下载句向量/情绪模型，不训练新闻回归，不修改正式模拟配置，不运行真实LLM。

## 最新成果：69 个月 E 已验收（2026-10-07）

当前使用的资料包为 `outputs/sce_e_extension_2020_2025_verified_20261007/`，覆盖 **2020-01 至 2025-09，共 69 个月**。每月含 77 条数值信息和筛选后的标题＋摘要。它是独立的环境候选，尚未替换正式 study，也没有运行新的长期 Agent 模拟。

- 核验 160 份 BLS 初始发布 PDF，含 2019-01 至 2025-08 的历史支持。400 个 CPI 分项值、160 个 CPI 总体同比/环比值，均与独立的官方 HTML Table A 逐条一致，无待转录值和未核对值。就业主要数值全部可解析，但不将其称为全部经过第二来源数值对账。
- 官方 `EnvironmentBundle` 校验通过，69 月共 5313 条数值、2090 条运行新闻。通常每月 30 条新闻；2025-04 为 33、2025-05 为 47，沿用头版强相关新闻不硬截数量的既有规则。完整源月新闻台账有 2105 条，运行时再按各月截止日期筛选。
- 同信息基线输入已导出至 `outputs/sce_shared_e_2020_2025_20261007/shared_environment.jsonl`：69 行、77 数值列、无数值缺失，并保留同批新闻。这是输入导出，不是已训练的基线。
- 87 项相关测试及 9 项 subtest 通过。新真实 LLM 调用、付费 MCP 调用均为 0；NYT 账号账单未独立核查，不据此宣称全部接口免费。

本批修复旧 PDF 的 Table A/Table 1 列识别、疫情就业稿的“百万岗位”单位、明确数字跟在月份后的就业句式，以及 2024-06 CPI 未在开头重复月份的句式。就业“变化不大”不再默认转成零。2025 年 NYT 将文章类型从 `article` 改为 `Article`，现已兼容大小写，避免整年新闻静默漏选。实现与专项依据见 [旧版式解析复核](literature/sce/environment_extension/CPI_2019_PARSER_REVIEW_20261007.md)。

### 旧 2021 输入的版本差异

`legacy_2021_comparison.json` 证明旧包与新包的 2021 年 **12 个月数值和截止时间全部相同**。新闻在 2021-02、03、12 有 8 篇替换；现有 D050 实现先把当月原始档案截到截止日再排序，旧静态包这三个月仍符合“整月先排序，再截日期”的旧过程。即使入选文章本身未越过日期，选取过程也可能受之后文章影响。5/6 月开发输入新闻不变，旧配置与实验结果不覆盖。后续长期实验采用新候选并记录哈希，不直接复用旧静态新闻包。

### 2025-10：原始资料已齐，现有模板需要单独处理

来源已下载到 2025-09 BLS、2025-10 NYT；10 月检查记录为 `outputs/sce_e_extension_2025_10_release_gate_20261007/`。所需 24 份 PDF、60 分项和 24 总体 CPI 值均核验；唯一阻断是 9 月就业稿直到 **2025-11-20** 发布，晚于当前模板采用的 **2025-10-24 CPI 发布日**。这不是缺资料，而是模板假定各指标都能使用同一参考月。

下一步应按每个指标的实际发布时间选截止前最新可见值，或在 A 历史重建中明确采用回顾信息范围。不能默默把 10 月截止挪到 11 月，也不能把此次资料建设当成已冻结 A/B 时钟。10 月暂不混入已验收的 69 月候选。

### 仍需保留的来源边界

本包沿用 E v2 的当月 CPI 发布日末截止，**不是 B 的上月末预测输入**。每月 13 条汽油数据仍标 `vintage_unverified`；其当前快照和推定发布日期尚无完整历史版本证据。新增 2018-12 的 5 个周价格独立存于 `data/raw/eia_gasoline_support/20261007T085903Z/`，未覆盖原汽油文件。NYT 当前 API 文本也标记 `unverified_archive_snapshot`。A 可在说明这些边界后进行回顾研究；B 需要另外构建可得信息包并补证或共同排除未核验部分。`strict_pit_certified=false` 保持。

可版本管理的小型验收回执见 [sources/sce_environment_2020_2025_20261007.json](sources/sce_environment_2020_2025_20261007.json)。原始 PDF、新闻和大产物留本地缓存；此前失败批次保留，不作为成功产物。

## 前一批 2022 验收记录

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

前一批先准备2022全年（本次已扩至上述69个月）：所需2021-01至2022-11的BLS参考资料、2021-12至2022-12的NYT原始月档案。沿用现有价格/就业类别、12点历史和新闻筛选规则；只生成独立候选，不替换2021包。

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

## 5. 离线复算与后续顺序

以下示例在项目根执行，使用 `socioverse` Conda 环境；`new_check` 必须是尚不存在的新目录。缓存齐备时不需要 fetch 标志，不访问模型服务：

```sh
python scripts/extend_sce_environment_sources.py --targets 2020-01..2025-09 \
  --gas-weekly-csv data/raw/eia_gasoline_support/20261007T085903Z/gasoline_retail_regular_consolidated.csv \
  --build-candidate --out outputs/sce_e_new_check
python scripts/audit_sce_environment_candidate.py outputs/sce_e_new_check
python scripts/prepare_sce_shared_environment.py \
  --environment outputs/sce_e_new_check/environment_candidate.json \
  --output-dir outputs/sce_shared_e_new_check --allow-unverified-vintage
```

最后一个标志仅明确允许此 A 回顾导出沿用带标记的汽油快照；默认导出仍拒绝未核验版本，不能用该标志宣称严格 B 输入。候选继承了旧模板的其他上下文，正式运行前还需独立选择 P、验证 provider 输入与白名单，不把 E schema 通过等同于完整 study 可运行。

1. **已完成**：历史支持、2020–2025-09 连续 E 及基线共享输入；2025-10 原始来源已齐。
2. **接下来先做**：各指标“截止前最新发布值”的构建规则，单独解决 2025-10，并分别物化 A 重建包、B 预测包；登记汽油/新闻版本的处理办法。
3. **然后准备**：按同一来源做长跨度基线与 Agent 比较，划分训练、开发、评价时期，选择人口与模型并写运行卡；窗口和费用尚未新冻结。
4. **后续机制实验**：继续解释预期水平偏低与回答过窄，采用共同背景＋个体信息接触对照；暂缓高阶新闻基线，不因数据已齐而增加模型种类。
