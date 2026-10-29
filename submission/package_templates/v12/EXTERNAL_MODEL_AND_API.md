# 自备Key复现：外部模型与完整链路

本项目为本地开发的study适配器，真实生成使用DeepSeek V3.2，调用OpenRouter，固定SiliconFlow FP8，不要求MCP单选问卷接口。问卷输出契约为 `point_pct` 加 `q9.bin1` 至 `q9.bin10`，概率为0–100单位；非负且正总和的概率按原规则归一化。温度0.5、JSON、关闭思考、最多1024输出token，参数与完整Prompt均在包内。

作者不提供Key。评审在当前终端设置自己的 `OPENROUTER_API_KEY`，仅显式付费命令读取该环境变量；不会从作者 `.env` 或官方宿主目录寻找密钥。默认复算和通路检查0API。

**当前完整流程入口为包根 [PORTABLE_REPRODUCTION.md](PORTABLE_REPRODUCTION.md)。**其中包含独立工作区安装、公开源/P/E与新闻匹配重建、A/B批量生成、月度/周度真实状态递推、技术修复、断点恢复、独立评价和下游重估。

`simulation/reviewer_request.py`仍保留，供快速预览/重询任意一份封存的条件输入；它只运行一个条件，不替代新批次和新递推链。需要完整实验请选择 `simulation/reviewer_pipeline.py`。

原始模型回复和服务端request ID/时间/usage在 `reproduction_data/portable/evidence/`；公开源快照、编码映射、候选新闻与标签也提供。无须联系作者恢复某个日期、身份编号或隐藏参数。
