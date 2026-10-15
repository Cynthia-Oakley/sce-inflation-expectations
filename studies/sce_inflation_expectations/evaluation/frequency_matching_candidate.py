"""Offline 2020 four-quarter donor prototype; no answers, API or live config.

The source is retrospective and is NOT a target-aligned or release-PIT pool.
Unknown frequency weeks are already excluded by the frozen quarter audit;
supported all-zero weeks remain eligible. Whole four-category vectors travel
together through both donor assignment and the within-month placebo shuffle.
"""
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
QUARTERS = ROOT / 'outputs/sce_frequency_quarter_audit_20261015_v3/donor_weeks_private.json'
COVERAGE = ROOT / 'outputs/sce_coverage_age_audit_20261015_v1/person_coverage_private.json'
ORIGINAL = ROOT / 'outputs/sce_purchase_frequency_preparation_20261015_v1/assignments_private.json'
ARCHIVE = ROOT / 'data/raw/ce_experience/20261006/diary/diary20.zip'
CATEGORIES = ('food_at_home', 'food_away_from_home', 'household_cleaning_paper', 'personal_care_products')
# Protect budget and life stage, then broad family size before the more fragile
# fine income code. Priority is fixed from comparability/support, not SCE errors.
FIELDS = ('household_income_band', 'age_group', 'family_size_group',
          'fine_income_code', 'housing_tenure', 'region', 'education_group')


def income_code(income):
    """SCE Q47 intervals; exactly $100,000 is code 9, not the lower band."""
    if not math.isfinite(income):
        raise ValueError('Finite income required')
    bounds = (10000, 20000, 30000, 40000, 50000, 60000, 75000, 100000, 150000, 200000)
    return 1 + sum(income >= b for b in bounds)


def coarse_income(code):
    if not isinstance(code, int) or not 1 <= code <= 11:
        raise ValueError('Q47 income code required')
    return 'under_50k' if code <= 5 else '50k_to_100k' if code <= 8 else 'over_100k'


def family_group(size):
    if size is None or not math.isfinite(size) or size < 1 or int(size) != size:
        return None
    return str(int(size)) if size < 3 else '3+'


def recipient_profile(original, history):
    """Only own strictly prior records; no current answers or current fine P."""
    profile = {k: v for k, v in original['profile'].items() if k in FIELDS}
    statuses = {}
    for feature in ('fine_income', 'family_composition'):
        f = history['features'][feature]
        valid = (f['available'] and f['source_month'] < original['month']
                 and 0 < f['age_months'] <= 12)
        if feature == 'fine_income':
            # A disagreement with the existing current coarse label is not used
            # to choose a more convenient code. Drop the stale historical field.
            valid = valid and f.get('agrees_with_current_coarse_income', False)
            if valid:
                profile['fine_income_code'] = int(f['value'])
        else:
            valid = valid and not f.get('moved_after_record', True)
            if valid:
                value = family_group(f['value']['members_including_self_excluding_nonrelatives'])
                valid = value is not None
                if valid:
                    profile['family_size_group'] = value
        statuses[feature] = 'historical_available' if valid else 'unknown_or_stale'
    return profile, statuses


def load_donors():
    """Reuse validated day vectors, enrich only with raw public FMLD fields."""
    quarters = json.loads(QUARTERS.read_text())
    output = []
    with zipfile.ZipFile(ARCHIVE) as archive:
        for q, rows in quarters.items():
            raw = {}
            payload = archive.read(f'diary20/fmld20{q}.csv').decode('utf-8-sig')
            for record in csv.DictReader(io.StringIO(payload)):
                record = {k.upper(): v for k, v in record.items()}
                key = hashlib.sha256(f"ce-diary-2020|week|Q{q}|{record['NEWID']}".encode()).hexdigest()
                raw[key] = record
            cu_weights = defaultdict(list)
            enriched = []
            for r in rows:
                public = raw[r['week_key']]
                attrs = dict(r['attributes'])
                code = income_code(float(public['FINCBEFM']))
                attrs.update(fine_income_code=code, household_income_band=coarse_income(code))
                size = family_group(r['family_size'])
                if size is not None:
                    attrs['family_size_group'] = size
                item = {**r, 'attributes': attrs}
                enriched.append(item)
                cu_weights[item['cu_key']].append(item['weight'])
            # Equal source mass per quarter: a sensitivity pool, not an official
            # annual CE estimator. CU means prevent counting two weeks twice.
            mass = sum(float(np.mean(v)) for v in cu_weights.values())
            for item in enriched:
                item['weight'] /= mass
                output.append(item)
    return sorted(output, key=lambda r: r['week_key'])


def supported_pool(donors, profile, min_units=25, min_effective=15):
    active = [k for k in FIELDS if k in profile]
    requested = list(active)
    attempts = []
    while True:
        units = defaultdict(list)
        for w in donors:
            if all(w['attributes'].get(k) == profile[k] for k in active):
                units[w['cu_key']].append(w)
        keys = sorted(units)
        weights = np.array([np.mean([w['weight'] for w in units[k]]) for k in keys])
        effective = float(weights.sum() ** 2 / (weights @ weights)) if len(keys) else 0.0
        attempts.append({'fields': list(active), 'units': len(keys), 'effective_units': effective})
        if len(keys) >= min_units and effective >= min_effective:
            return units, keys, weights, {'matched_fields': list(active),
                'relaxed_fields': [k for k in requested if k not in active],
                'support': attempts[-1], 'search': attempts}
        if not active:
            raise ValueError('Insufficient global donor support')
        active.pop()


def assign(donors, profile, key, *, seed=20261015, min_units=25, min_effective=15):
    units, keys, weights, receipt = supported_pool(donors, profile, min_units, min_effective)
    seed_int = int.from_bytes(hashlib.sha256(f'{seed}|{key}'.encode()).digest()[:8], 'big')
    rng = np.random.default_rng(seed_int)
    cu = keys[rng.choice(len(keys), p=weights / weights.sum())]
    weeks = units[cu]
    ww = np.array([w['weight'] for w in weeks])
    week = weeks[rng.choice(len(weeks), p=ww / ww.sum())]
    return {**receipt, 'days': list(week['days']), 'week_key': week['week_key'],
        'cu_key': cu, 'quarter': week['quarter'], 'donor_attributes': week['attributes'],
        'conditional_cu_probability': float(weights[keys.index(cu)] / weights.sum()),
        'conditional_week_probability': float(week['weight'] / ww.sum()), 'seed': seed}


def permute_vectors(rows, seed=20261015):
    """A random cyclic derangement of records; never shuffle categories apart.

    Equal vectors may still occur after the permutation. No self-record remains,
    and the complete empirical distribution of vectors is preserved exactly.
    """
    if len(rows) < 2:
        raise ValueError('At least two records required')
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(rows))
    result = [None] * len(rows)
    for a, b in zip(order, np.roll(order, -1)):
        result[int(a)] = {'days': list(rows[int(b)]['days']), 'source_index': int(b)}
    return result


def run(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output required')
    originals = json.loads(ORIGINAL.read_text())
    histories = {(r['month'], r['agent_id']): r for r in json.loads(COVERAGE.read_text())}
    donors = load_donors()
    rows = []
    for original in originals:
        key = (original['month'], original['agent_id'])
        profile, status = recipient_profile(original, histories[key])
        selected = assign(donors, profile, '|'.join(map(str, key)))
        rows.append({'month': key[0], 'agent_id': key[1], 'profile': profile,
                     'history_status': status, **selected})
    for month in sorted({r['month'] for r in rows}):
        group = [r for r in rows if r['month'] == month]
        shuffled = permute_vectors(group, seed=20261015 + month)
        assert Counter(tuple(r['days']) for r in group) == Counter(tuple(r['days']) for r in shuffled)
        for i, r in enumerate(group):
            assert shuffled[i]['source_index'] != i
            r['permuted_days'] = shuffled[i]['days']
            r['permuted_source_agent_id'] = group[shuffled[i]['source_index']]['agent_id']
    summary = {'status': 'offline_source_limited_prototype_NOT_simulation_ready',
        'new_api_calls': 0, 'n_person_months': len(rows), 'donor_weeks': len(donors),
        'donor_CUs': len({r['cu_key'] for r in donors}),
        'supported_zero_weeks': sum(not any(r['days']) for r in donors),
        'source_year': 2020, 'source_quarters': [1, 2, 3, 4], 'seed': 20261015,
        'quarter_weighting': 'equal unconditional CU weight mass per quarter, not official annual estimator',
        'min_unique_CUs': min(r['support']['units'] for r in rows),
        'min_effective_CUs': min(r['support']['effective_units'] for r in rows),
        'field_coverage_and_retention': {k: {
            'available': sum(k in r['profile'] for r in rows),
            'retained': sum(k in r['matched_fields'] for r in rows)} for k in FIELDS},
        'history_status': {k: dict(Counter(r['history_status'][k] for r in rows))
                           for k in ('fine_income', 'family_composition')},
        'quarters_drawn': dict(Counter(r['quarter'] for r in rows)),
        'matched_means': dict(zip(CATEGORIES, np.mean([r['days'] for r in rows], axis=0).tolist())),
        'permutation_preserves_joint_distribution_each_month': True,
        'limits': ['Not target-aligned: public 2019/2021/2022 downloads returned HTTP 403.',
            '2020 pandemic/season/survey effects confounded; no cross-year stability established.',
            'FINCBEFM mean of imputations vs self-reported household income; CU/household not equivalent.',
            'Family size 1/2/3+ excludes SCE nonrelatives, which is only an approximate CE crosswalk.',
            'SCE child field is not equivalent to CE all under-18 CU members; not matched.',
            'Assets and actual shopping responsibility remain unknown; no gender/sex inference.',
            'Zero supported diary days do not imply habitual nonpurchase; single-week proxy, not trip rate.',
            'Own historical fields used only for route A diagnostics, not available as same-month route B P.',
            'No current SCE target answers loaded; no LLM messages sent; no effectiveness claim.'],
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (QUARTERS, COVERAGE, ORIGINAL, ARCHIVE, Path(__file__).resolve())}}
    out.mkdir(parents=True)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    (out / 'assignments_private.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
