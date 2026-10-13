"""Exploratory post-primary controls; no current-answer features or network."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

from .analysis import (sha,dump,prepare,state_keys,predictions,history_probabilities,
                       evaluation_summary,loss_rows,cluster_interval,block_interval)


def run_controls(root,out,primary):
    root,out,primary=Path(root).resolve(),Path(out).resolve(),Path(primary).resolve()
    if out.exists():
        raise FileExistsError('Use a new supplement output')
    out.mkdir(parents=True)
    main=json.loads((primary/'summary.json').read_text())
    protocol=main['protocol']
    supplement_path=root/'docs/workstreams/20261013_behavior/codex_controls_protocol.json'
    supplemental=json.loads(supplement_path.read_text())
    dump(out/'protocol_snapshot.json',supplemental)
    cache=root/protocol['source_cache']
    if sha(cache)!=main['source_hashes'][protocol['source_cache']]:
        raise ValueError('Cache drift since primary run')
    d,_=prepare(pd.read_parquet(cache))
    tables=json.loads((primary/'fitted_tables.json').read_text())
    parent=predictions(d,tables,protocol)['previous_belief_shape']
    d['state_key']=state_keys(d,tables['cuts'])
    d['count_bucket']=pd.cut(d.past_n,[-1,0,1,2,5,np.inf],labels=supplemental['past_observation_buckets']).astype(str)
    d['control_key']=d.state_key+'|'+d.count_bucket
    trainmask=d.date.between(*protocol['train'])
    train=d.loc[trainmask].copy()
    train['_w']=train.mw*len(train)/train.mw.sum()
    fitted={}
    for key,g in train.groupby('control_key',sort=True):
        if len(g)<protocol['table_min_rows'] or g.userid.nunique()<protocol['table_min_persons']:
            continue
        q=parent[g.index[0]]
        counts=np.bincount(g['class'],weights=g._w,minlength=3)
        tau=protocol['table_prior_mass']
        fitted[key]=((counts+tau*q)/(counts.sum()+tau)).tolist()
    base=np.array([fitted.get(k,parent[i]) for i,k in enumerate(d.control_key)])
    counts=d[[f'past_count_{k}' for k in range(3)]].to_numpy(float)
    own=history_probabilities(base,counts,protocol['personal_prior_mass'])
    mask=d.date.between(*protocol['evaluation']); t=d.loc[mask]
    a=evaluation_summary(t,base[mask]); b=evaluation_summary(t,own[mask])
    diff=loss_rows(t['class'],own[mask])-loss_rows(t['class'],base[mask])
    c=protocol['person_cluster_bootstrap'];mb=protocol['month_block_bootstrap']
    contrast={'person_cluster':cluster_interval(t,diff,c['repetitions'],c['seed']),
              'month_block':block_interval([x['brier']-y['brier'] for x,y in zip(b['monthly'],a['monthly'])],
                                          mb['repetitions'],mb['block_months'],mb['seed'])}
    # Permute only histories before the target. Current class is never in the strata.
    groups=list(t.groupby(['date','state_key','count_bucket'],sort=True).indices.values())
    rng=np.random.default_rng(supplemental['permutation']['seed'])
    n=t.past_n.to_numpy(float)
    old_counts=counts[mask]
    proportions=np.divide(old_counts,n[:,None],out=np.zeros_like(old_counts),where=n[:,None]>0)
    movable=np.zeros(len(t),bool)
    draws=[]
    for _ in range(supplemental['permutation']['repetitions']):
        order=np.arange(len(t))
        for indices in groups:
            if len(indices)>1 and n[indices[0]]>0:
                order[indices]=rng.permutation(indices)
                movable[indices]=True
        shuffled=history_probabilities(base[mask],proportions[order]*n[:,None],protocol['personal_prior_mass'])
        draws.append(evaluation_summary(t,shuffled))
    summary={'primary_source':str(primary.relative_to(root)),
             'primary_sha256':sha(primary/'summary.json'),'protocol':supplemental,
             'training_supported_cells':len(fitted),'evaluation':{'shape_and_count':a,'shape_count_personal_history':b},
             'history_contrast':contrast,
             'permutation':{'movable_rows':int(movable.sum()),'total_rows':len(t),
                            'fraction_movable':float(movable.mean()),
                            'mean_brier':float(np.mean([r['brier'] for r in draws])),
                            'brier_per_draw':[r['brier'] for r in draws],
                            'mean_accuracy':float(np.mean([r['accuracy'] for r in draws]))},
             'sources':{str(p.relative_to(root)):sha(p) for p in [supplement_path,cache,Path(__file__).resolve()]},
             'new_api_calls':0}
    dump(out/'summary.json',summary)
    dump(out/'fitted_control_tables.json',fitted)
    print(json.dumps({'supplement':str(out),'base_brier':a['brier'],'own_brier':b['brier'],
                      'shuffled_brier':summary['permutation']['mean_brier'],'new_api_calls':0}),flush=True)
    return summary
