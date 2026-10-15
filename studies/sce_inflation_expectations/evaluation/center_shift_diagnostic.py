"""Separate LLM group-center error from compressed individual positions, offline."""
from pathlib import Path
from collections import defaultdict
import hashlib
import json
import math

import numpy as np
from scipy.stats import wasserstein_distance,spearmanr

ROOT=Path(__file__).resolve().parents[3]
FILES={'development':ROOT/'outputs/sce_expanded_state_trial_20261014_v3/development_cases_private.json',
       'previous_evaluation':ROOT/'outputs/sce_expanded_state_evaluation_20261014_v1/cases_private.json'}


def quantile(x,q):
    a=np.sort(np.asarray(x,float));return float(a[max(0,math.ceil(len(a)*q)-1)])


def common_shift(previous,llm):
    """No current truth: preserve every prior position, match the LLM median."""
    p=np.asarray(previous,float);l=np.asarray(llm,float)
    if p.shape!=l.shape or not len(p) or not np.isfinite(p).all() or not np.isfinite(l).all():raise ValueError('Valid aligned centers required')
    return p+quantile(l,.5)-quantile(p,.5)


def metric(pred,truth,previous):
    p,t,b=[np.asarray(v,float) for v in [pred,truth,previous]]
    return {'center_MAE':abs(quantile(p,.5)-quantile(t,.5)),
        'signed_center_error':quantile(p,.5)-quantile(t,.5),
        'cross_W1':float(wasserstein_distance(p,t)),
        'change_W1':float(wasserstein_distance(p-b,t-b)),
        'IQR':quantile(p,.75)-quantile(p,.25),
        'individual_MAE':float(np.mean(np.abs(p-t))),
        'rank_correlation':float(spearmanr(p,t).statistic) if np.ptp(p)>0 and np.ptp(t)>0 else None}


def run(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output required')
    phases={};private=[]
    for phase,path in FILES.items():
        all_rows=json.loads(path.read_text());groups=defaultdict(list)
        for r in all_rows:
            if r['common']:groups[r['month'],r['repeat']].append(r)
        cells=[]
        for (month,repeat),rows in sorted(groups.items()):
            b=np.array([r['previous'] for r in rows]);l=np.array([r['self_update'] for r in rows]);truth=np.array([r['actual'] for r in rows])
            shifted=common_shift(b,l)
            assert abs(quantile(shifted,.5)-quantile(l,.5))<1e-10
            assert abs((quantile(shifted,.75)-quantile(shifted,.25))-(quantile(b,.75)-quantile(b,.25)))<1e-10
            arms={'LLM_direct':l,'prior_plus_LLM_common_shift':shifted,'copy_previous':b}
            cells.append({'month':month,'repeat':repeat,'n':len(rows),
                'LLM_common_shift':quantile(l,.5)-quantile(b,.5),
                'real_cohort_center_change_evaluation_only':quantile(truth,.5)-quantile(b,.5),
                'real_IQR':quantile(truth,.75)-quantile(truth,.25),
                'metrics':{k:metric(v,truth,b) for k,v in arms.items()}})
            for i,r in enumerate(rows):private.append({'phase':phase,'month':month,'repeat':repeat,'agent_id':r['agent_id'],
                                                     'prediction':float(shifted[i])})
        metrics={arm:{k:float(np.mean([c['metrics'][arm][k] for c in cells])) for k in cells[0]['metrics'][arm]} for arm in cells[0]['metrics']}
        phases[phase]={'cells':cells,'aggregate':metrics,'common_generations':sum(c['n'] for c in cells),
                       'unique_person_months':len({(r['month'],r['userid']) for r in all_rows if r['common']})}
    summary={'status':'completed_offline_center_only_architecture_diagnostic','new_api_calls':0,
        'phases':phases,'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*FILES.values(),Path(__file__).resolve()]},
        'formula':'prior_i + median(LLM centers in month/repeat) - median(prior centers in same cell)',
        'limits':['All months previously exposed: exploratory development diagnostic, not a new independent test.',
            'Center-only surrogate, not a generated Q9 questionnaire or a re-fitted density. No uncertainty/zero-bin claims.',
            'LLM common center preserved exactly, hence center MAE cannot improve by construction.',
            'Inherited prior ranks/width are not new LLM identity information or correct individual updates.',
            'Actual current answers enter metric evaluation only, never common_shift predictions. No parameter fitted or selected.']}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (out/'predictions_private.json').write_text(json.dumps(private,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v['aggregate'] for k,v in phases.items()},ensure_ascii=False));return summary
