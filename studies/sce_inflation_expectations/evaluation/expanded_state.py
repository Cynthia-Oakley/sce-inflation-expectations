"""Offline development selection, then frozen evaluation; never calls a model API."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from .behavior_comparison import score, finite, history_baselines
from ..reporting_behavior.mapping import cell_metrics
from ..scoring.sce_q9_frozen import provenance

ROOT=Path(__file__).resolve().parents[3]
MAIN=('sample_center_mae_pp','cross_section_w1_pp','delta_w1_pp')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dump(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def combine(previous,signal,alpha):
    a=np.asarray(previous,float);b=np.asarray(signal,float)
    if not 0<=alpha<=1 or a.shape!=(10,) or b.shape!=(10,):raise ValueError('Invalid mixture')
    if any((~np.isfinite(v)).any() or (v<0).any() or (v>100).any() or abs(v.sum()-100)>1e-6 for v in (a,b)):
        raise ValueError('Invalid probability inputs')
    return ((1-alpha)*a+alpha*b).tolist()

def load_cases(folder,phase):
    manifest=json.loads((folder/'manifest.json').read_text());protocol=json.loads((folder/'protocol.json').read_text())
    selected=set(protocol[phase+'_months'])
    ref=pd.read_parquet(ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet')
    lookup=ref.set_index(['userid','date'])
    links=[x for x in json.loads((folder/'evaluation_links_private.json').read_text()) if x['month'] in selected]
    histories=history_baselines(ref,[dict(userid=x['userid'],month=x['month'],agent_id=x['agent_id']) for x in links])
    history={(r['month'],r['agent_id']):r for r in histories}
    actions={};sources={};coverage=Counter()
    for job in manifest['jobs']:
        if job['phase']!=phase:continue
        directory=ROOT/'outputs/local_runs'/job['run_id']
        run=json.loads((directory/'run_manifest.json').read_text())
        if run['llm_kind']!='openai' or run['cost']['call_count']!=96:raise ValueError('Needs actual completed 96-call run')
        sources[str((directory/'run_manifest.json').relative_to(ROOT))]=sha(directory/'run_manifest.json')
        sources[str((directory/'study.duckdb').relative_to(ROOT))]=sha(directory/'study.duckdb')
        conn=duckdb.connect(str(directory/'study.duckdb'),read_only=True)
        rows=conn.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall();conn.close()
        if len(rows)!=96:raise ValueError('Missing action rows')
        previews={r['agent_id']:r['prompt_sha256'] for r in json.loads((folder/str(job['month'])/f"preview_{job['arm']}.json").read_text())}
        for aid,p in rows:
            p=json.loads(p) if isinstance(p,str) else p
            if p.get('actual_messages_sha256')!=previews[aid] or p.get('expanded_arm')!=job['arm']:
                raise ValueError('Response-to-input binding changed')
            key=(job['month'],job['repeat'],aid,job['arm']);actions[key]=p
            coverage[(job['arm'],p['validation_status'])]+=1
    cases=[]
    for link in links:
        month,aid,uid=link['month'],link['agent_id'],link['userid']
        truth=lookup.loc[uid,month];past=json.loads((folder/str(month)/'past_private.json').read_text())[aid]['prior']
        actualbins=[float(truth[f'Q9_bin{i}']) for i in range(1,11)];actual=score(actualbins)
        previousbins=[past['q9'][f'bin{i}'] for i in range(1,11)];previous=score(previousbins)
        for repeat in protocol['generation_repeats']:
            row=dict(month=month,repeat=repeat,agent_id=aid,userid=uid,profile=link['profile'],
                     survey_weight=link['survey_weight'],actual=actual['mean'],actual_iqr=actual['iqr'],
                     actual_zero_deflation=actual['zero_deflation'],previous=previous['mean'],
                     previous_bins=previousbins,previous_point=past['point_pct'],
                     actual_point=float(truth.Q8v2part2) if finite(truth.Q8v2part2) and abs(truth.Q8v2part2)<=100 else None,
                     copy_previous=previous['mean'],history_anchor_half=history[month,aid]['history_anchor_half'])
            for arm in ('self_update','new_signal'):
                p=actions[month,repeat,aid,arm]
                bins=[p.get(f'q9_bin{i}') for i in range(1,11)]
                s=score(bins) if p['validation_status']=='valid' else score([])
                row[arm]=s['mean'];row[arm+'_bins']=bins;row[arm+'_iqr']=s['iqr'];row[arm+'_zero_deflation']=s['zero_deflation']
                row[arm+'_point']=p.get('point_pct') if p['validation_status']=='valid' else None
            row['common']=all(finite(row[k]) for k in ('actual','previous','self_update','new_signal','history_anchor_half'))
            cases.append(row)
    return cases,sources,{f'{arm}:{status}':n for (arm,status),n in coverage.items()}

def metrics(cases,arm,alpha=None,weights=None):
    predictions=[];valid=[];uncertainty=[];zero=[];points=[]
    for r in cases:
        if arm=='program':
            result=score(combine(r['previous_bins'],r['new_signal_bins'],alpha))
            prediction=result['mean'];uncertainty.append(result['iqr']);zero.append(result['zero_deflation'])
            point=(1-alpha)*r['previous_point']+alpha*r['new_signal_point'] if all(finite(r[k]) for k in ('previous_point','new_signal_point')) else None
        else:
            prediction=r[arm];uncertainty.append(r.get(arm+'_iqr'));zero.append(r.get(arm+'_zero_deflation'))
            point=r['previous_point'] if arm=='copy_previous' else r.get(arm+'_point')
        predictions.append(prediction);points.append(point);valid.append(finite(prediction))
    if not all(valid):return None
    p=np.asarray(predictions);real=np.asarray([r['actual'] for r in cases]);prev=np.asarray([r['previous'] for r in cases])
    cells=[]
    for month in sorted({r['month'] for r in cases}):
        for repeat in (1,2):
            idx=np.array([i for i,r in enumerate(cases) if r['month']==month and r['repeat']==repeat])
            if not len(idx):raise ValueError('Empty month-repeat cell')
            w=None if weights is None else np.asarray(weights)[idx]
            values={k:float(v[0]) for k,v in cell_metrics(p[idx],real[idx],prev[idx],w).items()}
            pi=[i for i in idx if finite(points[i]) and finite(cases[i]['actual_point'])]
            if pi:
                pm=cell_metrics([points[i] for i in pi],[cases[i]['actual_point'] for i in pi],[cases[i]['previous_point'] if finite(cases[i]['previous_point']) else 0 for i in pi],None)
                values['q8_sample_center_mae_pp']=float(pm['sample_center_mae_pp'][0])
            ui=[uncertainty[i] for i in idx if finite(uncertainty[i])];zi=[zero[i] for i in idx if finite(zero[i])]
            values['mean_individual_density_iqr_pp']=float(np.mean(ui)) if ui else None
            values['zero_deflation_fraction']=float(np.mean(zi)) if zi else None
            values['real_mean_individual_density_iqr_pp']=float(np.mean([cases[i]['actual_iqr'] for i in idx]))
            values['real_zero_deflation_fraction']=float(np.mean([cases[i]['actual_zero_deflation'] for i in idx]))
            rho=spearmanr(p[idx],real[idx]).statistic
            values['rank_correlation']=float(rho) if finite(rho) else None
            cells.append(dict(month=month,repeat=repeat,n=len(idx),**values))
    keys=set().union(*(r.keys() for r in cells))-{'month','repeat','n'}
    aggregate={k:float(np.mean([r[k] for r in cells if finite(r.get(k))])) if any(finite(r.get(k)) for r in cells) else None for k in keys}
    return dict(aggregate=aggregate,cells=cells,case_predictions=p.tolist())

def select_weight(folder):
    if (folder/'weight_lock.json').exists():raise ValueError('Weight already frozen; do not retune')
    protocol=json.loads((folder/'protocol.json').read_text())
    if not provenance()['live_matches_pinned']:raise ValueError('Scorer changed')
    cases,sources,coverage=load_cases(folder,'development');common=[r for r in cases if r['common']]
    base=metrics(common,'copy_previous');grid=[]
    for a in protocol['alpha_grid']:
        result=metrics(common,'program',a)
        if result is None:
            grid.append(dict(alpha=a,eligible=False,reason='scoring_failure'));continue
        objective=float(np.mean([result['aggregate'][k]/max(.001,base['aggregate'][k]) for k in MAIN]))
        grid.append(dict(alpha=a,eligible=True,objective=objective,aggregate=result['aggregate'],cells=result['cells']))
    usable=[r for r in grid if r['eligible']]
    if not usable:raise ValueError('No scorable grid candidate')
    minimum=min(r['objective'] for r in usable)
    selected=min(r['alpha'] for r in usable if r['objective']<=minimum+1e-10)
    lock=dict(alpha=selected,phase='development_only',created_at_utc=datetime.now(timezone.utc).isoformat(),
              protocol_sha256=sha(folder/'protocol.json'),sources_sha256=sources,
              planned_person_months=384,common_person_months=len(common)//2,coverage=coverage,
              objective='equal normalized center/cross-W1/delta-W1',grid=grid,
              copy_previous=base['aggregate'],self_update=metrics(common,'self_update')['aggregate'])
    dump(folder/'development_cases_private.json',cases);dump(folder/'weight_lock.json',lock)
    print('Frozen alpha',selected,'using development months only;',len(common)//2,'common person-months')
    return lock

def evaluate(folder,out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored analysis directory')
    lock=json.loads((folder/'weight_lock.json').read_text());a=lock['alpha']
    if lock['protocol_sha256']!=sha(folder/'protocol.json'):raise ValueError('Protocol changed')
    cases,sources,coverage=load_cases(folder,'evaluation');common=[r for r in cases if r['common']]
    arms=('self_update','program','new_signal','copy_previous','history_anchor_half')
    results={arm:metrics(common,arm,a) for arm in arms}
    if any(v is None for v in results.values()):raise ValueError('Frozen candidate scoring failure: report instead of silently filtering')
    weighted={arm:metrics(common,arm,a,[r['survey_weight'] for r in common])['aggregate'] for arm in arms}
    # Paired individuals resampled within each month, two generations kept together.
    rng=np.random.default_rng(20261014);months=sorted({r['month'] for r in common})
    bootstrap={(ref,k):np.zeros(1000) for ref in ('self_update','copy_previous') for k in MAIN}
    real=np.asarray([r['actual'] for r in common]);prev=np.asarray([r['previous'] for r in common])
    for month in months:
        uids=sorted({r['userid'] for r in common if r['month']==month})
        multiplicity=rng.multinomial(len(uids),np.ones(len(uids))/len(uids),size=1000)
        position={uid:i for i,uid in enumerate(uids)}
        for repeat in (1,2):
            idx=np.array([i for i,r in enumerate(common) if r['month']==month and r['repeat']==repeat])
            w=multiplicity[:,[position[common[i]['userid']] for i in idx]]
            scores={arm:cell_metrics(np.asarray(results[arm]['case_predictions'])[idx],real[idx],prev[idx],w)
                    for arm in ('program','self_update','copy_previous')}
            for ref in ('self_update','copy_previous'):
                for key in MAIN:bootstrap[ref,key]+=(scores['program'][key]-scores[ref][key])/8
    differences={}
    for ref in ('self_update','copy_previous'):
        differences[ref]={}
        for k in MAIN:
            observed=results['program']['aggregate'][k]-results[ref]['aggregate'][k]
            ci=np.quantile(bootstrap[ref,k],[.025,.975]).tolist()
            # Four-month cluster sensitivity uses matched month-mean differences.
            monthly=[]
            for month in months:
                pm=np.mean([r[k] for r in results['program']['cells'] if r['month']==month])
                bm=np.mean([r[k] for r in results[ref]['cells'] if r['month']==month]);monthly.append(pm-bm)
            cluster=np.mean(np.asarray(monthly)[rng.integers(0,4,size=(10000,4))],axis=1)
            differences[ref][k]=dict(change_pp=observed,paired_person_bootstrap_95_interval_pp=ci,
                                    four_month_bootstrap_95_sensitivity_pp=np.quantile(cluster,[.025,.975]).tolist())
    for result in results.values():result.pop('case_predictions')
    valid_generated=sum(finite(r[arm]) for r in cases for arm in ('self_update','new_signal'))/1536
    passes=all(results['program']['aggregate'][k]<=results[ref]['aggregate'][k] for ref in ('self_update','copy_previous') for k in MAIN) and valid_generated>=.99
    summary=dict(status='completed_evaluation',alpha=a,model_requested='deepseek-flash',temperature=.5,
                 evaluation_months=months,planned_person_months=384,common_person_months=len(common)//2,
                 unique_people=len({r['userid'] for r in common}),coverage=coverage,
                 estimand='Equal-weight same-cohort returner A diagnostic; NOT nationwide or recursive B forecast',
                 results=results,survey_weighted_auxiliary=weighted,program_minus=differences,
                 predefined_success_gate_passed=passes,
                 intervals_scope='Conditional on these four months and selected returners; repeats not independent people. Four-month sensitivity has few clusters.',
                 source_sha256=sources,weight_lock_sha256=sha(folder/'weight_lock.json'),
                 scorer=provenance(),completed_at_utc=datetime.now(timezone.utc).isoformat())
    out.mkdir(parents=True);dump(out/'summary.json',summary);dump(out/'cases_private.json',cases)
    final=[]
    for r in common:
        final.append(dict(month=r['month'],repeat=r['repeat'],agent_id=r['agent_id'],alpha=a,
                          final_q9=combine(r['previous_bins'],r['new_signal_bins'],a),
                          final_q8=(1-a)*r['previous_point']+a*r['new_signal_point'] if all(finite(r[k]) for k in ('previous_point','new_signal_point')) else None,
                          role='offline program-derived final answer; underlying new_signal has genuine engine/LLM trajectory'))
    dump(out/'program_final_answers_private.json',final)
    return summary
