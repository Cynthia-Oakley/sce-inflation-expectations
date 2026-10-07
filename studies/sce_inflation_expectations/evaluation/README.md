# 统一评价与离线基线

2026-10-07：v1已实现并完成2020–2024、60月运算。见 [评价契约](../../../docs/SCE_EVALUATION_CONTRACT_V1.md)、[结果与来源](../../../docs/SCE_BASELINE_RESULTS_20261007.md)。旧版“待实现”仅为历史状态。

`metrics.py`提供加权经验分位数、W1/居中W1、全国MAE/RMSE/偏差及配对月份块bootstrap。`baselines.py/benchmark.py`实现持续性、12期均值、AR(1)、SCE+CPI的ARX、简单信息更新Agent，以及A人口条件/已知中位数重建。没有真实LLM或MCP调用。

## 一键复算全国基线

在项目根目录，使用已有Python数值环境（numpy）：

```sh
python scripts/run_sce_baselines.py --headlines-only \
  --aggregate-file docs/sources/sce_baseline_aggregate_sources_20261007.json
```

不需要联网、密钥、微观数据或SocioVerse引擎。依赖来自项目锁定环境；程序保存新run，不覆盖旧结果。公共聚合台账使Git干净副本能复算全国结果；复核原网页另用台账URL/原始哈希。

## 全部重建基线

本地已有官方两份微观xlsx、原始新闻稿/CPI归档及日历时：

```sh
python scripts/build_sce_baseline_inputs.py --micro
python scripts/run_sce_baselines.py \
  --aggregate-file docs/sources/sce_baseline_aggregate_sources_20261007.json
```

需pandas/openpyxl/pyarrow；原始文件路径由预处理脚本明确列出，缺文件会失败，不虚构成功。下载SCE新闻稿可用`python scripts/prepare_sce_baseline_sources.py --fetch`；CPI web工具归档及日历下载过程记录在结果报告，当前该脚本不自动下载它们。A统计重建使用官方派生字段，仅模拟均值/不确定性分布，不生成完整原始Q9。

## 新模拟的统一评价

按契约转换规范化JSON包，再运行：

```sh
python scripts/evaluate_sce_outputs.py \
  --simulated <simulated_bundle.json> --observed <truth_bundle.json> \
  --output <new_result.json>
python -m pytest tests/test_sce_unified_evaluation.py -q
```

匹配真值系列/月份，population双方计分版本必须一致。群体标签/稀疏支持、明确真人对应的个人辅助与已知宏观约束分别处理。既有轨迹暂需转换包；旧评价入口和历史结论未改写。研究线、信息截止和样本设计仍需运行卡证明，统计计算本身不能替代P/E审计。
