# 视频讲解 v05：先说明设计，再展示实际运行

本模块只编辑展示层，不修改研究配置、模拟回答、论文或研究包。输出位于项目根的 `deliverables/video/v05/`，未自动上传真实问卷条件节选或录屏。

## 本次范围

- 输入：作者2026-10-28 13:45手动保存的v04 PPT。首次准备后固定快照哈希；源文件发生变化会拒绝静默重建。
- 原生保留第1—4页与第9页的文字、布局、备注、图表标签与数据缓存、工作簿。只替换第5—8页。
- 第5页补SCE、CE、ATUS、Gallup来源和条件信息证据；外部字段均为合成匹配，不能称作同一受访者的真实联合记录。54类不是PCA确定的唯一最优解。
- 环境设计另存HTML场景；已有24份真实样本交互按字节复制，原场景不改。
- 第8页以约512份直接答卷口径绘制93个月的真人、原始模拟、固定组合和持续性基线。沿用已冻结的前48月MSE权重，未重新拟合；全期组合含拟权期，后34月另列。微观W1/IQR只列历史同批答卷，不虚构组合或预测段微观指标。
- 视频装配顺序改为方法→人口→环境→作答设计→真实输入输出→信息对照→概率计算→执行→结果→拓展。PPT物理页码不变，作者38.5秒第2段保留。

## 本地重建

使用当前项目的Conda Python和已安装的演示文稿运行库：

```bash
python studies/sce_inflation_expectations/reports/video_complete_v05/prepare.py
cp studies/sce_inflation_expectations/reports/video_complete_v05/build.mjs tmp/video_complete_v05/build.mjs
node tmp/video_complete_v05/build.mjs
python studies/sce_inflation_expectations/reports/video_complete_v05/publish.py
python studies/sce_inflation_expectations/reports/video_complete_v05/test_browser.py
python studies/sce_inflation_expectations/reports/video_complete_v05/verify.py
```

Node应使用桌面应用的bundled runtime；`prepare.py`在私人tmp目录建立其node_modules链接。浏览器检查复用已连接的本地Kimi Browser Extension会话，不调用模型。需要私有作者源文件和已封存结果，不能脱离本地资料执行全量重建。

生成PPT使用原生图表及表格，先检查原生包、字体、几何及内嵌工作簿，再逐页渲染。作者WPS图表的重复标签兼容仅用于私人预览副本，不写回交付PPT。最终未通过WPS应用程序另行打开验收，不能把结构检查称作WPS视觉验收。

私人验收、原件快照和源数据哈希放在 `tmp/video_complete_v05/`。原始视频放在 `deliverables/video/recordings/clips/`；最终拼接依 `recording_order.json` 的内容顺序，不按文件名字典序。
