"""Monthly proxy frames under an explicit nine-month publication-lag assumption.

The source files are later downloads, not certified historical byte vintages.
Only source waves whose month-end plus nine calendar months precedes the
cutoff are eligible. This is a retrospective assumed-availability backtest.
No recent B target answers, model endpoint, or dispatch authorization is used.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timezone
import argparse
import calendar
import importlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from .frozen_batch import ROOT, dump, read_json, sha
from .recent_b_preflight import (BINS, COLS, REVIEW, DELIVERY, CANDIDATE,
                                CATALOG, identity, select_population,
                                select_public_anchor, timestamp)
from .recent_b_priors import next_month
from ..population.monthly_fine_grid import GRID_VERSION
from ..prior_belief_preparation import valid_bins
from .. import personal_information_preparation as family

POLICY = 'survey_month_end_plus_nine_calendar_months_before_cutoff_assumed'
FAQ_URL = 'https://www.newyorkfed.org/microeconomics/sce/sce-faq'
SOURCE_FILES = (
    ('data/raw/sce_audit_20260928/micro_2020_2024.xlsx',
     '1b57ffb75c2170d767f46a001002db8c40c228fe5691f6dd19e39777ffe469c6'),
    ('data/raw/sce_micro_refresh_20261021/micro_latest.xlsx',
     '7da4bbcd3f23a4434ab5a94c4c93a255c46df7a57c38eef807b39466bf158f48'),
)


def inferred_available_date(month):
    """Conservative implementation assumption, not an actual release timestamp."""
    year, mon = divmod(int(month), 100)
    end_day = calendar.monthrange(year, mon)[1]
    idx = year * 12 + mon - 1 + 9
    y, m0 = divmod(idx, 12)
    return date(y, m0 + 1, min(end_day, calendar.monthrange(y, m0 + 1)[1]))


def select_source_wave(months, cutoff, target_month):
    timestamp(cutoff)  # require a timezone-aware cutoff
    cutoff_day = date.fromisoformat(cutoff[:10])
    eligible = [int(m) for m in months if int(m) < int(target_month)
                and inferred_available_date(m) < cutoff_day]
    if not eligible:
        raise ValueError('No source wave eligible under the declared lag assumption')
    return max(eligible)


def eligible_history(frame, wave):
    result = frame.loc[frame.date.le(int(wave))].copy()
    if result.empty or result.date.max() > int(wave):
        raise ValueError('Past-only source projection failed')
    return result


def make_people(history, wave):
    """Map only eligible profile rows; carry earlier own Q10/housing when absent."""
    history = eligible_history(history, wave)
    sys.path.insert(0, str(ROOT / 'scripts'))
    mapping = importlib.import_module('build_sce_fullperiod_sample_data')
    q43 = {int(u): dict(zip(g.date, g.Q43)) for u, g in
           history.loc[history.Q43.notna()].groupby('userid')}
    d3 = {int(u): dict(zip(g.date, g.D3)) for u, g in
          history.loc[history.D3.notna()].groupby('userid')}
    qcols = [f'Q10_{i}' for i in range(1, 11)]
    observed = history.loc[history[qcols].notna().any(axis=1)].sort_values(['date', 'userid'])
    jobs = {int(r.userid): r for _, r in observed.groupby('userid', sort=False).tail(1).iterrows()}
    people, weights, provenance = [], {}, {}
    for _, current in history.loc[history.date.eq(int(wave))].iterrows():
        r = current.copy(); uid = int(r.userid); aid = identity(uid)
        r['_agent_id'] = aid
        source_job = int(wave)
        if r[qcols].isna().all() and uid in jobs:
            r[qcols] = jobs[uid][qcols]
            source_job = int(jobs[uid].date)
        housing, housing_month, _, _ = mapping.bp._housing_carry_forward(q43, d3, uid, int(wave))
        p = mapping.build_persona(r, housing, int(wave), True)
        p.pop('init_state', None); p['weight'] = 1.
        p.update(source_reference_period=str(wave), public_known_by_utc=None,
                 availability_basis=POLICY, synthetic_proxy=True)
        people.append(p)
        weights[aid] = float(r.weight) if pd.notna(r.weight) and np.isfinite(r.weight) else None
        provenance[aid] = {'employment_observed_month':source_job,
                           'housing_observed_month':housing_month,
                           'profile_reference_month':int(wave)}
    return people, weights, provenance


def prepare(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    source_hashes = {str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),
                     str(REVIEW.relative_to(ROOT)):sha(REVIEW),
                     str(CATALOG.relative_to(ROOT)):sha(CATALOG)}
    projected = []
    for name, digest in SOURCE_FILES:
        source = ROOT/name
        if sha(source) != digest:
            raise ValueError('Source file differs from the registered download: '+name)
        source_hashes[name] = digest
        print('Reading whitelisted past-source fields: '+source.name, flush=True)
        part = pd.read_excel(source, skiprows=1, usecols=COLS)
        part = part.loc[part.date.notna()].copy()
        part['date'] = part.date.astype(int); part['userid'] = part.userid.astype('int64')
        projected.append(part)
    frame = pd.concat(projected, ignore_index=True).sort_values(['date','userid'])
    if frame.duplicated(['date','userid']).any():
        raise ValueError('Duplicate source respondent-month')
    if frame.date.max() >= 202511:
        raise ValueError('Recent B target microdata must not enter this preparation')
    out.mkdir(parents=True)
    frame.to_parquet(out/'public_snapshot_frame_private.parquet', index=False)
    reviewed = read_json(REVIEW)['months']
    releases = read_json(CATALOG)['headline_releases']
    selected, plans, source_waves, profile_provenance = {}, [], {}, {}
    all_family_ids = set()
    for entry in sorted(reviewed, key=lambda r:r['month']):
        month = entry['month']
        cutoff = '2025-11-13T23:59:59-05:00' if month=='202511' else entry['as_of']
        wave = select_source_wave(frame.date.unique(), cutoff, month)
        if wave not in source_waves:
            source_waves[wave] = make_people(frame, wave)
        people, weights, provenance = source_waves[wave]
        picked, plan, excluded = select_population(people, weights, month)
        selected[month] = picked
        profile_provenance[month] = {r['persona']['agent_id']:provenance[r['persona']['agent_id']] for r in picked}
        all_family_ids.update(int(u) for u in frame.loc[frame.date.eq(wave),'userid'])
        anchor = select_public_anchor(releases, month, cutoff)
        if sha(ROOT/anchor['source_file']) != anchor['source_sha256']:
            raise ValueError('Past public national release changed')
        source_hashes[anchor['source_file']] = anchor['source_sha256']
        env = (CANDIDATE if month=='202511' else DELIVERY/month)/'environment.json'
        if read_json(env)['provider_args']['targets'][0]['as_of'] != cutoff:
            raise ValueError('Environment cutoff differs from confirmed cutoff')
        source_hashes[str(env.relative_to(ROOT))] = sha(env)
        maxerr = max(abs(sum(r['analysis_weight'] for r in picked if r['stratum']==c)
                        /plan['population_weight_total']-v['population_fraction'])
                     for c,v in plan['cells'].items())
        source_age = (int(month)//100-wave//100)*12+int(month)%100-wave%100
        plans.append({'month':month,'as_of':cutoff,'old_population_reference_period':str(wave),
                      'source_age_months':source_age,'population_known_by_utc':None,
                      'availability_basis':POLICY,'inferred_available_date':inferred_available_date(wave).isoformat(),
                      'historical_byte_vintage_verified':False,'frame_n':len(people),
                      'positive_weight_frame_n':plan['frame_n'],'sample_n':len(picked),
                      'occupied_cells':len(plan['cells']),'invalid_source_weights_excluded':len(excluded),
                      'max_cell_fraction_error':maxerr,'last_public_national_anchor':anchor,
                      'environment_source':str(env.relative_to(ROOT)),
                      'source_wave_capped_by_local_micro_coverage':wave==int(frame.date.max())})
        print(f'{month}: wave {wave}, assumed public {inferred_available_date(wave)}, 512 proxy households', flush=True)
    # Keep historical source observations separate from sendable proxy profiles.
    donor_parts = []
    for wave in sorted(source_waves):
        recent = sorted(m for m in frame.date.unique() if m<=wave)[-3:]
        donor_parts.append(frame.loc[frame.date.isin(recent)])
    donors = pd.concat(donor_parts).drop_duplicates(['date','userid']).copy()
    joint = donors.Q8v2part2.notna() & np.isfinite(donors.Q8v2part2)
    joint &= donors[BINS].apply(lambda r:valid_bins(r.tolist()), axis=1)
    joint &= donors.weight.notna() & np.isfinite(donors.weight) & donors.weight.gt(0)
    donors.loc[joint].to_parquet(out/'old_joint_donor_pool_private.parquet', index=False)
    # Household composition is physically projected without belief/target fields.
    histories = defaultdict(list)
    for name, _ in SOURCE_FILES:
        for r in family.read_profile_rows(ROOT/name, all_family_ids):
            histories[int(float(r['userid']))].append((int(float(r['date'])),r))
    families = {}
    reverse = {identity(u):int(u) for u in all_family_ids}
    for p in plans:
        wave = int(p['old_population_reference_period']); month = p['month']
        families[month] = {r['persona']['agent_id']:family.past_state(histories[reverse[r['persona']['agent_id']]],next_month(wave))
                           for r in selected[month]}
    dump(out/'family_states_private.json', families)
    dump(out/'profile_provenance_private.json', profile_provenance)
    dump(out/'selected_proxy_population_private.json', selected)
    dump(out/'monthly_input_plan.json', plans)
    summary = {'status':'offline_rolling_proxy_P_under_declared_release_lag_assumption',
               'built_at_utc':datetime.now(timezone.utc).isoformat(),'new_api_calls':0,
               'source_snapshot_reference_max':str(int(frame.date.max())),
               'source_public_known_by_utc':None,'source_files':[n for n,_ in SOURCE_FILES],
               'monthly_source_waves':{p['month']:p['old_population_reference_period'] for p in plans},
               'family_states_file':str((out/'family_states_private.json').relative_to(ROOT)),
               'availability_basis':POLICY,'official_lag_rule_source':FAQ_URL,
               'historical_byte_vintage_verified':False,'source_rows':len(frame),
               'months':len(plans),'proposed_n_per_month':512,'proposed_unique_calls':512*len(plans),
               'grid_version':GRID_VERSION,'max_cell_fraction_error':max(p['max_cell_fraction_error'] for p in plans),
               'old_source_joint_donors':int(joint.sum()),'source_sha256':source_hashes,
               'limits':['Nine-month lag and conservative month-end convention are a declared availability assumption, not dated-byte certification.',
                         'Later source revisions cannot be excluded; no strict ex-ante forecast claim.',
                         'P weights describe selected source waves; no current target margins or outcomes used.',
                         'Latest locally available microdata cap is 2025-10; later eligible waves cannot be invented.',
                         'Employment and income follow observed source profiles; macro adjustment and entry/exit are not enabled.']}
    dump(out/'summary.json', summary)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    result=prepare(args.out)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False,indent=2))
