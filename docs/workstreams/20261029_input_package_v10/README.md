# v10：正式研究包补齐实际输入

2026-10-29。作者要求把可分享P/E、完整Prompt样本和实际选中新闻纳入新版，新闻限定赛事保密评审；同时将代码、论文与视频同步到既有私有GitHub。本轮不调用模型、不更改科研参数或既有答卷。

## 本版新增什么

- 66,822个实际请求位置：A41,970、B5,632、月度5,120、周度14,100。人口画像、合成属性、先验、价格、政策、问卷及选中新闻均保留在脱敏Prompt与分块输入中。
- 24,852份完整B/月度/周度输入，原消息哈希与历史输入一致，可从micro/model_outputs按run、period、household与Prompt哈希连接。
- A41,970份保留完整选中新闻，遮蔽真实个人完成/截止日期；私人身份和供体映射、原始ID、Key均不提供。
- 便携单次入口默认0API预览，只有显式confirm-paid才使用评委自己的OpenRouter Key。可选择匿名完整样本，一次一请求、无自动重试或供应商回退；价格和token guard保留。未做新的真实联网调用。

新闻是当时实际放进Prompt的标题、摘要/片段与公开日期，不是整套原始NYT资料库或文章全文。版权和来源归原权利人；本ZIP仅按作者要求供赛事保密评审，未声称取得公开再分发许可。新闻数据不进入GitHub，私有仓库亦不上传含新闻的ZIP，以免未来公开时连带发布。

## 最终交付与验收

唯一入口为[deliverables/README.md](../../../deliverables/README.md)及submission/latest_package.json。v09原件和此前审阅候选保持原字节；最新v10单独构建，初次构建的CSV换行检查记录保存在research_package/_build_history/v10_line_ending_review，不选作提交件。

最终验收记录以[v10_acceptance_public.json](v10_acceptance_public.json)和[输入全量对接检查](input_acceptance_public.json)为准。独立解压包的默认all、全部包内测试、输入预览、数据哈希与研究主体AST检查通过后，才切换交付指针。既有20份数值/答卷gz或CSV文件与v09逐字节一致，主要误差不变；本轮新增模型调用0。

## 如何运行

在解压包根安装锁定依赖后：

```sh
python studies/sce_inflation_expectations/run.py --mode all
```

真实输入预览：

```sh
python studies/sce_inflation_expectations/simulation/reviewer_request.py --candidate-dir studies/sce_inflation_expectations/reproduction_data/inputs
```

默认仅打印完整输入与参数。自行配置OPENROUTER_API_KEY，再显式加confirm-paid与新的out目录才发一次；不是一键重建全部历史或新自主链。完整说明在包根EXTERNAL_MODEL_AND_API.md。A实际日期缺口仍需受控恢复或明确标注新条件；后月/后周须由本次新前态重渲染，不能把封存前态当新链。

## 构建记录

源码构建入口新增v10 profile和必填input-data。实际输入投影为outputs/sce_submission_inputs_confidential_20261029_v1，当前数据目录使用明确白名单；原始身份映射只在作者本机投影时读取，未装包。

```sh
python scripts/build_sce_research_package.py --draft-version v10 --out <新交付目录> --public-log-registry outputs/sce_submission_experiment_logs_20261027_v4/experiment_registry_public.json --a-refresh-readout outputs/sce_full_a_t0_readout_20261026_v1 --micro-data outputs/sce_micro_reproduction_20261029_v3/data --input-data outputs/sce_submission_inputs_confidential_20261029_v1
```

构建需要作者原始工作区；评委默认复算不需要它。GitHub只同步代码/说明及作者确认的PDF、Word和MP4，保持原私有状态与既有分支，不改变默认分支。上传赛事网站及保存回执仍由作者完成。
