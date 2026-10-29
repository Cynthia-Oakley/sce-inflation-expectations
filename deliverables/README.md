# 当前交付入口

当前研究包为 **v09**，由交付前口径审查及官方六项要求对账生成。论文为作者定稿v1.0 PDF，视频为已确认成片；三者各自编号。旧v08/v07/v06及开发outputs不作为当前选包入口。

## 提交文件

**三个上传副本已汇集在[提交材料](提交材料/)目录**，与下列验收原件的SHA256完全相同。按作者确认的“赛道A：历史重建与未来预测”命名；若平台另要求子赛道字段，按实际选项调整外部文件名。

- **研究包 ZIP：**[SCE_research_package_draft_v09.zip](research_package/v09/SCE_research_package_draft_v09.zip)，约39MB。
- **视频 MP4：**[SCE_demo_v01.mp4](video/recordings/exports/assembled_v01/SCE_demo_v01.mp4)，4分27.9秒，作者已确认。
- **论文 PDF：**[SCE研究报告_v1.0.pdf](report/SCE研究报告_v1.0.pdf)，8页、约1.85MB；署名、批注排除、字体和图表已核验。[Word存档](report/SCE研究报告_v1.0.docx)与[验收记录](report/acceptance.json)保留。

三件材料已齐。最终路径/字节/SHA256见[FINAL_FILES.json](FINAL_FILES.json)，校验见[CHECKSUMS.sha256](CHECKSUMS.sha256)。上传副本须按报名的赛道/子赛道/队伍命名，用户上传后保存回执；本轮未代上传或公开GitHub。论文第2–3页人口表首行有跨页拆词，可选美化，原PDF不改。

## 如何审查研究包

- **新增输入补齐核查（尚未装入v09）：**[完整Prompt与P/E候选、来源边界及自备Key入口](../docs/workstreams/20261029_input_release_review/README.md)。66,822份输入均已找到；1,343份无新增新闻摘录的周度原Prompt可完整提供，其余新闻/真实关联日期使用明确占位槽。候选与原答卷全部对接，0新API；当前正式ZIP及上传副本不变。
- **作者本机先看：**[图文目录与运行导览](本地复现预览/v09/index.html)，可展开实际ZIP目录、查看README和一份真实脱敏答卷；[实际复算结果](本地复现预览/v09/verified_results/index.html)。这是实际上传ZIP的新解压练习副本，不作为额外上传材料。
- **本机重复运行：**[运行复现.command](本地复现预览/v09/运行复现.command)，使用已安装Python，每次写新目录，0API；[关系与命令说明](../docs/workstreams/20261029_package_walkthrough/README.md)。正式ZIP、论文和视频不变。
- [解压包README](research_package/v09/package/README.md)、[目录导航](research_package/v09/package/DIRECTORY_GUIDE.md)。
- [论文数字口径对照](research_package/v09/package/studies/sce_inflation_expectations/reports/PAPER_METRIC_GUIDE.md)：区分描述组合/冻结组合、配对/全波次微观、Core/Normal和费用范围。
- [模型原文与微观资料导读](research_package/v09/package/studies/sce_inflation_expectations/reproduction_data/micro/MICRO_DATA_GUIDE.md)。
- [独立ZIP验收](research_package/v09/verification/acceptance.json)、[实际复算结果](research_package/v09/verification/verified_results/index.html)、[ZIP哈希](research_package/v09/CHECKSUMS.sha256)。

v09修正旧版仅聚合的残留说明，从逐答卷增加论文41,042共同支持及两种组合的核验；72项包内测试通过。八份微观冻结资料及原12个CSV与v06逐字节一致，研究结果和原始模型回答未改，新增API为0。既有32,500向量数值拟合验收沿相同数据保留，本次不重复拟合。

本轮v09仅集中补全提交声明、链接既有真值取得/隔离证据并修正恢复输入的旧措辞；28个冻结复现文件与v07逐字节一致。六项官方要求、仓库职责、Kimi复核重点与上传步骤见[提交对账清单](SUBMISSION_CHECKLIST.md)；评委可读[包内复现声明](research_package/v09/package/REPRODUCIBILITY.md)。

唯一机器指针是[submission/latest_package.json](../submission/latest_package.json)。_build_history仅为构建检查历史；v08/v07/v06保留但不选作最新提交。

外部模型、自备Key与Q8/Q9回答格式已纳入[包根专门说明](research_package/v09/package/EXTERNAL_MODEL_AND_API.md)，包根README开头直接提示。v09同时修正CLI帮助；72项包内测试和独立逐答卷复算通过，28个冻结复现文件与v08逐字节一致。完整历史再生成需要合法恢复输入，便携单户联网功能未宣称已实现。

## 评委从ZIP运行

在解压包根安装requirements.lock.txt，然后执行：

```sh
python studies/sce_inflation_expectations/run.py --mode all
```

默认0API，依次运行20人两步工程例、聚合复算和正式逐答卷复算。只重算微观使用--mode micro；增加--refit-density可重新运行冻结数值拟合器，不调用LLM。输出写入新目录，打开其中index.html。

## 本地重建

在项目根执行，必须使用新输出目录：

```sh
SCE_PYTHON='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
SCE_PACKAGE_OUT="deliverables/research_package/v09_rebuild_$(date +%Y%m%dT%H%M%S)"
"$SCE_PYTHON" scripts/build_sce_research_package.py --draft-version v09 --out "$SCE_PACKAGE_OUT" --public-log-registry outputs/sce_submission_experiment_logs_20261027_v4/experiment_registry_public.json --a-refresh-readout outputs/sce_full_a_t0_readout_20261026_v1 --micro-data outputs/sce_micro_reproduction_20261029_v3/data
"$SCE_PYTHON" scripts/verify_sce_research_package.py --archive "$SCE_PACKAGE_OUT/SCE_research_package_draft_v09.zip" --out "$SCE_PACKAGE_OUT/verification"
```

微观投影不存在时先用scripts/export_sce_micro_reproduction.py --out <新目录>，它需要原始授权工作区。包本身可离线重算提交范围，但不包含完整新闻/提示或重新询问模型所需的全部历史输入。
