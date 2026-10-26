# B前一年同月日期：实现与状态

**2026-10-26后续：Kimi修复已接入，完整11期已重建。**`sce_recent_b_sampled_dates_complete_20261026_v1`包含5632份逐人冻结提示、11官方Core离线单元；January＋February缺口解除，旧源保留。新Terminal适配器复用full-A耐受零星错误的冻结消息调度，24项定向测试及5632位置/两次失败补跑回放通过。正式包`sce_recent_b_sampled_terminal_20261026_v1`绑定283项来源，预计$5.5634、主补总帽$8。自动审批拒绝启动，要求本批明确外发范围/目的地/预算，确认卡已发；尚无授权文件/进程/本批API。见[B运行说明](B_TERMINAL_RUNBOOK_20261026.md)。下文早期九期状态作为准备过程保留。

2026-10-26。用户文字最初为“前年同月”，已通过澄清明确选择**前一年同月、前12个月**。代码支持12/24两个配置，但当前唯一准备主版本为12个月，不将24个月误当用户决定。

## 实现规则

- 目标202511—202609，原B每月512户、54格及原权重、联合数值先验、食品采购角色和篮子不变。
- 日期概率取t−12月的未加权实际月内完成日频率，来源必须不晚于该期既定B可得源波次；月长不同时沿已验证区间重叠法映射概率质量。
- SHA256固定随机流`20261026|B-completion-date|目标月|代理ID`为每人抽一个日期，增删其他代理不改变该人结果。日期与人口特征及新闻档位不额外条件化。
- 个人信息截止为min(合成作答日前一天纽约23:59:59，原全局D)。不把日期随机化当成移动B预测时间。5,632个日期映射已写出，共139个实际日快照；不增加每人生成遍数。
- 逐日重选新闻、最新可用食品价格/政策/信心并重渲染提示，四档4/8/16/32与CPI1.5、个人警示1不改。全局E文件只作预测者D的元数据；LLM只接收逐人冻结提示，不从全局E额外获取信息。
- 抽到1日者的个人截止与合成先验参考月末同日。旧“相邻真人历史”渲染器要求严格早一日，不适合这个B语义。新增**局部B渲染器**允许已声明合成月末先验与截止同日，发布同日仍标不确定；数值先验与参考日期不改，也不放宽A真实历史的旧规则。未来日期仍拒绝。
- 新版本使用冻结消息Core/队列接口；不要把该输入直接交旧B night的严格历史渲染器。新付费执行器仍须在数据交付后绑定冻结消息队列、恢复/技术补跑及新依赖锁。

## 代码与输出

study实现`experiments/recent_b_sampled_dates.py`；CLI：`scripts/prepare_sce_recent_b_sampled_dates.py`。

日期计划：`outputs/sce_recent_b_sampled_dates_plan_20261026_v2/`。v1为早期未放宽同日合成参考的工程版本，不用于最终组装。代表月份202511/202604的1,024份新提示已通过2个官方Core离线单元，目录`sce_recent_b_sampled_dates_engineering_20261026_v2`。

完整11期预检在`sce_recent_b_sampled_dates_full_preflight_20261026_v1`明确阻断于January原文覆盖，不会生成一份假称可运行的完整包。January＋February都需要完整January档。无此缺口的9期已在`sce_recent_b_sampled_dates_healthy9_20261026_v1`完成4,608份提示、9个官方Core离线单元；不称已完成11期真实模拟。47项相关测试及4,608份提示的独立截止／原状态／问卷／哈希核验通过，172份同日合成参考用上述局部规则处理，数值先验不变。

## 复建

```bash
PY='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
"$PY" scripts/prepare_sce_recent_b_sampled_dates.py dates --lag-months 12 --out outputs/<fresh_date_plan>
"$PY" scripts/prepare_sce_recent_b_sampled_dates.py assemble \
  --date-plan outputs/<date_plan> \
  --repair-manifest outputs/<Kimi_delivery>/repair_manifest.json \
  --out outputs/<fresh_B_date_assembly>
```

只做代表月份的官方Core工程检查可加`--months 202511,202604`；其结果必须标成子集，不能当完整11期验收。

新修复来源通过独立archive_view映射到新文件，原canonical档不写入；实际源路径/哈希写进新manifest。增量标签只能增加新ID，不能静默改写旧分类。原文日期范围不足时先生成明确blocker，不启动LLM。

本轮0API、没有付费授权或启动；也没有重新拟合Q9。后处理参数仍保持已准备方案，时间随机化的真实SCE效果需本批运行后才能评价。
