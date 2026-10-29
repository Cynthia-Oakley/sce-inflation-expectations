# 最终交付与提交归档

更新：2026-10-29。作者已确认赛事平台提交成功，当前为 **v12已提交，等待评审反馈**。状态依据为作者在本对话中的明确确认；提交编号、精确提交时刻和回执文件尚未提供，见[提交记录](submission_record.json)。

唯一交付入口为[deliverables](../deliverables/README.md)，机器指针为[latest_package.json](latest_package.json)。比赛仓库检查点为 `submission-v1.0`，指向 `7ece55a`；之后的仓库更新只记录提交状态和说明，不改变已提交材料。

## 已提交的三项材料

- **研究包v12：**约1.15GB，作者本机原件为 `deliverables/research_package/v12/SCE_research_package_draft_v12.zip`；同内容的上传副本位于 `deliverables/提交材料/`。完整ZIP已由作者提交赛事平台，未存入GitHub。
- **[论文v1.0 PDF](../deliverables/report/SCE研究报告_v1.0.pdf)：**8页，作者已确认署名、内容与版式；[Word原件](../deliverables/report/SCE研究报告_v1.0.docx)保留存档。
- **[演示视频MP4](../deliverables/video/final/SCE_demo_v1.0.mp4)：**267.891秒，该GitHub副本与实际上传视频逐字节一致。

精确文件名、大小与SHA256统一见[FINAL_FILES.json](../deliverables/FINAL_FILES.json)和[提交记录](submission_record.json)。不从outputs、开发study或旧版本目录重新选择提交件；历史v05/v08/v11记录继续保留。

## 当前研究包的复现范围

v12提供66,822份完整原样Prompt、67,147条原始调用记录、公开人口/环境与新闻源、匿名SCE编号/日期及数据编码映射。API Key、密码、认证头等账号秘密不包含在包内。

- 默认0API：从既有真实答卷重算全国/微观指标和A/B Normal。
- 自备Key：重建输入、批量作答、月度/周度新回答递推、独立评价与原组合/宏观/下游回归重拟。[完整操作指南](package_templates/v12/PORTABLE_REPRODUCTION.md)与包内说明一致，命令应在研究ZIP解压根目录执行。

独立ZIP78项测试、42项便携定向测试、全量输入重建与全新公开依赖安装均已验收，见[验收汇总](../docs/workstreams/20261029_portable_reproduction/acceptance_public.json)。B、月度和周度没有同期真人微观真值，不将其群体分歧解释为微观准确性；模型知识、历史文本版本与严格事前资格等研究边界不变。

GitHub保存代码、说明、验收汇总及论文/视频；完整新闻、微观源和逐人输入输出仍在保密研究ZIP中。因此，从GitHub克隆代码不等于取得完整数据包。当前仓库继续私有，分发与备份范围见[提交材料导航](../deliverables/提交材料/README.md)。

## 后续维护

等待平台反馈，无反馈时不启动新模拟。若有复现问题，从固定检查点开独立修复分支，另存新包并验收，不覆盖v12或移动提交标签。回执可保存到本地 `deliverables/submission_receipts/20261029/`。具体归档和赛后公开安排见[仓库收尾计划](../docs/workstreams/20261029_repository_closeout/README.md)。
