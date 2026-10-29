# 研究包怎么读、怎么在本机复现

2026-10-29。对应正式研究包v09；本轮从“提交材料”中的实际上传ZIP新解压并运行，原ZIP、论文和视频均未改，0次新增模型调用。

## 先理解两个层级

官方的study是一项研究的工作单元：一个研究问题，对应`studies/<study_id>/`目录，人口P、环境E、运行、轨迹、报告按规范归类。本项目只有一个study，名称为`sce_inflation_expectations`。[官方说明](https://socioverse.fudan-disc.com/docs/zh/concepts/study-anatomy/)

研究包ZIP是交付容器。它包住这个study，并在外层补安装依赖、复现导航、来源/隔离声明、测试和实验索引。它不是整个开发仓库，也不需要把官方SocioVerse整仓复制进去；平台由锁定的依赖提供。

## 压缩包里的主要结构

```text
ZIP解压后的包根/
├── README.md                   安装、默认复现命令
├── requirements.lock.txt       依赖版本
├── DIRECTORY_GUIDE.md          目录导航
├── REPRODUCIBILITY.md          种子、调用、成本、真值隔离
├── EXTERNAL_MODEL_AND_API.md   外部模型、自备Key、再生成条件
├── DATA_RELEASE_POLICY.json    允许提供的数据范围
├── TRUTH_ISOLATION_EVIDENCE.json  真值取得与隔离凭据
├── PACKAGE_MANIFEST.json       文件内容哈希清单
├── tests/                     包内验收测试
├── experiment_logs/           公开实验索引
├── archive/                   可选历史源码，默认不导入
└── studies/
    └── sce_inflation_expectations/
        ├── study.yaml         标准study元信息与工程例装配
        ├── model.py / run.py   模型注册与统一运行入口
        ├── population/        人口说明与工程示例
        ├── environment/       环境说明与工程示例
        ├── simulation/        工程配置、正式运行配置登记
        ├── grounding/         事实、来源与假设
        ├── trajectory/        轨迹说明；运行结果另存
        ├── reports/           结果导读、论文口径和图片
        ├── reproduction_data/ 正式运行答卷与评价材料
        │   └── micro/         模型原文、有效字段、计分、Normal
        ├── components/        可复用人口、环境、行为组件
        ├── experiments/       各任务准备/运行流程
        ├── runtime/           执行与供应商适配
        ├── scoring/           Q9连续密度计分
        ├── evaluation/        误差与条件分布指标
        ├── submission_tools/  复现工具
        └── examples/          与正式结果分开的工程示例
```

实际ZIP共有251个文件，study根只有7个文件，其余分目录。872份原始开发源码封存在archive的补充ZIP，评委不用解开该归档才能运行默认入口。

## 必须区分的两套资料

标准population/environment/simulation中的20户两步例子检验官方Core接口，不能当成正式研究的人数。四个正式任务登记在`simulation/research_runs.json`，真实模型回复和有效答卷保存在`reproduction_data/micro/`。默认all会同时运行工程例和正式答卷复算，结果分开标识。

micro里含67,147条模型输出记录、67,334个有效状态、A配对/全波次评价参考、密度缓存、Normal后验材料。有效状态包含根月复用，不能当作新增API次数。模型原文与有效答卷通过匿名response_id逐字段关联；归一化、失败和补跑没有被隐藏。

## 评委怎样运行

在包含README.md和requirements.lock.txt的解压包根，用Python 3.11+：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python studies/sce_inflation_expectations/run.py --mode all
```

第一次安装依赖需要网络。之后默认入口不需要Key，禁止Python网络连接，0模型调用；每次在新目录写结果。终端打印Results路径，打开其中index.html。

默认顺序是文件哈希校验→20户两步工程例→全国/组合/下游误差复算→正式答卷计分、A微观指标与Normal重建。仅答卷使用`--mode micro`；加`--refit-density`可重跑数值密度拟合，不调用模型。下游阶段重算封存预测的误差，不重新拟合回归。

## 你的电脑已经可以看

- [本机图文导览](../../../deliverables/本地复现预览/v09/index.html)：目录可以展开，README可以切换阅读，还能看一份真实脱敏答卷。
- [本次新解压的完整包](../../../deliverables/本地复现预览/v09/isolated_package/)：来自实际上传ZIP，文件哈希相符。
- [本次实际复算结果](../../../deliverables/本地复现预览/v09/verified_results/index.html)。
- [再次运行.command](../../../deliverables/本地复现预览/v09/运行复现.command)：本机快捷入口，每次另存manual_results/新目录，不改正式上传文件。

本次复用已有、无system-site-packages的隔离Python，不是今天重新联网安装依赖。实际验收：250个清单文件（另加清单自身共251）、159个study模块从新解压包导入、72测试通过，聚合/逐答卷复算通过；本次0API。结果与当前v09正式验收一致。

预览目录是本机查看和练习副本，不作为第四项提交材料。正式提交仍选deliverables/提交材料中的PDF、ZIP、MP4。新的付费生成需要自己的Key及合法完整输入，当前ZIP不自动恢复历史新闻和个人匹配，见包根外部API说明。
