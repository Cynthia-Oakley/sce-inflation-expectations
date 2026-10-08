"""Evaluation layer for the isolated spending trial; never imported by simulation."""
import json
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
from .native_spending import ARMS
from .household_state_analysis import density, distribution
from .spending_audit import sha
from .scoring.sce_q9_frozen import provenance


def paired_metrics(rows):
    eligible=[r for r in rows if all(r[k] is not None and np.isfinite(r[k]) for k in ('real',)+ARMS)]
    real=np.asarray([r['real'] for r in eligible])
    result={'n_selected':len(rows),'n_common':len(eligible),'n_excluded':len(rows)-len(eligible),
            'estimand':'Equal food-rank strata diagnostic sample; not a nationwide indicator.',
            'real':distribution(real),'arms':{}}
    if not len(real):return result
    for arm in ARMS:
        pred=np.asarray([r[arm] for r in eligible]);d=distribution(pred)
        result['arms'][arm]={'distribution':d,'median_absolute_error_pp':abs(d['median']-result['real']['median']),
            'distribution_W1_pp':float(np.mean(abs(np.sort(pred)-np.sort(real)))),
            'IQR_absolute_gap_pp':abs(d['iqr']-result['real']['iqr']),
            'individual_MAE_auxiliary_pp':float(np.mean(abs(pred-real))),
            'food_strata':{str(s):{'real':distribution([r['real'] for r in eligible if r['food_stratum']==s]),
                                  'simulated':distribution([r[arm] for r in eligible if r['food_stratum']==s])} for s in range(4)}}
        g=result['arms'][arm]['food_strata']
        if all(g[str(s)][kind]['median'] is not None for s in [0,3] for kind in ['real','simulated']):
            actual_gap=g['3']['real']['median']-g['0']['real']['median']
            simulated_gap=g['3']['simulated']['median']-g['0']['simulated']['median']
            result['arms'][arm].update(real_high_minus_low_food_gap_pp=actual_gap,
                                      simulated_high_minus_low_food_gap_pp=simulated_gap,
                                      food_gap_absolute_error_pp=abs(simulated_gap-actual_gap))
    rng=np.random.default_rng(42);a=np.asarray([r['actual'] for r in eligible])
    contrasts={}
    for control in ['withheld','shuffled']:
        b=np.asarray([r[control] for r in eligible]);delta=abs(a-real)-abs(b-real)
        bs=rng.choice(delta,size=(2000,len(delta)),replace=True).mean(axis=1)
        contrasts[control]={'individual_mean_absolute_error_change_pp':float(delta.mean()),
                           'paired_resampling_95_interval_pp':np.quantile(bs,[.025,.975]).tolist(),
                           'scope':'Conditional sample uncertainty only; no estimate of repeated LLM generation variance.'}
    result['actual_minus_control']=contrasts
    return result


def analyze(root,folder,out):
    root,folder,out=map(Path,(root,folder,out));out.mkdir(parents=True,exist_ok=False)
    manifest=folder/'trial_manifest.json';plan=json.loads(manifest.read_text())
    if plan['status']!='completed' or any(j['status']!='completed' for j in plan['jobs']):
        raise ValueError('Requires completed genuine LLM trial')
    truthpath=root/'data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json'
    truth={(int(r['date']),int(r['userid'])):r for r in json.loads(truthpath.read_text())['per_person']}
    links=pd.read_parquet(folder/'private_evaluation_link.parquet')
    result={'trial_id':plan['trial_id'],'new_calls':plan['max_calls'],'estimated_cost_usd':plan['estimated_cost_usd'],
            'scorer':provenance(),'months':{},'sources':{str(manifest):sha(manifest),str(truthpath):sha(truthpath)}}
    if not result['scorer']['live_matches_pinned']:raise ValueError('Frozen scorer hash drift')
    detailed=[]
    for month in plan['months']:
        h=links[links.date==int(month)];by_arm={}
        for arm in ARMS:
            jobs=[j for j in plan['jobs'] if j['month']==month and j['arm']==arm]
            if len(jobs)!=1:raise ValueError('Duplicate/missing trial cell')
            directory=Path(jobs[0]['output_dir']);run=json.loads((directory/'run_manifest.json').read_text())
            if run['llm_kind']!='openai' or run['run_id']!=jobs[0]['run_id']:raise ValueError('Run identity mismatch')
            for name,v in run['effective_artifact_sha256'].items():
                if sha(directory/name)!=v:raise ValueError('Changed effective input')
            with duckdb.connect(run['store_path'],read_only=True) as db:
                rows=db.execute('SELECT agent_id,action_payload FROM panel WHERE step=1 ORDER BY agent_id').fetchall()
            if len(rows)!=len(h) or {aid for aid,_ in rows}!=set(h.agent_id):raise ValueError('Coverage mismatch')
            by_arm[arm]={aid:json.loads(payload) if isinstance(payload,str) else payload for aid,payload in rows}
            result['sources'][str(directory/'run_manifest.json')]=sha(directory/'run_manifest.json')
            result['sources'][run['store_path']]=sha(run['store_path'])
        q9=[];q8=[];uncertainty=[];status={}
        for _,r in h.iterrows():
            real=truth[(int(month),int(r.userid))]
            fits={'real':density([real.get(f'Q9_bin{i}') for i in range(1,11)]),
                  **{arm:density([by_arm[arm][r.agent_id].get(f'q9_bin{i}') for i in range(1,11)]) for arm in ARMS}}
            base={'date':int(month),'agent_id':r.agent_id,'food_stratum':int(r.food_stratum)}
            q9.append({**base,**{k:v['mean'] for k,v in fits.items()}})
            uncertainty.append({**base,**{k:v['iqr'] for k,v in fits.items()}})
            for k,v in fits.items():status[k+':'+v['status']]=status.get(k+':'+v['status'],0)+1
            point=real.get('Q8v2part2')
            q8.append({**base,'real':point if type(point) in (int,float) and np.isfinite(point) else None,
                       **{arm:by_arm[arm][r.agent_id]['point_pct'] for arm in ARMS}})
        result['months'][month]={'Q9_center':paired_metrics(q9),'Q8_secondary':paired_metrics(q8),
                                'personal_Q9_uncertainty':paired_metrics(uncertainty),'fit_status_counts':status}
        detailed.extend({'Q9':a,'Q8':b,'uncertainty':c} for a,b,c in zip(q9,q8,uncertainty))
    result['limits']=plan['limits']+['Same frozen approximate density scorer for real and simulated bins.',
          'Two months are development evidence, not independent validation. No causal attention identification.',
          'Actual-versus-shuffled can also reflect demographic plausibility of a spending vector, not attention alone.']
    write=lambda p,d:p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    write(out/'summary.json',result);write(out/'paired_evaluation_private.json',detailed)
    print(json.dumps({'analysis':str(out),'months':result['months']},ensure_ascii=False),flush=True)
    return result
