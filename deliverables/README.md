# 当前交付入口

当前正式研究包为 **v10**，含实际人口、先验、环境/选中新闻和完整Prompt样本。论文为作者定稿v1.0 PDF，视频为作者确认成片；三者独立编号。旧v09及更早包保留，不从outputs或_build_history挑选提交文件。

## 三个提交文件

上传副本集中在[提交材料](提交材料/)，与以下原件逐字节一致：

- **研究包 ZIP：**[SCE_research_package_draft_v10.zip](research_package/v10/SCE_research_package_draft_v10.zip)，206,059,457字节，约206 MB，低于2 GB。
- **论文 PDF：**[SCE研究报告_v1.0.pdf](report/SCE研究报告_v1.0.pdf)，8页、已确认署名与版式；[Word存档](report/SCE研究报告_v1.0.docx)。
- **视频 MP4：**[SCE_demo_v01.mp4](video/recordings/exports/assembled_v01/SCE_demo_v01.mp4)，4分27.9秒。[GitHub备份副本](video/final/SCE_demo_v1.0.mp4)与之完全相同。

指纹见[FINAL_FILES.json](FINAL_FILES.json)及[CHECKSUMS.sha256](CHECKSUMS.sha256)。由作者上传并保存回执，本机封包和GitHub备份不等于已提交赛事。文件按“赛道A：历史重建与未来预测／水上挽月”命名，平台若另有字段要求再核对外部文件名。

**研究包仅供赛事保密评审。**其中的NYT选中新闻摘录保留来源与第三方权利说明，不声明已获公开再分发许可，也不推送GitHub。GitHub同步代码、文档、作者确认的报告和视频，仓库保持私有；未来公开前应另审数据及历史记录。

## v10补齐了什么

- 66,822个实际输入位置：A41,970、B5,632、月度5,120、周度14,100；提供模型所见人口、合成属性、先验、价格、政策、问卷和选中新闻摘录。
- 24,852份B/月度/周度Prompt完整原样提供，可与67,147条既有模型回复连接。A保留选中新闻，遮蔽能推回真实完成日的日期；原始ID、身份/供体映射和Key均不提供。
- 新增默认离线的完整输入预览，以及显式使用评委自己Key的一次条件生成入口；不冒称一键重建全部A历史或新的自主递推链。
- 旧答卷与主要数值不变；20份既有数值/答卷gz或CSV文件与v09逐字节一致。新ZIP独立解压后76项测试、163模块隔离导入、工程/聚合/逐答卷复算通过，0新模型调用。

具体输入范围、版权说明和源指纹见[输入导读](research_package/v10/package/studies/sce_inflation_expectations/reproduction_data/inputs/README.md)、[新闻评审范围](research_package/v10/package/studies/sce_inflation_expectations/reproduction_data/inputs/NEWS_REVIEW_NOTICE.md)及[本轮记录](../docs/workstreams/20261029_input_package_v10/README.md)。原新闻库、未选文章、所有开发试验原文不在此新增范围。

## 作者本机审查

- [新版图文目录与运行预览](本地复现预览/v10/index.html)：实际新ZIP解压副本，含README、目录与真实答卷。
- [运行复现.command](本地复现预览/v10/运行复现.command)：每次另写结果目录，0API。
- [实际复算结果](本地复现预览/v10/verified_results/index.html)、[验收记录](research_package/v10/verification/acceptance.json)。隔离环境为本机既有无system-site-packages venv，本轮未重新安装。
- [解压包README](research_package/v10/package/README.md)、[目录导航](research_package/v10/package/DIRECTORY_GUIDE.md)、[自备Key说明](research_package/v10/package/EXTERNAL_MODEL_AND_API.md)。

本地预览目录不额外上传，旧v09预览仍保留。论文与视频原件不因新增输入层而改变。

## 评委从ZIP运行

解压并安装requirements.lock.txt后，在包根执行：

```sh
python studies/sce_inflation_expectations/run.py --mode all
```

默认禁止Python网络连接，不需要Key，运行20户两步工程例、聚合与正式逐答卷复算。只做答卷用--mode micro；--refit-density重新运行数值密度拟合，不调用LLM。

预览一份完整实际输入：

```sh
python studies/sce_inflation_expectations/simulation/reviewer_request.py --candidate-dir studies/sce_inflation_expectations/reproduction_data/inputs
```

同样默认0API。自行配置OPENROUTER_API_KEY后，显式加--confirm-paid和新的--out目录才发送一次。支持指定run、period、household；有日期缺口的A模板拒绝发送。固定供应商、无自动重试/回退，保守预留不超过$0.01，不是服务端美元硬限额；未来服务可用性和随机答案不保证相同。后月/后周的封存前态只支持条件单步，不是新链。详包根EXTERNAL_MODEL_AND_API.md。

## 本地重建

构建需要作者数据完整工作区。使用新目录，不能只给旧ZIP改名：

```sh
SCE_PYTHON='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
SCE_PACKAGE_OUT="deliverables/research_package/v10_rebuild_$(date +%Y%m%dT%H%M%S)"
"$SCE_PYTHON" scripts/build_sce_research_package.py --draft-version v10 --out "$SCE_PACKAGE_OUT" --public-log-registry outputs/sce_submission_experiment_logs_20261027_v4/experiment_registry_public.json --a-refresh-readout outputs/sce_full_a_t0_readout_20261026_v1 --micro-data outputs/sce_micro_reproduction_20261029_v3/data --input-data outputs/sce_submission_inputs_confidential_20261029_v1
"$SCE_PYTHON" scripts/verify_sce_research_package.py --archive "$SCE_PACKAGE_OUT/SCE_research_package_draft_v10.zip" --out "$SCE_PACKAGE_OUT/verification"
```

唯一机器指针为[submission/latest_package.json](../submission/latest_package.json)。新版仅补输入和复现能力，没有重新生成科研答卷、重拟组合或修改论文指标。
