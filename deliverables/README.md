# 当前交付入口

这里集中放供作者审查、最终提交的导出物；`outputs/`继续保存实验历史，不再作为交付入口。

## 研究包 v05

- [未压缩完整包](research_package/v05/package/README.md)：从这里阅读和运行。
- [对应ZIP](research_package/v05/SCE_research_package_draft_v05.zip)：约4.18MB，与未压缩包逐文件一致。
- [目录导航](research_package/v05/package/DIRECTORY_GUIDE.md)：标准study、组件、例子和归档的职责。
- [独立验收](research_package/v05/verification/acceptance.json)与[实际复算结果](research_package/v05/verification/results/index.html)。
- [SHA256](research_package/v05/CHECKSUMS.sha256)：防止误选、错传或传输后文件变化。

唯一机器指针是[submission/latest_package.json](../submission/latest_package.json)。旧v04及此前打包、实验原件保留在历史目录，**不作为本轮提交候选**。包版本与论文草稿版本各自编号，不能只凭“v05”混选文件。

本版已完成源码按职责归位、标准工件补齐、示例/正式配置分离和新环境0API验收。完整受控微观复现、最终4—8页PDF、视频及提交回执仍待收尾；这不是宣称全部赛事门槛已通过。

## 生成规则

此处研究包是白名单构建产物，不在Git中重复维护源码。在主项目根目录执行以下完整命令，可按**现有v05配置**生成一个新目录；不覆盖当前候选，也不会自动切换latest指针：

```bash
SCE_PYTHON='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
SCE_PACKAGE_OUT="deliverables/research_package/v05_rebuild_$(date +%Y%m%dT%H%M%S)"
"$SCE_PYTHON" scripts/build_sce_research_package.py \
  --draft-version v05 \
  --out "$SCE_PACKAGE_OUT" \
  --public-log-registry outputs/sce_submission_experiment_logs_20261027_v4/experiment_registry_public.json \
  --a-refresh-readout outputs/sce_full_a_t0_readout_20261026_v1
```

`--out`和`--public-log-registry`是必填参数；`--a-refresh-readout`在程序中可选，但本项目当前交付应保留它，才能纳入新版A T0的独立聚合复算输入。上述本地来源必须存在；命令不会下载原始数据或调用API。它构建的是工作区当时的内容，并非保证逐字节重现旧ZIP。

重建后先独立解压验收，再决定是否更新指针。例如同一终端继续执行：

```bash
"$SCE_PYTHON" scripts/verify_sce_research_package.py \
  --archive "$SCE_PACKAGE_OUT/SCE_research_package_draft_v05.zip" \
  --out "$SCE_PACKAGE_OUT/verification"
```

这条命令执行隔离解压检查；最终交付还须在新装、无系统site-packages的独立环境中加`--fresh-environment`验收。不得覆盖旧版或手动修改封包后沿用原验收。

**下一正式版本不能只改目录名。**当前CLI及构建器仅支持v01—v05，包内v05模板也带版本声明。新v06必须先新增相应构建配置、模板和验证支持，完成检查后再封包；论文v06与研究包v06仍是独立版本。
