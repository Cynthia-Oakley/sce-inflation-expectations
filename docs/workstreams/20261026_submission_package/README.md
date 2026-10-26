# 研究包与实验日志整理：交付说明

## 当前版：v02（2026-10-26新版A评价后）

最新ZIP：`outputs/sce_research_package_20261026_v2/SCE_research_package_draft_v02.zip`，约2.53MB。独立解压验收通过：官方Core无密钥示例、新旧A82与旧B11三个真实月级聚合replay、新A逐年（含2021）和新旧A早48/后34组合均匹配封存结果；30个study模块都来自解压包，0新增API，13项定向测试通过。验收收据在该目录acceptance.json，固定入口submission/latest_package.json。

新版A全国MAE0.298407（旧0.317093），2021年0.577424（旧0.822126）；早48月MSE拟模拟权重0.133976，后34月组合MAE0.184125/基线0.194118。MAE拟权0、2020/2025变差、W1略退、区间跨零及探索性边界一并保留。A82_comparison_summary.json只披露微观摘要，包内月级replay不声称重新计算W1/IQR。

日志另存v3：`outputs/sce_submission_experiment_logs_20261026_v3/`，15条选定记录中A完成记录纳入一次，主41,788＋补241＝42,029次新API，复用182份不重复收费。本批新API实报$33.060209542；选定全部API实报$78.243361980、未知费预留$2.680810930、token估费$3.706222、不可拆分$0.0414368分别列示，不是全项目发票总额。

当前仍为本地整理稿，未上传/提交；完整微观资料访问/许可、全新依赖安装与总账覆盖待完成。真实生成委托入口没有在本轮重新测试。原A控制器自动评价启动存在已记录的缩进问题，本轮仅单独执行未改动的冻结评价器恢复；不要再次run/resume已完成主批。原控制器源码/原收据保持不变，未来修复须另冻结版本；默认离线demo/replay不受影响。旧版v01和日志v2均保留。

## 下文为v01首次交付记录（历史状态）

2026-10-26，北京时间。本轮重新核查[赛事官网](https://socioverse.fudan-disc.com/challenge/)及[平台FAQ](https://socioverse.fudan-disc.com/docs/zh/faq/)，按study结构、复现说明、一键入口、模型/种子/调用与成本、数据及真值隔离要求形成可执行整理稿。要求与缺口见[逐项核查](official_requirements_and_gaps.md)；本版不是最终提交承诺。

## 先看这些文件

- 研究包ZIP：`outputs/sce_research_package_20261026_v1/SCE_research_package_draft_v01.zip`，约2.5MB。
- 解包后的README：`outputs/sce_research_package_20261026_v1/package/README.md`。
- 独立运行生成的阅读页：`outputs/sce_research_package_20261026_v1/verified_results/index.html`。
- 验收收据：`outputs/sce_research_package_20261026_v1/acceptance.json`。
- 实验记录入口：`outputs/sce_submission_experiment_logs_20261026_v2/README.md`，同目录有公开/私有JSON与CSV。
- 固定查找入口：`submission/latest_package.json`。原始日志仍在各原版本目录，本轮只做索引和源码/聚合白名单导出。

## 真正验证了什么

12项单元测试通过。ZIP共766个文件，其中739个是项目Python源码，不含整个官方仓库。解压到独立临时目录，以隔离Python模式从`/private/tmp`运行，765项包内清单哈希相符；30个实际导入的study模块均来自解压目录，没有从原工作区补读study源码。

默认一键命令实际完成两件事：

1. 官方SocioVerse2 Core运行20个手工合成代理、两步、种子42，产生40次规则决策和60条DuckDB面板记录；这是工程验证，不是实证准确率。
2. 用真实封存的月级聚合重算旧A82与旧B11的全国MAE/RMSE/偏差，及A早48月拟权、后34月评价的MAE/MSE组合。数字与旧归档匹配；没有重跑LLM或重新拟合Q9。

该测试使用现有锁定依赖环境；尚未在全新环境从网络重新安装全部依赖。完整微观Q9/W1/IQR复算没有在这个有限数据包中通过验收，不能拿宏观重算冒充。真实再生成入口要求完整受控工作区、冻结输入及显式收费确认，本轮没有执行。

## 实验记录如何计数

15条记录覆盖旧A82/B11、七期新闻/个人截止、财务/心理/数理/温度、Qwen/V3.2对照和当前A快照。索引保存canonical收据与来源哈希；旧运行、续跑、修复、最终overlay视图不作为四笔相加。用户原始日志没有移动、删减或改写。

选定记录的API实报为$45.183152438；未知费用预留$1.776657512、token用量估费$3.706222、无法拆分的合并金额$0.0414368分别列示。**它不是全项目总费用，也不是供应商发票核对结果。**分类补标、早期探索等未全部纳入，覆盖缺口保留。当前A快照不进入已完成费用小计。

运行快照只记录来源时间的逻辑尝试、已返回、在途与费用；物理请求数和可用回复数在没有对应证据时为null。182个历史复用槽是计划值，不用其替代已证实的实际物理调用。包内公开索引没有个人ID、原始答卷/模型文本、绝对路径或私有收据源路径；私有索引留在本地供追查。

## 数据和来源边界

包内只带手工合成工程人群、短公共BLS数值、公开全国指标与模拟月级聚合。原始SCE微观、CE/ATUS/GSS、NYT文本、逐篇标签与个人模型轨迹未随包分发；公开下载不能直接推定允许再分发。候选放行与未决事项见`DATA_RELEASE_POLICY.json`。

真值说明`TRUTH_ISOLATION_EVIDENCE.json`按实际文件SHA匹配已有获取记录，把获取时间、公开时间和历史版本分开。2017—19、2020—24、latest及近期2026-09首发的可证时间已登记；不能确认的获取时间/具体copy/vintage填null，未用目录名或文件mtime冒充。

生成与评价分进程的源码、白名单和原协议保留。包内月级真值只由replay阶段读取，不作为工程示例或付费生成的输入。A的历史当期画像/更早答卷是明确重建条件，B的旧人口/供体可得性是已披露假设；本包不把它们改写为严格事前盲预测。

## 如何复建

在主仓库中，输出目录必须新建：

```bash
PY='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
"$PY" scripts/build_sce_submission_experiment_logs.py --help
"$PY" scripts/build_sce_research_package.py \
  --out outputs/<fresh_package_directory> \
  --public-log-registry outputs/<selected_log_registry>/experiment_registry_public.json
```

ZIP解包后，依包内README安装依赖，再执行：

```bash
python studies/sce_inflation_expectations/run.py --mode all
```

后续需要纳入新版A/B最终结果、解决完整微观访问和分发范围、补齐总账及全新依赖安装测试，然后对最终ZIP再次独立验收。PDF和视频仍按既有计划分别收尾。此次未修改正在运行A的487项冻结来源，未启动新的模型调用或上传/提交。
