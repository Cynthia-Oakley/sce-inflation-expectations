"""Evaluation-only finite-population and cached-LLM Core/Normal checks.

Only selected Core answers are passed to the expansion. Current target answers
are read here for scoring, never by population/grid sampling or the estimator.
"""
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ..core_normal_joint import JointAnswer, PointAnswer, JointExpansion, FOUR_FIELDS
from ..population.grid_sampling import plan_core, draw_core
from ..monthly_analysis import weighted_summary
from .grid_dimension_selection import ROOT, CACHE, sha, dump
from .grid_oversampling import load_population_frame
from .metrics import compare_distributions, wasserstein1, quantile

PROTOCOL = Path(__file__).with_name('core_normal_protocol_20261023.json')
BINS = [f'Q9_bin{i}' for i in range(1, 11)]
PERIODS = {'development':(201901,202212),'2023_2024':(202301,202412),'2025_01_10':(202501,202510)}


def finite_point(x):
    return float(x) if isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x) and abs(x)<=100 else None


def population_frame():
    f = load_population_frame()
    tenure = pd.read_parquet(CACHE, columns=['date','userid','tenure'])
    f = f.merge(tenure,on=['date','userid'],validate='one_to_one')
    f['entry'] = np.where(f.tenure.eq(1),'newcomer',np.where(f.tenure.gt(1),'returner','unknown'))
    return f


def profiles(rows):
    result=[]
    for r in rows.to_dict('records'):
        result.append({'id':str(int(r['userid'])), 'weight':float(r['weight']), 'entry':r['entry'],
                       **{k:(None if pd.isna(r.get(k)) else str(r[k])) for k in [*FOUR_FIELDS,'gender']}})
    return result


def allocation_records(people):
    return [{'id':r['id'],'weight':r['weight'],
             'cell':'|'.join(r[k] for k in FOUR_FIELDS) if all(r[k] is not None for k in FOUR_FIELDS) else 'unknown'}
            for r in people]


def atom(uid, bins, mean, iqr, point):
    try:
        return JointAnswer(str(uid),tuple(float(v) for v in bins),float(mean),float(iqr),finite_point(point))
    except (ValueError,TypeError):
        return None


def answers_frame():
    return pd.read_parquet(CACHE,columns=['date','userid','Q9_mean','Q9_iqr','Q8v2part2',*BINS])


def answer_maps(rows):
    q9, q8 = {}, {}
    for r in rows.to_dict('records'):
        uid=str(int(r['userid'])); point=finite_point(r['Q8v2part2'])
        a=atom(uid,[r[k] for k in BINS],r['Q9_mean'],r['Q9_iqr'],point)
        if a is not None:q9[uid]=a
        if point is not None:q8[uid]=PointAnswer(uid,point)
    return q9,q8


def q9_metrics(answers, masses, target, weights):
    x=[a.q9_mean for a in answers]; y=[a.q9_mean for a in target]
    r=compare_distributions(x,masses,y,weights)
    mass=np.asarray(masses,float); tw=np.asarray(weights,float)
    return {'median_mae_pp':r['median_error_pp'],'median_bias_pp':r['median_bias_pp'],
            'w1_pp':r['w1_pp'],'iqr_pp':r['simulated']['iqr_pp'],
            'observed_iqr_pp':r['observed']['iqr_pp'],
            'mean_density_iqr_bias_pp':float(np.average([a.q9_iqr for a in answers],weights=mass)-np.average([a.q9_iqr for a in target],weights=tw)),
            'zero_deflation_share_bias':float(np.average([sum(a.q9_bins[5:])==0 for a in answers],weights=mass)-np.average([sum(a.q9_bins[5:])==0 for a in target],weights=tw))}


def q8_metrics(answers, masses, target, weights):
    x=[a.q8 for a in answers]; y=[a.q8 for a in target]
    p=weighted_summary(x,masses,interpolate_median=True)
    o=weighted_summary(y,weights,interpolate_median=True)
    return {'median_mae_pp':abs(p['weighted_median_pp']-o['weighted_median_pp']),
            'w1_pp':wasserstein1(x,masses,y,weights),
            'median_bias_pp':p['weighted_median_pp']-o['weighted_median_pp']}


def score_population(people, selected, q9_reference, q8_reference, *, tau=None):
    """No target answer enters model fit; reference masks applied afterwards."""
    core=[r['id'] for r in selected]; core_set=set(core)
    weights={r['id']:r['poststratified_weight'] for r in selected}
    valid9=[q9_reference[u] for u in core if u in q9_reference]
    valid8=[q8_reference[u] for u in core if u in q8_reference]
    people_by_id={r['id']:r for r in people}
    banks={}
    if tau is not None:
        try:
            banks['q9']=JointExpansion(people,core,valid9,weights,prior_strength=tau)
            banks['q8']=JointExpansion(people,core,valid8,weights,prior_strength=tau)
        except ValueError as error:
            return {'status':'unsupported_core_bank','error':str(error)}
    result={'status':'ok','core_n':len(core),'valid_q9_core_n':len(valid9),
            'valid_q8_core_n':len(valid8),'normal_n':len(people)-len(core)}
    for scope in ['normal','all']:
        eligible=[u for u in people_by_id if scope=='all' or u not in core_set]
        for name,reference,available,metric in [('q9',q9_reference,valid9,q9_metrics),('q8',q8_reference,valid8,q8_metrics)]:
            ids=[u for u in eligible if u in reference]
            if not ids or not available:
                result[f'{scope}_{name}']={'status':'no_valid_target_or_core'};continue
            target=[reference[u] for u in ids]; tw=[people_by_id[u]['weight'] for u in ids]
            if tau is None:
                answers=available;mass=np.array([weights[str(a.id)] for a in answers])
            else:
                model=banks[name];answers=model.answers;mass=model.atom_weights(ids)
            r=metric(answers,mass,target,tw)
            r.update(n_valid_targets=len(ids),target_weight_mass=float(sum(tw)),
                     valid_target_population_fraction=float(sum(tw)/sum(people_by_id[u]['weight'] for u in eligible)))
            if tau is not None:
                report=banks[name].report(ids)
                r.update(parent_fraction=report['parent_population_fraction'],
                         local_unsupported_fraction=report['unsupported_local_population_fraction'])
            result[f'{scope}_{name}']=r
    # Conditional distribution gaps, scored only on held-out Normal targets.
    groups=[]
    for field in [*FOUR_FIELDS,'entry']:
        for value in sorted({str(r.get(field)) for r in people}):
            ids=[r['id'] for r in people if r['id'] not in core_set and str(r.get(field))==value and r['id'] in q9_reference]
            if not ids:continue
            tw=[people_by_id[u]['weight'] for u in ids]
            if tau is None:
                aa=valid9;mass=np.array([weights[str(a.id)] for a in aa])
            else:
                aa=banks['q9'].answers;mass=banks['q9'].atom_weights(ids)
            r=q9_metrics(aa,mass,[q9_reference[u] for u in ids],tw)
            r.update(dimension=field,group=value,n=len(ids),ess=float(sum(tw)**2/np.dot(tw,tw)),
                     weight_mass=float(sum(tw)),sparse=bool(len(ids)<20 or sum(tw)**2/np.dot(tw,tw)<10))
            groups.append(r)
    result['conditional_q9']=groups
    return result


def aggregate(rows):
    result={'draw_month_cells':len(rows),'months':len({r['month'] for r in rows}),
            'unsupported_draw_cells':sum(r['status']!='ok' for r in rows)}
    good=[r for r in rows if r['status']=='ok']
    for scope in ['normal_q9','all_q9','normal_q8','all_q8']:
        available=[r[scope] for r in good if 'median_mae_pp' in r.get(scope,{})]
        if available:
            keys=[k for k,v in available[0].items() if isinstance(v,(int,float))]
            result[scope]={k:float(np.mean([a[k] for a in available])) for k in keys}
    return result


def run_human(out, *, months=None):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output directory required')
    out.mkdir(parents=True)
    p=json.loads(PROTOCOL.read_text());dump(out/'protocol.json',p)
    pop=population_frame();invalid=int((~(np.isfinite(pop.weight)&pop.weight.gt(0))).sum())
    pop=pop.loc[np.isfinite(pop.weight)&pop.weight.gt(0)]
    if months is not None:pop=pop.loc[pop.date.isin(months)]
    truth=answers_frame();monthly=[]
    for month,rows in pop.groupby('date',sort=True):
        people=profiles(rows);sampling=allocation_records(people)
        # Selection sees demographic P only; current answers projected below.
        draws=[]
        for setting in p['core_settings']:
            plan=plan_core(sampling,setting['n'],minimum=setting['minimum'])
            for seed in p['allocation_seeds']:
                draws.append((setting,seed,draw_core(sampling,plan,seed=seed,month=int(month))))
        q9,q8=answer_maps(truth.loc[truth.date.eq(month)])
        for setting,seed,selected in draws:
            for method in p['methods']:
                tau=None if method=='poststratified_Core_only' else float(method.removeprefix('joint_tau'))
                r=score_population(people,selected,q9,q8,tau=tau)
                monthly.append({'month':int(month),'core_budget':setting['n'],'seed':seed,'method':method,**r})
        dump(out/f'{month}_evaluation_private.json',[r for r in monthly if r['month']==int(month)])
        print(f'{month}: human-Core holdout complete',flush=True)
    # Freeze selection before computing temporal summaries.
    choices={}
    for setting in p['core_settings']:
        budget=setting['n'];dev=[r for r in monthly if r['core_budget']==budget and 201901<=r['month']<=202212]
        if not dev:continue
        alternatives={m:aggregate([r for r in dev if r['method']==m]) for m in p['methods'] if m.startswith('joint_')}
        base=alternatives['joint_tau0']['normal_q9']
        eligible={m:r for m,r in alternatives.items() if r.get('unsupported_draw_cells',1)==0 and r['normal_q9']['median_mae_pp']<=base['median_mae_pp']+.05}
        winner=min(eligible,key=lambda m:(eligible[m]['normal_q9']['w1_pp'],float(m.removeprefix('joint_tau')))) if eligible else None
        choices[str(budget)]={'selected_method':winner,'development':alternatives,'rule':p['parameter_selection']}
    dump(out/'development_selection_frozen_before_temporal.json',choices)
    periods={}
    for label,(start,end) in PERIODS.items():
        periods[label]={}
        for setting in p['core_settings']:
            budget=setting['n'];part=[r for r in monthly if r['core_budget']==budget and start<=r['month']<=end]
            if part:periods[label][str(budget)]={m:aggregate([r for r in part if r['method']==m]) for m in p['methods']}
    result={'status':'human_core_statistical_validation_not_llm_performance',
            'completed_at_utc':datetime.now(timezone.utc).isoformat(),'new_api_calls':0,'q9_refits':0,
            'positive_weight_person_months':len(pop),'invalid_weights_in_82_month_frame':invalid,
            'protocol':p,'development_selection':choices,'periods':periods,
            'source_sha256':{str(path.relative_to(ROOT)):sha(path) for path in [CACHE,PROTOCOL,Path(__file__),
                ROOT/'studies/sce_inflation_expectations/core_normal_joint.py',
                ROOT/'studies/sce_inflation_expectations/population/grid_sampling.py']}}
    dump(out/'monthly_private.json',monthly);dump(out/'summary.json',result)
    return result
