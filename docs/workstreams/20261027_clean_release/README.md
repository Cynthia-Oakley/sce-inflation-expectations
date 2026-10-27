# v05：实际归类后的研究交付包

用户发现v04仍有大量平铺代码、旧工程配置混淆，且交付位置埋在outputs。v04的导读/依赖筛选没有完成真正的读者目录整理，本轮据此重新导出，不改付费实验与原始科研算法。

## 唯一入口

[交付目录](../../../deliverables/README.md) → [v05包根README](../../../deliverables/research_package/v05/package/README.md)。ZIP与解压目录集中在deliverables/research_package/v05；最新指针在submission/latest_package.json。旧v04ZIP原字节保留，SHA仍为a20e0affd1b62c769b0036b2dbcdb54e0f6b076ed9d6a14baba32bfeee5ab6f1。

## 实际改变

- study根仅3个Python文件：run.py、model.py、__init__.py；加README、FILE_GUIDE、study.yaml和resources.json共7个顶层文件。
- 原平铺代码分别进入components/population、components/environment、components/behavior、runtime或evaluation；来源版本辅助与报告行为模块也归入相应components子目录。
- 根model只注册显式工程示例，不再自动注册早期实验。20人两步资料单列examples/core_demo；标准P/E/S文件仍可供官方Core验收，均有说明它们不是正式512人实证输入。
- 正式研究统一看simulation/research_runs.json；旧B等配置移到明确历史区域。补齐grounding、合成roster及reports/report.md，resources.json亦通过官方ResourceManifest校验。
- 159份主包源码，831份原始开发源码按原路径/原字节封存。SOURCE_INDEX逐文件给出迁移路径及前后SHA；原开发源码和冻结执行包不搬动。
- B说明明确个人日期只改变E，P/合成先验仍按全局D；周度原始分数与已有组合对照分别表达。没有因此改造模型或重跑实验。

## 验收

[机器收据](acceptance.json)。独立无系统site-packages的venv，单独解压最终ZIP、清除密钥环境、禁止离线路径联网：

- 62项针对性测试通过，包括人口质量/抽样、联合Normal缺字段与概率归一化。
- 157个study模块从独立解压包导入，5类官方schema通过；不解压源码归档即可运行。
- 144份科研代码主体AST在去除已声明的导入/定位变化后与原件相同；仅复现入口有显式例子路径/输出目录适配。
- 229项清单文件及831份归档原源码校验；study根无散落业务脚本。
- 与v04比较，全部A/B/Normal/月度/周度/下游replay结果及工程收据完全一致；12个聚合CSV原字节一致。
- 新API调用0；原算法、原输入、原运行与旧ZIP均未修改。

这是离线工程和聚合证据验收，不把它说成完整个人密度/W1重算或全部数据许可已闭环。最终论文与视频继续按既有收尾计划推进。
