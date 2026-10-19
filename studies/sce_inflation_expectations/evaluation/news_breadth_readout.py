"""Read out the registered news allocation contrasts from already-scored cases.

Reuses shared metrics/intervals; no API, probability fit, or input selection.
"""
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np

from ..experiments.frozen_batch import ROOT, dump, read_json, sha, verify
from .cognition import _common_person_months
from scripts.report_sce_information_exposure import cell_metrics, summarize


def report(folder, evaluation, out):
    began=perf_counter(); folder,evaluation,out=map(lambda p:Path(p).resolve(),(folder,evaluation,out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored readout required')
    manifest,protocol=verify(folder); scored=read_json(evaluation/'summary.json')
    if protocol['id']!='sce-news-breadth-v1' or scored['protocol']!=protocol:
        raise ValueError('Completed matching evaluation required')
    cases=read_json(evaluation/'cases_private.json')
    support=_common_person_months(cases,protocol['arms'],protocol['generation_repeats'],'q9')
    truth_path=ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
    if sha(truth_path)!=manifest['source_sha256'][str(truth_path.relative_to(ROOT))]:
        raise ValueError('Historical scalar baseline cache changed')
    historical={(r['month'],r['agent_id'],r['repeat']):r['baselines'] for r in read_json(truth_path)}
    arms=['carry','history_anchor_half',*protocol['arms']]
    allocation={(r['month'],r['agent_id']):r for r in read_json(folder/'allocation_private.json')}
    cells=[]; checks=0
    def cell(rows,month,repeat):
        y=np.array([r['real']['q9_mean'] for r in rows]);prev=np.array([r['real']['previous_q9_mean'] for r in rows])
        w=np.array([r['survey_weight'] for r in rows]);pred={a:np.array([r['arms'][a]['mean'] for r in rows]) for a in protocol['arms']}
        pred['carry']=prev
        pred['history_anchor_half']=np.array([historical[month,r['agent_id'],repeat]['history_anchor_half'] for r in rows])
        return {'month':month,'repeat':repeat,'n':len(rows),'effective_n':float(w.sum()**2/(w@w)),
            'arms':{a:cell_metrics(y,prev,p,w) for a,p in pred.items()},
            'weighted_news_on_common_support':{a:float(np.average([allocation[month,r['agent_id']][a] for r in rows],weights=w)) for a in protocol['arms']}}
    for month in protocol['months']:
        for repeat in protocol['generation_repeats']:
            rows=[r for r in cases if r['month']==month and r['repeat']==repeat and (month,r['userid']) in support]
            if not rows: raise ValueError('Empty common support')
            c=cell(rows,month,repeat);cells.append(c)
            for arm in protocol['arms']:
                original=next(v for v in scored['arms'][arm]['auxiliary_survey_weighted']['q9']['cells'] if v['month']==month and v['repeat']==repeat)
                for left,right in [('center_mae_pp','q9_center_mae_pp'),('personal_mae_pp','individual_density_mean_mae_pp'),('w1_pp','cross_section_w1_pp')]:
                    if abs(c['arms'][arm][left]-original[right])>1e-8:
                        raise ValueError('Independent aggregation differs')
                    checks+=1
    aggregate=summarize(cells,arms)
    monthly=[{'month':m,'n':next(c['n'] for c in cells if c['month']==m),
        'arms':summarize([c for c in cells if c['month']==m],arms)} for m in protocol['months']]
    per_repeat={str(r):summarize([c for c in cells if c['repeat']==r],arms) for r in protocol['generation_repeats']}
    intervals={'news_matched_minus_baseline':scored['paired_intervals'],**(scored['additional_paired_intervals'] or {})}
    contrasts={}
    for base,alt in protocol['prespecified_contrasts']:
        contrasts[alt+'_minus_'+base]={
            'difference':{k:aggregate[alt][k]-aggregate[base][k] for k in aggregate[alt]},
            'paired_interval_from_shared_evaluator':intervals.get(alt+'_minus_'+base),
            'monthly_center_nonworse':sum(m['arms'][alt]['center_mae_pp']<=m['arms'][base]['center_mae_pp'] for m in monthly),
            'leave_one_month_out_center_difference':{str(m):float(np.mean([v['arms'][alt]['center_mae_pp']-v['arms'][base]['center_mae_pp'] for v in monthly if v['month']!=m])) for m in protocol['months']}}
    primary=contrasts['news_matched_minus_news_randomized']
    passed=bool(not scored['accuracy_descriptive_only'] and primary['monthly_center_nonworse']>=4
        and primary['difference']['center_mae_pp']<0 and primary['difference']['w1_pp']<0)
    groups={}
    for feature in protocol['population_groups']:
        groups[feature]={}
        for value in sorted({str(r['profile'].get(feature)) for r in cases}):
            gc=[]
            for month in protocol['months']:
                for repeat in protocol['generation_repeats']:
                    rows=[r for r in cases if r['month']==month and r['repeat']==repeat and (month,r['userid']) in support and str(r['profile'].get(feature))==value]
                    if len(rows)>=3: gc.append(cell(rows,month,repeat))
            if gc: groups[feature][value]={'cells_used':len(gc),'min_cell_n':min(c['n'] for c in gc),
                'weighted_metrics':summarize(gc,arms),'descriptive_only':True}
    receipts=[read_json(ROOT/'outputs/local_runs'/j['run_id']/'run_manifest.json') for j in manifest['jobs']]
    cost=sum(r['cost']['estimated_cost_usd'] for r in receipts)
    calls=sum(r['cost']['call_count'] for r in receipts)
    if calls!=protocol['planned_calls'] or cost>protocol['budget_cap_usd']:
        raise ValueError('Call count/budget mismatch')
    start=min(r['started_at_utc'] for r in receipts);end=max(r['finished_at_utc'] for r in receipts)
    identities=set();fingerprints=set();api_errors=0
    import json
    for job in manifest['jobs']:
        for line in (ROOT/'outputs/local_runs'/job['run_id']/'llm_calls.jsonl').read_text().splitlines():
            row=json.loads(line);identities.add(str(row.get('returned_model')));fingerprints.add(str(row.get('system_fingerprint')))
            api_errors+=bool(row.get('error'))
    result={'status':'completed_news_breadth_readout','protocol_sha256':manifest['protocol_sha256'],
        'new_api_calls_from_reporting':0,'new_q9_fits_from_reporting':0,'independent_numeric_checks':checks,
        'common_person_months':len(support),'independent_people':len({r['userid'] for r in cases if (r['month'],r['userid']) in support}),
        'weighted_metrics':aggregate,'weighted_monthly':monthly,'weighted_cells':cells,'generation_sensitivity':per_repeat,
        'prespecified_contrasts':contrasts,'development_screen_passed':passed,'automatic_upgrade':False,
        'group_metrics':groups,'coverage':scored['coverage'],'accuracy_descriptive_only':scored['accuracy_descriptive_only'],
        'q8_weighted_metrics':{a:scored['arms'][a]['auxiliary_survey_weighted']['q8']['aggregate_equal_month_repeat_cells'] for a in protocol['arms']},
        'unweighted_metrics':{a:scored['arms'][a]['q9']['aggregate_equal_month_repeat_cells'] for a in protocol['arms']},
        'median_rmse_pp_descriptive':{a:float(np.sqrt(np.mean([c['arms'][a]['center_bias_pp']**2 for c in cells]))) for a in arms},
        'planned_and_actual_calls':calls,'estimated_cost_usd_not_bill':cost,'cap_usd':protocol['budget_cap_usd'],
        'api_errors':api_errors,'automatic_retries':0,'started_at_utc':start,'finished_at_utc':end,
        'parallel_window_seconds':(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds(),
        'returned_model_ids':sorted(identities),'returned_fingerprints':sorted(fingerprints),
        'notes':['Matched/randomized is the primary allocation comparison; uniform8 differs in weighted news quantity.',
            'Intervals condition on six selected development months; repeated generations are not new respondents.',
            'Group summaries are descriptive and skip cells below3; do not select post-hoc population-specific treatment.',
            'History anchor uses the same previously scored strictly past cache and fixed half coefficient; no new fits.'],
        'seconds':perf_counter()-began,'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in
            [Path(__file__),ROOT/'scripts/report_sce_news_breadth.py',evaluation/'summary.json',evaluation/'cases_private.json',truth_path]}}
    out.mkdir(parents=True);dump(out/'summary.json',result);return result
