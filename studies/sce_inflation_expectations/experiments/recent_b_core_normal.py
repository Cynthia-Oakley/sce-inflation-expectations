"""Offline, fixed-size B proxy expansion. No target truth or new model calls.

Represent the existing old-frame mass at a declared 1300-proxy scale. Preserve
Core raw population mass, integrate only its unrepresented remainder, and use
the already A-selected tau=8 empirical-Bayes joint-answer estimator unchanged.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import math

import numpy as np

from .frozen_batch import ROOT, read_json, dump, sha
from . import recent_b_sampled_terminal as source_run
from . import frozen_message_queue as queue
from ..core_normal_joint import JointAnswer, JointExpansion
from ..population.monthly_fine_grid import profile, PROFILE_KEYS
from ..submission_tools.reproduce import no_network

SEED=20261026
TAU=8.
SOURCE=ROOT/'outputs/sce_recent_b_sampled_terminal_20261026_v1'
A_PROTOCOL=ROOT/'docs/workstreams/20261026_core_normal_full_a/protocol.json'
A_SELECTION=ROOT/'outputs/sce_full_a_core_normal_prediction_20261026_v2/parameter_selection.json'


def draw_rng(*parts):
    key=hashlib.sha256('|'.join(map(str,(SEED,*parts))).encode()).digest()
    return np.random.default_rng(int.from_bytes(key[:8],'big'))


def allocate_normal(masses, n):
    """At least one row for each positive-mass cell; no fictitious zero cells."""
    keys=sorted((k for k,v in masses.items() if v>1e-10),key=str)
    if not keys or n<len(keys):raise ValueError('Insufficient Normal rows for supported residual cells')
    total=sum(masses[k] for k in keys)
    ideal={k:(n-len(keys))*masses[k]/total for k in keys}
    result={k:1+math.floor(ideal[k]) for k in keys}
    rest=n-sum(result.values())
    ordered=sorted(keys,key=lambda k:(-(ideal[k]-math.floor(ideal[k])),str(k)))
    for k in ordered[:rest]:result[k]+=1
    assert sum(result.values())==n
    return result


def make_frame(records, month, target_n):
    """Size changes row representation, not the old-frame CDF or grid mass."""
    ids=[r['persona']['agent_id'] for r in records]
    if len(set(ids))!=len(ids) or target_n<=len(ids):raise ValueError('Unique Core and larger proxy target required')
    bycell=defaultdict(list);mass=defaultdict(float);retained=defaultdict(float)
    for r in records:
        weight,raw=r['analysis_weight'],r['raw_source_weight']
        if any(type(w) not in (int,float) or not math.isfinite(w) or w<=0 for w in (weight,raw)):
            raise ValueError('Positive declared analysis and raw-source weights required')
        features=profile(r['persona']['attributes']);key=tuple(features[k] for k in PROFILE_KEYS)
        bycell[key].append(r);mass[key]+=weight;retained[key]+=raw
    total=sum(mass.values());scale=target_n/total
    residual={k:mass[k]-retained[k] for k in mass}
    if any(v < -1e-8*max(1.,total) for v in residual.values()):
        raise ValueError('Core raw population mass exceeds represented cell mass')
    residual={k:max(0.,v) for k,v in residual.items()}
    allocation=allocate_normal(residual,target_n-len(records))
    frame=[];profiles={};core_weights={}
    for r in records:
        aid=r['persona']['agent_id'];features=profile(r['persona']['attributes'])
        frame.append(dict(id=aid,weight=r['raw_source_weight']*scale,entry='unknown',**features))
        profiles[aid]=dict(kind='Core_LLM',attributes=deepcopy(r['persona']['attributes']),
                          source_frame_reference=r['persona']['source_reference_period'])
        core_weights[aid]=r['analysis_weight']
    index=0
    for key in sorted(allocation,key=str):
        members=sorted(bycell[key],key=lambda r:r['persona']['agent_id'])
        probabilities=np.array([r['analysis_weight'] for r in members],float);probabilities/=probabilities.sum()
        n=allocation[key];weight=residual[key]*scale/n
        for _ in range(n):
            index+=1;aid=f'BNormal-{month}-{index:04}'
            donor=members[int(draw_rng('profile',month,aid).choice(len(members),p=probabilities))]
            frame.append(dict(id=aid,weight=weight,entry='unknown',**dict(zip(PROFILE_KEYS,key))))
            profiles[aid]=dict(kind='statistical_Normal',attributes=deepcopy(donor['persona']['attributes']),
                profile_donor_id=donor['persona']['agent_id'],source_frame_reference=donor['persona']['source_reference_period'])
    actual=defaultdict(float)
    for r in frame:actual[tuple(r[k] for k in PROFILE_KEYS)]+=r['weight']
    error=max(abs(actual[k]-mass[k]*scale) for k in mass)
    if len(frame)!=target_n or not math.isclose(sum(r['weight'] for r in frame),target_n,abs_tol=1e-8) or error>1e-8:
        raise ValueError('Proxy size or population-mass conservation failed')
    return frame,profiles,core_weights,dict(original_represented_mass=total,target_mass=target_n,
        scale=scale,core_mass_fraction=sum(retained.values())/total,grid_mass_max_error=error,
        known_or_partial_cells=len(mass),normal_cells=len(allocation),
        note='Unknown entry for all recent proxies; no invented newcomer/returner status. Cell mass is the old frame, not current population truth.')


def model_projection(source,p):
    """Bind effective fields to raw main/one-repair responses, then lookup scores."""
    cachepath=source/'evaluation/scoring_cache_private.json'
    expected=read_json(source/'evaluation/manifest.json')['files_sha256'][cachepath.name]
    if sha(cachepath)!=expected:raise ValueError('Frozen scorer cache changed')
    cache={tuple(r['bins']):r['score'] for r in read_json(cachepath)}
    for name,digest in read_json(source/'combined/manifest.json')['files_sha256'].items():
        if sha(source/'combined'/name)!=digest:raise ValueError('Combined output changed')
    mi,mr=queue.archive(source/'main');ri,rr=queue.archive(source/'repair')
    slots={r['key']:r for r in read_json(source/'slot_index_private.json')}
    source_run.transport._validate_main_archive(mi,mr,list(slots.values()))
    main={r['key']:r for r in mr};repairs={r['key'].removeprefix('repair1|'):r for r in rr}
    policy=read_json(source/'package/execution_policy.json')
    targets=source_run.transport._repair_targets(mr,slots,policy)
    source_run.transport._validate_repair(ri,rr,targets,slots)
    initials={m:read_json(ROOT/p['input_templates']/m/'initial_states_private.json') for m in p['months']}
    projected=defaultdict(dict);used={}
    for line in (source/'combined/positions_private.jsonl').open():
        r=json.loads(line);m,aid,key=r['month'],r['agent_id'],r['key']
        if not r['actual_model_results'] or aid in projected[m]:raise ValueError('Only unique actual model records accepted')
        state=source_run.merge_state(initials[m][aid],main[key],repairs.get(key),targets.get(key,{}).get('fields',[]),m)
        if state!=r['state_after'] or not all(state['transition']['field_updated_from_model'].values()):
            raise ValueError('Effective answer not bound to full actual model output')
        bins=state['fields']['q9']['value'];score=cache.get(tuple(bins))
        if score is None or any(type(score.get(k)) not in (int,float) or not math.isfinite(score[k]) for k in ('mean','iqr')):
            raise ValueError('Finite cached model-only density scores required; no refit or prior substitution')
        projected[m][aid]=dict(id=aid,q9_bins=bins,q9_mean=score['mean'],q9_iqr=score['iqr'],q8=state['fields']['q8']['value'])
        used[tuple(bins)]=score
    return projected,[dict(bins=list(k),score=v) for k,v in used.items()]


def run(out,target_n=1300,source=SOURCE):
    out,source=Path(out).resolve(),Path(source).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs') or target_n not in (1200,1300):
        raise ValueError('Fresh ignored output and predeclared size 1200 or 1300 required')
    p,manifest=source_run.checked(source)
    receipt=read_json(source/'generation_receipt.json')
    if receipt['technical_complete']!=5632 or not receipt['actual_model_results']:
        raise ValueError('Completed full B model generation required')
    if read_json(A_SELECTION)['selected_tau']!=TAU:
        raise ValueError('Imported fixed A tau differs; do not choose it using B results')
    # Freeze population size and imported A tau before any expansion. No target
    # values or target human questionnaire records are accessed anywhere here.
    out.mkdir()
    protocol=dict(schema='sce_B_proxy_Core_Normal/v1',months=p['months'],target_n=target_n,
        core_n=512,normal_n=target_n-512,tau=TAU,tau_source='A-selected fixed tau=8; no B tuning',
        seed=SEED,target='Declared synthetic proxy scale, not observed current survey membership',
        mass='Core retains old raw-source mass; Normal receives only remaining old-frame mass; uniformly rescale total to target_n',
        primary='Exact posterior-mean atom CDF; sampled Normal rows are inspection microdata only',
        evaluation_requested=False,micro_accuracy_evaluation=False,new_API_calls=0,new_Q9_fits=0,
        state_chain=False,normal_rows_are_independent_model_evidence=False,prepared_at_utc=datetime.now(timezone.utc).isoformat())
    dump(out/'protocol.json',protocol)
    population=read_json(ROOT/p['population_preflight']/'selected_proxy_population_private.json')
    projected,scores=model_projection(source,p)
    dump(out/'model_score_projection_private.json',scores)
    summary=[]
    for month in p['months']:
        rows=population[month];frame,profiles,cw,diagnostics=make_frame(rows,month,target_n)
        core_ids=list(cw)
        if set(projected[month])!=set(core_ids):raise ValueError('Answer bank differs from declared Core roster')
        answers=[JointAnswer(r['id'],tuple(r['q9_bins']),r['q9_mean'],r['q9_iqr'],r['q8']) for r in projected[month].values()]
        model=JointExpansion(frame,core_ids,answers,cw,prior_strength=TAU)
        atom_mass=model.atom_weights();draws=model.draw_normal(month=month,seed=SEED)
        dest=out/month;dest.mkdir()
        atoms=[dict(donor_id=str(answer.id),weight=float(w),**answer.payload()) for answer,w in zip(model.answers,atom_mass) if w>0]
        dump(dest/'atoms_private.json',dict(month=month,total_mass=target_n,atoms=atoms,
            method='Exact weighted empirical-Bayes posterior mean, preserving Core mass'))
        dump(dest/'frame_private.json',frame)
        dump(dest/'core_model_answers_private.json',list(projected[month].values()))
        with (dest/'expanded_population_private.jsonl').open('x') as stream:
            for person in frame:
                aid=person['id'];meta=profiles[aid]
                if aid in projected[month]:
                    answer={k:v for k,v in projected[month][aid].items() if k!='id'}
                    answer.update(donor_id=aid,source='Core_actual_LLM')
                else:answer=draws[aid]
                row=dict(month=month,proxy_id=aid,analysis_weight=person['weight'],profile=meta,
                    answer=answer,independent_LLM_response=aid in projected[month],
                    inspection_draw_only=aid not in projected[month],synthetic_population=True)
                stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
        report=model.report()
        summary.append(dict(month=month,n=target_n,Core=512,Normal=target_n-512,**diagnostics,
            mass_conservation_error=report['mass_conservation_error'],
            valid_model_answer_atoms=len(answers),exact_atom_mass=float(atom_mass.sum())))
        print(month,f'512 Core + {target_n-512} Normal = {target_n}; mass checked',flush=True)
    result=dict(status='completed_offline_B_proxy_expansion_without_accuracy_evaluation',months=11,
        total_rows=11*target_n,total_core=5632,total_normal=11*(target_n-512),
        new_API_calls=0,new_Q9_fits=0,truth_opened=False,tau=TAU,monthly=summary,
        limits=['1300 is a declared synthetic proxy scale; recent actual membership/margins remain unknown.',
                'Population rows and answer atoms add no independent model evidence.',
                'No recent human micro structure or accuracy evaluation; no B parameter optimisation.',
                'Normal inspection draws do not supply genuine persistent individual belief states.',
                'Imported A tau is a fixed approximation, not B-validated optimal.'])
    dump(out/'summary.json',result)
    files={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file()}
    sources={str(f.relative_to(ROOT)):sha(f) for f in (Path(__file__),ROOT/'studies/sce_inflation_expectations/core_normal_joint.py',
        ROOT/'studies/sce_inflation_expectations/population/monthly_fine_grid.py',source/'package/manifest.json',
        source/'combined/manifest.json',source/'combined/positions_private.jsonl',source/'evaluation/scoring_cache_private.json',
        ROOT/p['population_preflight']/'selected_proxy_population_private.json',A_PROTOCOL,A_SELECTION)}
    dump(out/'manifest.json',dict(files_sha256=files,source_sha256=sources,original_generation_protocol_sha256=manifest['protocol_sha256'],new_API_calls=0))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--target-n',type=int,choices=(1200,1300),default=1300)
    args=parser.parse_args(argv)
    with no_network():run(args.out,args.target_n)

