# 新闻摘录：赛事保密评审范围

本v12研究包按作者2026-10-29的明确要求，补入四个最终任务实际使用的NYT新闻标题、摘要/片段、公开日期及其在Prompt中的安排，供SocioVerse Challenge评委理解、检验和按适用条件复现输入。作者说明赛事方将保密处理；本项目未另行核验赛事内部的保密协议条款。

来源：The New York Times，NYT Archive API及项目已登记的历史新闻获取来源。第三方文字的版权仍属于相应权利人；附随这些摘录不表示项目作者取得或转授其公开再分发许可。API访问、研究使用、模型处理、保密评审与公开发布是不同范围。

本包仅供赛事保密评审，不是公开数据集；请勿上传公开仓库、网站或重新批量分发。若需扩大用途或对外公开，应自行取得原来源的适用授权。可公开的项目代码、方法、报告和自制视频与该新闻数据层分开管理。

参考：

- NYT官方Archive API说明：https://github.com/nytimes/public_api_specs/blob/master/archive_api/archive_api.md
- API条款入口：https://developer.nytimes.com/tou
- 署名说明入口：https://developer.nytimes.com/attribution

本轮未获得可确认的批量文字公开再分发许可，不能以“赛事保密”代替这项许可。前一轮不含新闻的来源核查存档在SOURCE_TERMS_PREVIOUS_REVIEW.md；它记录当时的保守投影决定。本版按作者新要求在本说明的限制范围内纳入选中摘录，并未改写历史审计或宣称新增版权授权。

本包portable源资料层提供本研究实际使用的候选新闻档案与标签，包含未最终选中的候选文章；inputs层提供所有原始Prompt与选中摘录。原始公开SCE匿名编号和内部Agent/供体匹配来源同样保留。作者API Key、密码、认证头和付款秘密不提供。未曾抓取的出版商全文不伪造补写。按作者明确要求，A原Prompt中来自公开SCE调查的日期/截止日保留，B/月度合成日期与周度公共截止日同样保留，全部Prompt无需回填。
