# 新闻机制 V3：运行与恢复手册

2026-10-25。执行包：`outputs/sce_media_mechanism_v3_20261025_v1/`。

**最新Terminal入口已另备：**请优先使用[Terminal执行附录](TERMINAL_EXECUTION_ADDENDUM_20261025.md)，其中列出 `run_sce_media_mechanism_terminal.py` 的启动、观察和仅续未发送命令。下文旧入口保留作Kimi原实现的追溯，不与新入口混用；旧job级resume不能代替逐请求恢复。

## 1. 已验证范围

- 月份：2019-05、2020-09、2021-06、2021-09、2021-12、2022-06、2023-12。
- 组别：R0/Q0/Q1/Q2/Q3，每组每月96人、两遍；70 jobs、3360提示位置、6720物理调用上限。
- A82只复用原始一遍，不虚构第二遍。
- 70/70官方Core scripted任务完成，70/70实际提示哈希一致，0真实API调用。
- `authorization.json` 初始为 `approved: false`。补标授权不构成模拟授权。

## 2. 离线复算

```bash
cd /Users/wushuyue/Documents/科研/DISC/socioverse_challenge
PY=/Users/wushuyue/anaconda3/envs/socioverse/bin/python

$PY scripts/audit_sce_media_mechanism_v3.py \
  --folder outputs/sce_media_mechanism_v3_20261025_v1
```

准备和附件已经执行，不要在原目录重复创建：

```bash
$PY scripts/prepare_sce_media_mechanism_v3.py \
  --out outputs/<新的准备目录>
$PY scripts/run_sce_media_mechanism_v3.py attach-evaluation \
  --folder outputs/<新的准备目录>
$PY scripts/run_sce_media_mechanism_v3.py dry-run \
  --folder outputs/<新的准备目录> --workers 4
```

## 3. 真实运行（须单独批准）

预算估计 $6.213030；极端预留 $25.688224；协议硬上限 **$32.11028**。目的地为 OpenRouter → SiliconFlow FP8 的 DeepSeek V3.2，温度0.5，无自动重试或供应商回退。人物画像、历史信念和环境会外发，需用户明确同意。

只有授权文件与协议哈希、调用数、目的地和预算完全一致后，才执行：

```bash
$PY scripts/run_sce_media_mechanism_v3.py run \
  --folder outputs/sce_media_mechanism_v3_20261025_v1 --workers 4
```

若中断：**不要再次执行 `run`**。先检查各 `outputs/local_runs/<run_id>/run_manifest.json` 和日志。完整成功任务会跳过；从未启动任务可以继续；部分失败或状态不明的任务会阻止恢复，不会自动重发。

```bash
$PY scripts/run_sce_media_mechanism_v3.py resume \
  --folder outputs/sce_media_mechanism_v3_20261025_v1 --workers 4
```

`resume` 日志若因上次异常已存在，也会停下要求人工核对，不覆盖旧日志。

## 4. 评价

全部真实任务完成后，在新目录生成评价和A82对照：

```bash
$PY scripts/evaluate_sce_media_mechanism_v3.py \
  --folder outputs/sce_media_mechanism_v3_20261025_v1 \
  --out outputs/sce_media_mechanism_v3_evaluation_20261025_v1
```

输出包括全国Q9中心MAE/bias、个人MAE、W1/IQR、逐月逐遍、四档、上期预期高/中/低和Q2实际Fox接收分层；Q8独立。七个月都曾在A82中出现，只能称探索性机制诊断，不称独立时间外验证。

## 5. 证据

- 离线验收：`outputs/sce_media_mechanism_v3_20261025_v1/offline_acceptance.json`
- 工程检查：`outputs/sce_media_mechanism_v3_20261025_v1/engineering_checks.json`
- 提示、上下文、协议和哈希：同目录 `<month>/`、`protocol.json`、`manifest.json`
- NYT补标：`outputs/sce_news_mechanism_labels_20261025_v1/`
- Fox补标：`outputs/sce_fox_mechanism_labels_20261025_v1/`
- 标签复核：`outputs/sce_news_mechanism_label_audit_20261025_v1/`、`outputs/sce_fox_mechanism_label_audit_20261025_v1/`
