"""Post-generation national evaluation of a fixed-cohort autonomous chain.

No new model calls, no re-estimation of combination weights, and no claims about
recent real-person W1 or IQR accuracy. Shared roots are identified explicitly.
"""
from collections import defaultdict
import csv
import json
from pathlib import Path

from .frozen_batch import ROOT, read_json as read, dump, sha
from .recent_b_recursion import checked, checkpoint, SOURCE
from ..evaluation.recent_b_readout import validate_catalog
from ..evaluation.metrics import distribution_summary, headline_errors
from ..evaluation.cognition import _score_bins


def evaluate(folder):
    folder=Path(folder).resolve();p,_=checked(folder)
    receipt=read(folder/'generation_receipt.json')
    if receipt['status']!='monthly_recursion_generation_complete' or not receipt['actual_model_results']:
        raise ValueError('Complete actual generation required; fixtures cannot be evaluated as model results')
    out=folder/'evaluation'
    if out.exists():raise ValueError('Keep the original evaluation; use a new output version for repairs')
    pe=ROOT/p['PE'];weights=read(pe/'weights_private.json');roots=read(pe/'root_answers_private.json')
    ids=sorted(roots);w=[weights[a]['analysis_weight'] for a in ids]
    cat=ROOT/p['target_catalog_evaluation_only'];validate_catalog(cat,p['months'])
    releases={r['reference_period']:r for r in read(cat)['headline_releases']}
    params=read(ROOT/p['parameter_source']);alpha=params['blends']['mse']['simulation_weight']
    # This cache is a deterministic function of the exact Q9 vector, not a
    # donor answer or a national target. Reuse never changes the new simulation.
    cachepath=SOURCE/'evaluation/scoring_cache_private.json'
    if sha(cachepath)!=read(SOURCE/'evaluation/manifest.json')['files_sha256'][cachepath.name]:
        raise ValueError('Exact-vector scorer cache changed')
    cache={tuple(r['bins']):r['score'] for r in read(cachepath)};newfits=0
    def score(state):
        nonlocal newfits
        bins=state['fields']['q9']['value'];key=tuple(bins)
        if key not in cache:cache[key]=_score_bins(bins);newfits+=1
        mean=cache[key]['mean']
        if mean is None:raise ValueError('Unscorable retained/model state; retain roster and investigate explicitly')
        return mean
    rootvalues=[score(roots[a]['state_after']) for a in ids];rootdesc=distribution_summary(rootvalues,w)
    independent=read(SOURCE/'evaluation/summary.json');independent_rows={str(r['month']):r for r in independent['monthly']}
    # Public anchors already sealed in the independently prepared B plan; no
    # current target is used in initialization or in the generation subprocess.
    sourcep=read(SOURCE/'package/protocol.json')
    plans={r['month']:r for r in read(ROOT/sourcep['population_preflight']/'monthly_input_plan.json')}
    persons=read(pe/'population_private.json');attrs={r['agent_id']:r['attributes'] for r in persons['personas']}
    previous_values=rootvalues;monthly=[];groups=[];sources={str(cat.relative_to(ROOT)):sha(cat)}
    for month in p['months']:
        current=roots if month==p['months'][0] else checkpoint(folder/'checkpoints'/month)[0]
        if set(current)!=set(ids) or any(r['month']!=month or r['agent_id']!=aid for aid,r in current.items()):
            raise ValueError('Fixed recursive identities changed')
        values=[score(current[a]['state_after']) for a in ids]
        q8=[current[a]['state_after']['fields']['q8']['value'] for a in ids]
        desc=distribution_summary(values,w);ref=month[:4]+'-'+month[4:];truth=releases[ref]
        if sha(ROOT/truth['source_file'])!=truth['source_sha256']:raise ValueError('National target source changed')
        sources[truth['source_file']]=truth['source_sha256'];anchor=plans[month]['last_public_national_anchor']['value_pp']
        changes=[x-y for x,y in zip(values,previous_values)]
        changed=[abs(x-y)>1e-9 for x,y in zip(values,previous_values)]
        total=sum(w)
        row=dict(month=month,truth_pp=truth['value_pp'],recursive_pp=desc['median_pp'],anchor_pp=anchor,
            root_retention_pp=rootdesc['median_pp'],fixed_blend_pp=(1-alpha)*anchor+alpha*desc['median_pp'],
            independently_initialized_B_pp=independent_rows[month]['sim_pp'],
            simulated_cross_person_iqr_pp_descriptive=desc['iqr_pp'],simulated_q8_median_pp_descriptive=distribution_summary(q8,w)['median_pp'],
            simulated_weighted_mean_abs_monthly_change_pp=sum(abs(v)*a for v,a in zip(changes,w))/total,
            simulated_weight_share_changing=sum(a for v,a in zip(changed,w) if v)/total,
            simulated_weighted_mean_abs_root_drift_pp=sum(abs(v-r)*a for v,r,a in zip(values,rootvalues,w))/total,
            q8_retained_technical_failure=sum(not current[a]['state_after']['transition']['field_updated_from_model']['q8'] for a in ids),
            q9_retained_technical_failure=sum(not current[a]['state_after']['transition']['field_updated_from_model']['q9'] for a in ids),
            n_fixed=512,shared_reused_root=month==p['months'][0])
        if row['shared_reused_root']:
            row['simulated_weight_share_changing']=None;row['simulated_weighted_mean_abs_monthly_change_pp']=None
        monthly.append(row)
        for dim in ('education_group','numeracy','age_group','household_income_band'):
            bins=defaultdict(list)
            for aid,value,weight in zip(ids,values,w):bins[str(attrs[aid].get(dim) or 'unknown')].append((value,weight))
            for level,rs in sorted(bins.items()):
                groups.append(dict(month=month,dimension=dim,level=level,simulation_only=distribution_summary([x[0] for x in rs],[x[1] for x in rs])))
        previous_values=values
    families=('recursive_pp','anchor_pp','root_retention_pp','fixed_blend_pp','independently_initialized_B_pp')
    def metrics(rows):return {k:headline_errors([r[k] for r in rows],[r['truth_pp'] for r in rows]) for k in families}
    result=dict(status='completed_national_recursion_diagnostic',months=11,fixed_households=512,
        all_11_months=metrics(monthly),post_root_10_months_primary=metrics(monthly[1:]),monthly=monthly,
        combination_simulation_weight=alpha,coefficient_refit=False,new_API_calls=0,new_Q9_fits=newfits,
        limits=p['limits']+['The shared root month is not a new independent validation month.',
            'The auxiliary fixed blend adds an external public anchor after generation; autonomous raw drift is reported separately.',
            'Independent-B comparison changes both initialization and roster; it is not a paired causal estimate.'],
        source_sha256=sources,call_receipt=receipt)
    out.mkdir();dump(out/'summary.json',result);dump(out/'simulated_groups_descriptive_only.json',groups)
    dump(out/'scoring_cache_private.json',[dict(bins=list(k),score=v) for k,v in cache.items()])
    with (out/'monthly_national.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(monthly[0]));writer.writeheader();writer.writerows(monthly)
    make_figure(monthly,out)
    body='<h1>固定家庭的月度信念连续递推</h1><p>512户固定人口；2025年11月原答复用，其后10期使用本人上一模拟状态。无进出、无月度先验重新校准、无Normal代答。</p>'
    body+='<p>主要评价为根月之后10期；11期结果另列。真实微观资料不可得，IQR和分组仅描述模拟轨迹。</p><img src="monthly_recursion.png" alt="递推路径、误差和模拟分歧">'
    body+='<p>独立初始化B采用不同月份名单，比较仅供描述；固定组合沿用A线参数，没有使用近期真值拟权。</p><a href="summary.json">完整指标与限制</a> · <a href="monthly_national.csv">逐月数值</a>'
    (out/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>月度信念递推</title><style>body{max-width:1120px;margin:30px auto;padding:20px;font-family:"Times New Roman","Kaiti SC",serif;line-height:1.8;color:#242424}img{width:100%}p{text-indent:2em}</style>'+body+'</html>')
    dump(out/'manifest.json',dict(files_sha256={f.name:sha(f) for f in out.iterdir() if f.is_file()},new_api_calls=0))
    return {k:result[k] for k in ('status','all_11_months','post_root_10_months_primary','new_API_calls')}


def make_figure(rows,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC'],'axes.unicode_minus':False})
    fig,axes=plt.subplots(3,1,figsize=(11,9),sharex=True,layout='constrained');x=list(range(len(rows)))
    for key,label,color,style in [('truth_pp','官方SCE','#222222','-'),('recursive_pp','连续递推','#c06000','-'),
        ('anchor_pp','最后公开值','#777777','--'),('fixed_blend_pp','固定组合','#0066ac','-')]:
        axes[0].plot(x,[r[key] for r in rows],style,color=color,label=label,marker='o',markersize=3)
        if key!='truth_pp':axes[1].plot(x,[abs(r[key]-r['truth_pp']) for r in rows],style,color=color,label=label,marker='o',markersize=3)
    axes[2].plot(x,[r['simulated_cross_person_iqr_pp_descriptive'] for r in rows],color='#8c3b87',marker='o',label='模拟家庭之间IQR')
    for ax,label in zip(axes,['未来12个月通胀预期（%）','绝对误差（pp）','模拟分歧（pp，仅描述）']):
        ax.set_ylabel(label);ax.legend(frameon=False);ax.grid(axis='y',alpha=.15);ax.spines[['top','right']].set_visible(False)
    axes[2].set_xticks(x,[r['month'][:4]+'-'+r['month'][4:] for r in rows],rotation=40)
    fig.savefig(out/'monthly_recursion.png',dpi=180);plt.close(fig)
