# 七期个人截止 × 警示新闻：本机终端运行

2026-10-25。用户选择本人在Terminal启动，Codex不代启动。最终v4已通过本机prepare/review；28项新日期与调度定向测试通过，56个官方Core单元及原4096槽假回放保留。只运行v4，旧v1/v2/v3终端包因源码升级保留不运行。

## 运行内容

科学输入包`outputs/sce_media_timing_package_20261025_v3/`保持不变：七期、671个人月、四组各两遍，另有旧Q3参照。精确复用后主批4,096个新请求；随后只对本批新请求的技术失败各补一次，最多主批加补跑8,192次尝试，实际通常远少于上界。旧实验的失败位置不补，不按真值误差或密度拟合结果重抽。

DeepSeek V3.2经OpenRouter固定SiliconFlow FP8，温度0.5、JSON、关闭思考、最多1,024输出token。资料范围见[实验说明](TIMING_FACTORIAL_RUN_PLAN_20261025.md)。本批会发送由个人完成日期减一天得到的截止日；该信息能够推回完成日期。无原始ID、权重、本期目标答案或第三方原始个人记录。

预计主批$3.94；**主批、补跑、在途及未知费用预留共用$17硬上限**，不是启动即扣$17。运行命令中的确认参数由本人执行时，才记录这一批数据范围、预算和一次技术补跑的授权。没有82个月全量或B线调用。

## 启动

最终终端包为`outputs/sce_media_timing_terminal_20261025_v4/`，尚未授权或启动。启动命令：

```bash
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_media_timing.py run \
  --run-dir outputs/sce_media_timing_terminal_20261025_v4 \
  --confirm-scope-and-budget
```

程序先校验冻结文件，再启动独立后台进程；本终端持续显示进度。它不依赖Codex每批人工调度，Codex额度用完不会主动关闭该进程。进程通过caffeinate请求运行期间不因空闲休眠，仍需电脑开机和网络可用。

## 关闭观察窗口后继续查看

Ctrl+C只退出进度观察，不停止独立后台。重新查看使用：

```bash
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_media_timing.py watch \
  --run-dir outputs/sce_media_timing_terminal_20261025_v4
```

`watch`只读本地进度，不发新的API请求。不要为查看进度再次执行`run`。

## 容错与完成

临时连接、超时、429或502等故障在既有有界策略内冷却、降并发，只继续从未发送的位置；失败原始回答保留，主批完成后再统一补一次。认证、余额、预算或供应商异常保存并停止。网络不能无限恢复时也会停止，而不是无限扣费。

补跑与原回答分开存档。原Q8成功、Q9失败时，只采用补跑的合法Q9；反之亦然。补跑仍失败的字段保持缺失，继续评价，不为少数缺失无限循环。SDK没有自动重试，供应商没有自动回退。

主批和补跑结束后，独立评价进程才读取本期真人答案，计算同支持中心MAE、逐月/逐遍结果、真实上期基线、分布及独立Q8指标。技术完成不等于拟合已经改善；本轮不自动改写旧结果或启动全量。

如果程序因硬错误保存停止，先检查`latest_receipt.json`。补充余额或解决问题后，人工续跑只会发送对应阶段未发送位置；不会再给已经尝试过的失败位置第三次机会。具体续跑由该次停止收据决定，不需要重新准备输入。
