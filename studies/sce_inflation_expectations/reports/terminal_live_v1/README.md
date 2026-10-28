# Terminal真实单户演示

目标是视频第7页的一次实际模型回答，不用规则工程例冒充真实生成。输入沿用已确认的A01案例，Prompt与正式A T0运行的原始消息逐字节一致；不会读入旧回答或当前目标真值作为新请求。

准备入口：`python studies/sce_inflation_expectations/reports/terminal_live_v1/demo.py prepare`。默认生成私人忽略目录 `deliverables/video/terminal_live_v01/`。`preview.command`只显示输入，0API；`record_live.command`逐阶段展示后，要求人类输入RUN，明确允许这1个OpenRouter→SiliconFlow FP8 DeepSeek V3.2请求与$0.01上限，之后才读取凭据和发出请求。

沿用温度0.5、JSON模式、关闭思考、最多1024输出token和已有价格上限。输入及执行器哈希冻结；新调用不自动重试、不切供应商。先持久化请求意图，再调用API；重复运行、未知在途或中途失败不再自动发送。回复按API实际流式分块打印，原始事件、部分文本、完整文本、Q9比例归一化视图和计费收据分别保存。默认不对原始回复做键名修补。

准备阶段读取已物化的SCE人口、既有信念及匹配环境，不现场下载新闻或重新抽样。运行前核对所有入选新闻、食品价格的公开时间和实际Prompt。终端显示中文字段和提问摘要，完整原英文Prompt进入API并私下归档。单户不计算全国MAE，也不并入正式研究结果。

支持离线技术验收：`python -m pytest tests/test_sce_terminal_live_demo.py -q`。覆盖中途断流、错误模型／供应商、缺元数据、截断、费用、归一化原文保留、重复执行及未来信息。没有真实API验跑前只能称离线通过，不能称真实模型流式调用已经通过。

接口依据：[OpenRouter流式说明](https://openrouter.ai/docs/api/reference/streaming)、[用量计费说明](https://openrouter.ai/docs/use-cases/usage-accounting)。最终用量帧不一定有正文；身份缺失不推定为已核验。所有流式参数只作用于本演示，不改正式研究执行器。
