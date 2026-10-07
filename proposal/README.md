# 开题提案

## 当前可提交版（2026-10-07）

**提交文件：[socioverse_challenge_proposal_20261007.pdf](build/socioverse_challenge_proposal_20261007.pdf)**。可编辑源稿：[socioverse_challenge_proposal_20261007.md](socioverse_challenge_proposal_20261007.md)。共 **2 页 A4**，逐页视觉核验通过，沿用楷体、Times New Roman、首行两字缩进、1.25 倍行距及表格边框。

本次保留原六节结构，在局部更新后依用户意见进一步理顺十一处段落：说明消费篮子的匹配方法、支撑假设、使用方式与验证路径，把当前效果问题与下一步机制对照连接起来；明确开发月份中模拟 SCE 与真实 SCE 的趋势方向一致，但水平偏低、人群分歧不足。未改模型或研究配置，未覆盖 Kimi 待审的 `proposal.md`；旧候选和旧 PDF 原样保留。用户已于 2026-10-07 在本会话确认开题提交，平台回执尚未在本地归档。

新增数据来源说明：第四节逐项列明 SCE、CE Interview/Diary、BLS CPI/就业首发稿、EIA 汽油周价与纽约时报新闻档案的用途，区分已使用和拟研究资料，明确评价答案与预测版本边界。最新 PDF 仍为两页、约 0.25 MB。

官方要求已于 2026-10-07 复核：1–2 页 PDF，须包含问题、赛道、人群/环境/行为设定草案与数据来源，截止 **10-12 23:59（北京时间）**；通过平台「研究目录」页参赛入口提交。来源为[赛事官网](https://socioverse.fudan-disc.com/challenge/)及其当前公开 `challenge.js?v=20261005a`。结构检查和修改依据见 [提交前检查](submission_review_20261007.md)。

重建命令：`python3 proposal/render_proposal.py --stem socioverse_challenge_proposal_20261007`。来源、PDF 哈希、页数与核验记录在 `build/submission_review_20261007.json`。

## 前一提交候选（2026-10-05）

可编辑稿：[proposal_submission_candidate_20261005.md](proposal_submission_candidate_20261005.md)。PDF：`build/proposal_submission_candidate_20261005.pdf`，已导出并视觉核验，共 **2 页**。PDF 为本地产物，不自动推送；审定、平台提交及回执由用户办理，目前未提交。

本版以原 `proposal.md` 为底稿更新，保留原标题、六节结构和 P/E/B 表格。面向赛事评委，突出研究问题、SocioVerse 框架、价格体验的经济学逻辑与验证路径；用最新流程与经验发现替换过时进展，正文不列具体模型、人数、费用数字或内部截止日期。运行明细留在实验记录中。正式参数仍待开发验证后冻结。

官方开题要求为 1–2 页 PDF，截止 **2026-10-12 23:59（北京时间）**；最终材料截止 **2026-10-31 23:59**。[官方日程与要求](https://socioverse.fudan-disc.com/challenge/)，核查于 2026-10-05。此前 10 月 9 日截止已延期。

前一版较大改写的候选稿与 PDF 已本地归档到 `build/archive_candidate_before_editorial_20261005/`，当前同名候选为本次基于原稿的修订。

## 保留的历史草稿

- `proposal.md`：Kimi 10-03 待审批次中的原稿，本轮未覆盖、提交或还原。
- [proposal_track_a_revision_20261005.md](proposal_track_a_revision_20261005.md)：较早的 A/B 口径修订草稿，不含本轮全部最新结果。
- `build/proposal.pdf`：10-01 导出的旧 PDF，不是当前候选，原样保留。

## 本版依据与复算

- [两月真实实验记录](../docs/CORE_NORMAL_LLM_RECEIPT_20261005.md)：输入、配置、结果、费用与准确路径。
- [机制诊断与 CPI 对照](../docs/INFLATION_MECHANISM_DIAGNOSTIC_20261005.md)：确认事实、候选解释、经济学参考与诊断边界。
- [当前任务板](../docs/NEXT_ACTIONS.md)：下一步推进，以最新条目为准。

2026-10-05 按用户排版要求更新：A4 两页，中文楷体（Kaiti SC）、英文与数字 Times New Roman、正文 10pt、首行缩进两汉字、1.25 倍行距；P/E/B 表格使用完整横竖边框，并按内容调整三列宽度。验证方案从第二页开始，避免列表跨页。报告正文未改。

可复现排版入口：在仓库根目录运行 `python3 proposal/render_proposal.py`，需要本机 pandoc、xelatex、fc-match 与上述字体。源码仍为 Markdown，LaTeX 编译中间文件与 PDF 写入被忽略的 `proposal/build/`。既往正文修订的来源与哈希保留在 `outputs/core_normal_llm_review_20261005T094100Z/proposal_editorial_provenance_20261005.json`；该记录中的 PDF 哈希属于排版调整前的版本。
