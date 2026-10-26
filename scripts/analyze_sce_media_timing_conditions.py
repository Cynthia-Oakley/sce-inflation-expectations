#!/usr/bin/env python3
"""Descriptive subgroup checks of cached timing responses; zero API/Q9 fits."""
import argparse,json,sys
from pathlib import Path
from collections import Counter
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation import cognition as shared
from studies.sce_inflation_expectations.experiments.frozen_batch import read_json,dump,sha,ROOT

def analyze(evaluation,out):
    if out.exists():raise ValueError('Fresh output required')
    s=read_json(evaluation/'summary.json');cases=read_json(evaluation/'cases_private.json')
    support={tuple(x) for x in s['support_summaries']['four_new_arms_common_support']['q9_positions']}
    selected=[r for r in cases if (r['month'],r['userid']) in support]
    features=['age_group','education_group','household_income_band','numeracy','housing_tenure']
    rows=[]
    def group(r,f):
        if f!='previous_q9_level':return r['profile'].get(f,'unknown')
        value=r['real'].get('previous_q9_mean')
        return 'no_observed_previous' if not shared.finite(value) else 'below_2' if value<2 else '2_to_5' if value<5 else '5_or_more'
    for f in features+['previous_q9_level']:
        groups=sorted({group(r,f) for r in selected})
        for g in groups:
            matching=[r for r in selected if group(r,f)==g]
            cells=[]
            for m in s['protocol']['months']:
                for rep in [1,2]:
                    cell=[r for r in matching if r['month']==m and r['repeat']==rep]
                    if not cell:continue
                    w=np.array([r['survey_weight'] for r in cell],float)
                    result={a:shared._q9_cell_metrics(cell,a,w) for a in ['C0','C1','T0','T1']}
                    cells.append(dict(month=m,repeat=rep,n=len(cell),ess=float(w.sum()**2/(w@w)),arms=result))
            names=('q9_center_mae_pp','q9_center_bias_pp','individual_density_mean_mae_pp','cross_section_w1_pp','cross_person_iqr_pp')
            aggregate={a:{k:float(np.mean([c['arms'][a][k] for c in cells])) for k in names} for a in ['C0','C1','T0','T1']}
            rows.append(dict(feature=f,group=g,n_person_months=len(matching)//2,month_repeat_cells=len(cells),
                minimum_cell_n=min(c['n'] for c in cells),minimum_cell_ess=min(c['ess'] for c in cells),
                weak_support=any(c['n']<10 or c['ess']<10 for c in cells),arms=aggregate,
                change_T0_C0={k:aggregate['T0'][k]-aggregate['C0'][k] for k in names},
                change_T1_T0={k:aggregate['T1'][k]-aggregate['T0'][k] for k in names}))
    out.mkdir(parents=True)
    result=dict(status='descriptive_conditional_cache_analysis_complete',new_api_calls=0,new_q9_fits=0,
        common_support_person_months=len(support),groups=rows,
        notes=['Exploratory overlapping profile subgroups, not randomized treatment heterogeneity.',
               'Month/repeat cells equally weighted within each available subgroup; sparse cells marked not hidden.',
               'Subgroup medians and MAEs cannot be added to reconstruct the whole-sample median or MAE.',
               'Unknown profiles retained as a separately marked group; no fabricated field values.'],
        source_sha256={str((evaluation/f).relative_to(ROOT)):sha(evaluation/f) for f in ['summary.json','cases_private.json']})
    dump(out/'summary.json',result)
    dump(out/'manifest.json',dict(summary_sha256=sha(out/'summary.json'),script_sha256=sha(__file__),new_api_calls=0,new_q9_fits=0))
    return dict(out=str(out),groups=len(rows),new_api_calls=0,new_q9_fits=0)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(analyze(a.evaluation.resolve(),a.out.resolve()),ensure_ascii=False))
