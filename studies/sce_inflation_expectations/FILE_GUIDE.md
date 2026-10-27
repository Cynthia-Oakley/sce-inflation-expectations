# 文件导读：从研究问题找到实现

这里的分类表示文件在当前研究中的角色，不是对每个历史文件的重新运行认证。**未采用某项机制，不等于其代码没有研究价值；不在默认运行链上，也不等于可以直接删除。**

## 评委和首次读者的最短路线

`README.md` → P/E/simulation配置说明 → `submission_tools/reproduce.py` → `reproduction_data/`（仅提交包生成）→ `reports/index.html`（提交包图表导览）。

先执行离线入口，再按需要看算法。不要从几百个脚本中寻找一条“看起来最新”的付费run命令。开发工作区的实际脚本在项目根scripts；精简提交包只带相应主线CLI及其源码依赖。

## 当前主要研究入口

- **A：个人信息时点历史重建。**`experiments/full_a_personal_inputs.py`准备人口/历史/信息窗口；`experiments/full_a_personal_terminal.py`调度；`evaluation/full_a_personal.py`隔离评价。对应CLI：prepare_sce_full_a_personal_inputs、run_sce_full_a_personal、analyze_sce_full_a_personal。
- **B：按历史日期分布的独立月模拟。**`experiments/recent_b_sampled_dates.py`、`recent_b_sampled_terminal.py`。对应prepare_sce_recent_b_sampled_dates、run_sce_recent_b_sampled。它与老版共同截止B不同，不按文件名省略版本。
- **Core＋Normal。**`core_normal_joint.py`为联合答卷经验收缩，`experiments/full_a_core_normal.py`和`evaluation/full_a_core_normal.py`接A，`experiments/recent_b_core_normal.py`接B。它增加统计代表人数，不增加独立LLM信息。
- **月度个人信念自主递推。**`experiments/recent_b_recursion.py`；对应run_sce_recent_b_recursion。固定家庭、根月之后不重新按全国值初始化。
- **周度发布后校准。**`experiments/weekly_inputs.py`、`weekly_priors.py`、`weekly_news.py`、`weekly_state.py`、`weekly_terminal.py`、`weekly_evaluation.py`、`weekly_final_readout.py`。运行、状态、新闻、评价分开，不与月度自主链混称。
- **组合及下游。**`evaluation/aggregate_blend.py`、`full_a_macro_calibration.py`和`downstream_regression.py`。不同参数的训练窗口与信息时点分别追踪；下游是原月度序列，不是周度序列。
- **研究包与日志。**`submission_tools/package_builder.py`、`reproduce.py`、`release_evidence.py`、`source_layout.py`、`experiment_logs.py`。源码选择不读取真人答卷；默认重算不调用模型。

## 公共依赖：名字旧，也可能仍在使用

`model.py`和`__init__.py`注册官方接口；`information_exposure.py`、`household_state_mechanism.py`、`confidence_experiment.py`、`news_exposure.py`等参与共用消息或兼容初始化。若干lifetime、prior_belief等早期模块也仍被初始化导入。它们保留不代表当前采纳了所有历史机制。

`scoring/`承担近似Q9连续密度计分；`evaluation/metrics.py`承担加权分位数、W1和误差等。不要为了目录美观另写一套统计默认。`population/`内的grid_sampling等是抽样代码，旁边的人口JSON/JSONL不能按同一规则自动分发。

## 历史、未采纳及辅助研究

数理实答、财务/心理、lifetime经历、采购频率、Q8变化值、温度和模型格式等实验保留为方法取舍证据。专题源码通常位于根目录、experiments和evaluation；是否纳入当前配置请查实验台账及各批冻结协议，不从“文件存在”推断。

在精简提交包中，当前入口加静态依赖留在study正常路径，其余专题/历史/开发辅助源码放包根 `archive/research_source_supplement.zip`。归档有原相对路径与逐文件哈希，默认不用解压。需要复查早期实验时，在独立副本展开并恢复合法原输入；不要覆盖正式主包。

## 旧报告和本地记录

`reports/progress_20261015*`是早期汇报稿，`reports/final_report_draft*`是分版本论文/作图源码；它们不代表最终提交稿。开发仓库中为保留冻结引用仍在原位；提交包的阅读路线不指向旧汇报。当前PDF另交，正式稿以最终交付指针和版本为准。

真实人口、个人先验、逐人响应、权重、原始新闻及匹配键不在公共阅读范围。`.DS_Store`、`__pycache__`是本机杂项，不进入提交包。目录清单只记录文件角色/哈希，不包含这些资料的行内容。

## 怎么理解分类清单

- `current_research_entry`：当前研究或交付的明确入口。
- `transitive_runtime_or_compatibility_dependency`：被主线静态导入或包初始化牵连，保留路径。
- `supporting_or_historical_source_supplement`：不在这条入口依赖链，进入补充源码档；不等于全部过期。
- `historical_report_preserved_in_place`：旧稿保留原位，避免破坏冻结引用。
- `versioned_configuration_or_evidence_review_required`：需结合该批协议判断，不能当作默认配置。
- `local_population_or_fixture_not_auto_distributed`：可能是真实资料，也可能是合成fixture；必须逐文件白名单，不能整目录打包。

开发目录逐文件清单由 `scripts/catalog_sce_study.py --out <新目录>` 生成；提交包精确源码清单看包根 `SOURCE_INDEX.json`，归档内容看 `archive/SOURCE_INDEX.json`。静态分析无法证明任意动态加载方式均被覆盖，实际离线验收是另一个必要检查。
