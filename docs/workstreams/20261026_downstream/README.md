# SCE 下游经济用途：第一阶段数据包

日期：2026-10-26。本目录是独立的离线下游研究，不改变 SCE 模拟目标、as_of、测试切分或任何冻结运行包，不启动 Simulation/LLM。

## 本阶段范围

只准备四个主结局及第一轮 ARX 所需的公共控制变量：

1. Atlanta Fed Wage Growth Tracker 的总体工资增速；
2. FRED `PCEDGC96` 实际耐用品消费；
3. FRED `REVOLSL` 循环消费信贷余额；
4. FRED `MICH` 密歇根大学一年期通胀预期。

公共控制变量为 `UNRATE`、`JTSJOL`、`DSPIC96`、`CPIAUCSL`、`CPILFESL`、`UMCSENT`、`FEDFUNDS`；信贷另取 `TERMCBCCINTNS` 与 `TERMCBCCALLNS` 作为候选利率控制，待元数据核查后选用。暂不展开 BIE、车辆销量、信用卡逾期、TIPS/SPF 等第二批内容。

## 时间和版本约定

- 原始序列从 2017-01 起抓取至数据源当前可得月末，保留滞后项和未来结局所需的历史窗口。
- 按用户决定，本阶段使用抓取日的当前公开版本，不补 ALFRED、首发值或修订历史；因此后续结果只能称为回顾性样本外回测，不能称为严格实时预测。
- 原始文件不做覆盖、不手工改值。清洗、月频率对齐和对数增长等转换另存派生表，并记录公式。
- 每个来源保存原始文件、来源 URL/系列 ID、抓取时间、行列范围、缺失情况和 SHA-256。密钥不写入任何文件。

## 文件分工

- `outputs/sce_downstream_data_20261026_v1/wages/`：工资代理；Atlanta Fed 官方文件和元数据。
- `outputs/sce_downstream_data_20261026_v1/durables/`：耐用品代理；`PCEDGC96`。
- `outputs/sce_downstream_data_20261026_v1/credit/`：信贷代理；`REVOLSL` 和信用卡利率候选。
- `outputs/sce_downstream_data_20261026_v1/expectations/`：预期代理；`MICH`。
- `outputs/sce_downstream_data_20261026_v1/controls/`：公共控制变量代理；七个公共 FRED 序列。

各代理只写自己的子目录和本子目录的 manifest，不改公共代码、其他实验或官方宿主。主代理后续负责合并、覆盖检查和回测入口。

## 后续识别边界

最终模拟指标使用项目已确定的组合值，但不能把组合值单独回归后的全部效果归因于模拟。后续回测将比较同结构的领域控制模型与加入组合指标的模型；A 的 82 个月用于开发/滚动评价，B 的 11 个月只作迁移敏感性，不拼接成同质长样本。

## 已完成交付与验收

2026-10-26 已通过五个并行子代理完成公开抓取，另用本地脚本完成合并。没有新增 Simulation、LLM 或付费取数调用。

- 原始文件和来源清单：`outputs/sce_downstream_data_20261026_v1/{wages,durables,credit,expectations,controls}/`。
- 合并面板：`outputs/sce_downstream_data_20261026_v1/derived/monthly_panel.csv`。
- 变量定义：`outputs/sce_downstream_data_20261026_v1/derived/variable_dictionary.json`。
- 覆盖、缺失和 14 个来源文件哈希核验：`outputs/sce_downstream_data_20261026_v1/derived/coverage_report.json` 与 `derived/manifest.json`。

面板为 2017-01—2026-09 共 117 个月。`PCEDGC96`、`REVOLSL` 及其余部分 BEA/G.19 序列目前到 2026-08；工资和 `MICH` 到 2026-09。2025-10 的工资、失业率、总体 CPI 和核心 CPI 保留空值；信用卡利率按季度发布，月度面板中 78 个空值不填充。未做任何插值、前向填充、缩放或季调。

复算命令（从主仓库根目录执行，使用新的输出目录，不覆盖原面板）：

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python \
  scripts/prepare_sce_downstream_data.py \
  --raw-root outputs/sce_downstream_data_20261026_v1 \
  --out outputs/sce_downstream_data_20261026_v1/derived_replay
```

该命令会逐个核验原始文件 SHA-256，再生成面板、变量字典和覆盖报告；不访问网络。已实际运行此复算命令，并用独立 Python 检查逐月值与原始 CSV 一致、行数/日期边界正确、缺失数量符合预期，结果通过。

## 下一步（仍为零 LLM）

1. 读取既有 A82/B11 组合序列，按月份与本面板连接，明确每个预测时点的可用控制变量。
2. 先对四个主结局分别定义增长/水平和预测 horizon，再做持续性、AR、领域 ARX 与加入组合值的同结构对照。
3. 使用滚动样本外 RMSE/MAE；不把当前版本回测称为严格实时预测，不把 B 的 11 个月单独用于复杂模型拟合。

## ConsumerSim 风格回归结果（2026-10-27）

已在查看下游结果前冻结 `regression_protocol.json`，随后完成 4 个结局 × 1—3 个月预测期 × 8 个模型的离线分析。A 使用扩展窗口回测，每个原点仅使用当时已经形成结局标签的训练行，最少 36 行；B 的模型只用首个 B 原点前的 A 标签拟合一次，不用 B 结局更新。联合完整案例剔除保证同一结局和预测期下各模型使用相同样本，未插值。

- 阅读页及全部表格：`outputs/sce_downstream_regression_20261027_v1/index.html`。
- 逐月预测：`predictions.csv`，4,896 行；全部模型指标：`model_metrics.csv`，192 行。
- 全部 17 类配对对照：`contrasts.csv`，408 行；重点子集：`key_contrasts.csv`，120 行。
- 输入、代码与输出哈希：`manifest.json`；结局、模型、控制和缺失规则：`regression_protocol.json`。
- 新 Simulation/LLM 调用为 0，未改动任何冻结模拟结果。

### 应该怎样读结果

RMSE 改善为候选相对参照的百分比，正数表示误差下降；ΔR²来自 A 样本内回归，不能替代样本外表现。A 各结局×预测期的有效原点为 41—44 个，B 仅 7—10 个，且 2/3 个月结局存在重叠，不能把各行当独立证据。

A 中有局部正向结果，但跨结局和预测期不稳定：

- 原始模拟相对官方 SCE，在循环信贷未来 1/2/3 个月的 RMSE 分别改善 **3.55% / 8.17% / 1.69%**；在 MICH 的 2/3 个月改善 **0.88% / 0.68%**。但 12 个结局×预测期只有 5 个为正，工资和耐用品均为负。
- 最终组合相对官方 SCE，在循环信贷未来 2/3 个月改善 **5.03% / 4.80%**，但 1 个月退步 **3.18%**；全部 12 项只有 3 项为正。
- 官方 SCE＋原始模拟相对领域 ARX，在 MICH 1 个月、耐用品 2 个月、工资 1/3 个月等 5 项为正，其中分别为 **5.04% / 7.98% / 1.72% / 3.63%**；其余 7 项为负。样本内 ΔR²为正也不能推出滚动 RMSE 必改善。
- 简单基线仍很强：A 的耐用品和工资在三个预测期均以持续性 RMSE 最低，MICH 以 AR(1) 最低，循环信贷以历史均值最低。

B 只作冻结迁移敏感性。组合在耐用品 1/3 个月和信贷三个预测期为正，但其他多项为负；官方＋模拟相对 ARX 在工资三个预测期为正，却在耐用品三个预测期均为负。样本很小，不能据此确认或否定稳定迁移能力。

因此，报告可选择循环信贷等正向结果作为“下游用途的初步线索”，但必须同时链接完整 408 行对照，并披露比较数量、负向结果和强基线；目前不支持“模拟普遍提高宏观预测能力”或因果性表述。

### 复算与验证

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -m pytest \
  tests/test_sce_downstream_regression.py -q

/Users/wushuyue/anaconda3/envs/socioverse/bin/python \
  scripts/analyze_sce_downstream_regression.py \
  --panel outputs/sce_downstream_data_20261026_v1/derived/monthly_panel.csv \
  --a outputs/sce_full_a_macro_calibration_20261026_v1/monthly_predictions_public.csv \
  --b outputs/sce_recent_b_core_normal_evaluation_20261026_v1/monthly_national.csv \
  --protocol docs/workstreams/20261026_downstream/regression_protocol.json \
  --out outputs/<新的回归输出目录>
```

9 项定向测试通过；真实输出另经有限值、逐月八模型配对、B 训练数恒定、4 个代表原点独立 OLS 和 192 组指标复算检查。完整命令在临时新目录重跑后，除含时间戳的 `manifest.json` 外，11 个交付文件逐字节一致。

2026-10-27 全套测试限制：`pytest tests -q` 在收集阶段因 `tests/test_sce_core_normal.py` 无法从 `scripts.expand_sce_core_normal` 导入 `validate_packages` 而中断。排除该文件后运行其余测试，结果为 **1686 passed、1 failed、10 errors、12 subtests passed**；失败来自既有 CPI 组件提取与环境构建：`test_extract_cpi_components.py` 仅提取 444/490 个组件值，`test_build_sce_environment_v2.py` 的 10 个错误均由缺少 `cpi_food_yoy` 引起。这些不涉及本次新增下游回归模块，本任务未修改对应实现。
