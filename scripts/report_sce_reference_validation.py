#!/usr/bin/env python3
"""Write aggregate Chinese findings and update the existing project reading page."""
import argparse
from html import escape
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def f(x,n=3):
    return '缺失' if x is None else f'{x:.{n}f}'


def write_report(source, execution, figures, dest, update_html=False):
    s=json.loads(source.read_text());e=json.loads(execution.read_text())
    if s['status']!='completed_sce_reference_scaleup_evaluation':raise ValueError('Completed frozen evaluation required')
    if dest.exists():raise ValueError('Fresh report file required')
    scopes=s['scopes'];new=scopes['new_months'];allmonths=scopes['all_months']
    mm=new['model_metrics_equal_month_repeat_cells'];base=new['scalar_baselines_equal_month_repeat_cells']['copy_previous']['metrics']
    macro=new['macro_center_errors'];goal=s['point3_project_goal_diagnostics']['new_months'];coverage=s['coverage']
    diagnostic_path=ROOT/'docs/workstreams/20261017_reference_scaleup/update_diagnostic_v2.json'
    diagnostic=json.loads(diagnostic_path.read_text())
    if diagnostic['source_summary_sha256']!=__import__('hashlib').sha256(source.read_bytes()).hexdigest():
        raise ValueError('Post-hoc diagnostic must refer to this exact evaluation')
    groups=s['prespecified_descriptive_groups']['new_months']
    def group_value(dim,value,key):return f(groups[dim][value]['descriptive_means_on_reportable_cells'][key])
    interval=s['macro_exploratory_year_block_intervals']['new_months']['metrics']['reference_minus_copy_previous_mae_pp']
    ci=interval.get('interval_95_unadjusted_pp');diff=interval.get('point_mean_pp')
    ci_text='未能计算' if ci is None else f'[{f(ci[0])}, {f(ci[1])}]'
    holds=mm['q9_center_mae_pp'] is not None and mm['q9_center_mae_pp']<=.3
    trend='达到本项目0.3pp的平均误差目标' if holds else '未达到本项目0.3pp的平均误差目标'
    comparison='低于' if diff is not None and diff<0 else '高于或等于'
    lines=['# 十二个月扩大验证结果','',
        '## 1. 本次完成了什么','',
        f"2020—2025每年预选两个月，共12个月；每月192名回访者，同一参考配置生成两遍，计划4,608次请求。实际完成{e['actual_call_count']}次，原始回答与轨迹逐项核验；有效率{coverage['valid_fraction']:.2%}。模拟token费用估算${e['estimated_peak_token_cost_usd_not_bill']:.3f}，低于授权$21.50，运行约{e['wall_clock_seconds']/60:.1f}分钟。新闻分类另计约$0.711。金额均非平台账单。",'',
        '输入沿用人口画像、合成CE支出、美联储信心、公开价格/新闻/政策、本人真实上期Q8/Q9和更早摘要、信息发布时间标签及直接作答。未新增Q1、数理实答、购买频率或更新规则。人口来自完整合格回访者池，按年龄×收入分层；评价用调查权重÷入样概率，模型不接收权重。','',
        '## 2. 先看新增八个月，而不是用旧月好结果拉低平均','',
        f"主要检验的新增8个月，同样本Q9中心MAE为**{f(mm['q9_center_mae_pp'])}pp**，{trend}；同样本照抄本人上期为{f(base['q9_center_mae_pp'])}pp。模型点估计{comparison}该基线，模型减基线的误差差为{f(diff)}pp，按年份分组重抽的探索性95%区间{ci_text}。区间衡量这组有限时期下的不确定性，不是未来准确率保证。",'',
        f"新增8个月中，有{goal['matched_sample']['months_below_or_equal_point3']}/{goal['matched_sample']['months_planned']}个月的两遍平均误差≤0.3pp，最差月份{f(goal['matched_sample']['worst_month_mae_pp'])}pp。整体平均达标与每个月稳定达标不同。",'',
        '| 时间范围 | 模型对同样本MAE | 照抄本人上期对同样本MAE | 模型对完整波次MAE | 完整波次上月值延续MAE |',
        '|---|---:|---:|---:|---:|']
    names={'new_months':'新增8月（主要检验）','old_months':'原4月','all_months':'全部12月'}
    for key in names:
        d=scopes[key];v=d['model_metrics_equal_month_repeat_cells'];a=d['macro_center_errors']
        lines.append(f"| {names[key]} | {f(v['q9_center_mae_pp'])} | {f(a['copy_previous_center_mae_pp'])} | {f(a['reference_vs_full_wave_center_mae_pp'])} | {f(a['previous_full_wave_carry_center_mae_pp'])} |")
    lines += ['', '单位均为通胀百分点。逐月、逐遍先取绝对误差，再按月等权平均；不是将多个月预测先平均后计误差。旧4月、新增8月、全12月不择优替换。','',
        f"原4个月扩大到192人后为{f(scopes['old_months']['model_metrics_equal_month_repeat_cells']['q9_center_mae_pp'])}pp，接近此前48人的0.290pp；主要差距出现在新增时期。扩大人数与扩展月份检验不同问题，不能把整体变差简单解释为人数增加。",'',
        '## 3. 同样本拟合与完整SCE重建必须区分','',
        f"新增8个月，模型对完整SCE微观波次的中心MAE为**{f(macro['reference_vs_full_wave_center_mae_pp'])}pp**，完整波次上月值延续为{f(macro['previous_full_wave_carry_center_mae_pp'])}pp。同样本中心误差与这一指标不能互相替代。完整波次也由同一近似计分器重算，不是直接换用官方发布headline。",'',
        '每月带符号的偏差分成：模型−所抽真人、所抽真人−完整合格回访者、合格回访者−完整SCE波次。三项相加等于模型−完整波次；只有带符号差可以相加，绝对误差不可相加。这用于观察抽样/回访覆盖与模型误差是否抵消，不是因果归因。','',
        '## 4. 个人分布是否更接近','',
        f"新增8个月个人Q9均值MAE：模型{f(mm['individual_density_mean_mae_pp'])}pp，对照抄上期{f(base['individual_density_mean_mae_pp'])}pp；跨人分布W1：模型{f(mm['cross_section_w1_pp'])}pp，对照{f(base['cross_section_w1_pp'])}pp。模型人际IQR为{f(mm['cross_person_iqr_pp'])}pp，真人为{f(mm['real_cross_person_iqr_pp'])}pp，照抄为{f(base['cross_person_iqr_pp'])}pp。人际IQR要接近真人，不应以越大越好。",'',
        f"模型变化分布W1为{f(mm['delta_w1_pp'])}pp；个人主观概率IQR误差为{f(mm['individual_density_iqr_mae_pp'])}pp。十档中的所有通缩概率都填0者，模型占{mm['zero_deflation_rate']:.1%}，真人占{mm['real_zero_deflation_rate']:.1%}。跨人分歧与同一个人的主观不确定性是两种不同对象。",'',
        '## 5. 人口规模与分组检查','',
        '同192份回答中，预先固定30组48⊂96⊂192子样本；不追加API，不选择表现最好的一组。以下范围是同一批回答的抽样敏感性，不能当作30次独立模型实验或置信区间。','']
    for size in ('48','96'):
        a=s['nested_sampling']['sampling_ranges'][size]['new_months']
        r=a['same_sample_center_mae_pp']['min_q025_median_q975_max_pp'];v=a['full_wave_center_mae_pp']['min_q025_median_q975_max_pp']
        lines.append(f"- 每月{size}人：30组同样本MAE的中位数{f(r[2])}pp，2.5%—97.5%范围[{f(r[1])}, {f(r[3])}]；对完整波次MAE中位数{f(v[2])}pp，范围[{f(v[1])}, {f(v[3])}]。")
    lines += ['', '年龄、收入、数理、教育、地区、住房、就业均按预设分组记录。每月每组不足3人不报告该格指标；缺失格不填补，分组差不能解读为该特征的因果影响。详见summary.json中的prespecified_descriptive_groups。','',
        f"新增8个月，高/低数理组中心MAE为{group_value('numeracy','high','q9_center_mae_pp')}/{group_value('numeracy','low','q9_center_mae_pp')}pp，个人均值MAE为{group_value('numeracy','high','individual_density_mean_mae_pp')}/{group_value('numeracy','low','individual_density_mean_mae_pp')}pp；高中/大学组中心MAE为{group_value('education_group','high_school','q9_center_mae_pp')}/{group_value('education_group','college','q9_center_mae_pp')}pp。差距提示应重点检验这些群体的信息理解与概率表达，尚不是控制其他特征后的因果效应，也不表示之前具体答题提示的效果已得到验证。",'',
        '## 6. 目前最清楚的机制线索','',
        f"事后复用已计分回答，扣除月份共同水平，对本期与本人上期信念做加权线性回归。全12月平均斜率：真人{f(diagnostic['scopes']['all_months']['real'])}，模型{f(diagnostic['scopes']['all_months']['model'])}。直观上，上期信念高1pp的人，本期真人仍平均高约0.60pp，模型保留约0.36pp的差距。模型保留了部分个人排序，但跨人差异收缩较强。此项只是描述关联，不是因果权重或可直接部署的更新系数；一年期预测窗口重叠11个月也会产生持续性。",'',
        f"模型在2020年3/9月、2021年9月、2025年3月偏低，在2022年6/12月等时期偏高。全12月平均带符号偏差{f(allmonths['model_metrics_equal_month_repeat_cells']['q9_center_bias_pp'])}pp，但MAE为{f(allmonths['model_metrics_equal_month_repeat_cells']['q9_center_mae_pp'])}pp，正负偏差相互抵消；单加统一常数不足以消除跨时期差距。",'',
        '下一步优先用已有轨迹定位哪些家庭改变过多、哪些月份更新方向错误，再审定历史持续性与新信息反应的机制。扩样减小了抽样波动，当前配置仍未显示额外信息的稳定预测增量。新机制需在开发期估计、未用于调整的时期检验，不能用本次12月调好再称独立成功。','',
        '## 7. 有效范围和下一步','',
        f"Q9共同可评分{coverage['q9_common_person_months']}/2,304个人月，真人缺失或不可拟合{coverage['human_q9_missing_or_unscorable_person_months']}个人月，任一遍模型Q9失败{coverage['any_repeat_model_q9_failure_person_months']}个人月；两者可能重叠，不能将真人缺失算作模型失败。Q8独立评价，不混入Q9中心。",'',
        '这是一项使用真实本人过去问卷和当期回顾性人口画像的A条件历史重建。每月各自重建，不是连续12月自主更新，也不是严格事前B预测。模型训练知识、受访者覆盖、合成CE/信心与新闻历史版本的限制仍保留。', '',
        '本轮结果不用于再改这套提示或选择月份。先区分宏观水平、微观分布、抽样与覆盖差异；若转向B，须另做合成人口、初始信念、连续递推和误差累积验证。','',
        '## 图表与复算','']
    for file,title in [('monthly_centers.png','十二期中心变化'),('macro_accuracy.png','两种目标与各自基线'),('microstructure.png','个人误差与人际分布'),('sample_size.png','预设48/96子样本敏感性')]:
        rel=__import__('os').path.relpath(figures/file,dest.parent)
        lines += [f'![{title}]({rel})','']
    lines += [f'原始聚合评价：{source}',f'执行与费用：{execution}',
        '评价入口：scripts/analyze_sce_reference_validation.py（新输出目录；0API）',
        '图表入口：scripts/plot_sce_reference_validation.py；本文件由report_sce_reference_validation.py生成。','']
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text('\n'.join(lines))
    if update_html:
        target=ROOT/'docs/workstreams/20261013_behavior/codex_expansion_diagnostic_20261014.html'
        content=target.read_text();key='expanded-reference-validation-results'
        if f'id="{key}"' in content:raise ValueError('Result section already exists; preserve it')
        parts=[f'<section id="{key}" style="font-family:\'Times New Roman\',\'Kaiti SC\',\'STKaiti\',serif;border-bottom:1px solid #ddd;padding-bottom:28px;margin-bottom:36px">']
        table=False
        for line in lines:
            if line.startswith('|'):
                if line.startswith('|---'):continue
                if not table:parts.append('<div class="table-scroll"><table>');table=True
                parts.append('<tr>'+''.join('<td>'+escape(c.strip()).replace('**','')+'</td>' for c in line.strip('|').split('|'))+'</tr>');continue
            if table:parts.append('</table></div>');table=False
            if line.startswith('![ '):continue
            if line.startswith('!['):
                title=line[2:line.index(']')];image=line[line.index('](')+2:-1]
                path=(dest.parent/image).resolve();rel=__import__('os').path.relpath(path,target.parent)
                parts.append(f'<figure><img src="{escape(rel)}" alt="{escape(title)}"><figcaption>{escape(title)}；冻结评价的聚合图，非官方headline。</figcaption></figure>')
            elif line.startswith('# '):parts.append('<h1>'+escape(line[2:])+'</h1>')
            elif line.startswith('## '):parts.append('<h2>'+escape(line[3:])+'</h2>')
            elif line:parts.append('<p>'+escape(line.replace('**',''))+'</p>')
        if table:parts.append('</table></div>')
        parts.append('</section>');content=content.replace('<main>','<main>'+''.join(parts),1);target.write_text(content)
    return dest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--execution',type=Path,required=True)
    p.add_argument('--figures',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--update-html',action='store_true')
    a=p.parse_args();print(write_report(a.source.resolve(),a.execution.resolve(),a.figures.resolve(),a.out.resolve(),a.update_html))
