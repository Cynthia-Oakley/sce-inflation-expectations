"""Paired evaluation of the isolated prior-role contrast; never calls an API."""
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path

import duckdb
import numpy as np

from .behavior_comparison import score,finite
from .expanded_state import metrics,MAIN,sha,dump
from ..reporting_behavior.mapping import cell_metrics
from ..scoring.sce_q9_frozen import provenance

ROOT=Path(__file__).resolve().parents[3]
TRUTH=ROOT/'outputs/sce_expanded_state_trial_20261014_v3/development_cases_private.json'


def load_cases(folder):
    manifest=json.loads((folder/'manifest.json').read_text());protocol=json.loads((folder/'protocol.json').read_text())
    if sha(folder/'protocol.json')!=manifest['protocol_sha256'] or not provenance()['live_matches_pinned']:
        raise ValueError('protocol or scorer changed')
    links=json.loads((folder/'evaluation_links_private.json').read_text())
    # Reuse already scored truth/past baselines, not old LLM predictions.
    truthrows=json.loads(TRUTH.read_text());lookup={}
    fields=['actual','actual_iqr','actual_zero_deflation','previous','previous_bins','previous_point',
            'actual_point','copy_previous','history_anchor_half']
    for row in truthrows:
        key=(row['month'],row['agent_id']);current={name:row[name] for name in fields}
        if key in lookup and lookup[key]!=current:raise ValueError('truth differs across old generation rows')
        lookup[key]=current
    actions={};coverage=Counter();sources={str(TRUTH.relative_to(ROOT)):sha(TRUTH)};cost=0
    for job in manifest['jobs']:
        directory=ROOT/'outputs/local_runs'/job['run_id'];run=json.loads((directory/'run_manifest.json').read_text())
        if run['llm_kind']!='openai' or run['cost']['call_count']!=protocol['n_per_month']:
            raise ValueError('requires complete real run; preserve incomplete cells separately')
        cost+=run['cost']['estimated_cost_usd']
        for name in ['run_manifest.json','study.duckdb']:
            sources[str((directory/name).relative_to(ROOT))]=sha(directory/name)
        previews={r['agent_id']:r['prompt_sha256'] for r in json.loads((folder/str(job['month'])/f"preview_{job['arm']}.json").read_text())}
        conn=duckdb.connect(str(directory/'study.duckdb'),read_only=True)
        records=conn.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall();conn.close()
        if len(records)!=protocol['n_per_month']:raise ValueError('missing actions')
        for aid,payload in records:
            payload=json.loads(payload) if isinstance(payload,str) else payload
            if payload.get('anchor_role_arm')!=job['arm'] or payload.get('actual_messages_sha256')!=previews[aid]:
                raise ValueError('input/output binding mismatch')
            coverage[(job['arm'],payload['validation_status'])]+=1
            actions[job['month'],job['repeat'],aid,job['arm']]=payload
    cases=[];scorable=Counter()
    for link in links:
        month,aid=link['month'],link['agent_id'];truth=lookup[month,aid]
        for repeat in protocol['generation_repeats']:
            row={**truth,'month':month,'repeat':repeat,'userid':link['userid'],'agent_id':aid,
                 'profile':link['profile'],'survey_weight':link['survey_weight']}
            for arm in protocol['arms']:
                payload=actions[month,repeat,aid,arm];bins=[payload.get(f'q9_bin{i}') for i in range(1,11)]
                scored=score(bins) if payload['validation_status']=='valid' else score([])
                row[arm]=scored['mean'];row[arm+'_bins']=bins;row[arm+'_iqr']=scored['iqr'];row[arm+'_zero_deflation']=scored['zero_deflation']
                row[arm+'_point']=payload.get('point_pct') if payload['validation_status']=='valid' else None
                scorable[(arm,'scorable' if finite(scored['mean']) else 'unscorable')]+=1
            row['common']=all(finite(row[k]) for k in ['actual','previous','original','belief_start','history_anchor_half'])
            cases.append(row)
    return cases,sources,{f'{a}:{s}':n for (a,s),n in coverage.items()},{f'{a}:{s}':n for (a,s),n in scorable.items()},cost


def prior_response(cases,arm):
    cells=[]
    for month in sorted({r['month'] for r in cases}):
        for repeat in [1,2]:
            rows=[r for r in cases if r['month']==month and r['repeat']==repeat]
            previous=np.array([r['previous'] for r in rows]);x=previous-previous.mean();denom=float(np.mean(x*x))
            y=np.array([r[arm] for r in rows]);real=np.array([r['actual'] for r in rows])
            beta=float(np.mean(x*(y-y.mean()))/denom) if denom>0 else None
            target=float(np.mean(x*(real-real.mean()))/denom) if denom>0 else None
            cells.append({'month':month,'repeat':repeat,'slope':beta,'real_slope':target,
                          'absolute_slope_gap':abs(beta-target) if beta is not None else None})
    return {'cells':cells,'average_slope':float(np.mean([r['slope'] for r in cells if r['slope'] is not None])),
            'average_absolute_slope_gap':float(np.mean([r['absolute_slope_gap'] for r in cells if r['absolute_slope_gap'] is not None]))}


def compare_cases(cases,protocol,draws=2000):
    common=[r for r in cases if r['common']]
    if not common:raise ValueError('no common scorable cases')
    arms=['original','belief_start','copy_previous','history_anchor_half']
    results={arm:metrics(common,arm) for arm in arms}
    real=np.array([r['actual'] for r in common]);previous=np.array([r['previous'] for r in common])
    months=sorted({r['month'] for r in common});repeats=protocol['generation_repeats']
    rng=np.random.default_rng(20261015);bootstrap={key:np.zeros(draws) for key in MAIN}
    for month in months:
        uids=sorted({r['userid'] for r in common if r['month']==month});pos={uid:i for i,uid in enumerate(uids)}
        multiple=rng.multinomial(len(uids),np.ones(len(uids))/len(uids),size=draws)
        for repeat in repeats:
            idx=np.array([i for i,r in enumerate(common) if r['month']==month and r['repeat']==repeat])
            weights=multiple[:,[pos[common[i]['userid']] for i in idx]]
            values={arm:cell_metrics(np.array(results[arm]['case_predictions'])[idx],real[idx],previous[idx],weights) for arm in ['original','belief_start']}
            for key in MAIN:bootstrap[key]+=(values['belief_start'][key]-values['original'][key])/(len(months)*len(repeats))
    contrasts={}
    for key in MAIN:
        monthly=[]
        for month in months:
            new=np.mean([r[key] for r in results['belief_start']['cells'] if r['month']==month])
            old=np.mean([r[key] for r in results['original']['cells'] if r['month']==month]);monthly.append(new-old)
        sensitivity=np.mean(np.array(monthly)[rng.integers(0,len(months),size=(10000,len(months)))],axis=1)
        contrasts[key]={'change_pp':results['belief_start']['aggregate'][key]-results['original']['aggregate'][key],
                        'paired_person_within_month_ci95_pp':np.quantile(bootstrap[key],[.025,.975]).tolist(),
                        'month_bootstrap_sensitivity95_pp':np.quantile(sensitivity,[.025,.975]).tolist()}
    slopes={arm:prior_response(common,arm) for arm in ['original','belief_start']}
    weighted={arm:metrics(common,arm,weights=[r['survey_weight'] for r in common])['aggregate'] for arm in arms}
    for arm in results:results[arm].pop('case_predictions')
    unique={(r['month'],r['userid']) for r in common};counts=Counter((r['month'],r['userid']) for r in common)
    return {'results':results,'belief_start_minus_original':contrasts,'prior_position':slopes,
            'survey_weighted_auxiliary':weighted,'common_generation_rows':len(common),'unique_common_person_months':len(unique),
            'person_months_with_both_repeats':sum(n==len(repeats) for n in counts.values()),
            'distinct_people':len({r['userid'] for r in common}),
            'interval_scope':'Conditional on four selected months; within-month person pairing preserves repeated generations; month-level sensitivity has only four clusters; not nationwide inference.'}


def evaluate(folder,out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('fresh ignored output')
    protocol=json.loads((folder/'protocol.json').read_text())
    cases,sources,coverage,scorable,cost=load_cases(folder)
    result=compare_cases(cases,protocol)
    valid=sum(scorable.get(arm+':scorable',0) for arm in protocol['arms'])/protocol['planned_calls']
    contrasts=result['belief_start_minus_original']
    gate=contrasts['cross_section_w1_pp']['paired_person_within_month_ci95_pp'][1]<0 and all(contrasts[key]['change_pp']<=0 for key in ['sample_center_mae_pp','delta_w1_pp']) and valid>=.99
    summary={'status':'completed_real_prior_role_trial','completed_at_utc':datetime.now(timezone.utc).isoformat(),
             'protocol_sha256':sha(folder/'protocol.json'),'protocol':protocol,'new_api_calls':protocol['planned_calls'],
             'estimated_peak_token_cost_usd':cost,'cost_is_provider_bill':False,'coverage':coverage,'scorable_coverage':scorable,
             'valid_scorable_fraction':valid,'candidate_continue_gate_passed':gate,'source_sha256':sources,'scorer':provenance(),**result}
    out.mkdir(parents=True);dump(out/'summary.json',summary);dump(out/'cases_private.json',cases)
    return summary
