# 当前交付入口

当前研究包为 **v06**。导出物集中在这里；outputs保存开发和实验原件，不作为选包入口。论文、视频与研究包分别编号，不凭相同版本号混选文件。

## 研究包 v06

- [完整解压包](research_package/v06/package/README.md)
- [对应ZIP](research_package/v06/SCE_research_package_draft_v06.zip)，约39MB。
- [目录导航](research_package/v06/package/DIRECTORY_GUIDE.md)
- [模型原文、答卷与微观资料导读](research_package/v06/package/studies/sce_inflation_expectations/reproduction_data/micro/MICRO_DATA_GUIDE.md)
- [独立ZIP验收](research_package/v06/verification/acceptance.json)、[实际复算](research_package/v06/verification/verified_results/index.html)、[密度重拟合验收](research_package/v06/density_refit_acceptance.json)
- [SHA256](research_package/v06/CHECKSUMS.sha256)

v06补入四个最终任务的模型输出、有效答卷、A最小配对/全波次评价层，以及A/B Normal后验重算。不是只从全国月度表重新求MAE，也不重新调用LLM。范围和边界见[本轮说明](../docs/workstreams/20261029_micro_reproduction/README.md)。

唯一机器指针是[submission/latest_package.json](../submission/latest_package.json)。旧[v05](research_package/v05/package/README.md)保留为历史，不作为最新候选。_build_history是构建审查快照，不是提交目录。

## 评委从ZIP运行

在解压包根安装requirements.lock.txt，然后执行：

```sh
python studies/sce_inflation_expectations/run.py --mode all
```

默认0API，分别运行20人两步工程例、聚合复算、正式答卷微观复算。只重算微观用--mode micro；加--refit-density重跑冻结数值拟合器，仍不调用LLM。输出到新目录，打开其中的index.html。

## 从本地开发工作区重建

在主项目根执行完整命令；必须使用新的输出目录：

```sh
SCE_PYTHON='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
SCE_PACKAGE_OUT="deliverables/research_package/v06_rebuild_$(date +%Y%m%dT%H%M%S)"
"$SCE_PYTHON" scripts/build_sce_research_package.py --draft-version v06 --out "$SCE_PACKAGE_OUT" --public-log-registry outputs/sce_submission_experiment_logs_20261027_v4/experiment_registry_public.json --a-refresh-readout outputs/sce_full_a_t0_readout_20261026_v1 --micro-data outputs/sce_micro_reproduction_20261029_v3/data
"$SCE_PYTHON" scripts/verify_sce_research_package.py --archive "$SCE_PACKAGE_OUT/SCE_research_package_draft_v06.zip" --out "$SCE_PACKAGE_OUT/verification"
```

微观投影尚不存在时，先运行scripts/export_sce_micro_reproduction.py --out <新的outputs目录>，再把对应data子目录传给--micro-data。它依赖原始账本与合法来源，不是从有限ZIP恢复全部生成输入；会产生本地数值拟合工作，但不调用模型。

v06是新增的构建配置、模板和验证入口，不是改名旧ZIP。默认复算独立于开发路径；付费新生成仍需恢复合法输入并明确授权。

## 论文、视频与剩余交付

- 当前Word：[v10作者审阅稿](../docs/reports/final_report_draft_v10/SCE研究报告_作者审阅稿_v10.docx)，最终4—8页清洁PDF待导出。
- 作者确认的视频：[完整MP4](video/recordings/exports/assembled_v01/SCE_demo_v01.mp4)，4分27.9秒。
- 最后需统一PDF/ZIP/MP4、费用和署名/文件名，用户审阅上传并保存回执。没有代上传或公开GitHub。
