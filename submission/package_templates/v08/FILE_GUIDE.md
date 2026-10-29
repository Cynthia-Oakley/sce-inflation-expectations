# 文件导读：按评审问题定位

默认流程由工程示例、真实聚合复算和正式答卷微观复算三部分组成。先运行包根 README 中的 --mode all，再按问题查阅以下文件；不用从历史源码归档猜测运行入口。

## 运行与配置

run.py 是 study 的统一入口；每次运行写入新输出目录。默认流程不调用模型 API。model.py 仅注册清楚标明的工程示例；真实研究运行参数见 simulation/research_runs.json。

examples/core_demo/ 收纳 20 个合成家庭、两步工程示例所用配置。这个案例验证接口，不是正式人口或研究结果。

## P、E 与行为机制

人口数据与说明在 population/，人口实现见 components/population/。环境资料与说明在 environment/、grounding/，环境实现见 components/environment/。来源、发布时间、取得时间和 as-of 应分开核对；包内不提供受限新闻全文。

components/behavior/core_normal_joint.py 实现 Core＋Normal 的联合答卷经验扩展；它扩展统计代表规模，不增加独立模型回答。runtime/openrouter_frozen_runtime.py 是冻结消息运行适配器，用于获准的真实生成流程；默认复算不会调用它。

## 按研究任务查入口

experiments/full_a_personal_inputs.py 组织 A 线个人信息时点历史重建的输入准备。experiments/recent_b_sampled_dates.py 对应按历史作答日期分布准备的近期独立月度 B 任务。experiments/weekly_inputs.py 组织周度任务输入；周度状态更新与评价仍按其各自模块和运行记录查看。

月度自主递推和其他扩展也位于 experiments/。各文件是否属于某项冻结运行，应结合 simulation/research_runs.json 判断，不能仅凭文件存在推断。

## 计分、评价与复算

evaluation/metrics.py 提供共同评价指标；evaluation/ 放置误差比较和任务评价流程。scoring/ 中的 sce_q9.py、sce_q9_frozen.py 等模块将十档回答映射为连续密度。Q8 与 Q9、全国中心与微观分布是不同的评价目标。

reproduction_data/保存聚合案例和micro逐答卷资料。replay核验全国结果、组合与下游误差；micro从正式答卷重算个人密度、A的W1/IQR及条件指标，并重建Normal后验原子质量。all包含两者。近期人群分歧仅作描述，下游回归仍按封存预测检验误差，不重新训练。

## 结果与历史来源

reports/report.md 汇总结果和解释边界；reports/REVIEW_GUIDE.md 说明研究设计、时间口径、基线与限制。前者是结果导读，不是最终 8 页论文。

archive/research_source_supplement.zip 与 archive/SOURCE_INDEX.json 供原始源码追溯。归档代码不参加默认流程。

## 论文数字对照

reports/PAPER_METRIC_GUIDE.md明确样本内描述组合与冻结权重组合、共同样本与全波次微观比较，及模型调用费用的不同范围。配套reproduction_data/paper_metric_crosswalk.json和paper_A82_comparison.csv用于逐项对照论文，不能把两种组合的权重互换。
