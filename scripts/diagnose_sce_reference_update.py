#!/usr/bin/env python3
"""Post-hoc slope diagnostic from existing fitted cases; zero new model calls."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def diagnose(folder,out):
    folder,out=Path(folder),Path(out)
    if out.exists():raise ValueError('Fresh diagnostic output required')
    s=json.loads((folder/'summary.json').read_text());cases=json.loads((folder/'cases_private.json').read_text());ok={}
    for r in cases:
        key=(r['month'],r['userid'])
        good=(r['arms']['reference']['validation_status']=='valid' and r['arms']['reference']['mean'] is not None
              and r['real']['q9_mean'] is not None and r['real']['q9_iqr'] is not None)
        ok[key]=ok.get(key,True) and good
    rows=[]
    for cell in s['cells']:
        a=[r for r in cases if r['month']==cell['month'] and r['repeat']==cell['repeat'] and ok[r['month'],r['userid']]]
        assert len(a)==cell['common_scorable_n']
        w=np.array([r['design_survey_weight'] for r in a]);w=w/w.sum()
        x=np.array([r['baselines']['copy_previous'] for r in a]);xc=x-np.sum(w*x);den=np.sum(w*xc*xc)
        row={'month':cell['month'],'repeat':cell['repeat'],'n':len(a)}
        for name,y in [('model',np.array([r['arms']['reference']['mean'] for r in a])),('real',np.array([r['real']['q9_mean'] for r in a]))]:
            row[name+'_slope_on_prior']=float(np.sum(w*xc*(y-np.sum(w*y)))/den)
        rows.append(row)
    result={'status':'posthoc_descriptive_no_new_fitting_or_api','method':'Within each month/generation, weighted OLS of current fitted Q9 mean on observed previous fitted mean, with intercept; retain the same common Q9 support/design-survey weights. Average cell slopes without treating repeats as new people. No causal or prospective claim; overlapping one-year windows share11months.',
        'cells':rows,'scopes':{k:{name:float(np.mean([r[name+'_slope_on_prior'] for r in rows if r['month'] in d['months']])) for name in ('model','real')} for k,d in s['scopes'].items()},
        'source_summary_sha256':hashlib.sha256((folder/'summary.json').read_bytes()).hexdigest(),
        'diagnostic_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'new_api_calls':0}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['scopes'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();diagnose(a.folder,a.out)
