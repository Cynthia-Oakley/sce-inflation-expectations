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

此处研究包是白名单构建产物，不在Git中重复维护源码。重建入口为`scripts/build_sce_research_package.py --draft-version v05`，允许输出到新的`deliverables/research_package/<版本>/`；必须独立解压验收通过后再更新latest指针。不得覆盖旧版或手动修改封包后假装仍通过原验收。
