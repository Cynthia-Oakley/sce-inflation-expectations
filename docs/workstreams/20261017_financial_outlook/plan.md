# 家庭财务前景Q2：机制探索与共用实验入口

日期：2026-10-17。本轮是A条件历史重建；输入是本人上月Q2，不是本期Q2或人格乐观。用户已明确批准768请求及$4上限，授权与协议同目录保存。实际运行状态以本地`real_dispatch.json`和逐job记录为准，不能重复启动已有run。

## 问题与对照

普通家庭对自身未来财务的判断，是否使模型在相同公开信息与原有通胀信念下，更接近真人？原输入为同期对照，处理组只增加本人上月Q2事实，不规定其通胀方向或变化幅度。

新增文字示例（仅演示Q2=2）：

> Your household financial outlook in your previous survey:
> You expected your household financial situation 12 months after that survey to be somewhat worse than it was then.

原P/E、上期Q8/Q9、更早摘要、问卷与直接回答格式逐字保留。没有新增Q1、具体认知题、购买频率或心理供体；缺失Q2不补值、不删人。

## 配置与解释边界

- 四个月：2020-03、2022-06、2023-12、2025-09，覆盖疫情初期、高通胀、回落和较近时期。均来自已看过的十二期，非新盲测。
- 每月48人，从既有年龄×收入分层的192人中按数理组比例抽取；选择不使用本期答案或Q2。评价权重为原调查权重÷两阶段入样概率。
- 两组、各两遍，共768请求。两组同期运行，不以旧批次直接替代对照；重复生成不是新增真人。
- DeepSeek官方端点、deepseek-flash、温度0.5、关闭思考、输出上限1024、无自动重试。可变别名不能证明固定模型权重或训练截止。
- 主看Q9同样本加权中位数MAE；同时报告个人均值误差、跨人W1、更新分布、个人不确定性与Q8。各月和两遍等权；不以某一指标的小幅收益替代整体取舍。
- 上期Q2是对当时未来12个月家庭财务的五档判断，其窗口与现在不完全相同；它不是外生收入冲击或稳定人格。真实问卷条件不能改名为严格B。

## 离线依据已完成，不能当作模拟效果

复用2284共同人月；前后时期在控制月份、人口、上期/Sim/历史后，上期Q2的样本内R²增量约0.60/1.31个百分点。较差前景通常伴随较高预期，但极端档不完全单调；没有识别因果。

逐年前推后八期，加入Q2后，回归的个人RMSE5.423→5.409、跨人W1 1.818→1.775；中心MAE0.534→0.669、个人MAE3.330→3.351。不是稳定提升，也不是LLM结果。保留这个反例；本轮真实模拟只检验事实输入是否提供可辨认增量，不承诺改善。详`offline_summary.json`。

## 工程复用实际落地

唯一新共用入口为`scripts/run_sce_frozen_trial.py`，支持prepare/dry-run/run/worker/evaluate。月份、人数、模型参数和上限由配置决定；新增机制以自己的小型准备/信息块适配器接入，不再复制完整运行器。

共用层负责冻结提示、协议/预算授权、官方引擎执行、错误停批、费用和逐次调用审计；评价层复用原计分与人群指标，旧真人计分直接缓存，新模型概率按向量缓存。原始历史试验文件保持原样。首次接入解决了本地源码与官方导出包的导入优先级问题，不修改官方Core。

本轮缓存诊断约0.28秒、材料准备约0.34秒；这些只是计算步骤，不包含开发/审阅。16个官方引擎干跑全部通过、API调用0；8项新增定向测试通过，不重跑全项目测试或整份官方数据审计。

## 操作与恢复

```sh
# 从项目根运行；只有已绑定授权的run动作可调用API。
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/run_sce_frozen_trial.py run --folder outputs/sce_financial_outlook_trial_20261017_v1 --workers 4
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/run_sce_frozen_trial.py evaluate --folder outputs/sce_financial_outlook_trial_20261017_v1 --out outputs/sce_financial_outlook_evaluation_20261017_v1
```

中断先查看`real_dispatch.json`及各job的run_manifest/llm_calls；禁止重新执行已有任务或自动重试。准备阶段不打开当前通胀答案；真实运行全部完成后评价器才读取已冻结真值。估约$0.89，保守预留约$3.56，上限$4；token估算与服务商账单分开。
