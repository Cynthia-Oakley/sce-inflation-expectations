"""Audit current public GSS waves for A-line synthetic state experiments.

No SCE target answers or LLM clients. Keep the old matching categories and
weight choice; a wave replacement must not silently change the estimator.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from .household_state_audit import gss_education, gss_income

REGIONS = {'northeast': 'Northeast', 'midwest': 'Midwest', 'south': 'South', 'west': 'West'}
COLS = ['year', 'id', 'age', 'educ', 'degree', 'income16', 'region', 'happy', 'satfin',
        'wtssps', 'mode', 'fileversion']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_wave(frame, actual_labels, wave):
    """Use labels attached to the actual variables, not similarly named old dictionaries."""
    if not frame.year.eq(wave).all() or frame.id.duplicated().any():
        raise ValueError('A single unique GSS cross section is required')
    for field in ('happy', 'satfin'):
        expected = ({1: 'very happy', 2: 'pretty happy', 3: 'not too happy'} if field == 'happy'
                    else {1: 'pretty well satisfied', 2: 'more or less satisfied', 3: 'not satisfied at all'})
        if any(actual_labels[field].get(k) != v for k, v in expected.items()):
            raise ValueError('Psychological categories changed: '+field)
    checks = {18: '$40,000 to $49,999', 19: '$50,000 to $59,999', 21: '$75,000 to $89,999',
              22: '$90,000 to $109,999', 23: '$110,000 to $129,999', 26: '$170,000 or over'}
    if any(actual_labels['income16'].get(k) != v for k, v in checks.items()):
        raise ValueError('INCOME16 boundaries changed; do not reuse numeric crosswalk')
    region_codes = {code: REGIONS.get(label) for code, label in actual_labels['region'].items()}
    if any(region_codes.get(code) is None for code in frame.region.dropna().unique()):
        raise ValueError('Unknown/coarsened geography needs an explicit mapping')
    valid = frame.happy.isin([1, 2, 3]) & frame.satfin.isin([1, 2, 3])
    weighted = np.isfinite(frame.wtssps) & frame.wtssps.gt(0)
    g = frame.loc[valid & weighted].copy()
    g['_AGE_CAT'] = g.age.map(lambda a: None if pd.isna(a) or not 18 <= a <= 89 else
                            ('Under 40' if a < 40 else ('40 to 60' if a < 60 else 'Over 60')))
    g['_EDU_CAT'] = [gss_education(d, e) if pd.notna(d) and pd.notna(e) and 0 <= d <= 4 and 0 <= e <= 20
                     else None for d, e in zip(g.degree, g.educ)]
    g['_HH_INC_CAT'] = g.income16.map(gss_income)
    g['_REGION_CAT'] = g.region.map(region_codes)
    g['donor_weight'] = g.wtssps
    g['source_wave'] = wave
    return g


def load_wave(path, wave):
    path = Path(path)
    with pd.io.stata.StataReader(path, convert_categoricals=False) as reader:
        variable_labels = reader.variable_labels()
    missing = set(COLS)-set(variable_labels)
    if missing: raise ValueError('Missing GSS fields: '+str(missing))
    frame = pd.read_stata(path, columns=COLS, convert_categoricals=False)
    labeled = pd.read_stata(path, columns=['region', 'income16', 'happy', 'satfin'], convert_categoricals=True)
    actual = {field: {int(c): str(v).lower() for c, v in zip(frame[field], labeled[field]) if pd.notna(c)}
              for field in labeled}
    # Dollar labels have no case-sensitive words except the terminal open category.
    donors = normalize_wave(frame, actual, wave)
    base = np.isfinite(frame.wtssps) & frame.wtssps.gt(0)
    joint = frame.happy.isin([1, 2, 3]) & frame.satfin.isin([1, 2, 3])
    total = donors.donor_weight.sum()
    distribution = {f'{int(h)}|{int(s)}': float(g.donor_weight.sum()/total)
                    for (h, s), g in donors.groupby(['happy', 'satfin'])}
    summary = {'wave': wave, 'source_path': str(path), 'source_sha256': digest(path),
        'fileversion': sorted(map(float, frame.fileversion.dropna().unique())),
        'file_rows': len(frame), 'positive_main_weight_n': int(base.sum()),
        'not_in_main_weight_n': int((~base).sum()), 'joint_raw_n': int(joint.sum()),
        'joint_weighted_n': len(donors),
        'complete_matching_n': int(donors[['_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT', '_REGION_CAT']].notna().all(axis=1).sum()),
        'ambiguous_90k_110k_joint_n': int(donors.income16.eq(22).sum()),
        'weight': 'wtssps', 'weighted_joint': distribution,
        'actual_field_labels': {field: {str(k): v for k, v in values.items()} for field, values in actual.items()},
        'mode_weighted_shares': {str(int(k)): float(g.wtssps.sum()/frame.loc[base, 'wtssps'].sum())
                                 for k, g in frame.loc[base].groupby('mode')},
        'age_rule': '18-39 / 40-59 / 60+; SCE legacy strings 40 to 60 and Over 60 retained only for keys',
        'income_rule': 'Previous-calendar-year nominal family income proxy; crossing 100k band excluded, no midpoint imputation',
        'weight_rule': 'WTSSPS baseline sample only; AmeriSpeak oversample requires different composite weights and is not mixed in'}
    return donors[['id', 'happy', 'satfin', 'donor_weight', '_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT', '_REGION_CAT', 'source_wave']], summary


def audit(raw_manifest, out):
    manifest = json.loads(Path(raw_manifest).read_text()); out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    summaries = {}
    for entry in manifest['sources']:
        p = Path(entry['file'])
        if digest(p) != entry['file_sha256']: raise ValueError('Raw data hash changed')
        donors, summary = load_wave(p, entry['wave'])
        dest = out/f"gss{entry['wave']}_donors_private.jsonl"
        donors.to_json(dest, orient='records', lines=True)
        summary.update(donor_path=str(dest), donor_sha256=digest(dest))
        summaries[str(entry['wave'])] = summary
    (out/'summary.json').write_text(json.dumps({'waves': summaries, 'scope': 'A offline; current releases, no historical byte-vintage proof',
        'new_api_calls': 0}, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return summaries
