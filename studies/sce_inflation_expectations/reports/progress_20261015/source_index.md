# 汇报来源与证据索引

核查日：2026-10-15。仅复用已有资料，没有新模拟或拟合。个人记录留在本地忽略目录；下表的路径/哈希用于追溯，不构成公开分享许可。

## 本地证据

- `docs/sources/sce_baseline_aggregate_sources_latest_20261007.json`
  - SHA-256：`a1a275df4fb77e3567a8984293460f9bf671a6eea141319f13d6ed42df609f43`
- `outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet`
  - SHA-256：`a4eb7d134f603136f7c01303597068777cf5614a372d72ee228312f467c1e7dc`
- `outputs/sce_expanded_state_evaluation_20261014_v1/summary.json`
  - SHA-256：`b358a5d1ad1dcf98c14bbdad663885927fd271804066a669f498ab1eb9e47095`
- `outputs/sce_expanded_state_evaluation_20261014_v1/cases_private.json`
  - SHA-256：`83f6347a6dd126764c94f3b16b7e84237b62d84d3b53776e315498653d0cc7c3`
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
- `docs/workstreams/20261013_behavior/codex_u1_real_results_20261014.md`
  - SHA-256：`a55d93df1df6c3419b5f7d5b4ca7fc3163455d7bd870e88443170f3f40b6b3fb`
- `docs/workstreams/20261013_behavior/codex_mapping_results.md`
  - SHA-256：`55b692e17892498d95f124cee49d0ccb37bcb7fff037c6a7076d5935fd53aff9`
- `docs/workstreams/20261013_behavior/codex_expanded_protocol_20261014.json`
  - SHA-256：`3b615709b197e3eedf28a4e406706b6c75efddac0520dbdb30f74f2108129b83`
- `docs/sources/sce_progress_report_planning_20261015.json`
  - SHA-256：`39d91e3e19e1551b38f022c01ff48b129276ca3c04950cc87aead721bc2b8a2c`

## 官网、调查与文献

- SocioVerse Challenge 2026：https://socioverse.fudan-disc.com/challenge/ 。当前规则下载和哈希见docs/sources/sce_progress_report_planning_20261015.json。
- SCE官方数据与原材料：https://www.newyorkfed.org/microeconomics/sce 。
- SCE FAQ：https://www.newyorkfed.org/microeconomics/sce/sce-faq 。当前FAQ称约1,200位家庭财务负责人、最长12个月轮换。正文避免沿用早期资料中约1,300人的固定口径，实验使用实际人数。
- D’Acunto, Malmendier, Ospina & Weber (2021), Exposure to Grocery Prices and Inflation Expectations, Journal of Political Economy, 129(5). https://www.journals.uchicago.edu/doi/10.1086/713192 。
- Malmendier & Nagel (2016), Learning from Inflation Experiences, Quarterly Journal of Economics, 131(1). 作者稿：https://eml.berkeley.edu/~ulrike/Papers/InflExp_4.pdf 。不是把观察关联当成任意记忆提示必定有效的证据。
- Armantier et al., The Price Is Right: Updating of Inflation Expectations in a Randomized Price Information Experiment, NY Fed Staff Report 543. https://www.newyorkfed.org/research/staff_reports/sr543.html 。
- Carroll (2003), Macroeconomic Expectations of Households and Professional Forecasters, Quarterly Journal of Economics, 118(1), 269–298. 项目文献综述保留原研究与信息传播的迁移边界。
- Armantier et al. (2017), An Overview of the Survey of Consumer Expectations, FRBNY Economic Policy Review. 官方方法资料及本地问卷归档见docs/sce_source_manifest.json。
- ConsumerSim (2026)：https://arxiv.org/abs/2606.30395 。参考人群投影、行为惯性和验证设计，不把其不同对象/单位的误差作为本项目成功门槛。

## 制作和内容核查

- 5幅图分别为官方序列、加权真人分布、实验同样本中心、实验同样本ECDF和真人条件关联。
- 主图中心误差由既有配对案例独立汇总，0.6355480844242238，与冻结评价完全一致；没有重新计分个人回答或改变估计目标。
- 全部20页已转成PNG逐页概览，另对第6/11/12/13/17页检查细节；最终PDF20页、约0.55MB，中文可提取，文字无越页。
- HTML同源20页、5幅本地SVG资源存在；PDF图像使用对应PNG，文稿不依赖网页字体或远端图像。
- 15份受保护文件哈希均保持；没有新增真实LLM调用、费用或个人数据外发。
- 后续内容修改需重新生成并重查；上述QA不能自动继承。
