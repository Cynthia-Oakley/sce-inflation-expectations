#!/usr/bin/env python3
"""Evaluate normalized SCE bundles without loading inputs into the simulation engine."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'studies/sce_inflation_expectations'))
from evaluation.metrics import compare_distributions, headline_errors, quantile


def evaluate_bundles(simulated, observed):
    for key in ['kind', 'truth_series_id']:
        if simulated.get(key) != observed.get(key) or not simulated.get(key):
            raise ValueError(f'Bundle mismatch/missing: {key}')
    if simulated['kind'] == 'population' and (
            not simulated.get('scoring_version') or simulated['scoring_version'] != observed.get('scoring_version')):
        raise ValueError('Population scoring versions must match; mixed-scoring comparisons require a separate sensitivity analysis')
    sim, real = defaultdict(list), defaultdict(list)
    for row in simulated['records']:
        sim[row['target_month']].append(row)
    for row in observed['records']:
        real[row['target_month']].append(row)
    if set(sim) != set(real) or not sim:
        raise ValueError('Declare and match evaluation months; do not silently drop missing forecasts')
    if simulated['kind'] == 'headline':
        if any(len(sim[m]) != 1 or len(real[m]) != 1 for m in sim):
            raise ValueError('Headline bundles need exactly one record per month')
        months = sorted(sim)
        return {'kind': 'headline', 'truth_series_id': simulated['truth_series_id'],
                'metrics': headline_errors([sim[m][0]['value_pp'] for m in months],
                                           [real[m][0]['value_pp'] for m in months]),
                'monthly': [{'target_month': m, 'prediction_pp': sim[m][0]['value_pp'],
                             'observed_pp': real[m][0]['value_pp']} for m in months]}
    if simulated['kind'] != 'population':
        raise ValueError('kind must be headline or population')
    result = []
    for month in sorted(sim):
        sx, sw = [r['mean_pp'] for r in sim[month]], [r['weight'] for r in sim[month]]
        tx, tw = [r['mean_pp'] for r in real[month]], [r['weight'] for r in real[month]]
        comparison = compare_distributions(sx, sw, tx, tw)
        uncertainty = None
        if all('uncertainty_pp' in r for r in sim[month] + real[month]):
            uncertainty = abs(quantile([r['uncertainty_pp'] for r in sim[month]], sw, .5)
                              - quantile([r['uncertainty_pp'] for r in real[month]], tw, .5))
        groups = []
        for field in simulated.get('group_fields', []):
            if not all(field in r for r in sim[month] + real[month]):
                raise ValueError(f'Group field absent: {field}')
            for category in sorted({str(r[field]) for r in real[month]}):
                sr = [r for r in sim[month] if str(r[field]) == category]
                tr = [r for r in real[month] if str(r[field]) == category]
                minimum = simulated.get('minimum_group_count', 20)
                if len(sr) < minimum or len(tr) < minimum:
                    groups.append(dict(field=field, category=category, status='insufficient_support',
                                       simulated_count=len(sr), observed_count=len(tr)))
                    continue
                groups.append(dict(field=field, category=category, status='evaluated',
                    **compare_distributions([r['mean_pp'] for r in sr], [r['weight'] for r in sr],
                                            [r['mean_pp'] for r in tr], [r['weight'] for r in tr])))
        paired = None
        if simulated.get('pairing') == 'same_observed_person':
            def indexed(rows):
                ids = [r['person_id'] for r in rows]
                if len(set(ids)) != len(ids):
                    raise ValueError('Duplicate person identifiers in paired evaluation')
                return {r['person_id']: r for r in rows}
            sm, tm = indexed(sim[month]), indexed(real[month])
            if set(sm) != set(tm):
                raise ValueError('Paired records require matched person IDs and an explicit common mask')
            ids = sorted(tm)
            errors = np.array([sm[i]['mean_pp'] - tm[i]['mean_pp'] for i in ids], dtype=float)
            weights = np.array([tm[i]['weight'] for i in ids], dtype=float)
            valid = np.isfinite(errors) & np.isfinite(weights) & (weights > 0)
            if valid.any():
                paired = dict(n_pairs=int(valid.sum()), n_excluded=int((~valid).sum()),
                              weighted_mae_pp=float(np.average(np.abs(errors[valid]), weights=weights[valid])),
                              weighted_bias_pp=float(np.average(errors[valid], weights=weights[valid])))
        result.append(dict(target_month=month, uncertainty_median_error_pp=uncertainty,
                           groups=groups, paired=paired, **comparison))
    constraints = simulated.get('constraints', [])
    primary = 'centered_w1_pp' if 'national_median' in constraints else 'w1_pp'
    if any(c != 'national_median' for c in constraints):
        raise ValueError('Additional constraints require an explicit unfit-validation metric contract')
    return dict(kind='population', scoring_version=simulated['scoring_version'], constraints=constraints,
                primary_metric=primary, primary_mean_pp=sum(r[primary] for r in result) / len(result),
                national_median_role='constraint_satisfaction_only' if constraints else 'validation', monthly=result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simulated', type=Path, required=True)
    p.add_argument('--observed', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = evaluate_bundles(json.loads(a.simulated.read_text()), json.loads(a.observed.read_text()))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(a.output)
