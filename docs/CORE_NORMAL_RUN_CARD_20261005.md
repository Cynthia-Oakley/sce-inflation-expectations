# 真实 Core 开发运行卡（两月已完成）

2026-10-05。用户已对明确列出的两月 300 Core、DeepSeek 数据发送范围与总 $2 上限表示同意；自动审批接受启动命令。5 月完成：300 次调用、300 条有效回答、技术审计与 Q9 拟合通过，保守费用估算 $0.266405。6 月补充明确授权后审批通过并完成。两月各 300 次调用全部有效，合计保守费用估算 $0.536425；技术审计、配对评价、Normal 扩展和全月对照完成。结果与准确路径见 [真实实验记录](CORE_NORMAL_LLM_RECEIPT_20261005.md)。

## 可审阅的范围

- 路线 A 历史重建开发；完整人口 1,234/1,297 人，按月各 300 Core，Normal 不调用 LLM。
- 使用当月真实画像与固定随机优先级抽样，不要求全年完访，旧 73 人试验计划保留作历史备选。
- 两个月：2021-05 / 2021-06；现有 E 截止分别为 5 月 12 日、6 月 10 日末，E/prompt 不在本轮另调。
- 目的地：DeepSeek 官方 API `https://api.deepseek.com`；发送去标识画像（年龄、教育、收入档、地区、就业、住房等）、公开经济信号、新闻标题与摘要，以及 Q8/Q9 问卷提示词。真实问卷答案不发送。
- 模型请求名 `deepseek-flash`（官方当前映射 V4.1-Flash）；以 API 返回信息为准，知识截止未知。该回顾性运行不能声称严格事前预测。
- `sce-q8-q9-v2-abstract`，temperature 0.5，max_tokens 1024，seed 42，关闭 thinking，每条最多额外重试一次。
- 正常 600 次请求，每月最多 600 次（含重试），两月最多 1,200 次。
- 已批准**两月总上限 $2：每月独立 $1 上限**；不得自动提高。正常估计 $0.56–0.94，重试另计。估价来自每次输入 2,500–4,000、输出 150–300 token，实际记 usage。
- 输入 $0.30 / 百万、输出 $1.20 / 百万，按峰时/未缓存最高常规价保守累计；正式调用前重核 [官方价格](https://api-docs.deepseek.com/quick_start/pricing/)。账单可能更低，本地累计不是服务商账单。
- 静态预算守卫在每次请求前检查下一次保守费用；极端失败/重试会提前停止，未获回答保留失败，不能自动补齐调用。

## 执行入口

两个月实际画像已通过无请求预检：每月 300 个 Core、77 信号、30 条含摘要新闻；均未注入本人上期回答或真实问卷答案。输入哈希与实际提示词样例见 `outputs/preflight_20261005T091701Z_2891ef40/`（5 月）、`outputs/preflight_20261005T091701Z_55fbb6d2/`（6 月），每条内容约 9,230–9,647 UTF-8 字节，字节数不作为收费 token 数。

以下命令在主仓库中运行。每次生成独立 run_id；第一月出错先检查，不自动续跑第二月。将月包路径写成绝对路径是运行器现有接口要求。

```sh
python scripts/run_sce_local.py --llm openai --model deepseek-flash \
  --population "$PWD/outputs/monthly_inputs_20261005T044602Z_f8c1a697/n300/202105/population.json" \
  --environment "$PWD/outputs/monthly_inputs_20261005T044602Z_f8c1a697/n300/202105/environment.json" \
  --simulation "$PWD/outputs/monthly_inputs_20261005T044602Z_f8c1a697/n300/202105/simulation.json" \
  --prompt-version sce-q8-q9-v2-abstract --temperature 0.5 \
  --max-tokens 1024 --retry-max 1 --max-calls 600 \
  --extra-body '{"thinking":{"type":"disabled"}}' \
  --price-in 0.30 --price-out 1.20 --cost-cap-usd 1.0 --confirm-spend
```

6 月使用同一包 `n300/202106/` 下三文件，其他参数相同。不要用全月或全年默认配置冒充两月。

## 运行后的验收

1. `scripts/audit_sce_monthly_run.py` 核验实际 P/E、回答、来源与源码；真实和失败记录不覆盖。
2. `scripts/evaluate_sce_dev_run.py` 对 Core 真实回答作独立评价，使用完整两月 `data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json`；截止后、前、同日分别报告。
3. `scripts/expand_sce_core_normal.py` 生成 Normal 并并列 Core 直接加权、扩展汇总和组支持。不把 Normal 填补值当真实个体误差评价。
4. 检查回答有效率、预期水平、跨人分歧、跨月变化、调用/重试/费用以及扩展的增益；不根据结果追调计分器或换种子。

此前 73 人启动被自动审批拦截，未执行。补充明确的数据发送范围、两月 300 Core 及预算问题后，用户答复“这个真实的实验你准备怎么做，配置是什么，我觉得可以做实验”；本轮启动已通过自动审批。授权记录保存在 `outputs/run_authorizations/core300_20261005T092656Z.json`。5 月 run_id：`sce-local-openai-20261005T092656Z-202105-8d2e3b2c`；6 月预留 run_id：`sce-local-openai-20261005T092656Z-202106-e4f49f76`。实际费用与结果待运行结束核验，不能继续引用离线阶段的零费用。
