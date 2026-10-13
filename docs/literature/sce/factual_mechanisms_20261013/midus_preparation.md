# MIDUS：已下载什么，接下来如何使用

2026-10-13。账户由用户本人注册；本轮使用已登录的Chrome及Kimi浏览器扩展定位文件。没有读取MIDUS个体记录、没有发送数据到Simulation API，没有新付费调用。

## 已完成

两份SPSS原始文件在独立下载目录：

- `/Users/wushuyue/Downloads/sce_midus_private_20261013/M2_P1_SURVEY_N4963_20200720.sav`：MIDUS 2主调查，约20.2 MB，官方文件标示4,963例。留作原队列的参考，不直接和Refresher混成一个人口池。
- `/Users/wushuyue/Downloads/sce_midus_private_20261013/MR1_P1_SURVEY_N3577_20250407.sav`：Refresher 1主调查，约15.8 MB，官方文件标示3,577例。首批人格/乐观分布的优先参考。

公开码本、问卷、人格量表、抽样及权重说明在：

`/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/data/raw/midus_sources/20261013/`

大小、SHA-256、原始链接、版本及下载失败记录见[下载清单](midus_download_receipt.json)。刷新样本的独立年龄说明链接返回404，年龄定义可先查已下载码本；两份数据本身均已完整下载。Chrome的下载目录控制被扩展拒绝，M2使用原下载按钮后移动，MR1按页面实际地址完成传输；没有更改浏览器安全设置或接受新的协议。

## 为什么优先Refresher

它于2011—2014年重新抽取全国概率样本，招募目标年龄25—74岁；只用原队列容易把队列老化误当全国人口变化。[官方研究条目](https://midus.colectica.org/item/midus.wisc.edu/1ca6c7d2-8005-4a8d-83fc-aca7fdd40db5)

码本计算年龄实际为23—76岁。首版程序明确只分析25—74岁，以对应文档中的权重目标范围；这不是把SCE所有年龄强行塞入该区间。18—24岁和更高年龄者暂不外推，粗年龄组跨越边界也不能假装知道精确年龄。

人格/乐观来自自填问卷，不能按3,577例宣称所有人都有心理数据。公开码本说明约2,600人有自填问卷，其中各量表仍有缺失；实际有效样本须由用户本地统计确认。

## 首批字段与含义

- `RA1PRAGE`：访谈时计算年龄；`RA1PB1`：教育完成程度。电话问卷PDF第47页核对教育编码1—5/6—8/9—12，分别为高中及以下/部分大学或专科/本科及以上。
- `RA1SNEURO`、`RA1SEXTRA`、`RA1SOPEN`、`RA1SCONS2`、`RA1SAGREE`：五类人格复合量表，1—4。CONS2多一个题项，不和CONS1混用。
- `RA1SORIEN`：LOT总体乐观，6—30；高分代表总体更乐观。`RA1SOPTIM`、`RA1SPESSI`可作分量表复核，但首版不把三个重叠得分作为独立因素叠加。
- 人格中的8、自填缺席的-1、LOT中的98、教育中的97/98、SAQ权重中的99均不是有效心理数值。
- 当前文件的`RA1SWGHT6`用于SAQ，按教育、种族、性别、年龄、婚姻状态调整；7/8可作权重敏感性。不能拿电话问卷权重直接当作已修正SAQ选择的权重。

上述定义来自[2026量表说明](https://midus-study.github.io/public-documentation/MR1P1/Documentation/MR1_P1_DocumentationOfPsychosocialConstructsAndCompositeVariables_20260318.pdf)、[2025码本](https://midus-study.github.io/public-documentation/MR1P1/Documentation/MR1_P1_Codebook_20250508.pdf)、[权重说明](https://midus-study.github.io/public-documentation/MR1P1/Documentation/MR1_P1_DocumentationOfPost-StratificationWeights_20250409.pdf)。

## 用户本地统计程序已准备

入口：`scripts/summarize_midus_local.py`；核心：`studies/sce_inflation_expectations/midus_group_summary.py`。依据公开码本编写，四项人工数据测试通过，**尚未在真实MIDUS文件上执行**。

请在普通终端中运行，不让AI Agent代为读取真实文件：

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python /Users/wushuyue/Documents/科研/DISC/socioverse_challenge/scripts/summarize_midus_local.py \
  --input /Users/wushuyue/Downloads/sce_midus_private_20261013/MR1_P1_SURVEY_N3577_20250407.sav \
  --out /Users/wushuyue/Downloads/sce_midus_private_20261013/mr1_group_summary_v1.json
```

所需读取库已安装到既有SocioVerse环境。程序核验输入文件哈希，只读白名单字段，不联网、不导出个人行，输入/输出均拒绝放入DISC工作区，不覆盖既有结果。

首版按三个年龄范围×三个教育范围，给出六个心理量表的加权均值与协方差；每组至少60名完整受访者，只公布样本量区间。60是本项目的支持门槛，不是理论最优样本数。神经质×乐观的九格联合分布，只有九格每格都至少11人时才整张输出，否则整张省略，避免用总数反推小格。三档依据有效样本加权三分位划分，是合成粒度，不是临床分类。

这些摘要有助于保留同一来源的联合结构；均值/协方差仍不能完全恢复真实分布。程序采用完整案例，会带来选择性；尚未估计复杂抽样标准误，不能称精确全国分布。不要为获得更多可用格子而按模拟效果反复调整分组。

## 尚需判断的两项边界

**历史版本。** README说明原始数据2016年发布，当前文件2025年更新并新增后分层权重。新权重虽参照2012年CPS，也不等于2012年就能拿到。当前下载可服务披露来源的A线研究与后续候选准备；严格2021年B线须另找当时已经公开的版本/权重。[官方更新说明](https://midus-study.github.io/public-documentation/MR1P1/MR1_P1_README_20250409.pdf)

**使用路径。** MIDUS条款限制向不保障保密与不留存的外部AI上传数据。本轮只传输了文件，没有将记录交给模型。请先在本地审阅摘要；哪些分析摘要或合成产物可进一步分享、调用API，须依协议确定，统计程序不替代此判断。[MIDUS条款](https://midus.colectica.org/Account/Register)

后续先检查支持度，再依据允许使用的群体分布合成P。合成心理不等于SCE真人心理；不能直接规定“乐观所以通胀低”，需单独验证它如何改变持续性判断、信息理解和不确定性。先验实验与人格实验分开进行。
