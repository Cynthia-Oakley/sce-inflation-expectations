"""Offline source-qualified population and national-lag preparation for recent B.

This does not construct dispatchable prompts, initialize recent beliefs, open
target microdata, or call an API. Existing A packages are never modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from .frozen_batch import ROOT, dump, read_json, sha
from ..population.grid_sampling import plan_core, draw_core
from ..population.monthly_fine_grid import cell, GRID_VERSION
from ..prior_belief_preparation import valid_bins

EVIDENCE = ROOT/'outputs/sce_recent_environment_evidence_20261023_v1/micro_publication_evidence.jsonl'
REVIEW = ROOT/'outputs/sce_recent_environment_review_20261024_v1/monthly_readiness_reviewed.json'
DELIVERY = ROOT/'outputs/sce_fullperiod_materialized_20261022_v2'
CANDIDATE = ROOT/'outputs/sce_recent_environment_evidence_20261023_v1/202511_candidate_asof20251113'
CATALOG = ROOT/'data/evaluation/sce_baselines_latest_20261007/aggregate_inputs.json'
BINS = [f'Q9_bin{i}' for i in range(1,11)]
COLS = ['date','userid','tenure','weight','Q8v2part2',*BINS,
        '_AGE_CAT','_EDU_CAT','_HH_INC_CAT','_NUM_CAT','_REGION_CAT','_STATE',
        'Q43','D3',*[f'Q10_{i}' for i in range(1,11)]]
ATTRIBUTES = {'age_group','education_group','household_income_band','numeracy',
              'region','state','housing_tenure','employment_status'}


def timestamp(value):
    value = datetime.fromisoformat(value.replace('Z','+00:00'))
    if value.tzinfo is None:
        raise ValueError('Timezone-aware evidence and cutoffs required')
    return value.astimezone(timezone.utc)


def qualify_micro(evidence, cutoff, *, root=ROOT):
    """An archived publication timestamp qualifies bytes, never a survey date."""
    source = root/evidence['local_file']
    if (timestamp(evidence['snapshot_time_utc']) >= timestamp(cutoff)
            or source.stat().st_size != evidence['bytes']
            or sha(source) != evidence['sha256']):
        raise ValueError('Microdata snapshot is not verified before cutoff')
    return source


def select_public_anchor(releases, month, cutoff):
    """Date-only releases on cutoff day are conservatively withheld."""
    target = f'{month[:4]}-{month[4:]}'
    eligible = [r for r in releases if r['published_date'] < cutoff[:10]]
    if any(r['reference_period'] >= target for r in eligible):
        raise ValueError('Current/future target cannot be an initial national anchor')
    if not eligible:
        raise ValueError('No proven public past national SCE anchor')
    return deepcopy(max(eligible,key=lambda r:(r['published_date'],r['reference_period'])))


def validate_frame(frame, evidence):
    frame = frame.loc[frame.date.notna()].copy()
    frame['date'] = frame.date.astype(int)
    frame['userid'] = frame.userid.astype('int64')
    cov = evidence['coverage']
    if (frame.date.min() != int(cov['min_survey_month'])
            or frame.date.max() != int(cov['max_survey_month'])
            or len(frame) != cov['n_rows'] or frame.duplicated(['date','userid']).any()):
        raise ValueError('Snapshot coverage or unique respondent-month evidence differs')
    return frame


def identity(uid):
    # A proxy donor label, explicitly distinct from an actual recent respondent.
    return 'proxy_' + hashlib.sha256(f'recent-B-public-v1|{int(uid)}'.encode()).hexdigest()[:16]


def select_population(people, weights, month, *, budget=512, minimum=8):
    """The same outcome-free 54-cell design as A; old-frame masses only."""
    if len({p['agent_id'] for p in people}) != len(people):
        raise ValueError('Duplicate proxy identity')
    rr = []; excluded = []
    for p in people:
        w = weights[p['agent_id']]
        if w is None or not np.isfinite(w) or w <= 0:
            excluded.append(p['agent_id']); continue
        rr.append({'id':p['agent_id'],'cell':cell(p['attributes']),'weight':float(w)})
    plan = plan_core(rr,budget,minimum=minimum)
    chosen = draw_core(rr,plan,seed=20261023,month=int(month))
    indexed = {p['agent_id']:p for p in people}; result = []
    for r in chosen:
        p = deepcopy(indexed[r['id']])
        p['attributes'] = {k:v for k,v in p['attributes'].items() if k in ATTRIBUTES}
        result.append({'persona':p,'stratum':r['cell'],
                       'analysis_weight':r['poststratified_weight'],
                       'raw_source_weight':r['weight'],
                       'inclusion_probability':r['inclusion_probability']})
    return result, plan, excluded


def prepare(out, *, november_cutoff):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('A fresh ignored outputs directory is required')
    # The changed date is an explicit user decision, not a performance choice.
    if november_cutoff != '2025-11-13T23:59:59-05:00':
        raise ValueError('This version implements the user-approved November-13 candidate')
    evidence_rows = [json.loads(line) for line in EVIDENCE.read_text().splitlines()]
    evidence = next(r for r in evidence_rows if r['record']=='wayback_snapshot_20250702')
    reviewed = read_json(REVIEW)['months']
    cutoffs = {r['month']:(november_cutoff if r['month']=='202511' else r['as_of']) for r in reviewed}
    source = qualify_micro(evidence,min(cutoffs.values(),key=timestamp))
    out.mkdir(parents=True)
    print('Reading the archived July-2025 microdata snapshot; no current microdata is opened.',flush=True)
    frame = validate_frame(pd.read_excel(source,skiprows=1,usecols=COLS),evidence)
    frame.to_parquet(out/'public_snapshot_frame_private.parquet',index=False)
    wave = int(frame.date.max())
    old = frame.loc[frame.date.eq(wave)].copy()
    # Reuse the existing P mappings and own earlier housing carry-forward.
    sys.path.insert(0,str(ROOT/'scripts'))
    mapping = importlib.import_module('build_sce_fullperiod_sample_data')
    q43 = {int(u):dict(zip(g.date,g.Q43)) for u,g in frame.loc[frame.Q43.notna()].groupby('userid')}
    d3 = {int(u):dict(zip(g.date,g.D3)) for u,g in frame.loc[frame.D3.notna()].groupby('userid')}
    people = []; weights = {}
    for _,row in old.iterrows():
        uid = int(row.userid); row = row.copy(); row['_agent_id'] = identity(uid)
        housing,_,_,_ = mapping.bp._housing_carry_forward(q43,d3,uid,wave)
        p = mapping.build_persona(row,housing,wave,True)
        p['weight'] = 1.
        # Old observed answers stay in a separate donor file; no zero/actual
        # previous-month placeholder is included in a sendable persona.
        p.pop('init_state',None)
        p['source_reference_period'] = str(wave)
        p['public_known_by_utc'] = evidence['snapshot_time_utc']
        p['synthetic_proxy'] = True
        people.append(p)
        w = row.weight
        weights[p['agent_id']] = float(w) if pd.notna(w) and np.isfinite(w) else None
    # Keep the newest three SOURCE months; these are not called target-lag one.
    source_months = sorted(frame.date.unique())[-3:]
    donors = frame.loc[frame.date.isin(source_months)].copy()
    joint = donors.Q8v2part2.notna() & np.isfinite(donors.Q8v2part2)
    joint &= donors[BINS].apply(lambda r:valid_bins(r.tolist()),axis=1)
    joint &= donors.weight.notna() & np.isfinite(donors.weight) & donors.weight.gt(0)
    donors.loc[joint].to_parquet(out/'old_joint_donor_pool_private.parquet',index=False)
    releases = read_json(CATALOG)['headline_releases']
    selected = {}; plans = []; sources = {str(p.relative_to(ROOT)):sha(p) for p in (EVIDENCE,REVIEW,CATALOG,source,Path(__file__))}
    for month,cutoff in sorted(cutoffs.items()):
        anchor = select_public_anchor(releases,month,cutoff)
        archived = ROOT/anchor['source_file']
        if sha(archived) != anchor['source_sha256']:
            raise ValueError('National release archive changed')
        sources[str(archived.relative_to(ROOT))] = sha(archived)
        root = CANDIDATE if month=='202511' else DELIVERY/month
        env_file = root/'environment.json';env = read_json(env_file)
        if env['provider_args']['targets'][0]['as_of'] != cutoff:
            raise ValueError('Environment cutoff differs from approved recent-B cutoff')
        sources[str(env_file.relative_to(ROOT))] = sha(env_file)
        picked,plan,excluded = select_population(people,weights,month)
        selected[month] = picked
        maxerr = max(abs(sum(p['analysis_weight'] for p in picked if p['stratum']==c)/plan['population_weight_total']-v['population_fraction']) for c,v in plan['cells'].items())
        age = (int(month[:4])-wave//100)*12+int(month[4:])-wave%100
        plans.append({'month':month,'as_of':cutoff,'old_population_reference_period':str(wave),
                      'source_age_months':age,'population_known_by_utc':evidence['snapshot_time_utc'],
                      'frame_n':len(old),'positive_weight_frame_n':plan['frame_n'],
                      'sample_n':len(picked),'occupied_cells':len(plan['cells']),
                      'unknown_cell_n':plan['cells'].get('unknown',{}).get('frame_n',0),
                      'invalid_source_weights_excluded':len(excluded),'max_cell_fraction_error':maxerr,
                      'last_public_national_anchor':anchor,'environment_source':str(env_file.relative_to(ROOT)),
                      'registered_environment_status':next(r['inputs'] for r in reviewed if r['month']==month),
                      'november_candidate_supersedes_old_date':month=='202511',
                      'environment_eligible_for_dispatch':False,'belief_initialization_ready':False})
        print(f'{month}: {len(picked)} old-frame proxy profiles; public national anchor {anchor["reference_period"]}; not dispatchable.',flush=True)
    dump(out/'selected_proxy_population_private.json',selected)
    dump(out/'monthly_input_plan.json',plans)
    summary = {'status':'offline_public_P_and_past_anchor_ready_not_dispatchable',
        'built_at_utc':datetime.now(timezone.utc).isoformat(),'new_api_calls':0,'new_q9_fits':0,
        'new_current_microdata_read':False,'source_snapshot_reference_max':str(wave),
        'source_public_known_by_utc':evidence['snapshot_time_utc'],'source_rows':len(frame),
        'old_source_joint_donors':int(joint.sum()),'donor_source_months':[str(v) for v in source_months],
        'months':len(plans),'proposed_n_per_month':512,'proposed_unique_calls':len(plans)*512,
        'n_per_month_is_proposal_not_paid_authorization':True,'repeats':1,'grid_version':GRID_VERSION,
        'november_cutoff_human_confirmed':november_cutoff,
        'max_cell_fraction_error':max(p['max_cell_fraction_error'] for p in plans),
        'source_sha256':sources,
        'pending':['Specify synthetic-prior updating from old joint answers to the last public anchor; do not relabel old answers as observed previous-month answers.',
                   'Decide and document historical text-version treatment; old strict-B news pool remains uncertified.',
                   'Validate actual food/policy/confidence prompt sources at the new cutoff; exclude uncertified gasoline from strict inputs.',
                   'Construct prompts, run official Core dry-run, freeze budget and obtain a new batch approval.'],
        'limitations':['Population weights represent the 2024-08 source frame, not measured 2025/2026 population margins.',
                       'A public data snapshot is input-publication evidence only; it does not certify LLM training knowledge.',
                       'No recent respondent-level truth is available: evaluation will be national only.',
                       'The old per-month environment status is retained as a reference and not automatically promoted for the new November cutoff.']}
    dump(out/'summary.json',summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--november-cutoff',required=True)
    args = parser.parse_args(argv)
    result = prepare(args.out,november_cutoff=args.november_cutoff)
    print(json.dumps({k:v for k,v in result.items() if k not in {'source_sha256'}},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
