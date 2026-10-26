# SCE一年期通胀预期：研究包整理稿

队伍：水上挽月；参赛赛道A。此包遵循SocioVerse的`studies/<id>/`布局，供本地复现和最终提交前审阅。**当前不是最终提交版**：新版A个人截止T0已完成，完整微观重算所需资料的分发/取得安排和部分历史实验总账仍待收束。

研究对象是纽约联储的消费者预期调查SCE：每月约1,300名受访者，以轮换面板连续回访。我们模拟未来12个月通胀的点预期Q8和概率回答Q9，目标是重建居民如何回答调查，并检验总体中心、个体分歧与更新行为；实际CPI是经济背景，不是同一个预测目标。调查来源：https://www.newyorkfed.org/microeconomics/sce。

## 安装与一键运行

使用Python 3.11及以上。先建立自己的虚拟环境并安装锁定依赖；安装步骤需要网络，离线运行本身不连接模型服务。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python studies/sce_inflation_expectations/run.py --mode all
```

最后一条命令是默认复现入口。它运行官方Core的无密钥工程示例，再用真实已归档的月级聚合结果分别重算旧A82、新版T0 A82与旧B11误差及A的48/34月组合。新版A另按年份核对，重点含2021年。输出写入全新的`outputs/reproduction_<time>/`，包括`receipt.json`、`index.html`和工程轨迹库；不覆盖输入，不读取API key，不启动主批。纳入版本以`aggregate_cases.json`为准。

依赖版本和本地使用的官方仓库commit见`DEPENDENCIES.json`。本版需在现有锁定依赖环境中独立解压验收；不同操作系统的全新安装尚需另验，不能仅凭生成依赖文件声称已完成。

## 三种运行的含义

1. `--mode dry-run`：20个手工合成家庭、两步、种子42，通过官方SocioVerse2的P/E/B/collector与DuckDB存储。它检验工程链路，**不产生实证拟合成绩，也不等同于验证512人新版配置的效果**。
2. `--mode replay`：从包内真实月级缓存重算新旧A82、旧B11的全国MAE/RMSE/偏差，以及A早48月拟权、后34月评价。它不重新询问LLM、不重新拟合个人Q9，也不声称重算真人W1/IQR。A与B分别评价，不汇成93个月同口径总误差。
3. `--mode generate`：真实API再生成。需要合法、完整、经哈希冻结的输入和执行包、相应模型密钥与预算。该入口只委托现有冻结执行器，不能用聚合缓存冒充重新生成，也不能默认收费。

真实生成示例仅用于已恢复完整资料的受控工作区，不应在审阅时直接运行：

```bash
python studies/sce_inflation_expectations/run.py --mode generate \
  --source-workspace /path/to/data_complete_workspace \
  --prepared-run outputs/your_new_frozen_run \
  --confirm-paid
```

冻结输入缺失或哈希不符时必须失败，不能静默改成规则输出。原机器的冻结包含本地路径，迁移后须依据已披露算法/输入重新prepare新包并明确预算；不能把复制旧路径当作完成可迁移再生成。本整理稿尚不把完整微观再生成列为已通过验收。

## 包内有什么

- `studies/sce_inflation_expectations/study.yaml`、P/E/simulation目录、`trajectory/`、`reports/`与`run.py`：官方study布局；默认元数据指向工程示例，主研究配置见study README。
- study和`scripts/`中的Python源码：按代码根和`.py`后缀白名单收录，记录原源码哈希；未复制整个官方仓库，也不修改冻结源码。
- `reproduction_data/`：仅月级公开全国指标与模拟聚合，不含真人问卷或个体模型回答；`A82_comparison_summary.json`披露同名单微观摘要，这些微观摘要没有在月级replay中重新计算。
- `experiment_logs/registry_public.json`：所纳入实验的聚合记录；原始JSONL/修复账本不移动、不合并改写。覆盖范围、未决费用和运行中快照分别注明。
- `SOURCE_INDEX.json`、`PACKAGE_MANIFEST.json`、`DATA_RELEASE_POLICY.json`：文件哈希、适配层、排除项及资料放行状态。

`python studies/sce_inflation_expectations/run.py --mode verify`只校验清单，不运行模拟或重算。

## 研究与评价边界

Q8是一年期通胀点预期；Q9是同期限十个区间的概率。主研究从Q9拟合连续分布，取个人密度均值，再取跨家庭的设计加权中位数。Q8单独报告。W1衡量跨人分布差异，IQR描述跨人或个人概率分布宽度，二者不能与全国中心误差互换。

A线使用历史人口与严格更早本人答卷/近期供体，属于明确重建条件下的模拟。B线用截止前可得性假设下的旧人口和经已公开历史全国值校准的合成起点；现有B11是结果公布后进行的时点回测，不是事前封存预测。文本版本、微观发布的精确历史版本和LLM知识边界不足均保留，不能把发布时间筛选合格写成没有泄漏风险。

模型历史包括Flash、Qwen2.5-72B与DeepSeek V3.2。主模型固定为OpenRouter→SiliconFlow FP8的V3.2；主实验采用温度0.5、JSON、关闭思考，具体名单、生成遍数、预算和技术补跑以各批冻结协议为准。真实LLM抽样不能承诺逐字重现；已有回答的重算与真实重新生成分别说明。种子控制抽样/信息分配和工程示例，不保证供应商推理的随机数流。

## 数据、日志与最终补齐项

原始SCE微观、CE/ATUS/GSS供体、NYT文本、新闻逐篇标签和个人模型轨迹默认不随此整理稿分发。公开可下载不自动等于可再分发；见`DATA_RELEASE_POLICY.json`中的待核项。完整微观复算需按许可恢复输入或另设合规访问，不能用月级重算替代这一未决事项。

原始日志留在原版本目录，本包只收聚合白名单。API实报、token估费、未知费用预留、历史复用和当前运行快照分开；登记实验的小计不是全项目供应商账单。研究包准备、检查与离线运行本身没有新增模型调用。

新版A全国MAE为0.298pp（旧版0.317），2021年为0.577pp（旧版0.822），仍高于相应历史基线。按早48月MSE拟得模拟权重0.133976，后34月组合MAE为0.184pp、基线0.194pp；MAE拟权则为0。多个机制同时变化，历史结果也曾用于开发，不称独立盲测或因果识别。2020、2025年变差和微观W1恶化一并保留，不能只展示改进年份。

提交前还需按实际进度更新B候选（当前仍旧B11）、补齐完整微观访问/复现安排、核对总账覆盖及数据许可，并再次独立解压执行。PDF为4—8页、演示为不超过5分钟MP4，均独立提交；本README不替代论文和视频。官网要求来源见`OFFICIAL_REQUIREMENTS.json`及https://socioverse.fudan-disc.com/challenge/。
