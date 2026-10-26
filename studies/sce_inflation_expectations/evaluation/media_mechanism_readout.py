"""Read cached media V3 scores; align supports before comparing mechanisms.

No model calls and no Q9 refits. Frozen evaluation and raw segment ledgers stay
untouched. A82 remains one archived generation, not a synthetic second repeat.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import numpy as np

from ..experiments.frozen_batch import ROOT, dump, read_json, sha
from ..experiments import frozen_message_queue as queue
from . import cognition as metrics
from .media_mechanism_v3 import prior_groups

ARMS=['R0','Q0','Q1','Q2','Q3']
LABELS={'A82':'A82原配置','R0':'修正新闻路由','Q0':'四档新闻量','Q1':'警示新闻×2','Q2':'混入Fox','Q3':'CPI相关度×1.5','copy_previous':'照抄本人上期'}
PAIRS=[('A82','R0'),('R0','Q0'),('Q0','Q1'),('Q0','Q2'),('Q0','Q3')]
KEYS=['q9_center_mae_pp','q9_center_bias_pp','cross_section_w1_pp','cross_person_iqr_pp',
      'real_cross_person_iqr_pp','individual_density_mean_mae_pp','individual_density_iqr_mean_pp',
      'real_individual_density_iqr_mean_pp','probability_tv_pct']


def summarize(cases,arm,months,repeats,s9,s8):
    source=[r for r in cases if r['repeat']==1] if arm=='A82' else cases
    reps=[1] if arm=='A82' else repeats
    v=metrics._summarize_arm(source,arm,months,reps,s9,s8)['auxiliary_survey_weighted']
    aggregate={k:v['q9']['aggregate_equal_month_repeat_cells'][k] for k in KEYS}
    aggregate.update(v['q8']['aggregate_equal_month_repeat_cells'])
    aggregate['center_rmse_pp']=float(np.sqrt(np.mean([r['q9_center_bias_pp']**2 for r in v['q9']['cells']])))
    monthly=[]
    for month in months:
        rows=metrics._cell_rows(source,month,reps[0],s9)
        w=[r['survey_weight'] for r in rows]
        truth=metrics.quantile([r['real']['q9_mean'] for r in rows],w,.5)
        cells=[r for r in v['q9']['cells'] if r['month']==month]
        monthly.append(dict(month=month,n=len(rows),truth_center_pp=truth,
            **{k:float(np.mean([r[k] for r in cells])) for k in KEYS},
            model_center_pp=truth+float(np.mean([r['q9_center_bias_pp'] for r in cells])),
            repeat_center_mae_pp={str(r['repeat']):r['q9_center_mae_pp'] for r in cells}))
    repeat_metrics={str(rep):{k:float(np.mean([r[k] for r in v['q9']['cells'] if r['repeat']==rep])) for k in KEYS} for rep in reps}
    return {'metrics':aggregate,'monthly':monthly,'repeat_metrics':repeat_metrics,'generation_count':len(reps)}


def effects(values):
    result=[]
    for base,candidate in PAIRS:
        b,c=values[base],values[candidate]
        rows=[]
        for bm,cm in zip(b['monthly'],c['monthly']):
            assert bm['month']==cm['month']
            rows.append({'month':bm['month'],**{k:cm[k]-bm[k] for k in KEYS}})
        delta={k:c['metrics'][k]-b['metrics'][k] for k in KEYS}
        result.append(dict(base=base,candidate=candidate,delta=delta,monthly=rows,
            center_mae_improvement_fraction=-delta['q9_center_mae_pp']/b['metrics']['q9_center_mae_pp'],
            center_win_months=sum(r['q9_center_mae_pp']<0 for r in rows),
            w1_win_months=sum(r['cross_section_w1_pp']<0 for r in rows),
            per_repeat_delta=({str(rep):{k:c['repeat_metrics'][str(rep)][k]-b['repeat_metrics'][str(rep)][k] for k in KEYS}
                              for rep in (1,2)} if base!='A82' else None),
            leave_one_month_out_mae_delta={str(r['month']):float(np.mean([x['q9_center_mae_pp'] for x in rows if x['month']!=r['month']])) for r in rows},
            y2021_mae_base=float(np.mean([r['q9_center_mae_pp'] for r in b['monthly'] if r['month']//100==2021])),
            y2021_mae_candidate=float(np.mean([r['q9_center_mae_pp'] for r in c['monthly'] if r['month']//100==2021]))))
    return result


def readout(folder,out):
    folder,out=Path(folder).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh analysis directory required')
    c=read_json(folder/'config.json');package=Path(c['package']);p=read_json(package/'protocol.json')
    latest=read_json(folder/'latest_receipt.json')
    if latest['status']!='generation_and_evaluation_complete':
        raise ValueError('Complete generation and evaluation required')
    evaluation=Path(latest['round_dir'])/'evaluation'
    for relative,digest in read_json(evaluation/'manifest.json')['files_sha256'].items():
        path=(evaluation/relative).resolve()
        if not path.is_relative_to(evaluation) or sha(path)!=digest:
            raise ValueError('Frozen evaluation changed: '+relative)
    intents,replies=queue.archive(folder)
    if len(intents)!=p['planned_calls'] or len(replies)!=len(intents):
        raise ValueError('Complete transport ledger required')
    cases=read_json(evaluation/'cases_private.json')
    reference={(r['month'],r['agent_id']):r for r in read_json(package/'a82_reference_private.json')}
    for row in cases:
        old=reference[row['month'],row['agent_id']]
        if old['real']!=row['real'] or old['survey_weight']!=row['survey_weight']:
            raise ValueError('A82 target/weight mismatch')
        row['arms']['A82']=deepcopy(old['arms']['monthly_reconstruction'])
    s9=metrics._common_person_months(cases,ARMS+['A82'],[1,2],'q9')
    s8=metrics._common_person_months(cases,ARMS+['A82'],[1,2],'q8')
    main={a:summarize(cases,a,p['months'],[1,2],s9,s8) for a in ['A82',*ARMS]}
    for arm in ARMS:
        original=read_json(evaluation/'summary.json')['arms'][arm]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells']
        if not np.isclose(main[arm]['metrics']['q9_center_mae_pp'],original['q9_center_mae_pp'],atol=1e-12):
            raise ValueError('Main support changed unexpectedly')
    b9=metrics._common_person_months(cases,ARMS+['A82','copy_previous'],[1,2],'q9')
    b8=metrics._common_person_months(cases,ARMS+['A82','copy_previous'],[1,2],'q8')
    baseline={a:summarize(cases,a,p['months'],[1,2],b9,b8) for a in ['A82',*ARMS,'copy_previous']}
    contexts={month:read_json(package/str(month)/'contexts_private.json') for month in p['months']}
    priors={month:prior_groups(cases,month) for month in p['months']}
    groups=[]
    for dimension,levels in [('prior',['low','middle','high']),('news_count',[4,8,16,32])]:
        for level in levels:
            subset=[r for r in cases if (priors[r['month']][r['agent_id']] if dimension=='prior'
                else contexts[r['month']]['Q0'][r['agent_id']]['news_count'])==level]
            for arm in ARMS:
                v=metrics._summarize_arm(subset,arm,p['months'],[1,2],s9,s8)['auxiliary_survey_weighted']['q9']
                # Report support before interpreting sparse within-month group centers.
                ns=[x['n_person_months'] for x in v['cells']]
                groups.append(dict(dimension=dimension,label=str(level),arm=arm,
                    min_n_per_month_repeat=min(ns),mean_n_per_month_repeat=float(np.mean(ns)),
                    metrics={k:v['aggregate_equal_month_repeat_cells'][k] for k in KEYS}))
    errors=Counter((r.get('error') or 'output_shape_error') for r in replies if not all(queue.fields(r).values()))
    normalization=0
    for row in replies:
        if queue.fields(row)['q9']:
            normalization+=queue.response_view(row['raw_response_text'])['applied']
    elapsed=(datetime.fromisoformat(max(r['finished_at_utc'] for r in replies))-
             datetime.fromisoformat(min(r['started_at_utc'] for r in replies))).total_seconds()/60
    allkeys=[(r['month'],r['agent_id']) for r in cases if r['repeat']==1]
    human_missing=sum(not all(metrics.finite(r['real'].get(k)) for k in ('q9_mean','q9_iqr','q9_zero_deflation')) for r in cases if r['repeat']==1)
    result={'status':'completed_cached_media_mechanism_readout','new_api_calls':0,'new_q9_fits':0,
        'months':p['months'],'arms':ARMS,'labels':LABELS,'people_per_month':96,'generation_repeats':[1,2],
        'support':{'selected_person_months':len(allkeys),'main_q9_person_months':len(s9),'main_q8_person_months':len(s8),
                   'baseline_q9_person_months':len(b9),'baseline_q8_person_months':len(b8),
                   'human_q9_missing_person_months':human_missing,
                   'main_support_excludes_any_arm_any_repeat_invalid_fields':True},
        'main':main,'with_previous_truth':baseline,'effects':effects(main),'groups':groups,
        'technical':{**queue.account(intents,replies),'errors_by_reason':dict(errors),
                     'usable_fraction':sum(all(queue.fields(r).values()) for r in replies)/len(replies),
                     'normalization_applied':normalization,'elapsed_generation_minutes':elapsed,
                     'provider_counts':dict(Counter(r['returned_provider'] for r in replies if not r.get('error'))),
                     'model_counts':dict(Counter(r['returned_model'] for r in replies if not r.get('error'))),
                     'automatic_retries':0,'provider_fallbacks':0},
        'source_sha256':{str(path.relative_to(ROOT)):sha(path) for path in
            (evaluation/'summary.json',evaluation/'cases_private.json',evaluation/'comparison/summary.json',
             package/'protocol.json',package/'manifest.json',package/'a82_reference_private.json',folder/'latest_receipt.json')},
        'limits':['Same 96 people per month, not nationally calibrated 96-person sample; center metrics are same-support, not official headline errors.',
                  'All seven months were already inspected in A82; exploratory mechanism results.',
                  'A82 is one archived generation, other arms have two; A82 contrasts include generation/hosting variability.',
                  'Fixed allocation and two response generations do not test different news allocation seeds.',
                  'Main 641-person-month and real-previous 524-person-month views must not be mixed.',
                  'Q2 changes outlet and content jointly; R0 to Q0 changes tier counts and content, not pure article count.',
                  'Group centers are descriptive; some group-months have fewer than 20 people.']}
    out.mkdir(parents=True)
    dump(out/'summary.json',result)
    dump(out/'manifest.json',{'source_sha256':result['source_sha256'],'summary_sha256':sha(out/'summary.json'),'new_api_calls':0,'new_q9_fits':0})
    return result
