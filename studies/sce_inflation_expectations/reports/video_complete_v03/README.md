# 完整视频录制稿 v03 的制作入口

本模块只整理冻结证据、编辑演示材料，不启动模拟或重新选择研究参数。交付在`deliverables/video/v03/`，独立发言稿与录制操作单分开；真实样本交互沿用`samples_v02`。所有本地交付及私有中间数据均被排除自动Git收集。

## 输入与职责

- `prepare.py`：核对旧文件与冻结证据，汇总A/B、周度CSV和2021-06抽样权重，生成本地数据与独立口播稿。
- `storyboard.json`：9页内容、旁白、停留时间和操作的唯一文字源。
- `build.mjs`：Artifact Tool合并原样页并新增6页，保留原生文字和图表，运行封包/布局检查，渲染9张PNG。
- `preserve_sample_charts.py`：恢复已验收样页的4个真实图表及嵌入工作簿，避免导入丢失编辑数据。只改新构建副本。
- `publish.py`：生成可本地打开的9页预览、独立录制操作单与说明。
- `test_browser.py`：通过本机浏览器桥检查翻页、旁白、交互链接和16:9录屏画面。
- `verify.py`：验证证据来源、旁白/PPT对应、原图表与工作簿、原文件保护和最终文件哈希。

私有工作区为`tmp/video_complete_v03/`。制作时发现WPS重新保存了原样页：最新正文和布局保留，已验收图表使用最初封存的对应版本。源文件不回写；无效OOXML枚举和图表标题公式只在私人导入副本作兼容修复，留有机器收据。

## 本机复建

以下命令从项目根运行，依赖已存在的样页、封存研究包及私有汇总资料。`SCE_KAITI_FONT`可指定本地楷体字体；默认引用先前报告所用的完整Kaiti SC文件，仅用于渲染，不打包字体。

```bash
PY=/Users/wushuyue/anaconda3/envs/socioverse/bin/python
NODE=/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node
$PY studies/sce_inflation_expectations/reports/video_complete_v03/prepare.py
cp studies/sce_inflation_expectations/reports/video_complete_v03/build.mjs tmp/video_complete_v03/build.mjs
$NODE tmp/video_complete_v03/build.mjs
$PY studies/sce_inflation_expectations/reports/video_complete_v03/publish.py
$PY studies/sce_inflation_expectations/reports/video_complete_v03/test_browser.py
$PY studies/sce_inflation_expectations/reports/video_complete_v03/verify.py
```

这些是制作命令，不是评委复现研究的入口。研究复现仍通过正式研究包的`run.py`。

作者手动修改完整PPT之后，须以手改稿为基础继续编辑，不运行旧构建器覆盖。原报告、原方法图与研究包保持独立。
