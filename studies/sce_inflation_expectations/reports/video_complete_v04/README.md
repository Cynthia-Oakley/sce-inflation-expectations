# 视频末页修订 v04

以作者手改的完整v03 PPT和独立发言稿为基底，仅重做第9页。最新输出在`deliverables/video/v04/`。研究结果、原v03、论文与研究包不回写。

`prepare.py`快照作者源件和封存证据，`build.mjs`用Artifact Tool创建第9页的三幅可编辑图，再经`replace_slide9.py`接回原9页PPT。前8页的原生幻灯片和备注字节不变，原图表的标签、坐标、数值缓存、嵌入工作簿保留。WPS的无效分组枚举与标题单元格公式只作不改变外观的兼容修复。

`render_copy.py`只对私有PNG渲染副本处理WPS标签继承，避免预览引擎把数值和百分数重复画出，不写回正式PPT。`publish.py`生成本地预览与操作单，`verify.py`核对源件保护和数值，`test_browser.py`检查本地浏览器预览。预览中第4/5页的交互链接按作者PPT现有顺序对齐，原有24样本交互文件不变。

本机制作流程（项目根）：

```bash
PY=/Users/wushuyue/anaconda3/envs/socioverse/bin/python
NODE=/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node
$PY studies/sce_inflation_expectations/reports/video_complete_v04/prepare.py
cp studies/sce_inflation_expectations/reports/video_complete_v04/build.mjs tmp/video_complete_v04/build.mjs
$NODE tmp/video_complete_v04/build.mjs
$PY studies/sce_inflation_expectations/reports/video_complete_v04/publish.py
$PY studies/sce_inflation_expectations/reports/video_complete_v04/test_browser.py
$PY studies/sce_inflation_expectations/reports/video_complete_v04/verify.py
```

新一轮作者手改后须重新快照并审查，不用旧构建器覆盖。私人源件、映射和验收在`tmp/video_complete_v04/`，本地演示节选不自动加入公开Git或研究包。全流程0新增模型调用、0新增研究拟合。
