"""Offline adapter for a completed recent-B run, including evaluation-only sources.

The frozen sender/evaluator, raw ledgers and worker failure receipts are untouched.
An explicit replacement release catalog fixes an omitted target; it never changes
inputs or forecasts. All distribution/group comparisons below are descriptive.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import json
import math

import numpy as np

from ..experiments.frozen_batch import ROOT, read_json, dump, sha
from ..experiments.state_continuity_execution import verify
from ..experiments import recent_b_evaluation as frozen
from .metrics import distribution_summary, paired_month_mae_interval

DIMENSIONS = ('age_group', 'education_group', 'household_income_band', 'numeracy',
              'employment_status', 'region', 'housing_tenure')
LABELS = {'age_group':'年龄', 'education_group':'学历', 'household_income_band':'家庭收入',
          'numeracy':'数理能力', 'employment_status':'就业', 'region':'地区', 'housing_tenure':'住房'}
VALUES = {'under 40':'40岁以下', 'Under 40':'40岁以下', '40 to 60':'40—60岁', 'over 60':'60岁以上', 'Over 60':'60岁以上',
          'high_school':'高中及以下', 'some_college':'部分大学教育', 'college_plus':'本科及以上',
          'college':'本科及以上', 'under_50k':'低于5万美元', '50k_to_100k':'5—10万美元',
          'over_100k':'高于10万美元', 'high':'高数理', 'low':'低数理', 'missing':'未知',
          'employed':'在职', 'unemployed':'失业', 'not_in_labor_force':'非劳动力',
          'retired':'退休', 'homemaker':'料理家务', 'student':'学生', 'disabled':'因健康无法工作', 'on_leave':'暂时休假',
          'owner':'自有住房', 'renter':'租房', 'other':'其他', 'South':'南部', 'West':'西部',
          'Midwest':'中西部', 'Northeast':'东北部'}


def records(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def validate_catalog(catalog, months):
    """Fail before density fitting or writing output if a target is absent."""
    rows = read_json(catalog)['headline_releases']
    refs = [r['reference_period'] for r in rows]
    if len(set(refs)) != len(refs):
        raise ValueError('Duplicate national release reference period')
    wanted = {str(m)[:4]+'-'+str(m)[4:] for m in months}
    if not wanted <= set(refs):
        raise ValueError('Missing target releases: '+', '.join(sorted(wanted-set(refs))))
    for r in rows:
        if r['reference_period'] in wanted and sha(ROOT/r['source_file']) != r['source_sha256']:
            raise ValueError('National release archive hash mismatch')


def validate_combined(folder):
    for name,digest in read_json(Path(folder)/'combined/manifest.json')['files_sha256'].items():
        if Path(name).name != name or sha(Path(folder)/'combined'/name)!=digest:
            raise ValueError('Combined ledger hash mismatch: '+name)


def technical_readout(folder):
    paths = sorted(folder.glob('main_stages/*/segment_*/calls_private.jsonl'))
    main_rows = [r for p in paths for r in records(p)]
    repair_paths = sorted(folder.glob('repair_stages/segment_*/calls_private.jsonl'))
    repair_rows = [r for p in repair_paths for r in records(p)]
    final = list(records(folder/'combined/positions_private.jsonl'))
    def updated(r, field):
        return r['state_after']['transition']['field_updated_from_model'][field]
    original_failed = {r['reuse_key']:r for r in main_rows if not all(updated(r,f) for f in ('q8','q9'))}
    repairs = {r['reuse_key']:r for r in repair_rows}
    latencies = [r['latency_ms']/1000 for r in main_rows+repair_rows if r.get('latency_ms') is not None]
    times = [datetime.fromisoformat(r['timestamp_utc'].replace('Z','+00:00')) for r in main_rows+repair_rows]
    end = datetime.fromisoformat(read_json(folder/'generation_receipt.json')['ended_at_utc'])
    return {'main_attempts':len(main_rows), 'repair_attempts':len(repair_rows),
            'main_technical_failures':len(original_failed),
            'main_failure_types':dict(Counter(r.get('error') or 'field_format_or_truncation' for r in original_failed.values())),
            'repair_successful_positions':sum(all(updated(r,f) for f in ('q8','q9')) for r in repair_rows),
            'repaired_fields':{f:sum(not updated(old,f) and updated(repairs[k],f)
                                   for k,old in original_failed.items() if k in repairs) for f in ('q8','q9')},
            'final_technical_complete':sum(all(updated(r,f) for f in ('q8','q9')) for r in final),
            'remaining_fields':{f:sum(not updated(r,f) for r in final) for f in ('q8','q9')},
            'returned_models':dict(Counter(r.get('returned_model') for r in main_rows+repair_rows if r.get('returned_model'))),
            'returned_providers':dict(Counter(r.get('returned_provider') for r in main_rows+repair_rows if r.get('returned_provider'))),
            'prompt_tokens':sum((r.get('usage') or {}).get('prompt_tokens',0) or 0 for r in main_rows+repair_rows),
            'completion_tokens':sum((r.get('usage') or {}).get('completion_tokens',0) or 0 for r in main_rows+repair_rows),
            'latency_median_seconds':float(np.median(latencies)), 'latency_p95_seconds':float(np.quantile(latencies,.95)),
            'generation_elapsed_minutes':(end-min(times)).total_seconds()/60,
            'normalizations_in_final':sum(r['state_after']['transition'].get('q9_proportional_normalization',False) for r in final),
            'original_worker_receipt':read_json(folder/'worker_receipt.json'),
            'generation_receipt':read_json(folder/'generation_receipt.json')}


def describe(rows):
    w=[r['weight'] for r in rows]
    sim=distribution_summary([r['center'] for r in rows],w)
    prior=distribution_summary([r['prior_center'] for r in rows],w)
    delta=distribution_summary([r['center']-r['prior_center'] for r in rows],w)
    uncertainty=[r for r in rows if r['uncertainty'] is not None]
    return {'n':len(rows), 'ess':sim['ess'], 'weight_sum':sum(w),
            'sim':sim, 'prior':prior, 'change':delta,
            'median_person_uncertainty_iqr_pp':distribution_summary(
                [r['uncertainty'] for r in uncertainty],[r['weight'] for r in uncertainty])['median_pp'] if uncertainty else None}


def summarize_group_months(groups):
    pooled=defaultdict(list)
    for r in groups:
        if r['supported']:
            pooled[r['dimension'],r['value']].append(r)
    result=[]
    for (dim,val),rs in sorted(pooled.items()):
        result.append({'dimension':dim, 'dimension_label':LABELS[dim], 'value':val,
                       'label':VALUES.get(val,val), 'eligible_months':len(rs),
                       'n_person_months':sum(r['n'] for r in rs),
                       'sim_median_pp':float(np.mean([r['sim']['median_pp'] for r in rs])),
                       'prior_median_pp':float(np.mean([r['prior']['median_pp'] for r in rs])),
                       'sim_iqr_pp':float(np.mean([r['sim']['iqr_pp'] for r in rs])),
                       'prior_iqr_pp':float(np.mean([r['prior']['iqr_pp'] for r in rs]))})
    return result


def analyze(folder, catalog, out, score_cache=None):
    folder,catalog,out=[Path(p).resolve() for p in (folder,catalog,out)]
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    p,_=verify(folder/'package')
    validate_combined(folder)
    validate_catalog(catalog,p['months'])
    out.mkdir(parents=True)
    original_score=frozen._score_bins
    cache={}
    if score_cache is not None:
        score_cache=Path(score_cache).resolve()
        expected=read_json(score_cache.parent/'manifest.json')['files_sha256'][score_cache.name]
        if sha(score_cache)!=expected:raise ValueError('Exact-vector scoring cache changed')
        cache={tuple(r['bins']):r['score'] for r in read_json(score_cache)}
    previous_keys=set(cache)
    def score(bins):
        key=tuple(bins)
        if key not in cache:cache[key]=original_score(list(key))
        return cache[key]
    previous_catalog=frozen.CATALOG
    frozen.CATALOG=catalog
    frozen._score_bins=score
    try:
        if (folder/'evaluation/summary.json').exists():
            evaluation=read_json(folder/'evaluation/summary.json')
            if evaluation['source_sha256'].get(str(catalog.relative_to(ROOT)))!=sha(catalog):
                raise ValueError('Existing evaluation catalog differs; preserve it and use a new version')
        else:
            # Explicit post-run binding: no frozen source or generation input is edited.
            evaluation=frozen.evaluate(folder)
    finally:
        frozen.CATALOG=previous_catalog
        frozen._score_bins=original_score
    print('National evaluation complete; calculating descriptive groups',flush=True)
    pop=read_json(ROOT/p['population_preflight']/'selected_proxy_population_private.json')
    rosters={m:{r['persona']['agent_id']:r for r in rs} for m,rs in pop.items()}
    initials={m:read_json(ROOT/p['input_templates']/m/'initial_states_private.json') for m in p['months']}
    individual=[];fallbacks=0
    for row in records(folder/'combined/positions_private.jsonl'):
        m,aid=row['month'],row['agent_id'];person=rosters[m][aid]
        before=initials[m][aid]['fields'];after=row['state_after']['fields']
        a,b=score(after['q9']['value']),score(before['q9']['value'])
        used_fallback=a['mean'] is None
        if used_fallback:a=b;fallbacks+=1
        if a['mean'] is None or b['mean'] is None:raise ValueError('Unscorable prior')
        individual.append(dict(month=m,agent_id=aid,attributes=person['persona']['attributes'],
                               weight=person['analysis_weight'],center=a['mean'],prior_center=b['mean'],
                               uncertainty=a['iqr'],q8=after['q8']['value'],density_fallback=used_fallback))
    monthly_desc=[];group_months=[];quantiles=[]
    for m in p['months']:
        rs=[r for r in individual if r['month']==m];desc=describe(rs)
        monthly_desc.append(dict(month=m,**desc))
        for dim in DIMENSIONS:
            cats=defaultdict(list)
            for r in rs:cats[str(r['attributes'].get(dim) or 'missing')].append(r)
            for value,sub in sorted(cats.items()):
                d=describe(sub)
                group_months.append(dict(month=m,dimension=dim,value=value,label=VALUES.get(value,value),
                                         supported=d['n']>=20 and d['ess']>=10,**d))
        # Every month's normalized mass is 1/11: it is not pooled raw source weights.
        total=sum(r['weight'] for r in rs)
        quantiles.extend(dict(center=r['center'],prior_center=r['prior_center'],weight=r['weight']/total)
                         for r in rs)
    modelerr=[r['sim_pp']-r['truth_pp'] for r in evaluation['monthly']]
    baseerr=[r['anchor_pp']-r['truth_pp'] for r in evaluation['monthly']]
    delta=paired_month_mae_interval(modelerr,baseerr,block_length=3,draws=5000,seed=20261025)
    technical=technical_readout(folder)
    summary={'status':'completed_offline_recent_B_readout', 'created_at_utc':datetime.now(timezone.utc).isoformat(),
             'evaluation':evaluation, 'technical':technical, 'monthly_distributions':monthly_desc,
             'group_months':group_months, 'group_summary':summarize_group_months(group_months),
             'paired_mae_interval':delta,
             'mean_monthly_sim_iqr_pp':float(np.mean([r['sim']['iqr_pp'] for r in monthly_desc])),
             'mean_monthly_prior_iqr_pp':float(np.mean([r['prior']['iqr_pp'] for r in monthly_desc])),
             'density_fallbacks':fallbacks, 'new_api_calls':0,
             'new_q9_fits':len(set(cache)-previous_keys),
             'interpretation':['Q9 center = weighted median across fitted individual density means; Q8 is separate.',
                               'Simulated dispersion and subgroup patterns lack recent micro truth; not W1/IQR accuracy.',
                               'Prior refers to synthetic older donors calibrated to past national values, not true individual beliefs.',
                               'Each month weighted internally, months equally averaged; group month support n>=20 and ESS>=10.',
                               '11 dependent months, one generation; block interval is exploratory conditional uncertainty.',
                               'Frozen combination simulation share remains 0; no fitting on recent targets.'],
             'sources':{str(catalog.relative_to(ROOT)):sha(catalog),
                        str((folder/'combined/manifest.json').relative_to(ROOT)):sha(folder/'combined/manifest.json'),
                        str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),
                        str(Path(frozen.__file__).relative_to(ROOT)):sha(Path(frozen.__file__))}}
    if score_cache is not None:summary['sources'][str(score_cache.relative_to(ROOT))]=sha(score_cache)
    (out/'readout_source_snapshot.py').write_bytes(Path(__file__).read_bytes())
    dump(out/'summary.json',summary)
    dump(out/'scoring_cache_private.json',[dict(bins=list(k),score=v) for k,v in cache.items()])
    dump(out/'individual_descriptive_private.json',individual)
    rows=evaluation['monthly']
    with (out/'monthly_national.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    # The original failure receipt stays intact; a new receipt documents offline recovery.
    dump(out/'evaluation_recovery.json',dict(status='completed_offline_only',
         original_failure=technical['original_worker_receipt'], new_api_calls=0,
         catalog=str(catalog.relative_to(ROOT)), reason='Frozen catalog omitted 2026-09; added official first release, no forecast changes',
         frozen_generation_package_unchanged=True))
    make_figures(summary,individual,out)
    make_html(summary,out)
    dump(out/'manifest.json',{'files_sha256':{f.name:sha(f) for f in out.iterdir() if f.is_file()},
                              'run_directory':str(folder.relative_to(ROOT)), 'new_api_calls':0})
    return {k:summary[k] for k in ('status','new_api_calls','mean_monthly_sim_iqr_pp','mean_monthly_prior_iqr_pp')}


def make_figures(s,individual,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC'],'font.size':11,
                         'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    blue,orange,gray='#1769aa','#d26813','#343b43'
    months=s['evaluation']['monthly'];x=np.arange(len(months));labels=[str(r['month'])[:4]+'-'+str(r['month'])[4:] for r in months]
    fig,ax=plt.subplots(2,1,figsize=(11.5,7),layout='constrained',sharex=True)
    for key,label,color,style in [('truth_pp','官方SCE首发值',gray,'-'),('sim_pp','本期模拟',blue,'-'),('anchor_pp','截止前最后公开值',orange,'--')]:
        ax[0].plot(x,[r[key] for r in months],style,color=color,label=label,marker='o',markersize=4)
    ax[0].set(title='近期11期：模拟值、官方值与持续性基线',ylabel='一年期通胀预期（%）');ax[0].legend(ncol=3,frameon=False)
    ax[1].bar(x-.19,[abs(r['sim_pp']-r['truth_pp']) for r in months],width=.36,color=blue,label='模型绝对误差')
    ax[1].bar(x+.19,[abs(r['anchor_pp']-r['truth_pp']) for r in months],width=.36,color=orange,label='基线绝对误差')
    ax[1].set(ylabel='绝对误差（pp）',xlabel='目标调查月份');ax[1].set_xticks(x,labels,rotation=35);ax[1].legend(frameon=False)
    for a in ax:a.grid(axis='y',alpha=.15)
    fig.savefig(out/'national_comparison.png',dpi=170);plt.close(fig)
    ds=s['monthly_distributions'];fig,ax=plt.subplots(1,2,figsize=(12,4.4),layout='constrained')
    for kind,col,label in [('sim',blue,'模拟回答'),('prior',orange,'合成起点')]:
        ax[0].plot(x,[r[kind]['iqr_pp'] for r in ds],marker='o',color=col,label=label)
    ax[0].set(title='人际分歧：不同人的Q9中心有多分散',ylabel='跨人IQR（pp）',xlabel='目标调查月份');ax[0].set_xticks(x,[z[2:] for z in labels],rotation=40);ax[0].legend(frameon=False)
    # Per-month normalized mass, then equal month pooling, common 0.5pp bins.
    ws=np.array([r['weight']/next(d['weight_sum'] for d in ds if d['month']==r['month'])/len(ds) for r in individual])
    edges=np.arange(-4,16.001,.5)
    for key,col,label in [('center',blue,'模拟回答'),('prior_center',orange,'合成起点')]:
        mass,_=np.histogram([r[key] for r in individual],bins=edges,weights=ws)
        ax[1].stairs(mass*100,edges,color=col,linewidth=2,label=label)
    ax[1].set(title='11期等权汇总的Q9个人中心分布',xlabel='个人Q9密度均值（%）',ylabel='每0.5pp区间的人口比例（%）');ax[1].legend(frameon=False)
    fig.suptitle('描述性结构比较：合成起点并非同期真人分布',fontsize=13)
    fig.savefig(out/'dispersion.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(11,7.5),layout='constrained')
    for dim,a in zip(DIMENSIONS[:4],axes.flat):
        gs=[r for r in s['group_summary'] if r['dimension']==dim];idx=np.arange(len(gs))
        a.barh(idx-.18,[r['sim_median_pp'] for r in gs],height=.33,color=blue,label='模拟中心')
        a.barh(idx+.18,[r['prior_median_pp'] for r in gs],height=.33,color=orange,label='起点中心')
        a.set_yticks(idx,[r['label'] for r in gs]);a.set(xlabel='各月组中位数的平均值（%）',title=LABELS[dim]);a.invert_yaxis()
    axes[0,0].legend(frameon=False,loc='lower left',bbox_to_anchor=(0,1.03),ncol=2)
    fig.suptitle('人口分组中的模拟差异：没有同期分组真值，不能判断拟合优劣',fontsize=12)
    fig.savefig(out/'population_groups.png',dpi=170,bbox_inches='tight');plt.close(fig)


def make_html(s,out):
    ev=s['evaluation'];t=s['technical'];r=t['generation_receipt'];fmt=lambda x:f'{x:.3f}'
    rows=''.join(f'<tr><td>{str(m["month"])[:4]}-{str(m["month"])[4:]}</td><td>{m["truth_pp"]:.1f}</td><td>{m["sim_pp"]:.3f}</td><td>{m["anchor_pp"]:.1f}</td><td>{abs(m["sim_pp"]-m["truth_pp"]):.3f}</td><td>{abs(m["anchor_pp"]-m["truth_pp"]):.3f}</td></tr>' for m in ev['monthly'])
    score=f'''<div class="metrics"><div><small>模型MAE</small><strong>{fmt(ev['model']['mae_pp'])}<em>pp</em></strong></div><div><small>持续性基线MAE</small><strong>{fmt(ev['persistence']['mae_pp'])}<em>pp</em></strong></div><div><small>模型胜出月份</small><strong>{ev['model_win_months']}<em>/11</em></strong></div><div><small>完整答卷</small><strong>5,632<em>/5,632</em></strong></div></div>'''
    body=f'''<header><span>SCE · 2025-11—2026-09 · DeepSeek V3.2</span><h1>近期11个月：运行与模拟结果</h1><p>每月512个代理家庭，一次生成；使用各截止前推定可得的人口框架及合成个人起点。全国指标可评价，微观结构只能描述。</p></header>
    <nav><a href="#headline">总体误差</a><a href="#structure">人群结构</a><a href="#run">运行与补跑</a><a href="#boundary">口径与边界</a></nav>
    <section id="headline"><h2>01　全国预测误差</h2>{score}<p>模型RMSE <b>{fmt(ev['model']['rmse_pp'])}</b>pp，基线 <b>{fmt(ev['persistence']['rmse_pp'])}</b>pp；模型平均有符号误差 <b>{ev['model']['bias_pp']:+.3f}</b>pp。MAE按11个月等权；pp是百分点。</p><img src="national_comparison.png" alt="逐月全国SCE及绝对误差"><p class="caption">来源：封存模拟回答与纽约联储逐月首发新闻稿；基线为预测截止前最后公开的全国值。</p>
    <details><summary>查看11个月的具体数值</summary><table><thead><tr><th>月份</th><th>官方值%</th><th>模拟值%</th><th>基线%</th><th>模型误差pp</th><th>基线误差pp</th></tr></thead><tbody>{rows}</tbody></table></details>
    <p>早期48个月冻结的组合权重λ={ev['combination_simulation_share']:.1f}，所以本期冻结组合等于基线，MAE为{fmt(ev['frozen_combination']['mae_pp'])}pp。不根据这11个月重新拟权。</p></section>
    <section id="structure"><h2>02　模型输出的人群差异</h2><p>平均每月跨人IQR：模拟 <b>{s['mean_monthly_sim_iqr_pp']:.2f}</b>pp，合成起点 <b>{s['mean_monthly_prior_iqr_pp']:.2f}</b>pp。IQR衡量不同人Q9中心的分散程度，和一个人自身的不确定性不同。</p><img src="dispersion.png" alt="模拟与合成起点的跨人IQR和分布"><p class="caption">直方图每0.5pp一档，各月先按设计权重归一，再给月份相同质量；仅展示−4%至16%。起点不是同期真人真值，宽度变化不能直接称为误差。</p><img src="population_groups.png" alt="按年龄学历收入数理能力的描述性模拟分组"><p class="caption">每个月各组先计算加权中位数，再对合格月份等权平均；只纳入n≥20、ESS≥10的组月。详细分组与支持见summary.json。</p></section>
    <section id="run"><h2>03　模拟完成，评价错误已离线恢复</h2><p>主批5,632次，原始技术失败{t['main_technical_failures']}份；自动补跑{t['repair_attempts']}次，最终Q8缺失0、Q9缺失0，共5,652次实际API尝试。补跑是技术修复，不是重复实验。</p><p>生成耗时约{t['generation_elapsed_minutes']:.1f}分钟。API已报 <b>${r['reported_cost_usd']:.4f}</b>；未知费用预留 <b>${r['spent_or_reserved_usd']-r['reported_cost_usd']:.4f}</b>是未获完整回包请求的保守账目，不是已确认额外扣费；本批上限$8。</p><p>原评价进程因目录漏登2026-09而报KeyError，并非模拟中断。现单独归档官方2026-10-07发布的9月值3.9%，只补评价索引，原提示、回答、运行收据及冻结源码均保留。此次恢复没有新增模型调用。</p></section>
    <section id="boundary"><h2>04　如何理解这些结果</h2><p>全国指标：对每个人的十档Q9拟合连续密度，取个人密度均值，再取人群加权中位数。Q8点预期独立保留，不参与此指标计算。</p><p>近期没有真人微观答案，因此不能给出同期个人MAE、W1或真人IQR误差。分组差异只是模型行为，不能证明真实人群关系已被还原。一次生成也不能拆分稳定个体差异和模型随机性。</p><p>本批是回顾性的时点回测。人口可得月采用“调查月末加九个日历月”规则假设，源波次2025-01逐步推进至2025-10；历史文件字节版本、新闻原始版本和模型知识截止未完全认证，不能称严格事前预测。</p><p>11个月样本很短。探索性的3月区块配对MAE差95%区间为[{s['paired_mae_interval']['interval_95'][0]:+.3f}, {s['paired_mae_interval']['interval_95'][1]:+.3f}]pp；它不涵盖所有输入构造或模型选择不确定性。</p><p><a href="https://www.newyorkfed.org/newsevents/news/research/2026/20261007">9月官方首发来源</a> · <a href="summary.json">完整机器可读结果</a> · <a href="monthly_national.csv">逐月CSV</a></p></section>'''
    css='''body{max-width:1100px;margin:auto;padding:34px 26px;background:#f6f4ef;color:#24323b;font:18px/1.85 "Times New Roman","Kaiti SC","STKaiti","KaiTi",serif}h1{font-size:34px;line-height:1.4}h2{font-size:25px;margin-top:34px}header span,.caption,small{color:#596974}nav{display:flex;gap:24px;flex-wrap:wrap;border-bottom:1px solid #bcc8ce;padding:15px 0}a{color:#1769aa}section{padding:12px 0 25px;border-bottom:1px solid #cdd3d6}img{width:100%;background:white;margin:14px 0}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;background:#e8edf0;padding:20px}.metrics strong{display:block;font-size:32px}.metrics em{font-size:17px;font-style:normal;padding-left:5px}table{border-collapse:collapse;width:100%;font-size:16px}td,th{padding:9px;border-bottom:1px solid #c7cfd3;text-align:right}td:first-child,th:first-child{text-align:left}.caption{font-size:15px}summary{cursor:pointer} @media(max-width:650px){.metrics{grid-template-columns:repeat(2,1fr)}body{padding:20px 14px}h1{font-size:28px}}'''
    (out/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCE近期11个月模拟效果</title><style>'+css+'</style>'+body+'</html>')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--score-cache',type=Path)
    args=parser.parse_args()
    print(json.dumps(analyze(args.run_dir,args.catalog,args.out,args.score_cache),ensure_ascii=False,indent=2))
