# study目录整理：开发源码、提交主包与补充归档

2026-10-27。本轮只整理文件角色、导读和打包范围，不修改模型机制、原始数据、付费运行、冻结研究源码或已有数值。

## 先读与下载

- [开发目录README](../../../studies/sce_inflation_expectations/README.md)
- [按研究问题找代码](../../../studies/sce_inflation_expectations/FILE_GUIDE.md)
- [当前v04研究包ZIP，约3.45MB](../../../outputs/sce_research_package_20261027_v9/SCE_research_package_draft_v04.zip)
- [解压包根README](../../../outputs/sce_research_package_20261027_v9/package/README.md) · [给评委的目录导航](../../../outputs/sce_research_package_20261027_v9/package/DIRECTORY_GUIDE.md)
- [本次独立重算结果](../../../outputs/sce_research_package_20261027_v9/clean_environment_acceptance/verified_results/index.html)
- [分类清单](file_catalog.json) · [导入依赖](dependency_edges.json) · [验收](acceptance.json) · [数值/语法检查](validation.json)

## 为什么需要整理

开发study原有约465个文件、387份Python源码；上版打包又纳入所有scripts，共828份源码，最终ZIP解开有883个文件。旧README仍有“目前没有模拟结果”等过期说明。文件存在不等于采用，名称旧也不等于可删，这些差别没有对初读者表达清楚。

本轮增加源码分类器和目录说明后，开发study清单为468个文件，跨study/scripts共830份Python源码。角色分类以明确研究入口加静态导入分析为依据；不能声称所有历史程序都重新运行过。

## 已如何处理

1. **当前阅读入口。**重写study根、evaluation和reports的README；新增FILE_GUIDE，按A、B、Normal、月度链、周度链、组合/下游及公共依赖定位。
2. **精简提交主包。**当前研究入口加静态依赖保留178份源码；其余652份专题、历史实验及开发辅助源码进入包根 `archive/research_source_supplement.zip`。归档保留原路径、逐文件SHA和说明，默认不解压。
3. **历史文档。**3份过期README原文实际归档到docs/archive/2026-10/study_readmes_before_20261027，有原路径和哈希。早期汇报/论文稿另有reports/HISTORICAL_INDEX；受保护旧稿保留原位，从主阅读路线移开，不搬动后再改旧manifest。
4. **开发目录保持可复查。**原算法源码没有重命名/移动；一些早期模块仍经__init__加载，属于兼容依赖，不能按“未采纳”随意删除。真实人口和本地记录不自动分发，3份已有本地人口改动不混入提交。

主包可见文件883→239，源码178份；补充档652份仍完整。归档的含义是按需查阅，不是判定全部无效。旧v03 ZIP及其验收原样保留，当前指针在submission/latest_package.json。

## 验收了什么

- 20项针对性测试通过，包括相对导入/兼容初始化、缺入口阻断和归档原字节保留。
- 使用已有的独立新建venv，不解压源码补充档，单独解压v04执行默认all成功；31个study模块全部从精简包加载。
- 238个包内文件哈希和652份归档源码哈希全部核对，20项包内测试通过。
- 与v03比较：全部A/B/Normal/月度/周度/下游replay结果和规则示例收据逐项相同。新增API为0。
- 830份源码语法检查均通过；这不能替代每个历史脚本的功能验收、受控输入或合法再生成。

研究包的原限制没有改变：完整微观生成/密度/W1重算需受控资料，当前默认是工程示例与聚合复算；资料许可、正式PDF/MP4和最终提交仍待收尾。

## 如何复建

在完整开发工作区，使用新的输出目录：

```bash
python scripts/catalog_sce_study.py --out outputs/<新目录>
python scripts/build_sce_research_package.py \
  --draft-version v04 \
  --out outputs/<新包目录> \
  --public-log-registry outputs/sce_submission_experiment_logs_20261027_v4/experiment_registry_public.json \
  --a-refresh-readout outputs/sce_full_a_t0_readout_20261026_v1
python scripts/verify_sce_research_package.py \
  --archive outputs/<新包目录>/SCE_research_package_draft_v04.zip \
  --out outputs/<新包目录>/independent_acceptance
```

真实数据/模型输出留本地，不因归档扩大外发或公开范围。精简只改变交付组织，不为改善结果重新抽样、选参或调用API。
