"""Q8-specific readout added to the shared trial evaluator; no new fitter."""
from collections import defaultdict
import numpy as np
from .metrics import quantile, wasserstein1
from .cognition import finite


def legacy_truth(rows, reference):
    """Reuse old scored means/IQR and exact questionnaire bins; never refit."""
    import pandas as pd
    bins=[f'Q9_bin{i}' for i in range(1,11)]
    frame=pd.read_parquet(reference,columns=['date','userid',*bins])
    selected={(r['month'],r['userid']) for r in rows}
    frame=frame.loc[[tuple(k) in selected for k in frame[['date','userid']].to_numpy()]]
    lookup={(int(r['date']),int(r['userid'])):[float(r[k]) if finite(r[k]) else None for k in bins]
            for r in frame.to_dict('records')}
    result={}
    for row in rows:
        key=(row['month'],row['agent_id'],row['repeat'])
        if key in result:
            raise ValueError('Unique legacy evaluation rows required')
        actual=lookup[row['month'],row['userid']]
        if any(not finite(v) or v<0 or v>100 for v in actual) or abs(sum(actual)-100)>1e-6:
            if finite(row['actual']) or finite(row['actual_iqr']):
                raise ValueError('Legacy score present but actual probabilities invalid')
            actual=[]  # Genuine missing Q9, not an invented probability vector.
        result[key]={'q9_mean':row['actual'],'q9_iqr':row['actual_iqr'],
            'q9_zero_deflation':row['actual_zero_deflation'],'q8_point':row['actual_point'],
            'q9_bins':actual,'previous_q9_mean':row['previous'],'previous_q9_bins':row['previous_bins']}
    return result


def _metrics(rows, arm, weights=None):
    y=np.asarray([r['real']['q8_point'] for r in rows],float)
    p=np.asarray([r['prior_q8_point'] if arm=='copy_previous' else r['arms'][arm]['point'] for r in rows],float)
    w=np.ones(len(rows)) if weights is None else np.asarray(weights,float)
    result={'center_mae_pp':abs(quantile(p,w,.5)-quantile(y,w,.5)),
        'personal_mae_pp':float(np.average(abs(p-y),weights=w)),
        'w1_pp':wasserstein1(p,w,y,w),'iqr_pp':quantile(p,w,.75)-quantile(p,w,.25)}
    valid=np.array([finite(r.get('prior_q8_point')) for r in rows])
    if valid.any() and w[valid].sum()>0:
        old=np.asarray([r['prior_q8_point'] for r in rows if finite(r.get('prior_q8_point'))],float)
        result['delta_w1_pp']=wasserstein1(p[valid]-old,w[valid],y[valid]-old,w[valid])
    return result


def point_readout(cases,protocol,draws=1000):
    arms=protocol['arms'];by_person=defaultdict(list)
    for r in cases:by_person[r['month'],r['userid']].append(r)
    rows=[r for rr in by_person.values()
        if {r['repeat'] for r in rr}==set(protocol['generation_repeats'])
        and all(finite(r['real']['q8_point']) and all(finite(r['arms'][a]['point']) for a in arms) for r in rr)
        for r in rr]
    cells=[[r for r in rows if r['month']==m and r['repeat']==rep]
        for m in protocol['months'] for rep in protocol['generation_repeats']]
    if any(not c for c in cells):
        return {'status':'incomplete_common_q8_support','candidate_passed':False}
    def mean_metrics(cc,a,weighted=False):
        allmetrics=[_metrics(c,a,[r['survey_weight'] for r in c] if weighted else None) for c in cc]
        keys=set.intersection(*(set(x) for x in allmetrics))
        return {k:float(np.mean([x[k] for x in allmetrics])) for k in sorted(keys)}
    full={a:mean_metrics(cells,a) for a in arms}
    prior_cells=[[r for r in c if finite(r.get('prior_q8_point'))] for c in cells]
    prior={a:mean_metrics(prior_cells,a) for a in [*arms,'copy_previous']} if all(prior_cells) else None
    people=sorted({r['userid'] for r in rows});index={u:i for i,u in enumerate(people)}
    rng=np.random.default_rng(20261019);samples=[];names=('center_mae_pp','personal_mae_pp','w1_pp')
    for _ in range(draws):
        counts=np.bincount(rng.integers(len(people),size=len(people)),minlength=len(people))
        sums={a:np.zeros(3) for a in arms};ok=True
        for c in cells:
            w=np.asarray([counts[index[r['userid']]] for r in c],float)
            if not w.sum():ok=False;break
            for a in arms:
                v=_metrics(c,a,w);sums[a]+=[v[k] for k in names]
        if ok:samples.append((sums[arms[1]]-sums[arms[0]])/len(cells))
    intervals=dict(zip(names,np.quantile(samples,[.025,.975],axis=0).T.tolist())) if samples else None
    baseline9=[]
    for month in protocol['months']:
        for repeat in protocol['generation_repeats']:
            c=[r for r in cases if r['month']==month and r['repeat']==repeat
               and finite(r['real'].get('q9_mean')) and finite(r['real'].get('previous_q9_mean'))
               and all(finite(r['arms'][a].get('mean')) for a in arms)]
            if not c:continue
            y=[r['real']['q9_mean'] for r in c];p=[r['real']['previous_q9_mean'] for r in c]
            w=[r['survey_weight'] for r in c]
            baseline9.append({'month':month,'repeat':repeat,'n':len(c),
                'center_mae_pp':abs(quantile(p,w,.5)-quantile(y,w,.5)),
                'w1_pp':wasserstein1(p,w,y,w)})
    return {'status':'completed_independent_q8_readout','common_person_months':len({(r['month'],r['userid']) for r in rows}),
        'equal_people':full,'survey_weighted_sensitivity':{a:mean_metrics(cells,a,True) for a in arms},
        'same_prior_support':prior,'common_prior_person_months':len({(r['month'],r['userid']) for c in prior_cells for r in c}),
        'monthly_repeat_cells':[{'month':c[0]['month'],'repeat':c[0]['repeat'],'n':len(c),
                                'metrics':{a:_metrics(c,a) for a in arms}} for c in cells],
        'paired_person_intervals95':intervals,'bootstrap_draws_used':len(samples),
        'q9_copy_previous_same_q9_support':{'cells':baseline9,
            'center_mae_pp':float(np.mean([r['center_mae_pp'] for r in baseline9])) if baseline9 else None,
            'w1_pp':float(np.mean([r['w1_pp'] for r in baseline9])) if baseline9 else None},
        'scope':'Conditional on inspected months; repeated generations clustered with person. Not time-generalization or causal intervals.'}
