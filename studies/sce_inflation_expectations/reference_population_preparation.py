"""Freeze large-sample A-line P and past beliefs, without current targets/news labels."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from socioverse.schemas import PopulationBundle

from .expanded_state_inputs import profiles, sha, dump
from .monthly_population import build_monthly_population
from .prior_belief_preparation import eligible_previous, month_offset, prior_record
from .belief_state_preparation import compute_person_state
from .evaluation.behavior_comparison import score

ROOT = Path(__file__).resolve().parents[2]
MONTHS = (202003,202009,202103,202109,202206,202212,202306,202312,202404,202410,202503,202509)
N, SEED = 192, 20261017
FRAME = ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
ENV = ROOT/'outputs/sce_e_extension_2020_2025_verified_20261007/environment_candidate.json'


def stratum(attributes):
    return attributes.get('age_group','unknown')+'|'+attributes.get('household_income_band','unknown')


def sample_strata(personas, month, n=N, seed=SEED):
    """Bounded largest-remainder allocation, minimum one per observed stratum.

    Fixed population counts, then uniform without replacement within stratum.
    Outcomes, survey weights, Q1 and expected errors never enter allocation.
    """
    groups = {}
    for p in personas:
        groups.setdefault(stratum(p['attributes']),[]).append(p['agent_id'])
    total = sum(map(len,groups.values()))
    if total != len({p['agent_id'] for p in personas}) or not len(groups) <= n <= total:
        raise ValueError('Unique feasible stratified frame required')
    target = {key:n*len(ids)/total for key,ids in groups.items()}
    sizes = {key:min(len(groups[key]),max(1,math.floor(value))) for key,value in target.items()}
    while sum(sizes.values()) < n:
        keys = [key for key in groups if sizes[key]<len(groups[key])]
        key = min(keys,key=lambda key:(-(target[key]-sizes[key]),key))
        sizes[key]+=1
    while sum(sizes.values()) > n:
        keys = [key for key in groups if sizes[key]>1]
        key = min(keys,key=lambda key:(-(sizes[key]-target[key]),key))
        sizes[key]-=1
    chosen, probabilities = set(),{}
    for i,key in enumerate(sorted(groups)):
        ids = sorted(groups[key])
        rng = np.random.default_rng(np.random.SeedSequence([seed,month,i]))
        selected = rng.choice(ids,sizes[key],replace=False).tolist()
        chosen.update(selected)
        probabilities.update({aid:sizes[key]/len(ids) for aid in selected})
    return chosen,probabilities,{'frame_n':total,'selected_n':n,'seed':seed,
        'stratum_N':{k:len(v) for k,v in sorted(groups.items())},'stratum_n':dict(sorted(sizes.items())),
        'design':'age_group_x_income_band_stratified_SRS','allocation':'bounded largest remainder, minimum1 per nonempty stratum; alphabetic ties'}


def anonymous_id(userid):
    return 'ref_'+hashlib.sha256(f'sce_reference_scaleup_v1|{int(userid)}'.encode()).hexdigest()[:16]


def prepare_population(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    old_manifest_path=ROOT/'outputs/sce_expanded_state_trial_20261014_v3/manifest.json'
    old=json.loads(old_manifest_path.read_text())
    sources={str(old_manifest_path.relative_to(ROOT)):sha(old_manifest_path)}
    for path in (FRAME,ENV):
        name=str(path.relative_to(ROOT))
        if sha(path)!=old['source_sha256'][name]:raise ValueError('Archived source drift:'+name)
        sources[name]=sha(path)
    # No numeric current inflation responses loaded in the eligibility projection.
    eligibility=pd.read_parquet(FRAME,columns=['date','userid','panel_status','tenure_valid',
        'timeline_consistent','raw_prior_valid','survey_date'])
    prof,profile_hashes=profiles();sources.update(profile_hashes)
    env=json.loads(ENV.read_text());targets={int(t['target_month'].replace('-','')):t for t in env['provider_args']['targets']}
    out.mkdir(parents=True)
    links,coverage=[],[]
    for month in MONTHS:
        dest=out/str(month);dest.mkdir()
        current=eligibility[eligibility.date.eq(month)]
        previous=eligibility[eligibility.date.eq(month_offset(month,-1))].set_index('userid',drop=False)
        cutoff=datetime.fromisoformat(targets[month]['as_of']).date()
        candidates=[int(r['userid']) for r in current.to_dict('records') if r['userid'] in previous.index
                    and eligible_previous(r,previous.loc[r['userid']],month,cutoff)]
        bins=[f'Q9_bin{i}' for i in range(1,11)]
        # Strictly previous-month bins only: current month is not loaded here.
        prior=pd.read_parquet(FRAME,columns=['date','userid',*bins],
            filters=[('date','==',month_offset(month,-1)),('userid','in',candidates)]).set_index('userid')
        prior_eligible=[uid for uid in sorted(candidates) if score(tuple(float(prior.loc[uid,b]) for b in bins))['status']=='ok']
        weight_lookup=prof[prof.date.eq(month)].set_index('userid')['weight'].to_dict()
        eligible=[uid for uid in prior_eligible if uid in weight_lookup
                  and pd.notna(weight_lookup[uid]) and math.isfinite(float(weight_lookup[uid])) and weight_lookup[uid]>0]
        fullpop,pmeta=build_monthly_population(prof[prof.userid.isin(eligible)],month,n=None,seed=SEED)
        if len(fullpop['personas'])!=len(eligible):raise ValueError('Full eligible P mapping differs')
        selected,pi,sampling=sample_strata(fullpop['personas'],month)
        picked=[p for p in fullpop['personas'] if p['agent_id'] in selected]
        selected_uids=[int(p['agent_id'].removeprefix('sce_u')) for p in picked]
        # For each target month, read only selected people strictly BEFORE it.
        history=pd.read_parquet(FRAME,columns=['date','userid','Q8v2part2',*bins],
            filters=[('date','<',month),('userid','in',selected_uids)])
        if history.date.ge(month).any():raise ValueError('Current/future response crossed input boundary')
        lookup=history[history.date.eq(month_offset(month,-1))].set_index('userid')
        past={};idmap=[];newpersonas=[];monthlinks=[]
        for p in picked:
            source_id=p['agent_id'];uid=int(source_id.removeprefix('sce_u'));aid=anonymous_id(uid)
            state=compute_person_state(history[history.userid.eq(uid)],uid,month)
            if state is None:raise ValueError('Chosen person prior score changed; preserve selection, no resampling')
            past[aid]={'prior':prior_record(lookup.loc[uid]),'state':state}
            attrs=p['attributes'];survey=float(weight_lookup[uid])
            p.update(agent_id=aid,weight=1.,group_key=None,init_state={});newpersonas.append(p)
            idmap.append({'agent_id':aid,'userid':uid,'source_id':source_id})
            monthlinks.append({'month':month,'agent_id':aid,'userid':uid,'profile':attrs,
                'stratum':stratum(attrs),'survey_weight':survey,'inclusion_probability':pi[source_id],
                'design_survey_weight':survey/pi[source_id]})
        fullpop['personas']=newpersonas;fullpop['materialized_count']=N
        fullpop['provider_args'].update(sampling_design=sampling['design'],seed=SEED)
        PopulationBundle.model_validate(fullpop)
        nested=[];ids=sorted(p['agent_id'] for p in newpersonas)
        for k in range(30):
            seed=SEED+10000+k
            order=np.random.default_rng(np.random.SeedSequence([seed,month,907])).permutation(ids).tolist()
            nested.append({'seed':seed,'ids_48':order[:48],'ids_96':order[:96]})
        dump(dest/'population.json',fullpop);dump(dest/'past_private.json',past)
        dump(dest/'profile_index_private.json',idmap);dump(dest/'eligible_ids_private.json',eligible)
        dump(dest/'nested_subsamples_private.json',nested);dump(dest/'sampling_private.json',sampling)
        links.extend(monthlinks)
        w=np.array([r['design_survey_weight'] for r in monthlinks])
        coverage.append({'month':month,'as_of':targets[month]['as_of'],'n':N,
            'timeline_candidates_n':len(candidates),'prior_fit_eligible_n':len(prior_eligible),'full_eligible_n':len(eligible),
            'weight_ess':float(w.sum()**2/(w@w)),
            'profile_counts':{key:dict(Counter(p['attributes'].get(key,'unknown') for p in newpersonas))
                for key in ['age_group','household_income_band','numeracy','region','housing_tenure','employment_status']},
            'nested_subsample_sets':30,'current_targets_used_for_selection':False})
        print('Frozen population',month,N,'eligible',len(eligible),flush=True)
    dump(out/'evaluation_links_private.json',links);dump(out/'coverage.json',coverage)
    for p in [Path(__file__),ROOT/'studies/sce_inflation_expectations/monthly_population.py',
              ROOT/'studies/sce_inflation_expectations/belief_state_preparation.py',
              ROOT/'studies/sce_inflation_expectations/prior_belief_preparation.py']:
        sources[str(p.relative_to(ROOT))]=sha(p)
    manifest={'status':'population_and_past_frozen_no_news_or_simulation_calls',
        'prepared_at_utc':datetime.now(timezone.utc).isoformat(),'months':list(MONTHS),'n_per_month':N,
        'source_sha256':sources,'prepared_file_sha256':{str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')},
        'current_targets_read':False,'new_api_calls':0,'sampling_seed':SEED,'links_n':len(links)}
    dump(out/'manifest.json',manifest)
    return manifest
