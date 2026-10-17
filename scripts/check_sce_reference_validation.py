#!/usr/bin/env python3
"""Small independent aggregate check; reuse scored cases, never refit or call API."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import wasserstein_distance


def independent_median(values, weights):
    order=sorted(range(len(values)),key=lambda i:values[i])
    half=sum(weights)/2;running=0.
    for i in order:
        running+=weights[i]
        if running>=half:return values[i]
    raise ValueError('Empty positive-weight sample')


def verify(folder,out):
    folder,out=Path(folder),Path(out)
    if out.exists():raise ValueError('Fresh receipt required')
    s=json.loads((folder/'summary.json').read_text());cases=json.loads((folder/'cases_private.json').read_text())
    common={}
    for row in cases:
        key=(row['month'],row['userid'])
        good=(row['arms']['reference']['validation_status']=='valid'
              and all(row['arms']['reference'].get(k) is not None for k in ('mean','iqr'))
              and all(row['real'].get(k) is not None for k in ('q9_mean','q9_iqr')))
        common[key]=common.get(key,True) and good
    checks=[]
    for cell in s['cells']:
        rows=[r for r in cases if r['month']==cell['month'] and r['repeat']==cell['repeat'] and common[r['month'],r['userid']]]
        assert len(rows)==cell['common_scorable_n']
        w=[r['design_survey_weight'] for r in rows];real=[r['real']['q9_mean'] for r in rows]
        sim=[r['arms']['reference']['mean'] for r in rows];prior=[r['baselines']['copy_previous'] for r in rows]
        sc,rc=independent_median(sim,w),independent_median(real,w)
        expected={'simulated_center_pp':sc,'matched_sample_truth_center_pp':rc,
            'center_mae':abs(sc-rc),'person_mae':sum(abs(a-b)*v for a,b,v in zip(sim,real,w))/sum(w),
            'w1':wasserstein_distance(sim,real,u_weights=w,v_weights=w),
            'copy_center_mae':abs(independent_median(prior,w)-rc)}
        actual={'simulated_center_pp':cell['simulated_center_pp'],'matched_sample_truth_center_pp':cell['matched_sample_truth_center_pp'],
            'center_mae':cell['model_metrics_same_sample']['q9_center_mae_pp'],
            'person_mae':cell['model_metrics_same_sample']['individual_density_mean_mae_pp'],
            'w1':cell['model_metrics_same_sample']['cross_section_w1_pp'],'copy_center_mae':cell['copy_previous_center_mae_pp']}
        for name,value in expected.items():
            delta=abs(value-actual[name]);assert delta<1e-8,(cell['month'],name,delta)
            checks.append(delta)
        assert abs(cell['signed_center_decomposition']['identity_residual_pp'])<1e-8
    receipt={'status':'passed_independent_24_cell_aggregate_check','checks':len(checks),
        'maximum_absolute_difference':max(checks),'source_summary_sha256':hashlib.sha256((folder/'summary.json').read_bytes()).hexdigest(),
        'method':'Independent sorted cumulative-weight median, arithmetic weighted MAE, scipy Wasserstein; no second fitting pass.',
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'new_api_calls':0}
    out.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();verify(a.folder,a.out)
