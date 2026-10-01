# 2021-05/06 首试：用 BLS 首发新闻稿补足真实历史 E

核查日：2026-09-30。状态：**本地真实历史 E 已核验；据用户转述，平台也已读取并核对四份 PDF 和六条 JSON 信号，但尚未把它们物化为 study 环境或运行模拟。**

## 平台反馈与修正

SocioVerse Agent 对两次 `fred` 查询取得了 `CPIAUCSL`、`UNRATE` 的当前快照，但回包没有 `published_at`、`release_date`、`vintage` 或 `source_version`。按项目协议把它们列为 `unknown_as_of` 是正确的。此前上传提示把“合成 E”作为唯一备选，导致实验止步于 schema smoke；这里补入**有明确首发日和原始发布值**的官方来源。

两目标月与截止点不变：2021-05 对应 2021-04-30 23:59:59 纽约时间；2021-06 对应 2021-05-31 23:59:59 纽约时间。直接采用美国劳工统计局（BLS）的当期归档发布稿，而不把今日 FRED 快照重新标成历史版本。BLS 资料和本地 SHA-256 已写入[补充来源清单](peb_source_manifest.json)，可直接上传的六条信号在 [真实 E JSON](../proposal/cloud_input/sce_2021_05_06_bls_release_e.json)。

| 目标月 | 新闻稿首次可公开时间（纽约） | 原始发布期 | 使用的首发值 | BLS 版本 |
| --- | --- | --- | --- | --- |
| 2021-05 | 2021-04-02 08:30 | 2021-03 就业 | 季调失业率 6.0% | [USDL-21-0582](https://www.bls.gov/news.release/archives/empsit_04022021.pdf) |
| 2021-05 | 2021-04-13 08:30 | 2021-03 CPI | 全项目同比 2.6%（未季调）；环比 0.6%（季调） | [USDL-21-0651](https://www.bls.gov/news.release/archives/cpi_04132021.pdf) |
| 2021-06 | 2021-05-07 08:30 | 2021-04 就业 | 季调失业率 6.1% | [USDL-21-0816](https://www.bls.gov/news.release/archives/empsit_05072021.pdf) |
| 2021-06 | 2021-05-12 08:30 | 2021-04 CPI | 全项目同比 4.2%（未季调）；环比 0.8%（季调） | [USDL-21-0857](https://www.bls.gov/news.release/archives/cpi_05122021.pdf) |

四份 PDF 首页均有“embargoed until 8:30 a.m. ET”与版本编号，首页正文直接给出上述值。下载的是 **2026-09-29 可取到的 BLS 归档 PDF**，其当前字节哈希保存在本地；我们不能以此证明 PDF 字节在 2021 年以来从未变动，但日期、版本和首页数值提供了比无 vintage 的当前 FRED 回包更直接的历史发布证据。

本地复核命令：`python3 scripts/verify_bls_pit_e.py`（需 PyMuPDF）。它逐条检查 PDF 哈希、首页版本/数值、六条信号的发布时间与两个 `as_of`；2026-09-29 已通过。这个检查仍不等于云端已经成功导入文件。

**变量口径要分开。** 这份真实 E 使用新闻稿公布的 CPI-U 全项目同比/环比和失业率。CPI 增幅不是 `CPIAUCSL` 季调指数本身；平台不得把 2.6、4.2 误标为 CPI 指数，也不得把已隔离的 FRED 当前快照混进 JSON。失业率虽对应同一宏观概念，也以 BLS 新闻稿所写当期数值为准，不从当前 `UNRATE` 反填。

## 平台操作与解释范围

1. 平台已读取[真实 E JSON](../proposal/cloud_input/sce_2021_05_06_bls_release_e.json)及四份[本地 BLS PDF](../data/raw/bls_2021_initial_releases/)，核对了六条信号与 PDF 哈希。据平台反馈，下一步需在同一 study 经版本门创建新 version，把冻结快照绑定到 E；旧 synthetic E 仅是方案，未运行出基线。官方 Environment schema 支持 `information_program.broadcasts`：可用 step 0/1、`ttl=1` 分月播报，但须确认实际 provider 注册并由 `observe_batch` 交给 Agent；[schema 源码](https://github.com/sii-research/SocioVerse2/blob/fa678ff6aea0e5a6497a7ffac15459123200a150/socioverse/schemas/environment.py)只能证明格式能力，不能证明当前 study 已接入。
2. 保留此前 `fred` 回包在审计层，状态 `unknown_as_of`；它们不进入 B。合成 E 只在平台无法导入/物化这份真实 E 时，用于单纯流程故障排查，并明确标记。
3. 成功后可称“**真实历史宏观 E + 合成 P 的两月流程试验**”。由于 P 仍是人工编排的 20 人、B 的官方 Q9 个人密度未复现、月份只有两个，不据此报告全国 SCE 预测能力或改称完整历史回测。下一步才是历史可得 P、正式计分与更多开发月。

平台 Agent 现在可直接使用[版本门之后的继续消息](../proposal/cloud_input/continue_after_version_gate.md)。如导入本地 E 失败，请它报告具体文件解析、环境映射、权限或导出错误；这时才判断是否需要本地构建 Environment，不能再把“Event MCP 无 vintage”当作唯一停止原因。
