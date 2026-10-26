"""Past-only history resolution and reuse of the delivered environment builder.

No API client. Current weights are loaded separately, without current answers.
Original delivery files stay unchanged; resolved inputs live in a fresh folder.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import pandas as pd

from .state_continuity import ROOT, legal_prior_fields, month_index
from ..prior_belief_preparation import valid_bins, month_offset
from ..scoring.sce_q9_frozen import score_q9_frozen, provenance

FRAME = ROOT / 'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
BINS = [f'Q9_bin{i}' for i in range(1, 11)]
HISTORY_COLUMNS = ['date', 'userid', 'tenure', 'survey_date', 'Q8v2part2', *BINS,
                   '_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT']


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def anonymous_id(uid, salt):
    return 'sce_' + hashlib.sha256(f'{int(uid)}|{salt}'.encode()).hexdigest()[:16]


def finite_point(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and abs(x) <= 100 else None


@lru_cache(maxsize=12000)
def density_center(probabilities):
    result = score_q9_frozen(list(probabilities))
    return (float(result.mean) if result.status == 'ok' and result.mean is not None
            and math.isfinite(result.mean) else None)


def draw_legal_donor(past, profile, month, aid, salt):
    """Joint Q8/Q9 draw; strictly past first-time participants, no targets."""
    if not past.date.lt(int(month)).all():
        raise ValueError('Current/future rows cannot enter donor selection')
    pool = past.loc[past.tenure.eq(1)].copy()
    legal = pool.apply(lambda r: finite_point(r.Q8v2part2) is not None
                       and valid_bins([r[k] for k in BINS]), axis=1)
    pool = pool.loc[legal]
    edu = {'high_school': 'High School', 'some_college': 'Some College', 'college': 'College'}
    income = {'under_50k': 'Under 50k', '50k_to_100k': '50k to 100k', 'over_100k': 'Over 100k'}
    matches = [('_AGE_CAT', profile.get('age_group')),
               ('_EDU_CAT', edu.get(profile.get('education_group'))),
               ('_HH_INC_CAT', income.get(profile.get('household_income_band')))]
    rng = random.Random(f'20261022|{month}|{aid}|valid-initial-donor')
    for indexes in ((0, 1, 2), (0, 2), (0,), ()):
        subset = pool
        used = []
        for i in indexes:
            col, value = matches[i]
            if value is not None:
                subset = subset.loc[subset[col].eq(value)]
                used.append(col)
        if not subset.empty:
            row = subset.sort_values(['date', 'userid']).iloc[rng.randrange(len(subset))]
            return row, {'donor_agent_id': anonymous_id(row.userid, salt),
                         'donor_period': int(row.date), 'eligible_pool_n': len(subset),
                         'matched_columns': used, 'selection': 'uniform joint-valid historical entrant'}
    raise ValueError('No past joint-valid donor; do not invent a probability vector')


def resolve_person(past, uid, aid, profile, declared, month, salt):
    """Recover fields independently; preserve valid existing joint donor pairs."""
    month = int(month)
    if not past.date.lt(month).all():
        raise ValueError('Per-month history slice contains current/future answers')
    own = past.loc[past.userid.eq(uid)].sort_values('date')
    own_q8 = own.loc[own.Q8v2part2.map(lambda v: finite_point(v) is not None)]
    own_q9 = own.loc[own.apply(lambda r: valid_bins([r[k] for k in BINS]), axis=1)]
    fields = {}
    for key, eligible in [('q8', own_q8), ('q9', own_q9)]:
        if not eligible.empty:
            row = eligible.iloc[-1]
            fields[key] = {'source_kind': 'own_observed', 'source_period': int(row.date),
                           'value': finite_point(row.Q8v2part2) if key == 'q8'
                           else [float(row[k]) for k in BINS]}
    donor_meta = None
    if len(fields) < 2:
        q = declared['q8_q9']
        valid = legal_prior_fields(q)
        if (declared['source_kind'] == 'donor_initial' and valid['q8'] and valid['q9']
                and finite_point(q['q8_point_pct']) is not None
                and int(declared['source_period']) < month):
            pair = {'q8': float(q['q8_point_pct']), 'q9': list(q['q9_bins'])}
            donor_period = int(declared['source_period'])
            donor_meta = dict(declared.get('donor', {}), selection='preserved valid delivered joint donor')
        else:
            donor, donor_meta = draw_legal_donor(past, profile, month, aid, salt)
            pair = {'q8': float(donor.Q8v2part2), 'q9': [float(donor[k]) for k in BINS]}
            donor_period = int(donor.date)
        for key in ('q8', 'q9'):
            if key not in fields:
                fields[key] = {'source_kind': 'synthetic_donor', 'source_period': donor_period,
                               'value': pair[key]}
    centers = []
    for _, row in own_q9.iterrows():
        center = density_center(tuple(float(row[k]) for k in BINS))
        if center is not None:
            centers.append({'source_period': int(row.date), 'center': center})
    q9_source = fields['q9']
    previous_day = None
    if q9_source['source_kind'] == 'own_observed':
        row = own.loc[own.date.eq(q9_source['source_period'])].iloc[-1]
        if pd.notna(row.survey_date):
            previous_day = pd.Timestamp(row.survey_date).date().isoformat()
    if previous_day is None:
        # Synthetic state has a comparison reference day, not a fabricated interview.
        previous_day = (pd.Timestamp(f'{month // 100}-{month % 100:02}-01')
                        - pd.Timedelta(days=1)).date().isoformat()
    return {'fields': fields, 'donor': donor_meta, 'own_history_centers': centers,
            'comparison_reference_day': previous_day,
            'comparison_day_source': ('own_observed_survey_day' if q9_source['source_kind'] == 'own_observed'
                                      else 'initialization_reference_previous_month_end_not_actual_survey'),
            'declared_source_kind': declared['source_kind'],
            'declared_fields_valid': legal_prior_fields(declared['q8_q9'])}


def prepare_histories(preparation, out):
    preparation, out = Path(preparation), Path(out)
    if out.exists():
        raise ValueError('Fresh past-input folder required')
    chosen = json.loads((preparation / 'selected_private.json').read_text())
    delivery = ROOT / 'outputs/sce_fullperiod_data_20261021_v1'
    salt = json.loads((delivery / next(iter(chosen)) / 'population_state_private.json').read_text())['anon_salt']
    uids = pd.read_parquet(FRAME, columns=['userid']).userid.unique()
    identity = {anonymous_id(u, salt): int(u) for u in uids}
    out.mkdir(parents=True)
    summary, sources = {}, {str(FRAME.relative_to(ROOT)): sha(FRAME)}
    for month, people in chosen.items():
        # Physical column and date whitelists, before any history computation.
        past = pd.read_parquet(FRAME, columns=HISTORY_COLUMNS, filters=[('date', '<', int(month))])
        weight_rows = pd.read_parquet(FRAME, columns=['userid', 'weight', 'date'],
                                      filters=[('date', '==', int(month))]).set_index('userid')
        path = delivery / month / 'belief_state_private.json'
        sources[str(path.relative_to(ROOT))] = sha(path)
        declared = {r['agent_id']: r for r in json.loads(path.read_text())['persons']}
        resolved, weights, counts = {}, {}, Counter()
        for item in people:
            p = item['persona']; aid = p['agent_id']; uid = identity[aid]
            row = resolve_person(past, uid, aid, p['attributes'], declared[aid], month, salt)
            resolved[aid] = row
            for k, v in row['fields'].items():
                counts[f'{k}_{v["source_kind"]}'] += 1
                counts[f'{k}_original_missing'] += int(not row['declared_fields_valid'][k])
            raw_weight = weight_rows.loc[uid, 'weight']
            valid_w = pd.notna(raw_weight) and math.isfinite(float(raw_weight)) and float(raw_weight) > 0
            weights[aid] = {'survey_weight': float(raw_weight) if valid_w else None,
                            'inclusion_probability': item['inclusion_probability'],
                            'analysis_weight': float(raw_weight) / item['inclusion_probability'] if valid_w else None,
                            'weight_valid': bool(valid_w), 'substituted_one_used': False}
            counts['invalid_survey_weight_retained_in_roster'] += int(not valid_w)
        dump(out / f'{month}_resolved_private.json', resolved)
        dump(out / f'{month}_weights_private.json', weights)
        summary[month] = dict(counts)
        print(f'{month}: resolved {len(resolved)} past-only initial states', flush=True)
    dump(out / 'summary.json', {'status': 'resolved_past_only_fields', 'new_api_calls': 0,
                               'months': summary, 'source_sha256': sources,
                               'scorer': provenance(), 'scorer_cache': str(density_center.cache_info()),
                               'current_answer_columns_loaded': False,
                               'current_weight_columns_loaded_separately': ['userid', 'date', 'weight']})
    return summary


def prepare_families(preparation, out, *, delivery=None):
    """Reuse the physical household-field projection for this new Core cohort."""
    from ..personal_information_preparation import SOURCES, read_profile_rows
    preparation, out = Path(preparation), Path(out)
    if out.exists(): raise ValueError('Fresh family projection folder required')
    selected = json.loads((preparation / 'selected_private.json').read_text())
    aids = {v['persona']['agent_id'] for rows in selected.values() for v in rows}
    delivery = Path(delivery) if delivery is not None else ROOT / 'outputs/sce_fullperiod_data_20261021_v1'
    salt = json.loads((delivery / next(iter(selected)) / 'population_state_private.json').read_text())['anon_salt']
    uids = {int(u) for u in pd.read_parquet(FRAME, columns=['userid']).userid.unique()
            if anonymous_id(u, salt) in aids}
    projected, sources = {}, {}
    for path in SOURCES:
        sources[str(path.relative_to(ROOT))] = sha(path)
        for row in read_profile_rows(path, uids):
            month, uid = int(float(row['date'])), int(float(row['userid']))
            if month >= int(max(selected)): continue
            key = (month, uid)
            if key in projected and projected[key] != row: raise ValueError('Conflicting household projection')
            projected[key] = row
        print(f'Projected household-only fields: {path.name}', flush=True)
    out.mkdir(parents=True)
    dump(out / 'profiles_private.json', [projected[k] for k in sorted(projected)])
    summary = {'new_api_calls': 0, 'source_sha256': sources, 'people': len(uids),
               'rows': len(projected), 'physical_projection_excludes': ['Q8', 'Q9', 'Q1', 'Q2', 'survey_date'],
               'target_month_use': 'Each monthly role uses only records strictly before that month'}
    dump(out / 'summary.json', summary)
    return summary


def prepare_environments(out):
    """Reuse Kimi's local builder with isolated output/global shadow paths."""
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Fresh environment folder required')
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
    import build_sce_fullperiod_sample_environments as existing
    names = ['OUT_DIR', 'SUPPORT_DIR', 'EXISTING_COMPONENTS', 'TARGETS']
    old = {k: getattr(existing, k) for k in names}
    env_names = ['COMPONENTS_JSONL', 'GAS_WEEKLY_CSV', 'NYT_LEDGER']
    old_env = {k: getattr(existing.env2, k) for k in env_names}
    try:
        existing.OUT_DIR = out
        existing.SUPPORT_DIR = out / '_build_support'
        existing.EXISTING_COMPONENTS = ROOT / 'data/raw/bls_initial_releases/components_cpi_full.jsonl'
        existing.TARGETS = ['2025-05', '2025-06', '2025-07']
        existing.main()
    finally:
        for k, value in old.items(): setattr(existing, k, value)
        for k, value in old_env.items(): setattr(existing.env2, k, value)
    rows, catalog = [], {}
    from pypdf import PdfReader
    from ..procurement_price_views import extract_categories, validate_cutoff
    for month in ['202505', '202506', '202507']:
        bundle = json.loads((out / month / 'environment.json').read_text())
        args = bundle['provider_args']; cutoff = args['targets'][0]['as_of']
        signal = next(s for s in args['signals_by_step']['0']
                      if s['signal_id'].startswith('bls_cpi_food_at_home_yoy_') and s.get('role') != 'history')
        ref = signal['reference_period']; published = signal['published_at']
        pdf = ROOT / 'data/raw/bls_initial_releases' / ref / f'cpi_{ref.replace("-", "_")}_released_{published[:10].replace("-", "_")}.pdf'
        values = extract_categories([p.extract_text() for p in PdfReader(pdf).pages])
        if values['food_at_home']['yoy_nsa_percent'] != signal['value']:
            raise ValueError('Food category extraction disagrees with release signal')
        for fact in values.values():
            fact.update(reference_period=ref, published_at=published, source_file=str(pdf.relative_to(ROOT)),
                        source_sha256=sha(pdf), vintage=signal['source_version'], strict_B_eligible=False)
        validate_cutoff(values.values(), cutoff); catalog[month] = values
        rows.append({'month': month, 'as_of': cutoff, 'signals': len(args['signals_by_step']['0']),
                     'food_categories_extracted': len(values), 'data_gaps': args.get('data_gaps')})
    dump(out / 'food_catalog.json', catalog)
    dump(out / 'summary.json', {'new_api_calls': 0, 'months': rows,
         'source_sha256': {str((ROOT / 'scripts/build_sce_fullperiod_sample_environments.py').relative_to(ROOT)):
                          sha(ROOT / 'scripts/build_sce_fullperiod_sample_environments.py')},
         'original_delivery_modified': False})
    return rows
