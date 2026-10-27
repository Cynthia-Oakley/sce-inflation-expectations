# 最终研究包更新：本地开发、最新证据和复现边界

**本页为v03记录，原文件保留。**当前用于评审阅读的目录精简版已升级v04，见[目录整理与最新ZIP](../20261027_study_layout/README.md)；研究数据和复算结果完全一致。

2026-10-27。本轮依据用户要求重新获取官方规则，正文SHA-256仍为 `dce3d93a9ceab1377cf27a5d93d6b5f3fdebaaa70ee6154606339c2fc09bee53`。新核查见 `docs/sources/challenge_requirements_20261027.json`；旧ZIP、输入、回答、冻结程序与评价均保留，新增API调用0。

## 当前文件：先从这里看

- [研究包ZIP（约3.54MB）](../../../outputs/sce_research_package_20261027_v7/SCE_research_package_draft_v03.zip)
- [解压后README](../../../outputs/sce_research_package_20261027_v7/package/README.md)
- [本次实际复算结果](../../../outputs/sce_research_package_20261027_v7/clean_environment_acceptance/verified_results/index.html)
- [封存图表导览](../../../outputs/sce_research_package_20261027_v7/package/studies/sce_inflation_expectations/reports/index.html)
- [独立验收收据](acceptance.json) · [实验索引JSON](experiment_registry_public.json)
- [8页论文整合计划](../../../submission/package_templates/PAPER_INTEGRATION_PLAN.md) · [本地视频计划](../../../submission/package_templates/LOCAL_DEMO_PLAN.md)

## 交付内容

- **研究包v03**：标准 `studies/sce_inflation_expectations/`，默认0API，源码、P/E/simulation示例、trajectory说明、reports、run.py/README、锁定依赖与哈希。
- **评审可复算**：旧A82/旧B11/新A82、A Normal、最新B Core/Normal、月度自主10月主评、47周对应11月主评。固定组合精确关系核验；下游4,896个预测/192组误差/408配对对照全部入包。
- **微观边界**：可以重算82个月W1/IQR缓存摘要的平均值，不能宣称从个人答卷重算W1；完整个体生成与微观复现需合法恢复受控数据。本包不带原始调查、个体轨迹、新闻文本和密钥。
- **实验日志v4**：22项选定记录，实报API $96.119221356，未知预留$3.004863292，token估费$3.706222、未拆分$0.0414368分别列；不是全项目发票总额。Normal/下游为离线分析，不重复算LLM信息或费用。
- **论文与视频**：包内有8页论文整合及4分40秒本地视频计划，本轮不重写正式论文、不录制视频。视频按“问题→P/E/B→真实命令→结果→复现”组织，可用PPT/录屏混合；示例、缓存和真实生成分清。

## 运行和验证

从解压包根执行：

```bash
python studies/sce_inflation_expectations/run.py --mode all
```

无密钥官方Core示例20人两步，40规则决策/60面板行；其后真实聚合重算，默认网络阻断。输出目录为新建，不改输入。主研究真实生成来自本地冻结消息适配器，官方Core承担装配/离线验收，不能称整个付费主批由官方引擎在线执行。

本轮17项研究包定向测试及9项下游测试已通过；另在无系统site-packages的全新venv按固定依赖安装并独立解压，882项文件哈希一致，31个study模块全部来自包内，17项包内测试再次通过。初检发现并补齐pypdf与requests两项已有模块依赖，旧包保留；完整主仓库仍有已登记的既有失败，不称全套全绿。独立ZIP验收细节和最终ZIP路径见同目录 `acceptance.json`、固定指针 `submission/latest_package.json`。

## 未结束的收尾

1. 正式PDF整合最新B/Normal/递推/周度与信贷线索，按8页预算重排、逐图/逐页验收；v05仍是旧稿。
2. 录制并检查≤5分钟MP4，确认署名、文件命名和平台子赛道字段后由用户正式提交。
3. 完整微观复现的数据取得/许可/访问闭环、费用覆盖和来源版本仍需补齐；本机macOS/Python3.11全新环境已验收，不能自动推广到其他系统或替代微观闭环。
4. GitHub保持私有。赛事后公开前检查全部Git历史中的人口、答卷、密钥和新闻素材；本轮不改可见性、不重写历史、不上传3份本地真实人口资料改动。

新版本构建与独立验收脚本：`scripts/build_sce_research_package.py`、`scripts/verify_sce_research_package.py`。论文框架仍见 `docs/workstreams/20261027_final_delivery/`。当前不是已提交、完整微观认证或全项目费用核对完成声明。
