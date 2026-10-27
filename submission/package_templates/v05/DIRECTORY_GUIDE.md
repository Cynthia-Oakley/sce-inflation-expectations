# 目录导航：从一个入口开始

v05 的当前提交候选目录是 **deliverables/research_package/v05/package/**，配套压缩包为 **deliverables/research_package/v05/SCE_research_package_draft_v05.zip**。运行和审阅都从包根 README.md 开始。

## 最短阅读路线

1. 包根 README.md：安装、默认运行和复现范围。
2. studies/sce_inflation_expectations/run.py：执行默认 0 API 流程。
3. 本次运行输出中的 index.html 和 receipt.json：查看聚合复算和核对记录。
4. Study 的 reports/report.md：阅读结果导读。该文件不是 8 页最终论文。
5. Study 的 reports/REVIEW_GUIDE.md 和 FILE_GUIDE.md：按需查看方法或定位实现。

## Study 目录

studies/sce_inflation_expectations/ 是标准 study。Study 根目录只放七个文件：__init__.py、model.py、run.py、study.yaml、resources.json、README.md 和 FILE_GUIDE.md。其余内容放入以下分目录：

| 目录 | 用途 | 阅读时注意 |
|---|---|---|
| population/ | P 层人口输入与说明 | 仅纳入获准的示例、公开或聚合文件；不放个人答卷和私有权重 |
| environment/ | E 层价格、新闻、政策等环境资料 | 分开记录来源、发布时间和可用时间；不以下载时间代替历史版本 |
| simulation/ | 运行配置、种子策略和冻结运行登记 | research_runs.json 记录真实研究运行；根 model.py 只注册工程示例 |
| grounding/ | 外部来源、来源元数据和事实依据 | 提供引用及版本信息，不分发受限新闻全文 |
| trajectory/ | 工程示例轨迹与格式说明 | 真实个人轨迹不因此成为公开数据 |
| reports/ | report.md 结果导读、评审方法说明和图表 | report.md 不是赛事要求的最终 8 页 PDF |
| reproduction_data/ | 获准公开的聚合案例和复算输入 | 可重算已有聚合结果，不足以重建全部微观结果 |
| experiments/ | 按研究任务组织的准备、运行和分析代码 | 按入口和冻结版本阅读，不从文件存在推断其属于默认配置 |
| evaluation/ | 误差、比较和评价流程 | 评价读取目标值；目标值不作为生成输入 |
| scoring/ | Q9 答卷到连续密度的计分实现 | 方法说明保留近似计分与官方实现的差异 |
| components/ | 可复用 P/E/B 组件 | 子目录为 population/、environment/ 和 behavior/ |
| runtime/ | 运行适配器、调度和兼容依赖 | 运行层代码不是额外的研究配置 |
| submission_tools/ | 打包、来源清单和离线复算工具 | 默认复算不会触发真实模型调用 |
| examples/ | 清楚标注用途的工程示例与配置 | 20 人两步案例只用于流程检查 |

## 源码归位与追溯

旧 study 根目录的平铺 .py 源码按职责归位：人口相关进入 components/population/，环境相关进入 components/environment/，行为机制进入 components/behavior/，运行与兼容代码进入 runtime/。

包根 archive/research_source_supplement.zip 保留原始开发源码字节；archive/SOURCE_INDEX.json 记录原相对路径和 SHA-256。归档代码不进入默认导入链，也无需解压寻找运行入口。历史文件的存在不代表它们属于当前研究配置。

## 阅读时区分

- **工程示例：**20 个合成家庭、两步运行，只验证装配与流程。
- **真实聚合复算：**读取封存结果，重算已有全国误差和对照，不重建完整个人回答。
- **受控微观资料：**个人答卷、权重、轨迹和部分原始环境资料不在默认公开包内；缺少这些资料时，不能声称完整微观复现。
