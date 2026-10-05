# 两个月真实 LLM 开发运行卡（待预算确认）

2026-10-05。已完成无请求预检，尚未运行真实 LLM。

- 用途：沿用 73 人面板检查新 E 与标题＋摘要提示词；不能作为全国代表性结论。
- 开发月：2021-05 / 2021-06。统一 E 截止：2021-05-12 / 2021-06-10 23:59:59 America/New_York。
- 模型请求名称：`deepseek-flash`；现有端点为 `https://api.deepseek.com`。官方定价页核实该名称现对应 **DeepSeek-V4.1-Flash**，运行仍记录 API 实际返回 model / fingerprint / request_id，不能只写“V4”。知识截止未独立核实，按回顾性条件模拟报告。
- 提示词：`sce-q8-q9-v2-abstract`。每月 77 条信号、30 条新闻，60 条新闻全部有摘要。每条提示词约 9,230–9,646 UTF-8 字节；这不是 tokenizer token 数。
- `temperature=0.5`，沿用旧真实运行设置；`max_tokens=1024`，`seed=42`，每条最多重试一次。种子不保证服务端 LLM 输出完全可重复。
- 正常产出 146 条回答；最大请求数 292（含重试）。
- 建议本轮费用上限：**$1**，待用户确认。按官方峰时、未缓存最高价保守记账：输入 $0.30 / 百万 token，输出 $1.20 / 百万 token；不预先扣除缓存或非峰时优惠。
- 预算逻辑已修为调用前预留下一次请求费用，失败无 usage 也预留。它是指定费率下的本地保守限制，不是服务商账单；正式运行前再核实价格未变。
- 严格个人比较：只对截止日之后作答者主报；同日、之前及未知日期分别报告。新闻文本历史版本与汽油 vintage 仍有缺口，不能称完全验证的历史 PIT 预测。

定价/模型来源（2026-10-05 核查）：https://api-docs.deepseek.com/quick_start/pricing/?tab=case-studies 。

预检证据：`outputs/preflight_20261005T043547Z_e94f9abd/summary.json`，原始实际渲染样例见同目录 `prompt_samples.jsonl`。输入哈希已保存在该证据中。

确认后在主仓库运行下列命令；**本文件不是已获得预算授权的记录**：

```sh
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/run_sce_local.py \
  --llm openai --model deepseek-flash \
  --population population/population_main2021_a73.json \
  --environment environment/environment_dev2021_05_06_v2.json \
  --simulation simulation/simulation_dev2021_05_06_v2.json \
  --prompt-version sce-q8-q9-v2-abstract \
  --temperature 0.5 --max-tokens 1024 --retry-max 1 --max-calls 292 \
  --extra-body '{"thinking":{"type":"disabled"}}' \
  --price-in 0.30 --price-out 1.20 --cost-cap-usd 1.0 --confirm-spend
```

与本轮新建的按月完整人口/300/500 人输入分开：先保留这项已有开发设计，再决定是否用月度人口做新的主实验。两者分别留 run_id，不混为一组比较。

运行完成后使用独立评价入口（将 `<本轮运行目录>` 替换为新生成目录；真值在此阶段才读取）：

```sh
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/evaluate_sce_dev_run.py \
  --run-dir <本轮运行目录> \
  --profile-cache data/cache/monthly_profiles_7f0ed622ae0915902741.parquet \
  --profile-manifest outputs/monthly_inputs_20261005T044205Z_53cbc7e5/manifest.json
```

该命令默认使用原 73 人评价材料，真实与模拟 Q9 同一近似计分器，截止日后的个人比较单列。按月 300 人验收、完整真值与源码边界见 [本轮接力](MONTHLY_POPULATION_ACCEPTANCE_20261005.md)。
