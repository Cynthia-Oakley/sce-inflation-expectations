"""Read cached timing evaluation and describe paired effects; no API or Q9 fit."""
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from ..experiments.frozen_batch import ROOT,read_json,dump,sha
from ..experiments import frozen_message_queue as queue
from ..experiments.media_timing_inputs import parsed
from .metrics import quantile
from . import cognition as shared

LABELS={'O0':'旧Q3原始回答','C0':'共同截止：修正标签','C1':'共同截止＋警示','T0':'个人截止','T1':'个人截止＋警示','copy_previous':'照抄本人上期'}
METRICS=('q9_center_mae_pp','q9_center_bias_pp','cross_section_w1_pp','cross_person_iqr_pp',
         'real_cross_person_iqr_pp','individual_density_mean_mae_pp','delta_w1_pp')


def publish(run,out):
    run,out=Path(run).resolve(),Path(out).resolve()
    if out.exists():raise ValueError('Fresh readout required')
    receipt=read_json(run/'latest_receipt.json')
    if receipt['status']!='generation_and_evaluation_complete':raise ValueError('Completed evaluation required')
    ev=Path(receipt['round_dir'])/'evaluation';s=read_json(ev/'summary.json');cases=read_json(ev/'cases_private.json')
    for k,v in read_json(ev/'manifest.json')['files_sha256'].items():
        if sha(ev/k)!=v:raise ValueError('Cached evaluation changed')
    package=ROOT/'outputs/sce_media_timing_package_20261025_v3'
    prep=read_json(package/'summary.json');p=s['protocol'];months=p['months'];repeats=p['generation_repeats']
    sources={str(f.relative_to(ROOT)):sha(f) for f in (run/'latest_receipt.json',ev/'summary.json',ev/'cases_private.json',ev/'manifest.json',package/'summary.json',Path(__file__))}
    bycell=defaultdict(list)
    for r in cases:bycell[r['month'],r['repeat']].append(r)
    views={};checks=0
    for name,block in s['support_summaries'].items():
        support={tuple(x) for x in block['q9_positions']};arms={}
        for arm,b in block['summaries'].items():
            overall=b['overall']['auxiliary_survey_weighted'];metric=overall['q9']['aggregate_equal_month_repeat_cells']
            monthly=[]
            for m in months:
                v=b['by_month'][str(m)]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells']
                levels=[]
                for repeat in repeats:
                    rows=[r for r in bycell[m,repeat] if (m,r['userid']) in support]
                    w=np.array([r['survey_weight'] for r in rows],float)
                    real=quantile([r['real']['q9_mean'] for r in rows],w,.5)
                    model=quantile([r['arms'][arm]['mean'] for r in rows],w,.5)
                    levels.append((real,model))
                monthly.append(dict(month=m,n=len(rows),**v,
                    human_center_pct=float(np.mean([x[0] for x in levels])),
                    model_center_pct=float(np.mean([x[1] for x in levels]))))
            for key in METRICS:
                assert np.isclose(np.mean([r[key] for r in monthly]),metric[key],atol=1e-12)
                checks+=1
            arms[arm]=dict(metrics=metric,q8=overall['q8']['aggregate_equal_month_repeat_cells'],monthly=monthly,
                mae_all_pp=metric['q9_center_mae_pp'],
                mae_2021_pp=float(np.mean([r['q9_center_mae_pp'] for r in monthly if r['month']//100==2021])),
                mae_other_pp=float(np.mean([r['q9_center_mae_pp'] for r in monthly if r['month']//100!=2021])),
                rmse_pp=float(np.sqrt(np.mean([r['q9_center_mae_pp']**2 for r in overall['q9']['cells']]))),
                repeats={rep:v['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells'] for rep,v in b['by_repeat'].items()})
        views[name]=dict(q9_person_months=block['q9_person_months'],q8_person_months=block['q8_person_months'],arms=arms)
    main=views['four_new_arms_common_support']['arms']
    comparisons={}
    for candidate,base,view in [('T0','C0','primary_c0_t0_paired_support'),('T1','T0','pair_t0_t1_support'),
            ('C1','C0','pair_c0_c1_support'),('C0','O0','pair_o0_c0_support'),('T0','copy_previous','primary_c0_t0_plus_copy_previous_same_support')]:
        b=views[view];v=b['arms'];c=v[candidate];a=v[base]
        comparisons[candidate+'_minus_'+base]=dict(view=view,n=b['q9_person_months'],
            mae_change_pp=c['mae_all_pp']-a['mae_all_pp'],mae_2021_change_pp=c['mae_2021_pp']-a['mae_2021_pp'],
            w1_change_pp=c['metrics']['cross_section_w1_pp']-a['metrics']['cross_section_w1_pp'],
            per_month=[dict(month=x['month'],mae_change_pp=x['q9_center_mae_pp']-y['q9_center_mae_pp'],
                            model_center_change_pp=x['model_center_pct']-y['model_center_pct']) for x,y in zip(c['monthly'],a['monthly'])],
            repeat_mae_changes={rep:c['repeats'][rep]['q9_center_mae_pp']-a['repeats'][rep]['q9_center_mae_pp'] for rep in c['repeats']},
            leave_one_out_mae_changes={str(m):float(np.mean([x['q9_center_mae_pp']-y['q9_center_mae_pp'] for x,y in zip(c['monthly'],a['monthly']) if x['month']!=m])) for m in months})
    support={tuple(x) for x in s['support_summaries']['four_new_arms_common_support']['q9_positions']}
    dates={};date_summaries=[]
    draft=ROOT/'outputs/sce_media_timing_inputs_20261025_v3'
    for item in read_json(draft/'summary.json')['months']:
        m=item['month'];f=draft/str(m)/'date_views_private.json';sources[str(f.relative_to(ROOT))]=sha(f)
        for row in read_json(f):
            compare=parsed(row['information_cutoff']);old=parsed(item['shared_cutoff'])
            dates[m,row['agent_id']]='earlier' if compare<old else 'later' if compare>old else 'same'
        date_summaries.append(dict(month=m,**dict(Counter(v for (mo,_),v in dates.items() if mo==m))))
    grouped=[]
    for group in ('earlier','same','later'):
        for m in months:
            cells=[]
            for rep in repeats:
                rows=[r for r in bycell[m,rep] if (m,r['userid']) in support and dates[m,r['agent_id']]==group]
                if not rows:continue
                w=np.array([r['survey_weight'] for r in rows],float)
                cell=dict(n=len(rows),effective_n=float(w.sum()**2/(w@w)),
                    mean_T0_minus_C0_pp=float(np.average([r['arms']['T0']['mean']-r['arms']['C0']['mean'] for r in rows],weights=w)),
                    mean_T1_minus_T0_pp=float(np.average([r['arms']['T1']['mean']-r['arms']['T0']['mean'] for r in rows],weights=w)))
                for arm in ('C0','T0','T1'):
                    value=shared._q9_cell_metrics(rows,arm,w)
                    cell[arm+'_center_mae_pp']=value['q9_center_mae_pp']
                    cell[arm+'_individual_mae_pp']=value['individual_density_mean_mae_pp']
                cells.append(cell)
            if cells:grouped.append(dict(group=group,month=m,**{k:float(np.mean([c[k] for c in cells])) for k in cells[0]}))
    intentions,replies=queue.archive(run);ri,rr=queue.archive(run/'repair')
    assert len(intentions)==4096 and len(replies)==4096 and len(ri)==len(rr)==53
    assert all(row.get('actual_model_results') is True for row in replies+rr)
    counts=Counter(row.get('error') or ('format_or_nonstop' if not all(queue.fields(row).values()) else 'usable') for row in replies)
    execution=dict(s['execution'],main_failure_types=dict(counts),physical_api_attempts=len(intentions)+len(ri),
        repaired_new_request_slots=53,new_request_technical_usable_after_overlay=4096,
        old_attempted_failures_retained=6,classification_cost_token_based_usd=.0512538,
        model_or_human_statistical_missing_is_separate_from_technical_completeness=True)
    result=dict(status='completed_cached_timing_readout',new_api_calls=0,new_q9_fits=0,months=months,
        labels=LABELS,views=views,comparisons=comparisons,date_groups=grouped,date_summaries=date_summaries,
        design=dict(n_by_month=p['n_by_month'],repeats=repeats,arms=p['arms'],model=p['model'],route=p['route'],
            temperature=p['temperature'],quantity_tiers=p['quantity_tiers'],cpi_boost=1.5,alarm_boost=2,
            execution=execution,primary_support='four_new_arms_common_support',baseline_support='all_five_plus_copy_previous_same_support'),
        loss_scale_interaction_mae_pp=(main['T1']['mae_all_pp']-main['T0']['mae_all_pp'])-(main['C1']['mae_all_pp']-main['C0']['mae_all_pp']),
        prepared_exposure_summary=prep['context_summary'],reconciliation_count=checks,source_sha256=sources,
        limitations=['Seven inspected selected periods, not independent temporal validation.',
            'Main comparison uses 654 person-months, original report used 641; report-to-report subtraction is invalid.',
            'Personal-date treatment jointly changes available news, groceries, policy and confidence; not a news-only causal experiment.',
            'Two stochastic generations do not add people; no new temporal assignment seed.',
            'Sparse same-day subgroups and low effective sample size are descriptive only.',
            'No automatic adoption or new paid run.'])
    out.mkdir(parents=True);dump(out/'summary.json',result)
    dump(out/'manifest.json',dict(new_api_calls=0,new_q9_fits=0,summary_sha256=sha(out/'summary.json'),source_sha256=sources))
    return dict(status=result['status'],out=str(out),reconciliations=checks,new_api_calls=0,new_q9_fits=0)
