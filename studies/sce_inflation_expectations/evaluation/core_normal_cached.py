"""Reconstruct held-out saved V3.2 answers, without a new model call or fit."""
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from ..core_normal_joint import JointExpansion, PointAnswer
from ..population.grid_sampling import plan_core, draw_core
from .grid_dimension_selection import ROOT, sha, dump
from .core_normal_validation import (PROTOCOL, population_frame, profiles,
    allocation_records, atom, finite_point, score_population, q9_metrics, q8_metrics, aggregate)

CACHED = ROOT/'outputs/sce_v32_news_matching_evaluation_20261022_v2/cases_private.json'


def run(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output directory required')
    out.mkdir(parents=True)
    p=json.loads(PROTOCOL.read_text());dump(out/'protocol.json',p)
    cases=json.loads(CACHED.read_text())
    frame=population_frame().set_index(['date','userid'])
    groups=defaultdict(list)
    for r in cases:groups[(int(r['month']),int(r['repeat']))].append(r)
    monthly=[]
    for (month,repeat),rows in sorted(groups.items()):
        if len(rows)!=len({r['userid'] for r in rows}):raise ValueError('Duplicate saved person/month/repeat')
        pop=[];llm9={};llm8={};real9={};real8={}
        for r in rows:
            uid=str(int(r['userid']));source=frame.loc[(month,int(uid))].to_dict()
            source.update(userid=int(uid),weight=float(r['design_survey_weight']))
            # The first-stage sampled roster is this diagnostic's target frame.
            pop.extend(profiles(__import__('pandas').DataFrame([source])))
            llm=r['arms']['random_quantity'];real=r['real']
            for bank,v in [(llm9,llm),(real9,{'q9_bins':real['q9_bins'],'mean':real['q9_mean'],
                                           'iqr':real['q9_iqr'],'point':real['q8_point']})]:
                a=atom(uid,v['q9_bins'],v['mean'],v['iqr'],v['point'])
                if a is not None:bank[uid]=a
            if finite_point(llm['point']) is not None:llm8[uid]=PointAnswer(uid,float(llm['point']))
            if finite_point(real['q8_point']) is not None:real8[uid]=PointAnswer(uid,float(real['q8_point']))
        budget=64 if len(pop)<=96 else 128
        plan=plan_core(allocation_records(pop),budget,minimum=1)
        pp={r['id']:r for r in pop}
        for seed in p['allocation_seeds']:
            selected=draw_core(allocation_records(pop),plan,seed=seed,month=month)
            core=[r['id'] for r in selected];cw={r['id']:r['poststratified_weight'] for r in selected}
            for method in p['methods']:
                tau=None if method=='poststratified_Core_only' else float(method.removeprefix('joint_tau'))
                preservation=score_population(pop,selected,llm9,llm8,tau=tau)
                human={}
                if preservation['status']=='ok':
                    for scope in ['normal','all']:
                        allowed=[u for u in pp if scope=='all' or u not in set(core)]
                        for name,refs,reals,metric in [('q9',llm9,real9,q9_metrics),('q8',llm8,real8,q8_metrics)]:
                            # Same valid saved-LLM/human support, independently by field.
                            targets=[u for u in allowed if u in refs and u in reals]
                            if not targets:continue
                            answers=[refs[u] for u in core if u in refs]
                            if tau is None:
                                mass=np.array([cw[str(a.id)] for a in answers])
                            else:
                                model=JointExpansion(pop,core,answers,cw,prior_strength=tau)
                                answers=model.answers;mass=model.atom_weights(targets)
                            human[f'{scope}_{name}']=metric(answers,mass,[reals[u] for u in targets],[pp[u]['weight'] for u in targets])
                            human[f'{scope}_{name}']['n_valid_targets']=len(targets)
                monthly.append({'month':month,'repeat':repeat,'seed':seed,'core_budget':budget,
                                'target_roster_n':len(pop),'method':method,**preservation,
                                'human_comparison_same_saved_valid_support':human})
        print(f'{month} repeat {repeat}: cached-LLM preservation check complete',flush=True)
    result={'status':'cached_llm_subsample_preservation_not_full_wave_validation',
            'completed_at_utc':datetime.now(timezone.utc).isoformat(),'new_api_calls':0,'q9_refits':0,
            'protocol':p,'target_roster_months':len({m for m,r in groups}),'source_cases':len(cases),
            'methods':{m:aggregate([r for r in monthly if r['method']==m]) for m in p['methods']},
            'limitations':['64/96 or128/192, floor1 is a small saved-roster diagnostic, not the proposed full-wave 256/384/512 design.',
                           'Preservation error compares with other saved LLM answers, not human truth. Human fit is separate.',
                           'Only fixed random_quantity V3.2 arm used; repeats never increase distinct human count.',
                           'Existing cases sampled chiefly from prior-valid returners, not evidence for full newcomer performance.'],
            'source_sha256':{str(path.relative_to(ROOT)):sha(path) for path in [CACHED,PROTOCOL,Path(__file__),
                ROOT/'studies/sce_inflation_expectations/core_normal_joint.py',
                ROOT/'studies/sce_inflation_expectations/evaluation/core_normal_validation.py']}}
    dump(out/'monthly_private.json',monthly);dump(out/'summary.json',result)
    return result
