# 低成本模型对照进度与接力

> **2026-10-08 输入审计更正：**Qwen的220/240份消息继承DeepSeek上一月点预测，其中161份不同于Qwen自身上一月回答。结果数值不变；这是相同消息下的条件回答比较，不是Qwen独立更新的年度轨迹。详见[P/E诊断](SCE_PE_DIAGNOSTIC_20261008.md)。

**后续已完成：**用户对具体数据发送确认卡授权后，本实验已生成240份Qwen回答并完成全年同口径评价，总费用含预留$0.08263024。最终结论与路径见[SCE_QWEN_REUSE_RESULT_20261008](SCE_QWEN_REUSE_RESULT_20261008.md)。以下保存调用前/阻断时的免费复算记录，不是当前状态。

2026-10-08。本轮完成输入、入口、验收与免费基线复算，**Qwen尚未运行**。

## 已完成

- 旧DeepSeek固定20人×12月240个参考回答及原始消息封存，SHA256选择不使用答案；模型消息与旧存档逐字匹配。DeepSeek新调用0。
- Qwen指定DeepInfra、temperature0.5、max_tokens1024、总$0.50入口离线验收通过。最多一次相同原消息重试，不能改概率/更换供应商；恢复携带旧账务并去重，未知在途调用必须先核账。
- 10项定向测试通过：3入口mock、5预算/路由/费用、2离线评价。验证了99%→相同消息重试→100%和429费用预留停止；已知常数偏移与整年受访者成组bootstrap的独立预期值一致。没有真实API调用。
- 冻结近似计分器与其已锁定来源匹配；真实和模拟Q9使用相同计分。原73人全年876条和选定240条均复算。

## 免费复算结果

同20人子样本、共同有效Q9案例，每月18—20人：

- DeepSeek月度跨人中位数全年MAE **0.952pp**，RMSE **1.244pp**，带符号偏差 **−0.935pp**。
- 11次相邻月变化方向一致 **5次**；平均人际IQR差 **1.952pp**。回答仍比相应真人分布集中。
- 真值有3份无效概率、1份不相邻双区间无法拟合；DeepSeek240份均可计分。完整共同全年18人敏感性：MAE **0.903pp**、方向 **6/11**。
- 旧完整73人背景结果：同计分月中位数MAE **1.909pp**、方向 **7/11**。它不作为Qwen20人的直接比较对象；与20人差别提示小样本结果对人口选取敏感。

这些都是旧固定面板、旧4信号E的**等权开发诊断**，不等于全国headline，也不是当前完整P/E的效果。样本内真实个人派生值由同一近似计分器重算，不能与官方加权宏观指标混用。

## 当前阻断

真实命令由自动审批在创建进程前拒绝：认为方案/预算同意不足以明确授权具体画像向OpenRouter/DeepInfra外发。风险点是第三方接收真实受访者的去标识人口标签。请求已说明年龄、教育、收入档、地区、住房、就业、数理能力七类标签及公开BLS信息；不发送原ID、权重、真实答案，240请求、$0.50。

**新真实调用0、费用0、真实运行目录不存在。** 不把mock日志或离线图当Qwen结果。等具体授权回复后用以下原入口继续；不要使用原四模型/$20入口。

## 准确路径

- 输入：`outputs/sce_qwen_reuse_prepared_20261008_v1/`。
- 封存：[sources/sce_qwen_reuse_preparation_20261008.json](sources/sce_qwen_reuse_preparation_20261008.json)。
- 离线基线结果：`outputs/sce_deepseek_reuse_analysis_20261008_v1/summary.json`，同目录`monthly_comparison.png`和本地个人评价。
- 基线无个人记录封存：[sources/sce_deepseek_reuse_baseline_20261008.json](sources/sce_deepseek_reuse_baseline_20261008.json)。
- 待运行：`outputs/sce_qwen_reuse_run_20261008_v1/`，当前不存在。

续跑命令（必须先收到具体外发授权；`--authorization-note`填实际人类回复）：

```bash
python scripts/run_sce_reuse_probe.py \
  --inputs outputs/sce_qwen_reuse_prepared_20261008_v1 \
  --receipt docs/sources/sce_qwen_reuse_preparation_20261008.json \
  --out outputs/sce_qwen_reuse_run_20261008_v1 \
  --confirm-spend --authorization-note '<actual human authorization>'
```

运行完成后离线评价：

```bash
python scripts/analyze_sce_reuse_probe.py \
  --inputs outputs/sce_qwen_reuse_prepared_20261008_v1 \
  --receipt docs/sources/sce_qwen_reuse_preparation_20261008.json \
  --run outputs/sce_qwen_reuse_run_20261008_v1 \
  --out outputs/<new_comparison_folder>
```

按[运行卡](SCE_QWEN_REUSE_RUN_CARD_20261008.md)中预先登记的全年误差/分布/稳定性判据决定是否值得复核；不因当月有利结果追改提示。如无明确改善或差异，优先回P/E；即使改善也不能直接换正式模型。

15份用户/Kimi待审改动原样，未改正式study配置、DECISIONS、原计分程序或.env。
