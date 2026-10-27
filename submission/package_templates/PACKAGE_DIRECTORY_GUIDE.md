# 给评委的目录导航

## 最短阅读顺序

1. **包根README.md**：研究对象、安装、一命令、结果和限制。
2. **执行study/run.py**：真实跑一次0API流程，打开命令打印的index.html。
3. **study/reports/REVIEW_GUIDE.md**：核查为什么采用这些机制、时间/权重/基线是否成立。
4. **SOURCE_INDEX.json**：若需审查实现，按研究组找到源码；无需从全部文件顺序阅读。

## 标准study区域

`studies/sce_inflation_expectations/`：

- `study.yaml / resources.json`：装配元信息；默认是工程示例，主研究另列配置引用。
- `population/`：20个人工合成示例，不包含真实SCE行。
- `environment/`：短公共价格/合成示例，不包含新闻全文。
- `simulation/`：示例运行、主研究参数摘要及seed_policy；种子不保证服务端逐字重现。
- `trajectory/`：工程轨迹落库说明；真实主批本地JSONL未伪装为官方DuckDB。
- `reports/`：方法、图表、论文/视频计划；真正PDF和MP4另交。
- `run.py / README.md / FILE_GUIDE.md`：运行入口、study说明、算法定位。

## 为复现增加的支撑区域

- `reproduction_data/`（在study内）：合法范围内的全国/周度聚合、宏观预测及期望值；没有个人问卷。默认replay读取。
- `experiments/ / evaluation/ / scoring/ / submission_tools/`：当前研究、公共统计与复算代码，按原路径保持可导入。官方列出的目录是骨架，并不意味着真实项目只能有那几个子目录。
- `scripts/`（包根）：明确保留的当前CLI包装器；多数需要受控输入才能真实执行。优先用study/run.py，避免误触付费入口。
- `experiment_logs/`：22项选定实验，聚合运行/费用，非全部项目发票。
- `tests/`：本包相关测试，非全仓库全套。

## 按需查阅的归档

`archive/research_source_supplement.zip` 保存主线依赖之外的专题、历史实验和开发辅助Python源码；`archive/SOURCE_INDEX.json`保存原路径和SHA。

**默认不用解压。**它们不是被判定全部失效，而是从主阅读路线中移开。原开发仓库继续保留原路径；如需复查历史，在独立工作副本解压并恢复合法输入，不要覆盖当前study。

旧论文/汇报稿、个人数据、原始轨迹和新闻文本不进入主包；旧报告索引在开发仓库中保留。包根的许可证/真值/官方要求等JSON是机器核查材料，不要求初读时逐份阅读。

## 不要混淆

- **开发目录**：长期维护和历史兼容，文件多，不能直接压缩当研究包。
- **提交主包**：当前入口与依赖、最小合成示例、可复算聚合和导读。
- **补充源码档**：可审计研究过程，默认不参与执行。
- **受控本地资料**：个人记录、原新闻、完整回包等，依据许可另行恢复，不自动发送。
