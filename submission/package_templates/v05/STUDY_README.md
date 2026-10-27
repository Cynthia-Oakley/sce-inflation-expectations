# SCE study：研究入口与复现范围

本 study 研究美国纽约联储消费者预期调查（SCE）中居民如何回答 Q8 和 Q9。默认入口在包根目录执行：

~~~bash
python studies/sce_inflation_expectations/run.py --mode all
~~~

默认运行是 0 API 的工程示例与聚合复算组合。它用 20 个合成家庭运行两步，检查工程接口；然后用封存聚合数据复算既有指标。20 人两步仅为工程示例，不是正式人口规模、研究配置或实证成绩。

## 配置和代码

根目录 model.py 只注册明确标注为“工程示例”的模型，不代表正式研究模型。真实研究运行参数集中登记在 simulation/research_runs.json 及相应版本记录中；人口、环境和生成设置应按研究运行配置理解，不从示例推断。

P、E 和行为机制分别在 components/population/、components/environment/ 和 components/behavior/。共享运行与兼容代码在 runtime/。研究任务入口见 [FILE_GUIDE.md](FILE_GUIDE.md)，可按评审问题查阅，不需要扫描平铺源码或历史脚本。

## 结果和证据

各研究任务的真实数值、比较基线和限制见 [结果导读](reports/report.md)。研究设计、信息时点、评价口径与证据边界见 reports/REVIEW_GUIDE.md。结果导读不是最终 8 页论文。

包内提供许可范围内的配置、工程示例和聚合复算材料，不含真实个人答卷、个人权重、完整提示与回复、原始新闻全文或密钥。近期研究的微观结构不完整，因此不能声称已从个人数据重算完整密度、W1 或群体分布。聚合复算不等于重新运行真实模型，也不等于完整微观复现。

## Study 根目录

Study 根目录只保留七个文件：__init__.py、model.py、run.py、study.yaml、resources.json、README.md 和 FILE_GUIDE.md。其他代码与材料分别位于 population/、environment/、simulation/、grounding/、trajectory/、reports/、reproduction_data/、experiments/、evaluation/、scoring/、components/、runtime/、submission_tools/ 和 examples/。

旧 study 根目录源码按职责归入相应目录。包根 archive/ 保留原始源码字节，SOURCE_INDEX.json 记录原路径与校验值；归档用于审计历史，不是第二套运行入口。
