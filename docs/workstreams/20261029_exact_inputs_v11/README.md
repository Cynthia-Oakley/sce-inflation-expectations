# v11：完整保留原始消息和公开调查派生日期

2026-10-29。作者指出A的作答日期来自公开SCE资料，额外遮蔽会影响评委方便复现；本版撤销这一额外日期遮蔽。**没有改变原实验的信息截止、抽样、模型配置或科研结果。**

## 交付内容

四个最终任务共66,822个请求位置均提供完整原始messages：A41,970、B5,632、月度5,120、周度14,100。日期、人口、先验、选中新闻、价格、政策和问卷均按实际输入保留；所有消息哈希与原运行一致。日期/新闻占位槽均为0。prompt_templates文件名仅为兼容旧入口保留，其内容也完整，不是待填的模板。

原始受访者ID、身份/供体对应表、API Key仍不提供；匿名家庭键沿用已有答卷层。输入中的公开调查派生日期属于实际实验条件，按作者指示保留。不要再把旧版“日期待恢复”当作当前使用前提。

新闻ZIP仍仅供赛事保密评审，不进入GitHub；代码、文档、报告和视频的私有备份与新闻数据层分开。v10及更早包保留，唯一提交指针以[交付入口](../../../deliverables/README.md)及submission/latest_package.json为准。

## 评委操作

安装包根锁定依赖后，默认复算：

```sh
python studies/sce_inflation_expectations/run.py --mode all
```

列出A某月的完整样本，不读取Key、不联网：

```sh
python studies/sce_inflation_expectations/simulation/reviewer_request.py --candidate-dir studies/sce_inflation_expectations/reproduction_data/inputs --list --run A --period 201901 --limit 5
```

复制一个household键，去掉list/limit参数并增加household键即可预览；配置自己的OPENROUTER_API_KEY，再显式增加confirm-paid与全新out目录才发送一次。默认无参数预览也是一份完整A输入。无需向作者索取日期、身份映射或Key。

新生成保留给定历史前态这一条件；新的自主递推须由本次新前态重渲染下期，这是科学定义，与任何缺失日期无关。历史答卷和密度/误差可完全离线复算，本轮未新增真实模型请求。

## 验收与保留

输入全量检查见[input_acceptance_public.json](input_acceptance_public.json)，新ZIP独立验收见[v11_acceptance_public.json](v11_acceptance_public.json)。20份既有数值/答卷gz或CSV与v10逐字节一致，论文PDF与视频原件未改。原始A消息不是重新拼接或合成日期，是从冻结文件原样投影。

构建入口新增v11 profile，使用outputs/sce_submission_inputs_exact_20261029_v1；该新投影只用于保密包，不进入GitHub。先前文档措辞同步前的通过版本另存research_package/_build_history/v11_scope_wording_before_final；最终选包只看交付入口。
