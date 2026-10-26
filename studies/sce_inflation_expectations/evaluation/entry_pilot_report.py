"""Small entry-pilot reading page in the established project HTML style."""
from html import escape
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager

from . import cognition as shared
from .metrics import quantile
from ..experiments.frozen_batch import ROOT, read_json, dump
from ..experiments.entry_initialization_pilot import ARM

BASE='monthly_past_reference'
COLORS={ARM:'#c76800',BASE:'#7437aa','human':'#111111'}
GROUPS={'entrant':'首次受访者','returning':'真实上月回访者'}


def number(value):
    return '不可计算' if value is None else f'{value:.3f}'


def primary(view,arm=ARM):
    return view['arms'][arm]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells']


def publish(source,dest):
    source,dest=Path(source).resolve(),Path(dest).resolve()
    if dest.exists():raise ValueError('Fresh report folder required')
    s=read_json(source/'summary.json')
    if s['status']!='completed' or not s['receipt']['actual_model_results']:
        raise ValueError('Completed actual-model evaluation required')
    cases=read_json(source/'cases_private.json')
    months=sorted({r['month'] for r in cases});repeats=sorted({r['repeat'] for r in cases})
    dates=[f'{m//100}-{m%100:02}' for m in months];x=np.arange(len(months))
    dest.mkdir(parents=True);(dest/'figures').mkdir()
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':11,
                         'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,3,figsize=(14,8.2))
    for row,(group,label) in enumerate(GROUPS.items()):
        view=s['groups'][group]['fixed_roster']
        for col,(key,title) in enumerate([
                ('q9_center_mae_pp','人群中位数MAE：越低越好'),
                ('cross_section_w1_pp','跨人W1：越低越好'),
                ('cross_person_iqr_pp','跨人IQR：应接近真人')]):
            ax=axes[row,col];arms=[BASE,ARM]
            values=[primary(view,a)[key] for a in arms]
            bars=ax.bar([0,1],values,color=[COLORS[a] for a in arms],width=.55)
            ax.bar_label(bars,fmt='%.3f',padding=5)
            ax.set_xticks([0,1],['保留合成起点' if group=='entrant' else '照抄本人上期','V3.2模拟'])
            if key=='cross_person_iqr_pp':
                truth=primary(view)['real_cross_person_iqr_pp']
                ax.axhline(truth,color='black',linestyle='--',label=f'真人 {truth:.3f}')
                ax.set_ylim(0,max(*values,truth)*1.28+.05);ax.legend()
            ax.set_title(label+' · '+title,fontsize=11);ax.set_ylabel('百分点（pp）')
            ax.set_xlabel('相同人群、相同权重');ax.grid(axis='y',alpha=.12);ax.margins(y=.25)
    fig.suptitle('三期新人小试：月内设计加权，三个月及两遍等权汇总',fontsize=14)
    fig.tight_layout(rect=(0,0,1,.96));fig.savefig(dest/'figures/overall.png',dpi=170);plt.close(fig)
    series={};fig,axes=plt.subplots(2,2,figsize=(13,8.1))
    for row,(group,label) in enumerate(GROUPS.items()):
        rows=[r for r in cases if r['survey_entry_status']==group and shared.finite(r['survey_weight']) and r['survey_weight']>0]
        support=shared._common_person_months(rows,[ARM,BASE],repeats,'q9')
        data={a:[] for a in [ARM,BASE,'human']}
        for month in months:
            levels={a:[] for a in data};counts=[]
            for rep in repeats:
                cell=shared._cell_rows(rows,month,rep,support);w=[r['survey_weight'] for r in cell]
                counts.append(len(cell))
                for a in data:
                    values=[r['real']['q9_mean'] if a=='human' else r['arms'][a]['mean'] for r in cell]
                    levels[a].append(quantile(values,w,.5))
            for a in data:
                data[a].append({'month':month,'n':counts[0],'center_pct':float(np.mean(levels[a])),
                                'repeat_min_pct':min(levels[a]),'repeat_max_pct':max(levels[a])})
        for a,marker,line in [(BASE,'^','-.'),(ARM,'o','-'),('human','s','--')]:
            label_a={'human':'真人本期',BASE:'合成起点' if group=='entrant' else '本人上期',ARM:'V3.2模拟'}[a]
            values=[r['center_pct'] for r in data[a]]
            axes[row,0].plot(x,values,color=COLORS[a],marker=marker,linestyle=line,label=label_a,linewidth=2)
            for xx,v in zip(x,values):axes[row,0].annotate(f'{v:.2f}',(xx,v),xytext=(3,6 if a!=BASE else -14),textcoords='offset points',fontsize=8)
        for a,marker,line in [(BASE,'^','-.'),(ARM,'o','-')]:
            values=[primary(s['groups'][group]['by_month'][str(m)],a)['cross_section_w1_pp'] for m in months]
            axes[row,1].plot(x,values,color=COLORS[a],marker=marker,linestyle=line,label='保留起点' if a==BASE else 'V3.2模拟',linewidth=2)
            for xx,v in zip(x,values):axes[row,1].annotate(f'{v:.2f}',(xx,v),xytext=(3,7 if a==ARM else -14),textcoords='offset points',fontsize=8)
        axes[row,0].set_title(label+'：本期水平与起始水平');axes[row,0].set_ylabel('人群中位数（%）')
        axes[row,1].set_title(label+'：逐月分布距离');axes[row,1].set_ylabel('W1（百分点，越低越好）')
        for ax in axes[row]:
            ax.set_xticks(x,[f'{d}\nQ9 N={data[ARM][i]["n"]}' for i,d in enumerate(dates)])
            ax.set_xlabel('三个诊断月份（并非连续月份）');ax.legend(fontsize=9);ax.grid(axis='y',alpha=.12);ax.margins(y=.2)
        series[group]=data
    fig.tight_layout();fig.savefig(dest/'figures/monthly.png',dpi=170);plt.close(fig)
    table=[];details=[];verdict=[];q8table=[];support_notes=[]
    for group,label in GROUPS.items():
        g=s['groups'][group];view=g['fixed_roster'];model=primary(view);base=primary(view,BASE)
        dcenter=model['q9_center_mae_pp']-base['q9_center_mae_pp'];dw1=model['cross_section_w1_pp']-base['cross_section_w1_pp']
        verdict.append(f'<li><strong>{label}：</strong>相对保留起点，中心MAE变化 {dcenter:+.3f}pp，W1变化 {dw1:+.3f}pp（负值表示改善）。</li>')
        for arm,title in [(BASE,'合成起点' if group=='entrant' else '本人上期'),(ARM,'V3.2模拟')]:
            q=primary(view,arm);err=view['arms'][arm]['auxiliary_survey_weighted']['q9']['center_headline_errors']
            vals=[q['q9_center_mae_pp'],err['rmse_pp'],q['individual_density_mean_mae_pp'],q['cross_section_w1_pp'],
                  q['cross_person_iqr_pp'],q['real_cross_person_iqr_pp']]
            table.append('<tr><td>'+label+'</td><td>'+title+'</td><td>'+str(view['q9_person_months'])+'</td>'+''.join('<td>'+number(v)+'</td>' for v in vals)+'</tr>')
        sensitivity=g['usable_outputs'];sm=primary(sensitivity)
        eq=view['arms'][ARM]['q9']['aggregate_equal_month_repeat_cells']
        group_rows=[r for r in cases if r['survey_entry_status']==group and shared.finite(r['survey_weight']) and r['survey_weight']>0]
        model_support=shared._common_person_months(group_rows,[ARM],repeats,'q9')
        shared_support=shared._common_person_months(group_rows,[ARM,BASE],repeats,'q9')
        effective=[]
        for month in months:
            weights=[r['survey_weight'] for r in shared._cell_rows(group_rows,month,repeats[0],shared_support)]
            effective.append(sum(weights)**2/sum(w*w for w in weights))
        support_notes.append(f'{label}：单看本期真人与模型Q9可计分{len(model_support)}个人月；'
                             f'与起点同支持比较为{len(shared_support)}，逐月有效样本量约{min(effective):.1f}—{max(effective):.1f}。')
        for arm,title in [(BASE,'保留合成起点' if group=='entrant' else '照抄本人上期'),(ARM,'V3.2模拟')]:
            q8=view['arms'][arm]['auxiliary_survey_weighted']['q8']['aggregate_equal_month_repeat_cells']
            q8table.append('<tr><td>'+label+'</td><td>'+title+'</td><td>'+str(view['q8_person_months'])+'</td>'+
                           ''.join('<td>'+number(q8[k])+'</td>' for k in ['q8_center_mae_pp','q8_person_mae_pp','q8_cross_section_w1_pp'])+'</tr>')
        text=(f'{label}：固定Q9支持{view["q9_person_months"]}个人月，Q8支持{view["q8_person_months"]}个人月；'
              f'仅有效回包共同支持{sensitivity["q9_person_months"]}个人月，中心MAE {number(sm["q9_center_mae_pp"])}、W1 {number(sm["cross_section_w1_pp"])}。'
              f'等人权重中心MAE {number(eq["q9_center_mae_pp"])}、W1 {number(eq["cross_section_w1_pp"])}。'
              f'模型/真人个人概率内部IQR {number(model["individual_density_iqr_mean_pp"])}/{number(model["real_individual_density_iqr_mean_pp"])}pp，'
              f'通缩档全零比例 {100*model["zero_deflation_rate"]:.1f}%/{100*model["real_zero_deflation_rate"]:.1f}%。')
        details.append('<p>'+text+'</p>')
    fee=s['receipt'];header=''.join('<th>'+x+'</th>' for x in ['人群','对象','Q9个人月','中心MAE','中心RMSE','个人MAE','W1','跨人IQR','真人IQR'])
    en=s['groups']['entrant']['fixed_roster'];re=s['groups']['returning']['fixed_roster']
    enw=primary(en);enb=primary(en,BASE)
    q8center=lambda view,arm:view['arms'][arm]['auxiliary_survey_weighted']['q8']['aggregate_equal_month_repeat_cells']['q8_center_mae_pp']
    text=f'''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>新受访者近期起点小试</title>
<style>body{{margin:0;background:#faf8f3;color:#242424;font-family:"Times New Roman","Kaiti SC",STKaiti,KaiTi,serif;font-size:19px;line-height:1.75}}main{{max-width:1160px;margin:auto;padding:40px 28px}}h1{{font-size:34px;line-height:1.35}}h2{{font-size:26px;margin-top:40px}}.note{{background:#f0ebe1;padding:17px 22px}}figure{{margin:26px 0}}img{{width:100%;height:auto}}figcaption,small{{font-size:15px;color:#555}}.scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:16px;white-space:nowrap}}td,th{{padding:10px;text-align:right;border-bottom:1px solid #ddd}}td:first-child,th:first-child{{text-align:left}}summary{{cursor:pointer;font-weight:bold}}a{{color:#0078b5}}@media(max-width:700px){{main{{padding:22px 15px}}body{{font-size:17px}}h1{{font-size:28px}}}}@media print{{details{{display:block}}main{{padding:0}}figure{{break-inside:avoid}}}}</style><main>
<p>结果整理：2026-10-23 · DeepSeek V3.2 / SiliconFlow FP8 · 历史条件重建诊断</p><h1>新受访者没有本人历史时，近期合成起点能否支持模拟？</h1>
<p class="note">本轮完成三个诊断月份、每月24新人＋24回访者、各两遍。分别检查起始信念经过LLM更新后，中心和分布如何变化；不是全国准确度，也不是初始化方法的因果实验。82个月大批次继续暂停。</p>
<h2>一、实验设计</h2><p>新人用相邻上月匿名首次受访者的联合Q8/Q9构造起点；回访者保留本人真实相邻上月回答和更早摘要。人口、新闻、价格和政策模板原样复用。三期为2021-09、2022-06、2025-06，全部是已接触过数据的月份。每组24人的抽样波动较大，两遍只是相同人的重复生成。</p>
<p>两阶段抽样权重保持原设计；不使用本期答案挑人或调参。新人“保留起点”是统计基线，不能称照抄其真实上月信念。回访者的人口和信息也可能不同，两组成绩差不能归因于初始化。</p>
<h2>二、主要结果</h2><ul>{''.join(verdict)}</ul><figure><img src="figures/overall.png" alt="新人和回访者分别比较模型与起点的中心MAE、W1和跨人IQR"><figcaption>来源：冻结评价缓存。每月设计加权，三期×两遍等权；误差单位为百分点。IQR与真人比较，并非越大越好。</figcaption></figure>
<div class="scroll"><table><thead><tr>{header}</tr></thead><tbody>{''.join(table)}</tbody></table></div>
<p>中心来自每人Q9十档拟合密度的均值，再取跨人的加权中位数。个人MAE描述模拟值与该人本期回答的差距；随机合成起点没有识别新人的个人潜在信念，因此优先解读群体水平和分布。</p>
<h2>三、哪些月份出现差距？</h2><figure><img src="figures/monthly.png" alt="两类人群逐月的真人、起点和模型水平及W1"><figcaption>来源同上。水平曲线为两遍中位数的均值；主MAE每遍先取绝对误差再平均，二者不应直接互算。横轴为三个分散月份。</figcaption></figure>
<h2>四、这轮能够说明什么？</h2><p>近期供体解决了旧方案跨多年借用信念的问题，但供体的信念仍不是新人的真实先验；上期总体一致也不能保证本期分布一致。LLM更新是否压缩或扩大差异，应结合起点、真人与模型三者逐月比较。</p>
<p><strong>本轮新人中心MAE仅小幅下降，W1在三个诊断月均上升；两遍及仅有效回包下也没有消除分布差距。</strong>新人起点的跨人IQR约{number(enb['cross_person_iqr_pp'])}pp，真人{number(enw['real_cross_person_iqr_pp'])}pp，模型{number(enw['cross_person_iqr_pp'])}pp：起点偏宽，但模型又收缩到真人宽度以下。需要分别讨论供体分配的抽样误差与模型更新中的集中倾向，不能只归结为起点没有差异。</p>
<p>本轮没有“新人不加起点”的随机对照，也没有改变供体或新闻分配种子。即使优于保留起点，也不能独立识别合成先验或新闻的贡献；即使较差，也不能推出新人没有信念惯性。三个月的小试不能决定最终全国误差或贝叶斯扩展参数。</p>
<h2>五、Q8点预期：新人组未得到改善</h2><div class="scroll"><table><thead><tr><th>人群</th><th>对象</th><th>Q8个人月</th><th>中心MAE</th><th>个人MAE</th><th>W1</th></tr></thead><tbody>{''.join(q8table)}</tbody></table></div>
<p>Q8是单独的问题，不与Q9混算。新人Q8中心MAE由{number(q8center(en,BASE))}升至{number(q8center(en,ARM))}pp，回访者由{number(q8center(re,BASE))}降至{number(q8center(re,ARM))}pp；所以不能把Q9中心的小幅收益概括成新人问卷整体改善。个体误差受宽分布和极端回答影响，样本很小，不外推到全部首次受访者。</p>
<details><summary>有效样本、其他指标与敏感性</summary>{''.join(details)}<p>{'<br>'.join(support_notes)}</p><p>主表要求真人、模型及起点均可计分。回访者有一名本期Q9可计分但起点计分不足以进入该共同口径，故主表为69而非70；不是更换受访者。Q8按自己的合法性独立评价。有效样本量为权重集中度指标，不增加真实人数。完整逐月、逐遍统计见<a href="summary.json">聚合JSON</a>。</p></details>
<h2>六、调用与可复现性</h2><p>总尝试{fee['attempts']}次，281份可用回答、7次连接失败，均未补发；原16次与续272次账本保留。用户另授权仅续未发送位置，继续段最多32并发；原“16次全部成功”检查未通过的事实保留，不改成事后通过。1份概率回答按既定规则等比例归一化。API报告${fee['reported_cost_usd']:.4f}，含未知失败的保守记账${fee['spent_or_reserved_usd']:.4f}，上限$1.50。两段执行合计{fee['seconds']:.1f}秒，不含准备与分析。无自动重试、供应商回退或扩样。</p>
<p>有效输出敏感性与固定名单后备口径并列，后备状态不冒充新模型回答。本期答案只在隔离评价中读取；真值和旧起点直接复用冻结计分缓存，不重复拟合。</p>
<details><summary>复算入口与边界</summary><p>评价：scripts/evaluate_sce_entry_pilot.py evaluate；报告：scripts/report_sce_entry_pilot.py。使用新输出目录，已执行账本禁止重启。Core＋Normal扩展未包含在本轮；最终Core人数、贝叶斯模型与全量预算仍待明确。</p><p>评价缓存：{escape(str(source.relative_to(ROOT)))}。</p></details></main></html>'''
    (dest/'index.html').write_text(text,encoding='utf-8')
    dump(dest/'summary.json',s);dump(dest/'plot_series.json',series)
    return {'report':str((dest/'index.html').relative_to(ROOT)),'new_api_calls':0}
