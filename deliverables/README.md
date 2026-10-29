# 当前交付入口

当前正式研究包为 **v12**：评审可从包内公开源资料重建输入，在自己的设备上使用自己的OpenRouter Key重新生成、递推和评价。论文v1.0与视频不变；旧v11及更早包保留。最终文件只从本页或FINAL_FILES.json选择。

## 三个提交文件

上传副本集中在[提交材料](提交材料/)，与下列原件逐字节一致：

- **研究包：**[SCE_research_package_draft_v12.zip](research_package/v12/SCE_research_package_draft_v12.zip)，大小与SHA256见[FINAL_FILES.json](FINAL_FILES.json)，低于2 GB。
- **论文：**[SCE研究报告_v1.0.pdf](report/SCE研究报告_v1.0.pdf)，8页；[Word存档](report/SCE研究报告_v1.0.docx)。
- **视频：**[SCE_demo_v01.mp4](video/recordings/exports/assembled_v01/SCE_demo_v01.mp4)，4分27.9秒；[GitHub副本](video/final/SCE_demo_v1.0.mp4)内容相同。

统一指纹见[CHECKSUMS.sha256](CHECKSUMS.sha256)，官方要求对账见[SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md)。本地封包和GitHub备份不等于已提交赛事，仍由作者上传并保存回执。

## 评委能够怎样复现

先读解压包根的[README](research_package/v12/package/README.md)和[完整自备Key指南](research_package/v12/package/PORTABLE_REPRODUCTION.md)。安装锁定依赖后，有两条并列路径：

1. **核对既有研究结果，0API。** `python studies/sce_inflation_expectations/run.py --mode all`，重算正式答卷、全国与微观指标和Normal；不需要Key。
2. **在自己的设备上重新生成。** `review.py install`安装独立原工程与源快照；`prepare`运行人口、先验、环境和新闻匹配；`workflow`自动接模型作答、月度/周度新回答递推、独立评价与完整样本的组合/下游重拟。显式设置自己的Key、范围、预算和`--confirm-paid`后才产生费用。

可先运行默认少量家庭/时期的通路检查；完整运行保留原名单与时期。新运行写新目录，网络暂错有界冷却、已知技术失败最多补一次，未知在途不重发；中断保留账本并显式`--resume`。无需编码Agent逐批参与。

## v12提供了什么

- 四条最终任务全部66,822份完整原样Prompt、67,147条原始回包记录、67,334个有效状态及主/补/复用关联。
- 原始公开SCE工作簿、匿名调查编号与日期、内部Agent/供体编码映射、人口和先验源、价格政策、候选新闻及分类标签、逐调用request ID/时间/usage/费用与来源哈希。316条无返回request ID的失败保持null。
- 公开源资料重建、四任务批量及新状态递推、新回答计分与Normal、原训练期组合/宏观模型重估、下游扩展窗口回归重估的命令。
- 原答卷、论文指标和研究方法不因封包改变。本轮不新增付费模型调用，也不以注入回答作为实证结果。

原始公开匿名编号和数据日期不再额外遮蔽；**API Key、账号密码、认证头和付款秘密始终排除**。公开原始工作簿可能在文件中含目标答案，但生成阶段只读取白名单人口字段与严格更早的信念，评价另开进程；不把源文件存在等同于目标答案进入Prompt。

## 作者本机查看与验收

- [图文目录与运行预览](本地复现预览/v12/index.html)：来自新ZIP的解压副本，含原文说明、真实答卷和复算结果。
- [运行复现.command](本地复现预览/v12/运行复现.command)：使用本机已有隔离Python，每次另写结果，0API。
- [独立ZIP验收](research_package/v12/verification/acceptance.json)与[便携全流程验收](../docs/workstreams/20261029_portable_reproduction/acceptance_public.json)：范围、证据和限制分列。
- [目录地图](research_package/v12/package/DIRECTORY_GUIDE.md)、[论文指标口径](research_package/v12/package/studies/sce_inflation_expectations/reports/PAPER_METRIC_GUIDE.md)。

ZIP默认复算验收使用已有隔离Python；随后在全新venv从公开PyPI安装14项锁定依赖，pip check、独立运行和SDK请求格式/解析检查均通过，[全新环境记录](../docs/workstreams/20261029_portable_reproduction/fresh_dependencies_acceptance.json)。付费API连通性没有在封包时新增调用验证。新LLM回答受温度与外部服务版本影响，不保证逐字相同或误差恰好等于论文。

## 作者重建研究包

此命令用于作者完整工作区重新封包；评委不需要作者的outputs目录，而应使用包内review.py。

```sh
SCE_PYTHON='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
SCE_PACKAGE_OUT="deliverables/research_package/v12_rebuild_$(date +%Y%m%dT%H%M%S)"
"$SCE_PYTHON" scripts/build_sce_research_package.py --draft-version v12 --out "$SCE_PACKAGE_OUT" --public-log-registry outputs/sce_submission_experiment_logs_20261027_v4/experiment_registry_public.json --a-refresh-readout outputs/sce_full_a_t0_readout_20261026_v1 --micro-data outputs/sce_micro_reproduction_20261029_v3/data --input-data outputs/sce_submission_inputs_exact_20261029_v1 --portable-data outputs/sce_portable_release_20261029_v2
"$SCE_PYTHON" scripts/verify_sce_research_package.py --archive "$SCE_PACKAGE_OUT/SCE_research_package_draft_v12.zip" --out "$SCE_PACKAGE_OUT/verification"
```

机器指针为[latest_package.json](../submission/latest_package.json)。压缩前目录为`research_package/v12/package/`，不要从outputs或_build_history选择提交文件。

## 分发与GitHub

**ZIP仅供赛事保密评审。**第三方新闻保留来源及权利说明，不声明取得公开再分发许可。原始微观/新闻、完整输入输出及ZIP不进入GitHub；代码、说明、汇总验收、作者确认的论文和视频备份到[既有私有工作分支](https://github.com/Cynthia-Oakley/socioverse-challenge-2026/tree/docs/deepseek-reuse-20261008)。未来公开仓库前须另审历史记录中的数据范围。
