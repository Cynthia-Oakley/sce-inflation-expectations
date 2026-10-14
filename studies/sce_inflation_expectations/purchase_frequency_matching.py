"""Whole-vector CE Diary donors, CU-first sampling, no LLM or SCE answers."""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from .diary_experience import (_normal_row, _number, _int_code, _hash_key,
    file_sha256, read_official_diary_zip, category_map_from_dictionary,
    DAY_FIELD, DAY_FLAG_FIELD, VALID_DAY_FLAGS)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'data/interim/ce_experience/20261006T071002778274Z_ce_diary2020q4_4862a21e'
# Protect budget/life-stage matches when sparse housing categories would otherwise
# force global fallback. This is fixed from donor support, never from SCE answers.
FIELDS = ('household_income_band', 'age_group', 'housing_tenure', 'region', 'education_group')
CATEGORIES = ('food_at_home', 'food_away_from_home', 'household_cleaning_paper',
              'personal_care_products')
LABELS = {'food_at_home': 'groceries for home', 'food_away_from_home': 'meals away from home',
          'household_cleaning_paper': 'household cleaning products, paper and miscellaneous supplies',
          'personal_care_products': 'personal-care products'}


def _float(raw):
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError): return None


def normalize_attributes(raw):
    attrs = {}
    maps = {'housing_tenure': ('CUTENURE', {'1': 'owner', '2': 'owner', '3': 'owner', '4': 'renter', '5': 'other', '6': 'other'}),
            'region': ('REGION', {'1': 'Northeast', '2': 'Midwest', '3': 'South', '4': 'West'}),
            'education_group': ('EDUC_REF', {'0': 'high_school', '10': 'high_school', '11': 'high_school', '12': 'high_school',
                                          '13': 'some_college', '14': 'some_college', '15': 'college', '16': 'college'})}
    for key, (field, mapping) in maps.items():
        value = _float(raw.get(field))
        if value is not None and value.is_integer() and str(int(value)) in mapping:
            attrs[key] = mapping[str(int(value))]
    age = _float(raw.get('AGE_REF'))
    if age is not None and age >= 18:
        attrs['age_group'] = 'Under 40' if age < 40 else '40 to 60' if age <= 60 else 'Over 60'
    income = _float(raw.get('FINCBEFM'))
    if income is not None:
        # Same coarse thresholds as the existing CE basket adapter; not exact cross-survey equivalence.
        attrs['household_income_band'] = 'under_50k' if income < 50000 else '50k_to_100k' if income <= 100000 else 'over_100k'
    return attrs


def frequency_vector(raw_rows, mapping):
    counts = {k: Counter() for k in CATEGORIES}; days = {k: set() for k in CATEGORIES}
    for raw in raw_rows:
        row = _normal_row(raw); category = mapping.get(str(row.get('UCC') or '').strip().zfill(6))
        if category is None: continue
        c = counts[category]; flag = str(row.get('PUB_FLAG') or '').strip()
        if flag == '1': c['excluded_not_published'] += 1; continue
        if flag != '2': c['unknown_publication_flag'] += 1; continue
        value = _float(row.get('COST'))
        if value is None: c['invalid_cost'] += 1; continue
        if value <= 0: c['nonpositive_cost'] += 1; continue
        c['positive_published_rows'] += 1
        try:
            if str(row.get(DAY_FLAG_FIELD) or '').strip() not in VALID_DAY_FLAGS: raise ValueError()
            day = _int_code(row.get(DAY_FIELD), DAY_FIELD)
            if not 1 <= day <= 7: raise ValueError()
        except ValueError: c['missing_day'] += 1
        else: days[category].add(day)
    result = {}
    for k in CATEGORIES:
        c = counts[k]; uncertain = c['unknown_publication_flag'] + c['invalid_cost'] + c['missing_day']
        status = ('no_expd_rows' if not raw_rows else 'partial_support' if uncertain else
                  'excluded_only' if c['excluded_not_published'] and not c['positive_published_rows'] else
                  'no_positive_published_records' if not c['positive_published_rows'] else 'available')
        result[k] = {'status': status, 'recorded_days_7d': None if status in {'no_expd_rows', 'partial_support', 'excluded_only'} else len(days[k]),
                     'valid_day_codes': sorted(days[k]), 'record_counts': dict(c)}
    return result


def prepare_donors():
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    archive = Path(manifest['source']['archive_path']); dictionary = Path(manifest['dictionary']['path'])
    if file_sha256(archive) != manifest['source']['archive_sha256'] or file_sha256(dictionary) != manifest['dictionary']['sha256']:
        raise ValueError('source archive/dictionary changed')
    old_path = ROOT / 'outputs/ce_category_frequency_20261014_v1/category_days_private.jsonl'
    old_summary = json.loads((old_path.parent / 'summary.json').read_text())
    if file_sha256(old_path) != old_summary['private_output_sha256']: raise ValueError('old category output drift')
    old = {r['diary_week_key_sha256']: r for r in map(json.loads, old_path.read_text().splitlines())}
    broad, known, _ = category_map_from_dictionary(dictionary, year=2020, quarter=4)
    mapping = {u: k for u, k in broad.items() if k in CATEGORIES[:2]}
    cleaning = {'330110', '330210', '330310', '330510'}
    for u in cleaning:
        if u not in known or broad.get(u) != 'household_supplies_services': raise ValueError('cleaning UCC mapping')
        mapping[u] = 'household_cleaning_paper'
    for u, k in broad.items():
        if k == 'personal_care_products_services':
            if u.startswith('640'): mapping[u] = 'personal_care_products'
    fmld, expd, members, _ = read_official_diary_zip(archive)
    for key, value in members.items():
        if value['sha256'] != manifest['source']['members'][key]['sha256']: raise ValueError('source member changed')
    grouped = defaultdict(list)
    for raw in expd[4]: grouped[str(_normal_row(raw)['NEWID']).strip()].append(raw)
    units = defaultdict(list); all_rows = []; exclusions = Counter(); reclassified_missing = Counter()
    for raw in fmld[4]:
        r = _normal_row(raw); newid = str(r['NEWID']).strip(); key = _hash_key('week|Q4', newid); parent = old[key]
        vector = frequency_vector(grouped[newid], mapping)
        for cat in CATEGORIES[:2]:
            current, previous = vector[cat], parent['categories'][cat]
            if current['valid_day_codes'] != previous['valid_day_codes']:
                raise ValueError('food categories no longer reproduce source day codes')
            if current['recorded_days_7d'] != previous['recorded_days_7d']:
                if current['status'] == 'excluded_only' and previous['recorded_days_7d'] == 0:
                    reclassified_missing[cat] += 1
                else:
                    raise ValueError('unexpected food day count difference')
        for cat, oldcat in [('household_cleaning_paper', 'household_supplies_services'),
                            ('personal_care_products', 'personal_care_products_services')]:
            if not set(vector[cat]['valid_day_codes']) <= set(parent['categories'][oldcat]['valid_day_codes']):
                raise ValueError('refined category not a subset of source days')
        attrs = normalize_attributes(r); weight = _float(r.get('FINLWT21'))
        row = {'week_key': key, 'cu_key': parent['diary_cu_pair_key_sha256'],
               'week_number': parent['diary_week_number'], 'attributes': attrs,
               'weight': weight, 'categories': vector,
               'reference_person_sex_code': r.get('SEX_REF'), 'sex_used_in_matching': False}
        all_rows.append(row)
        if 'age_group' not in attrs or 'household_income_band' not in attrs or weight is None or weight <= 0:
            exclusions['missing_age_income_or_valid_weight'] += 1; continue
        if any(vector[k]['recorded_days_7d'] is None for k in CATEGORIES):
            exclusions['partial_or_missing_day_vector'] += 1; continue
        if not any(vector[k]['recorded_days_7d'] > 0 for k in CATEGORIES):
            exclusions['no_positive_contact_in_selected_categories'] += 1; continue
        units[row['cu_key']].append(row)
    donors = []; profile_changes = Counter()
    for cu, weeks in sorted(units.items()):
        for field in FIELDS:
            if len({w['attributes'].get(field) for w in weeks}) > 1:
                profile_changes[field] += 1
        if len({w['week_number'] for w in weeks}) != len(weeks) or len(weeks) > 2:
            raise ValueError('invalid CU-week pairing')
        donors.append({'cu_key': cu, 'attributes': weeks[0]['attributes'],
                       'weight': sum(w['weight'] for w in weeks) / len(weeks),
                       'weeks': sorted(weeks, key=lambda w: w['week_number'])})
    source = {'manifest_sha256': file_sha256(SOURCE / 'manifest.json'),
              'archive_sha256': file_sha256(archive), 'dictionary_sha256': file_sha256(dictionary),
              'old_frequency_sha256': file_sha256(old_path), 'year': 2020, 'quarter': 4,
              'category_uccs': {k: sorted(u for u, v in mapping.items() if v == k) for k in CATEGORIES},
              'excluded_housekeeping_uccs': ['330410', '330610', '340110', '340120'],
              'excluded_personal_repair_ucc': '650900',
              'excluded_personal_services_no_published_frequency': ['650110', '650210']}
    audit = {'raw_week_rows': len(all_rows), 'eligible_consumer_units': len(donors),
             'eligible_week_rows': sum(len(d['weeks']) for d in donors), 'exclusion_counts': dict(exclusions),
             'profile_missing_counts': {k: sum(k not in d['attributes'] for d in donors) for k in FIELDS},
             'CU_week_attribute_changes_retained': dict(profile_changes),
             'weeks_per_cu': dict(Counter(len(d['weeks']) for d in donors)),
             'gender_codes_in_raw_FMLD': dict(Counter(str(r['reference_person_sex_code']) for r in all_rows)),
             'old_zero_reclassified_unpublished_only': dict(reclassified_missing),
             'gender_is_reference_person_not_shopkeeper': True, 'source': source}
    return donors, all_rows, audit


def _draw(rows, weights, seed_text):
    total = sum(weights)
    u = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], 'big') / 2**64
    threshold = u * total; cumulative = 0.0
    for row, weight in zip(rows, weights):
        cumulative += weight
        if threshold < cumulative: return row
    return rows[-1]


class FrequencyAssigner:
    def __init__(self, donors, *, seed=20261014, min_units=25, min_effective_units=15):
        self.donors = sorted(donors, key=lambda d: d['cu_key'])
        self.seed, self.min_units, self.min_effective_units = seed, min_units, min_effective_units
        if len({d['cu_key'] for d in donors}) != len(donors): raise ValueError('duplicate CU')
        if any(not d['weeks'] or not math.isfinite(d['weight']) or d['weight'] <= 0 for d in donors): raise ValueError('bad donor weight')

    def assign(self, recipient_key, profile):
        valid = {'housing_tenure': {'owner', 'renter', 'other'}, 'household_income_band': {'under_50k', '50k_to_100k', 'over_100k'},
                 'age_group': {'Under 40', '40 to 60', 'Over 60'}, 'region': {'Northeast', 'Midwest', 'South', 'West'},
                 'education_group': {'high_school', 'some_college', 'college'}}
        fields = [k for k in FIELDS if profile.get(k) in valid[k]]; active = list(fields); attempts = []
        while True:
            pool = []
            for d in self.donors:
                weeks = [w for w in d['weeks'] if all(w.get('attributes', d['attributes']).get(k) == profile[k] for k in active)]
                if weeks:
                    # Preserve weekly imputation/profile differences instead of
                    # deleting the CU or drawing a nonmatching second week.
                    pool.append({**d, 'weeks': weeks,
                                 'weight': sum(w['weight'] for w in weeks) / len(weeks)})
            weights = [d['weight'] for d in pool]; total = sum(weights)
            effective = total**2 / sum(w*w for w in weights) if total else 0
            attempts.append({'fields': list(active), 'unique_units': len(pool), 'effective_units': effective})
            if len(pool) >= self.min_units and effective >= self.min_effective_units: break
            if not active: raise ValueError('insufficient global CU support')
            active.pop()
        donor = _draw(pool, weights, f'{self.seed}|{recipient_key}|cu')
        weekweights = [w['weight'] for w in donor['weeks']]
        week = _draw(donor['weeks'], weekweights, f'{self.seed}|{recipient_key}|week')
        return {'evidence_class': 'conditional_synthetic_CE_household_week',
                'cu_key': donor['cu_key'], 'week_key': week['week_key'], 'week_number': week['week_number'],
                'recorded_days_7d': {k: week['categories'][k]['recorded_days_7d'] for k in CATEGORIES},
                'matched_fields': active, 'relaxed_fields': [k for k in fields if k not in active],
                'unavailable_recipient_fields': [k for k in FIELDS if k not in fields],
                'pool_unique_units': len(pool), 'pool_effective_units': effective,
                'conditional_cu_probability': donor['weight'] / total,
                'conditional_week_probability': week['weight'] / sum(weekweights),
                'selected_week_attributes': dict(week.get('attributes', donor['attributes'])),
                'pool_search': attempts, 'seed': self.seed, 'sex_used_in_matching': False}


def render_frequency(assignment, *, active_rule):
    lines = ['Your assigned synthetic household shopping-contact profile:']
    for key in CATEGORIES:
        value = assignment['recorded_days_7d'][key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 7: raise ValueError('unsupported day count')
        lines.append(f'- {LABELS[key]}: positive published spending recorded on {value} of 7 days.')
    # Keep donor limitations in the audit; the respondent-facing input needs a
    # usable synthetic profile rather than a long disclaimer inviting disregard.
    lines.append('Recorded days are a weekly contact proxy, not shopping-trip counts. Zero recorded days does not mean you never buy the category.')
    if active_rule:
        lines.append('When judging price changes, give more attention and influence to the categories you purchase more frequently in this profile. Then consider whether the price changes can persist over the next 12 months; your previous belief and other information can still matter.')
    return '\n'.join(lines) + '\n\n'
