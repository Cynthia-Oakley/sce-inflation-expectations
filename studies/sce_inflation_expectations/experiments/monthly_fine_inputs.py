"""Opt-in four-dimensional A-line inputs. Existing frozen packages stay intact."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json

import numpy as np
import pandas as pd

from .frozen_batch import ROOT, read_json, dump, sha
from .monthly_reconstruction_inputs import PastScoreCache, resolve_draw, inventory
from .state_continuity_inputs import FRAME, HISTORY_COLUMNS, anonymous_id
from .state_continuity import month_index
from ..population.monthly_fine_grid import records, prior_bands, GRID_VERSION
from ..population.grid_sampling import plan_core, draw_core
from ..population.entry_initialization import EntryConfig, build_options, calibrate, draw
from ..prior_belief_preparation import valid_bins
from ..evaluation.entry_initialization import previous_month, mixture_summary
from ..scoring.sce_q9_frozen import provenance

DELIVERY = ROOT/'outputs/sce_fullperiod_materialized_20261022_v2'
SEED_CACHE = ROOT/'outputs/sce_monthly_reconstruction_full_inputs_20261022_v1/score_cache_private.json'


def choose(population, entry, raw_weights, *, budget, minimum, month, identity):
    people = {p['agent_id']:p for p in population['personas']}
    entries = {r['agent_id']:r for r in entry['persons']}
    if len(people) != len(population['personas']) or set(people) != set(raw_weights) or set(people) != set(entries):
        raise ValueError('Complete unique population/entry/weights identity join required')
    rr, excluded = records(population,raw_weights)
    # Match the previously checked local-userid SHA ordering; API IDs remain anonymous.
    reverse = {str(identity[r['id']]):r['id'] for r in rr}
    local = [{**r,'id':str(identity[r['id']])} for r in rr]
    plan = plan_core(local,budget,minimum=minimum)
    selected = draw_core(local,plan,seed=20261023,month=int(month)); result=[]
    for r in selected:
        aid=reverse[r['id']]; person=deepcopy(people[aid]);person['weight']=1.
        person['attributes']={k:v for k,v in person['attributes'].items() if k in {
            'age_group','education_group','household_income_band','employment_status',
            'housing_tenure','numeracy','region','state'}}
        result.append({'persona':person,'stratum':r['cell'],'profile_cell':r['cell'],'grid_version':GRID_VERSION,
                       'inclusion_probability':r['inclusion_probability'],'raw_survey_weight':r['weight'],
                       'design_weight':r['design_weight'],'poststratified_weight':r['poststratified_weight'],
                       'analysis_weight':r['poststratified_weight'],'weight_valid':True,
                       'survey_entry_status':entries[aid]['survey_entry_status']})
    return sorted(result,key=lambda r:r['persona']['agent_id']),plan,excluded


def prepare(out, *, months, budget=512, minimum=8, delivery=DELIVERY):
    out,delivery=Path(out).resolve(),Path(delivery).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored input directory required')
    if budget != 512 or minimum != 8:
        raise ValueError('This main-run candidate is 512/floor8; other designs need separate review')
    cache=PastScoreCache()
    for r in read_json(SEED_CACHE):
        bins=tuple(r['q9_bins']); value=r['center']
        if not valid_bins(bins) or (value is not None and (not isinstance(value,(int,float)) or not np.isfinite(value))):
            raise ValueError('Invalid deterministic past score-cache item')
        if bins in cache.values and cache.values[bins] != value:raise ValueError('Conflicting score cache')
        cache.values[bins]=value
    uid_rows=pd.read_parquet(FRAME,columns=['userid']);uids=uid_rows.userid.unique()
    sources={str(p.relative_to(ROOT)):sha(p) for p in [FRAME,SEED_CACHE,Path(__file__),
              ROOT/'studies/sce_inflation_expectations/population/monthly_fine_grid.py',
              ROOT/'studies/sce_inflation_expectations/population/grid_sampling.py',
              ROOT/'studies/sce_inflation_expectations/population/entry_initialization.py']}
    out.mkdir(parents=True);selected={};nodes=[];summaries=[];last={}
    for month in months:
        month=str(month)
        files=[delivery/month/name for name in ['population.json','population_state_private.json']]
        pop,entry=map(read_json,files);sources.update({str(p.relative_to(ROOT)):sha(p) for p in files})
        if any(p['agent_id'].startswith('synthetic') for p in pop['personas']):
            raise ValueError('Historical A-only; recent synthetic periods need B rules')
        identity={anonymous_id(u,entry['anon_salt']):int(u) for u in uids}
        weights=pd.read_parquet(FRAME,columns=['date','userid','weight'],filters=[('date','==',int(month))]).set_index('userid').weight
        raw={p['agent_id']:float(weights.loc[identity[p['agent_id']]]) for p in pop['personas']}
        people,plan,excluded=choose(pop,entry,raw,budget=budget,minimum=minimum,month=month,identity=identity)
        selected[month]=people; chosen={identity[p['persona']['agent_id']] for p in people}
        past=pd.read_parquet(FRAME,columns=HISTORY_COLUMNS+['weight','_NUM_CAT'],filters=[('date','<',int(month))])
        recent=(month_index(month)-past.date.map(month_index)).le(3)
        past=cache.score(past.loc[recent|past.userid.isin(chosen)],month)
        previous=past.loc[past.date.eq(previous_month(month))]
        bands,references,prior_plan=prior_bands(previous,budget=budget,minimum=minimum,seed=20261023+int(month))
        recipients=[{'agent_id':p['persona']['agent_id'],'userid':identity[p['persona']['agent_id']],
                    'weight':p['analysis_weight'],'profile':p['persona']['attributes'],
                    'donor_type':'entrant' if p['survey_entry_status']=='entrant' else 'returner'
                         if p['survey_entry_status'] in {'returning','gap_return'} else 'unknown'} for p in people]
        options=build_options(past,recipients,month,config=EntryConfig())
        before=mixture_summary(options,previous,calibrated=False);calibration=calibrate(options,bands)
        after=mixture_summary(options,previous,calibrated=True);draws=draw(options,month,20261022)
        resolved={};weights_out={};baselines={}
        for person,row in zip(people,draws):
            aid=person['persona']['agent_id'];state=resolve_draw(row,past,identity[aid],month)
            resolved[aid]=state
            weights_out[aid]={k:person[k] for k in ['raw_survey_weight','analysis_weight','design_weight',
                              'poststratified_weight','weight_valid','inclusion_probability','stratum','grid_version','profile_cell']}
            baselines[aid]={'initial_belief':state['fields'],'genuine_previous_q8':state['observed_previous_q8'],
                           'genuine_previous_q9':state['observed_previous_q9'],'survey_entry_status':person['survey_entry_status'],
                           'stratum':person['stratum'],'note':'Synthetic starts never count as true previous-person answers.'}
            core_entry='first_core_appearance' if aid not in last else 'continued_core' if month_index(month)-month_index(last[aid])==1 else 'core_gap_return'
            last[aid]=month
            nodes.append({'month':month,'agent_id':aid,'arm':'monthly_reconstruction','repeat':1,'dependency':None,
                          'logical_reuse_key':f'{month}|{aid}|r1|monthly_reconstruction',
                          'source_kind':'independent_monthly_initialization','survey_entry_status':person['survey_entry_status'],
                          'core_entry_status':core_entry})
        for suffix,data in [('resolved',resolved),('weights',weights_out),('baselines',baselines),('draws',draws)]:
            dump(out/f'{month}_{suffix}_private.json',data)
        summaries.append({'month':month,'selected_n':len(people),'grid':plan,'prior_grid':prior_plan,
                          'source_frame_n':len(pop['personas']),'positive_weight_frame_n':plan['frame_n'],
                          'source_records_without_valid_weight':len(excluded),'source_record_exclusion_scope':'sampling and weighted analysis only; source P unchanged',
                          'survey_entries':dict(Counter(p['survey_entry_status'] for p in people)),
                          'synthetic_q8':sum('q8' in r['synthetic_fields'] for r in draws),
                          'synthetic_q9':sum('q9' in r['synthetic_fields'] for r in draws),
                          'calibration':calibration,'references':references,'initial_mixture_before':before,'initial_mixture_after':after})
        print(f'{month}: {len(people)} direct-LLM positions, {calibration["status"]}',flush=True)
    dump(out/'selected_private.json',selected);dump(out/'state_dependencies_private.json',nodes)
    result={'status':'fine_grid_A_inputs_not_paid_authorized','mechanism':'monthly_reconstruction',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),'new_api_calls':0,'months':summaries,
            'grid_version':GRID_VERSION,'sampling_seed':20261023,'n_per_month':budget,'minimum_floor':minimum,
            'person_months':len(nodes),'logical_positions':len(nodes),'potential_unique_calls_before_prompt_hash':len(nodes),
            'repeats':1,'recursive_dependencies':0,
            'distinct_people':len(last),'source_sha256':sources,'scorer':provenance(),
            'score_cache':{'new_fits':cache.new_fits,'hits':cache.hits,'unique_vectors':len(cache.values)},
            'readiness_inventory':inventory(delivery),'primary_weight':'poststratified_weight',
            'limits':['A historical conditions, not strict B.','No Normal, no live API.','Current outcome columns never projected.',
                      'Missing original weights remain missing in source; 30 source rows excluded from positive-weight design.',
                      'Past-only soft calibration may leave residuals, reported without altering genuine answers.']}
    dump(out/'summary.json',result)
    dump(out/'score_cache_private.json',[{'q9_bins':list(k),'center':v} for k,v in cache.values.items()])
    return result
