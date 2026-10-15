# 修订版来源索引

核查日2026-10-15。个人记录留在本地忽略目录，不随报告或源码提交。

## 本地证据与哈希

- `docs/sources/sce_baseline_aggregate_sources_latest_20261007.json`
  - SHA-256：`a1a275df4fb77e3567a8984293460f9bf671a6eea141319f13d6ed42df609f43`
- `outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet`
  - SHA-256：`a4eb7d134f603136f7c01303597068777cf5614a372d72ee228312f467c1e7dc`
- `outputs/sce_expanded_state_evaluation_20261014_v1/summary.json`
  - SHA-256：`b358a5d1ad1dcf98c14bbdad663885927fd271804066a669f498ab1eb9e47095`
- `outputs/sce_expanded_state_evaluation_20261014_v1/cases_private.json`
  - SHA-256：`83f6347a6dd126764c94f3b16b7e84237b62d84d3b53776e315498653d0cc7c3`
- `outputs/sce_expanded_state_trial_20261014_v3/development_cases_private.json`
  - SHA-256：`a7d78f0c8bd2579c22ec1aba14ff908fd51dc01dcb7293d1899ed8b99aed20bd`
- `outputs/sce_expanded_state_evaluation_20261014_v1/execution_receipt.json`
  - SHA-256：`0e7b062b2a819fffc589168ec0869c822a886fa305461e5eb823bbbe89ac8df2`
- `outputs/sce_expanded_state_evaluation_20261014_v1/coverage_clarification.json`
  - SHA-256：`091d9c36b2c817ceb55ee9badcec38dbec1843c82af67e9e5b383ebe6c24fb53`
- `outputs/sce_population_associations_20261015_v1/summary.json`
  - SHA-256：`9b3eef3218dedc1f3691f25d7c52d691fbf6eecd3dec57180b82c7c3e58cf988`
- `outputs/sce_revision_format_evaluation_20261015_v1/summary.json`
  - SHA-256：`cf7d575baa399e2c100d69aaf5a7809cb1dccb4d4c237c8f5f415f9adc772b98`
- `outputs/sce_confidence_analysis_20261011_v2/summary.json`
  - SHA-256：`d0155ed3a394c8bef9ec724e8fb06ba2ba120b54746f7ce7162c00117ff9dc01`
- `docs/literature/sce/factual_mechanisms_20261013/prior_trial_summary.json`
  - SHA-256：`43084f050214436863eb41c4d904a413e9924cab481a56aaf5a84f02ea31d612`
- `docs/workstreams/20261014_mechanism/purchase_frequency_budget_card_20261015.json`
  - SHA-256：`a6871a017895661330ef54fdd744f771ea8444be1946ed7cad55083c5921a781`
- `outputs/sce_u1_trial_20261014_v2/trial_manifest.json`
  - SHA-256：`9c31dbd668c65b3626844f95e51bf4dd1725148528318f8c1d317548aa3ba9e9`
- `outputs/sce_behavior_comparison_u1_20261014_v1/summary.json`
  - SHA-256：`93fa85e4b74aba32eb47384eb8f2a2f1a3547db74c3ec9b5eb1911afa5b5131c`
- `outputs/sce_qwen_reuse_comparison_20261008_v1/summary.json`
  - SHA-256：`eb2e6398b867fe7013dc21b52261c07f29a5e2b37978ff168b18102ec05e7dcf`
- `docs/workstreams/20261013_behavior/codex_u1_real_results_20261014.md`
  - SHA-256：`a55d93df1df6c3419b5f7d5b4ca7fc3163455d7bd870e88443170f3f40b6b3fb`
- `docs/workstreams/20261013_behavior/codex_mapping_results.md`
  - SHA-256：`55b692e17892498d95f124cee49d0ccb37bcb7fff037c6a7076d5935fd53aff9`
- `docs/workstreams/20261013_behavior/codex_expanded_protocol_20261014.json`
  - SHA-256：`3b615709b197e3eedf28a4e406706b6c75efddac0520dbdb30f74f2108129b83`
- `docs/sources/sce_progress_report_planning_20261015.json`
  - SHA-256：`39d91e3e19e1551b38f022c01ff48b129276ca3c04950cc87aead721bc2b8a2c`

## 官方背景与解释

- 背景来源见background_source_receipt.json：https://www.newyorkfed.org/microeconomics/sce/sce-faq 及官方SCE主页。约1200为当前FAQ设计规模，实际月样本不同。次月发布是根据归档记录的一般描述，不指定固定日。
- 核心参考文献沿用第一版source_index.md。A允许事后资料还原人口，当前经济信息截断是具体实验设计，不能等同于B的严格执行时点。
- 八期数据来自同一实验，共756个共同人月、1509次共同生成；后四评价379人月、757次共同生成。开发资料不作为新的独立验证。
- 2021旧同消息对照：12个月Q9同样本中位数，DeepSeek/Qwen对SCE MAE .951849/.883506，对t+12月CPI首发同比5.663011/5.537260个百分点。计算在aggregate_data.json的historical_knowledge_diagnostic。
- 旧P/E仅4条BLS信号，Qwen部分消息沿用DeepSeek历史回答，非当前八期输入，非两模型各自递推。t+12月CPI只是调查日起未来12个月涨幅的月度近似，未送入模拟或用于调参。
- 拟合不好不能证明无记忆。部分月份更接近未来CPI的现象另见docs/literature/sce/heterogeneity_and_probability/lifetime_mechanism_diagnostic_20261012.md。训练边界前后检验仍待设计。
- 楷体取自系统TTC简体Regular，字体仅进入忽略的本地assets与PDF文档嵌入，不提交或单独发布字体。PDF中文字为楷体，英文数字为Times New Roman；图表同一字体组。

## 本轮检查

- PDF21页，全部转图并概览，2/4/5/12页详细查看，无可见截断或重叠。
- 可提取文字的字体逐字符核对、页面边界检查通过；跨字体抽取的空格经规范化后检查背景和主数值。
- HTML21页及图表资源存在；15份保护文件哈希保持；没有新LLM / MCP模拟或个人数据外发。
