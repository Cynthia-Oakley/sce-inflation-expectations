#!/usr/bin/env python3
"""Publish the existing HTML-report style for cached news-mechanism results."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import html
import json
import sys

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
LABELS={'fixed_8':'固定8篇','random_quantity':'随机新闻量','demographic_quantity':'人口匹配数量',
        'random_quantity_uniform_topics':'随机量＋均匀主题','carry':'照抄本人上期','human':'真人本期'}
COLORS={'fixed_8':'#777777','random_quantity':'#c76800','demographic_quantity':'#7437aa',
        'random_quantity_uniform_topics':'#0078b5','carry':'#222222','human':'#111111'}
STYLES={'fixed_8':('s','--'),'random_quantity':('o','-'),'demographic_quantity':('^','-.'),
        'random_quantity_uniform_topics':('D',':'),'carry':('x','--')}
PRIOR=['below_2','2_to_below_4','4_to_below_8','8_or_above']
PRIOR_LABELS=dict(zip(PRIOR,['上期＜2%','上期2—4%','上期4—8%','上期≥8%']))
GRID_LABELS={f'{e}|{j}':f'{ename} × {jname}' for e,ename in [('high_school','高中及以下'),
    ('some_college','部分大学教育'),('college','大学及以上')] for j,jname in [('attached','在职'),('not_attached','未在职')]}


def f(value,digits=3):
    return '未定义' if value is None else f'{value:.{digits}f}'


def supplementary_variance(source,dest):
    path=Path(source)/'prior_variance_supplement.json'
    if not path.exists():return ''
    raw=path.read_text();s=json.loads(raw);v=s['metrics']
    (Path(dest)/path.name).write_text(raw)
    h,b,r=v['human'],v['fixed_8'],v['random_quantity']
    return f'''<h3>补充诊断：差距主要在同档旧信念者内部</h3>
<p>按上期四档预期分组，使用同一月/遍和设计权重分解跨人方差。真人总方差{h['total_variance_pp2']:.2f}＝组间{h['between_grid_variance_pp2']:.2f}＋组内{h['within_grid_variance_pp2']:.2f}；固定8篇模型{b['total_variance_pp2']:.2f}＝组间{b['between_grid_variance_pp2']:.2f}＋组内{b['within_grid_variance_pp2']:.2f}（单位pp²）。</p>
<p>模型组间差异已大于真人，但同一旧信念档内部的差异明显不足。随机新闻量只将组内方差从{b['within_grid_variance_pp2']:.2f}增至{r['within_grid_variance_pp2']:.2f}，没有补齐主要缺口。</p>
<p class="note">这是事后描述，未进入筛选或用于校准；宽档内部还包含不同精确旧值、人口和历史差异，不能全解释为随机冲击。<a href="prior_variance_supplement.json">聚合分解</a>；<a href="../news_matching_results_20261022.md">完整解释与下一步</a>。</p>'''


def publish(source,dest,decision=None):
    source,dest=Path(source).resolve(),Path(dest).resolve()
    if dest.exists():raise ValueError('Fresh report destination required')
    s=json.loads((source/'summary.json').read_text())
    if s['status']!='completed_news_matching_cached_readout':raise ValueError('Completed canonical readout required')
    arms=s['arms'];names=[*arms,'carry'];r=s['fixed_roster_operational'];metrics=r['metrics'];months=s['months']
    dest.mkdir(parents=True);(dest/'figures').mkdir()
    adoption=None
    if decision is not None:
        adoption=json.loads(Path(decision).read_text())
        (dest/'adoption_decision.json').write_text(json.dumps(adoption,ensure_ascii=False,indent=2)+'\n')
    variance_html=supplementary_variance(source,dest)
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':11,
        'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    ticklabels=[LABELS[a].replace('＋','\n＋') for a in names]
    fig,axes=plt.subplots(1,3,figsize=(15,4.8))
    for ax,key,title,unit in zip(axes,['center_mae_pp','w1_pp','across_person_iqr_pp'],
            ['群体中位数MAE','跨人分布距离W1','跨人四分位距IQR'],
            ['百分点（越低越好）','百分点（越低越接近真人）','百分点（与真人比较）']):
        bars=ax.bar(range(len(names)),[metrics[a][key] for a in names],color=[COLORS[a] for a in names])
        ax.bar_label(bars,fmt='%.3f',padding=4,fontsize=9)
        ax.set_xticks(range(len(names)),ticklabels,rotation=30,ha='right');ax.set_title(title);ax.set_ylabel(unit)
        ax.set_xlabel('输入配置 / 基线');ax.margins(y=.2);ax.grid(axis='y',alpha=.12)
        if key=='across_person_iqr_pp':
            truth=metrics[arms[0]]['truth_across_person_iqr_pp']
            ax.axhline(truth,color=COLORS['human'],linewidth=1.8,linestyle='--',label=f'真人 {truth:.3f} pp');ax.legend(fontsize=9)
    fig.suptitle('固定人群：有效回答＋已登记的上期后备；八个月、两遍等权',fontsize=13)
    fig.tight_layout();fig.savefig(dest/'figures/overall.png',dpi=170);plt.close(fig)
    monthly={m:{a:{k:float(np.mean([c['arms'][a][k] for c in r['cells'] if c['month']==m]))
        for k in ('center_mae_pp','w1_pp','across_person_iqr_pp','truth_center_pp','predicted_center_pp')}
        for a in names} for m in months}
    x=np.arange(len(months));dates=[f'{m//100}-{m%100:02}' for m in months]
    fig,axes=plt.subplots(1,2,figsize=(14,4.8))
    for ax,key,title in zip(axes,['center_mae_pp','w1_pp'],['各月群体中位数误差','各月跨人分布距离']):
        for a in names:
            marker,line=STYLES[a];ax.plot(x,[monthly[m][a][key] for m in months],marker=marker,linestyle=line,
                color=COLORS[a],label=LABELS[a],linewidth=1.8)
        ax.set_xticks(x,dates,rotation=30,ha='right');ax.set_xlabel('目标调查月份（离散月份，非连续月线性趋势）')
        ax.set_ylabel('百分点（越低越好）');ax.set_title(title);ax.grid(axis='y',alpha=.13);ax.legend(fontsize=9,ncol=2)
    fig.tight_layout();fig.savefig(dest/'figures/monthly.png',dpi=170);plt.close(fig)
    groups=s['groups']['prior'];bands=[b for b in PRIOR if b in groups and groups[b]['metrics']]
    fig,axes=plt.subplots(1,2,figsize=(14,4.8));gx=np.arange(len(bands))
    truth=[groups[b]['metrics'][arms[0]]['truth_mean_pp'] for b in bands]
    axes[0].plot(gx,truth,'k*-',linewidth=2.2,label=LABELS['human'])
    for a in names:
        marker,line=STYLES[a]
        axes[0].plot(gx,[groups[b]['metrics'][a]['model_mean_pp'] for b in bands],marker=marker,
            linestyle=line,color=COLORS[a],label=LABELS[a],linewidth=1.8)
        axes[1].plot(gx,[groups[b]['metrics'][a]['w1_pp'] for b in bands],marker=marker,
            linestyle=line,color=COLORS[a],label=LABELS[a],linewidth=1.8)
    axes[0].set_title('不同旧信念人群：本期预期水平');axes[0].set_ylabel('组内个人预期均值（%）')
    axes[1].set_title('不同旧信念人群：分布拟合误差');axes[1].set_ylabel('W1（百分点，越低越好）')
    for ax in axes:
        ax.set_xticks(gx,[PRIOR_LABELS[b] for b in bands]);ax.set_xlabel('本人上期Q9预期组');ax.legend(fontsize=8,ncol=2);ax.grid(axis='y',alpha=.13)
    fig.tight_layout();fig.savefig(dest/'figures/prior_groups.png',dpi=170);plt.close(fig)
    rows=''.join('<tr><td>'+LABELS[a]+'</td>'+''.join('<td>'+f(metrics[a][k])+'</td>' for k in
        ('center_mae_pp','center_rmse_pp','w1_pp','delta_w1_pp','across_person_iqr_pp','personal_mae_pp'))+'</tr>' for a in names)
    alternatives=s['comparisons'];cards=[]
    for c in alternatives:
        d=c['candidate_minus_base'];passed=c['development_screen_passed'];nwin=sum(v['w1_pp']<=0 for v in c['monthly'].values())
        cards.append(f'''<section class="contrast"><h3>{LABELS[c['candidate']]} 对 {LABELS[c['base']]}</h3>
<p>W1差 <strong>{d['w1_pp']:+.3f} pp</strong>；中位数MAE差 <strong>{d['center_mae_pp']:+.3f} pp</strong>。差为负表示候选更好。</p>
<p>W1有{nwin}/8个月不增；两遍W1差分别为{c['generation']['1']['w1_pp']:+.3f}、{c['generation']['2']['w1_pp']:+.3f}pp。预登记的分布改善筛选：<strong>{'通过，仍需分配种子确认' if passed else '未通过'}</strong>。工作配置的取舍另见下文，不改写本筛选。</p></section>''')
    best=min(arms,key=lambda a:metrics[a]['w1_pp'])
    passed=[c for c in alternatives if c['development_screen_passed']]
    verdict=('至少一项达到预登记的开发筛选，需第二分配种子确认后再决定默认配置。' if passed else
             '本轮没有配置同时达到预登记的分布改善条件；局部收益与敏感性均须保留，工作配置另行决定。')
    adoption_html=''
    if adoption is not None:
        verdict=html.escape(adoption['summary'])
        adoption_html='<p class="note">工作配置取舍于2026-10-22根据用户反馈更新；原统计、预登记筛选及历史运行不变。<a href="adoption_decision.json">取舍记录</a>。采纳不等于已证实稳定改善微观结构。</p>'
    pair=s['actual_pair_support']['random_quantity_minus_fixed_8']
    pm=pair['metrics']
    available=s['actual_available'];av=available['metrics']
    avrows=''.join('<tr><td>'+LABELS[a]+'</td>'+''.join('<td>'+f(av[a][k])+'</td>' for k in ('center_mae_pp','w1_pp','delta_w1_pp'))+'</tr>' for a in names)
    mrows=''.join('<tr><td>'+f'{m//100}-{m%100:02}'+'</td>'+''.join('<td>'+f(monthly[m][a]['center_mae_pp'])+'</td>' for a in names)+'</tr>' for m in months)
    sparse_rows=[]
    for name,g in s['groups']['six_cell'].items():
        sparse_rows.append('<tr><td>'+html.escape(GRID_LABELS.get(name,'信息不足'))+'</td><td>'+str(g['person_months'])+'</td><td>'+str(g['unique_persons'])+'</td><td>'+str(len(g['sparse_cells']))+'</td>'+''.join('<td>'+f(g['metrics'].get(a,{}).get('w1_pp'))+'</td>' for a in arms)+'</tr>')
    fee=s['runtime'];reuse=s['reuse'];fallback=s['fallback_counts']
    q8={a:s['baseline_comparable_q8'][a]['aggregate_equal_month_repeat_cells'] for a in arms}
    q8['carry']=s['carry_q8']['aggregate_equal_month_repeat_cells']
    q8rows=''.join('<tr><td>'+LABELS[a]+'</td>'+''.join('<td>'+f(q8[a][k])+'</td>' for k in
        ('q8_center_mae_pp','q8_cross_section_w1_pp','q8_person_mae_pp'))+'</tr>' for a in names)
    fallbacktext='、'.join(LABELS[a]+str(fallback[a])+'个比较位置' for a in arms)
    intervals=html.escape(json.dumps(dict(primary=s['paired_intervals_actual_support'],additional=s['additional_intervals_actual_support']),ensure_ascii=False,indent=2))
    epochs=''.join('<p>'+label+'：'+ '；'.join(LABELS[a]+' MAE '+f(s['epochs'][key]['metrics'][a]['center_mae_pp'])+' / W1 '+f(s['epochs'][key]['metrics'][a]['w1_pp']) for a in names)+'</p>' for key,label in [('earlier_four','较早四期'),('later2025_four','2025年4/6/8/10月')])
    css='''body{font-family:"Times New Roman","Kaiti SC","STKaiti","KaiTi",serif;background:#faf9f6;color:#25282c;margin:0;line-height:1.75}main{max-width:1150px;margin:auto;padding:28px 22px}h1{font-size:29px}h2{font-size:23px;margin-top:32px}h3{font-size:19px}a{color:#7437aa}img{width:100%;height:auto}.lead{border-left:4px solid #c76800;background:#f1ebe1;padding:15px 20px}.note,figcaption{color:#625f59;font-size:14px}.contrasts{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.contrast{padding:10px 16px;background:white;border:1px solid #ddd9d0}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:9px;border-bottom:1px solid #d9d6ce;text-align:right}th:first-child,td:first-child{text-align:left}pre{white-space:pre-wrap;font-size:12px}details{margin:15px 0}nav{display:flex;gap:18px;flex-wrap:wrap}@media(max-width:750px){main{padding:18px 12px}.contrasts{grid-template-columns:1fr}h1{font-size:25px}}@media print{figure,.contrast{break-inside:avoid}}'''
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V3.2新闻数量与主题分配验证</title><style>{css}</style><main>
<nav><a href="../v32_new2025_results/index.html">此前V3.2验证</a><a href="../news_matching_plan_20261022.md">本轮设计</a><a href="summary.json">聚合结果JSON</a></nav>
<h1>新闻接触量与主题匹配：V3.2八期验证</h1>
<p class="lead"><strong>{verdict}</strong><br>完整运行组合中，跨人W1最低的是“{LABELS[best]}”。最低点估计不等于稳健的机制证据；以下同时报告中心、分布、时期和重复敏感性。</p>
{adoption_html}
<p>四个较早月份各96人、四个2025年月各192人，共1152个人月。固定8篇、随机3/8/20篇、人口匹配数量、随机量＋均匀主题四组，各两遍；模型、价格、个人先验及问卷不变。固定目标人群主口径可评价{r['person_months']}个人月、{r['unique_persons']}名不同受访者。</p>
<p class="note">所有图和主表使用设计权重，月内计算后对八个月/两遍等权。Q9个人密度均值的跨人中位数，不是Q8，也不是全国官方headline。固定人群口径含显式上期后备，不将后备当新模型回答。</p>
<p class="note">随机量的平均收益尚非稳定确认：第一遍中心MAE改善0.054pp，第二遍增加0.002pp；近期2025四期由0.108变为0.124pp，只有一个数量分配种子。近乎不变的总体W1不应自动否决工作采纳，但也不能据此证明无代价或每期都更好。</p>
<h2>1. 数量分配和主题加权分别产生了什么影响？</h2><div class="contrasts">{''.join(cards)}</div>
<figure><img src="figures/overall.png" alt="各组固定人群中位数误差、分布W1和跨人IQR"><figcaption>来源：冻结八期输入与完成的回答/计分缓存，2020-09至2025-10抽样月份；IQR虚线为同人群真人，不是误差下限。</figcaption></figure>
<div class="scroll"><table><thead><tr><th>配置</th><th>中心MAE</th><th>中心RMSE</th><th>跨人W1</th><th>变化W1</th><th>跨人IQR</th><th>个人MAE</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="note">单位均为百分点。前三项和个人MAE越低越好；IQR与真人接近才有意义。均匀主题组只在相同随机数量下取消相关加权，不代表已经运行“人口数量＋均匀主题”。不能把不同对照中最好的部件直接叠加。</p>
<details><summary>Q8点预期独立结果</summary><div class="scroll"><table><thead><tr><th>配置</th><th>Q8群体中位数MAE</th><th>Q8跨人W1</th><th>Q8个人MAE</th></tr></thead><tbody>{q8rows}</tbody></table></div><p class="note">单位pp；Q8支持独立于Q9，无效Q9不导致有效Q8被删除。表中{s['baseline_comparable_q8_person_months']}个人月另需有合法上期Q8才能比较照抄，所有当前模型有效Q8仍保留在聚合JSON；不为缺失的上期值造数。</p></details>
<h2>2. 平均变化是否由少数月份推动？</h2><figure><img src="figures/monthly.png" alt="八个月各组中位数误差与W1"><figcaption>来源同上；各点平均两遍各自误差，不是对平均预测先算误差。横轴为离散月份。</figcaption></figure>
<details><summary>逐月中位数MAE及两段时期</summary><div class="scroll"><table><thead><tr><th>月份</th>{''.join('<th>'+LABELS[a]+'</th>' for a in names)}</tr></thead><tbody>{mrows}</tbody></table></div>{epochs}</details>
<h2>3. 哪些旧信念人群受到影响？</h2><figure><img src="figures/prior_groups.png" alt="按上期预期分组的当前水平和分布误差"><figcaption>来源：固定人群、既有上期信念四档；每月/遍先计算再平均。各组有不同人数，稀疏格仅作描述。</figcaption></figure>
<details><summary>学历×就业六格支持与分布距离</summary><p class="note">任一月/遍N＜10或ESS＜10为稀疏；不同人数量按匿名受访者编号去重，重复生成不增加人口。“未在职”包含不同非就业状态，不将其视为同一种家庭经历。</p><div class="scroll"><table><thead><tr><th>六格类别</th><th>个人月</th><th>不同人</th><th>稀疏格</th>{''.join('<th>'+LABELS[a]+' W1</th>' for a in arms)}</tr></thead><tbody>{''.join(sparse_rows)}</tbody></table></div></details>
{variance_html}<h2>4. 缺失是否改变了判断？</h2><p>固定目标人群Q9后备：{fallbacktext}。Q8只有自身无效才回退，未因Q9失败一并删除。</p>
<p><strong>直接比较随机量与固定8篇，应优先看这两组都有可用回答的{pair['person_months']}个人月：</strong>中心MAE {f(pm['fixed_8']['center_mae_pp'])}→{f(pm['random_quantity']['center_mae_pp'])}，RMSE {f(pm['fixed_8']['center_rmse_pp'])}→{f(pm['random_quantity']['center_rmse_pp'])}，W1 {f(pm['fixed_8']['w1_pp'])}→{f(pm['random_quantity']['w1_pp'])}。中心误差仍有改善，分布距离近乎不变。</p>
<details><summary>四组均完整的更严格子样本：仅作缺失敏感性检查</summary><p>所有组/两遍共同实际输出剩{available['person_months']}个人月、{available['unique_persons']}人。此处随机与固定的MAE排序反转，但排除了另外两组缺失的家庭，不能取代上面的直接两组比较，也不能据此判定随机量无收益。</p>
<div class="scroll"><table><thead><tr><th>实际共同支持配置</th><th>中心MAE</th><th>跨人W1</th><th>变化W1</th></tr></thead><tbody>{avrows}</tbody></table></div>
<p class="note">不同支持上的模型和照抄始终配对。两种口径不能各选最低值拼成成绩。已另外保存三项两两比较支持、每遍、原答/归一化、删一月和地区/年龄/收入分组，见聚合JSON。</p></details>
<details><summary>实际共同支持的配对区间</summary><p class="note">使用共享家庭聚类重抽样，固定本次八个月；是未作多重比较校正的开发区间，不代表时间外推，也不等同固定人群后备口径的区间。</p><pre>{intervals}</pre></details>
<h2>5. 实施范围、调用与边界</h2><p>共{reuse['total_comparison_slots']:,}个比较位置，精确引用旧调用{reuse['archived_reused_slots']:,}个位置（{reuse['archived_unique_calls_reused']:,}次不同旧调用），本批相同提示共享{reuse['within_batch_alias_slots']:,}个位置；实际新增<strong>{fee['new_calls']:,}次请求</strong>。API报告新增<strong>${fee['api_reported_new_cost_usd']:.4f}</strong>，含未知计费失败的保守记账${fee['combined_spent_or_reserved_usd']:.4f}，授权上限${s['dispatch_budget_usd']:.0f}。调用耗时{fee['seconds']/60:.1f}分钟，自动重试{fee['automatic_retries']}次。</p>
<p>DeepSeek V3.2，OpenRouter→固定SiliconFlow FP8；温度0.5、关闭思考、JSON、最多1024输出token。前32次技术检查通过后自动由最多8并发升至16并发。旧失败和原答保留；合计为正的非负十档概率按原定规则等比例归一化。</p>
<p class="note">这是有本人真实上期信念的A线条件重建；八个月均曾用于其他项目研究，不称完全盲测。只有一个新闻分配种子，两遍是生成重复。外部人口关注模型预测力较弱，数量是实验设定；未测本人真实阅读量。旧控制与新调用并非同时完成，同名模型和固定路由不能证明托管权重绝不变化。人口/主题对照的收益若存在，仍须第二分配种子确认。</p>
<p class="note">生成于{datetime.now(timezone.utc).isoformat()}；原始个人提示与回答只保存在私有outputs，本页及JSON仅含聚合。{s['weighted_metric_crosschecks']}项主要加权统计交叉核对通过，报告生成不新增API、不重新拟合Q9。</p></main></html>'''
    (dest/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (dest/'index.html').write_text(page)
    return dict(report=str(dest/'index.html'),screen_passed=[c['candidate'] for c in passed])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--dest',type=Path,required=True)
    p.add_argument('--decision',type=Path,help='Separate later working-configuration decision; never changes frozen scores or screen')
    a=p.parse_args();print(publish(a.source,a.dest,a.decision))
