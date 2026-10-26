# SCE 实验分析面板（离线）

- 入口：`index.html`，浏览器直接打开（file:// 可用，无服务器、无网络、无外部库）。
- 新增同契约批次（`outputs/<批次>_evaluation_*/cases_private.json`）后，在仓库根运行
  `python scripts/build_sce_experiment_panel.py` 一条命令即可重建本目录的
  `index.html`、`panel_aggregate_v1.json` 与 `build_receipt.json`（原子发布）。
- 私有逐人中间文件写在 `outputs/sce_experiment_panel_private/`（git 忽略，勿提交、勿外传）；
  本目录只含允许发布的聚合产物。
- 统计口径版本见 `build_receipt.json` 的 `stats_version`；验收数字（0.459191pp 主指标、
  552/571 共同支持等）以冻结批次 summary 为准。
