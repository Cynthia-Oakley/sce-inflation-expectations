# CE 消费背景数据落地计划

2026-10-06；用户已同意 Interview 主篮子、官方分组表核查、Diary 后续频率分支。本轮只做本地数据与工程验收，不运行新增真实 LLM/MCP，不冻结正式参数。

## 本轮交付与接力顺序

1. **来源归档**：保留已有 Interview ZIP 与官方 XLSX 字典；下载官方 2020 Diary CSV ZIP，记录 URL、获取时间、SHA-256、大小、成员及当前修订版本边界。原始资料只追加，不覆盖历史副本。
2. **完整人口篮子**：使用已验收的 2021-05/06 完整 P，沿用 CE2020Q4、seed=42、min_pool=25，与既有 300 Core 保持相同匹配算法。生成全部人口侧车，再通过 ID 划分 Core/Normal；不使用真人问卷答案。
3. **独立验收**：核对 ID、画像哈希、份额、Core 一致性、回退支持度、类别分布及 donor 集中度。CE 与 SCE 构成不同，不以总体均值强制相等为验收标准。
4. **Diary 准备**：先核对官方字典与真实 CSV 表头；分别处理家庭周金额及购买日数（仅实际字段支持时）。一行不等于购物次数，两周不是全年习惯；不能用 NEWID 跨 Interview/Diary 联结。
5. **交接**：汇总准确路径、执行命令、来源清单、验证结果与缺口，更新任务板。Normal 使用篮子的扩展方法及真实对照实验留作下一项，不默默修改现行统计扩展。

## 存储职责

- `data/raw/ce_experience/20261006/`：原始下载、获取记录。旧 Interview 文件保持原位置；Diary 放在 `diary/` 子目录。
- `data/interim/ce_experience/<run_id>/`：Diary 清洗记录、机械统计、字段审计；含家庭记录，Git 忽略。
- `outputs/ce_population_baskets_<run_id>/`：每月全人口 experience、实际提示预览、构建清单与审计；Git 忽略，旧 v1 不覆盖。
- `docs/CE_CONSUMPTION_DATA_INDEX.md`：供用户查找的唯一数据入口，链接到确切本地文件。
- `docs/literature/sce/sources/`：可提交的来源与方法摘要；不包含个体数据。

## 分工与保护范围

- 主 Agent：归档/下载、全人口构建、集成核验、数据入口及任务板。
- Luna `ce_diary_prepare`：新增 Diary study 模块、准备入口、定向测试及字段说明。
- Luna `ce_population_audit`：新增篮子审计入口与测试。
- 10-03 用户待审文件不提交、不还原；提交一律 scoped add。官方框架核心、现行计分器、现行 Normal 和旧运行配置不改。

## 研究边界

当前 Interview 是事后下载的修订副本，用于 A 历史重建代理；不是 2021-05/06 的事前数据。Diary 的公开日期/历史版本另行核验，当前下载不证明当时可得。篮子金额不是个人成交价；购买日数不是注意力权重。工程验收不证明预期模拟效果改善。
