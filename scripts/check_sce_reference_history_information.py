#!/usr/bin/env python3
"""Check unused regression information already present in the frozen prompts."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from decompose_sce_reference_regression import FIELDS, fit


def run(folder, prepared, out):
    if out.exists():
        raise ValueError('A new output path is required')
    grouped = defaultdict(list)
    source = folder/'cases_private.json'
    for r in json.loads(source.read_text()):
        grouped[r['month'], r['userid']].append(r)
    histories, hashes, rows = {}, {}, []
    for (month, _), pair in grouped.items():
        if not all(r['arms']['reference']['validation_status'] == 'valid'
                   and all(v is not None and np.isfinite(v) for v in
                           (r['arms']['reference']['mean'], r['real']['q9_mean'],
                            r['real']['q9_iqr'], r['baselines']['copy_previous'])) for r in pair):
            continue
        if month not in histories:
            path = prepared/str(month)/'past_private.json'
            histories[month] = json.loads(path.read_text())
            hashes[str(month)] = hashlib.sha256(path.read_bytes()).hexdigest()
        r = pair[0]
        h = histories[month][r['agent_id']]
        prior = r['baselines']['copy_previous']
        state = h['state']
        center = round(state['center'], 1)
        low, high = round(state['low'], 1), round(state['high'], 1)
        anchor = state['anchor']
        point = h['prior']['point_pct']
        rows.append({'month': month, 'prior': prior, 'real': r['real']['q9_mean'],
                     'sim': np.mean([p['arms']['reference']['mean'] for p in pair]),
                     'weight': r['design_survey_weight'], 'profile': r['profile'],
                     'history_summary': [round(anchor, 1)-center if anchor is not None else 0.,
                                         int(anchor is not None), state['n_earlier_valid']],
                     'previous_uncertainty_shape': [high-low, (high+low)/2-center],
                     'previous_Q8_vs_Q9': [point-prior if point is not None else 0., int(point is None)]})
    m = np.array([r['month'] for r in rows])
    w = np.array([r['weight'] for r in rows])
    for month in set(m):
        w[m == month] /= w[m == month].sum()
    y = np.array([r['real'] for r in rows])
    x = np.column_stack([[r['prior'] for r in rows], [r['sim'] for r in rows],
                         *[m == month for month in sorted(set(m))]])
    for field in FIELDS:
        values = [str(r['profile'].get(field, 'missing')) for r in rows]
        x = np.column_stack([x, *[np.array([v == level for v in values], dtype=float)
                                 for level in sorted(set(values))[1:]]])
    baseline = fit(x, y, w)[0]
    recorded = json.loads((folder/'regression_diagnostic_20261017.json').read_text())
    assert abs(baseline['r2']-recorded['individual_nested_models']['month_prior_P_sim_update']['weighted_r2_in_sample'])<1e-12
    names = ('history_summary', 'previous_uncertainty_shape', 'previous_Q8_vs_Q9')
    blocks = {name: np.array([r[name] for r in rows], dtype=float) for name in names}
    report = {}
    for name in names:
        fit_report = fit(np.column_stack([x, blocks[name]]), y, w)[0]
        report[name] = {**fit_report, 'increment_r2_points': 100*(fit_report['r2']-baseline['r2'])}
    full = fit(np.column_stack([x, *blocks.values()]), y, w)[0]
    for name in names:
        reduced = fit(np.column_stack([x, *[blocks[k] for k in names if k!=name]]), y, w)[0]
        report[name]['drop_from_extended_full_r2_points'] = 100*(full['r2']-reduced['r2'])
    result = {'status': 'posthoc_exploratory_already_provided_past_information',
              'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'n': len(rows), 'new_api_calls': 0, 'baseline_full_r2': baseline['r2'],
              'blocks': report, 'all_past_blocks_r2': full['r2'],
              'all_past_blocks_increment_r2_points': 100*(full['r2']-baseline['r2']),
              'specification': {'history_summary': 'rounded displayed typical past mean minus rounded last mean; anchor available indicator; number of valid earlier surveys including t-1',
                                'previous_uncertainty_shape': 'displayed prior p75-p25; displayed quartile midpoint minus displayed prior mean',
                                'previous_Q8_vs_Q9': 'actual prior Q8 point minus raw fitted prior mean; missing point indicator'},
              'limits': ['All added information is already in frozen prompt; no current answers or new population variables added.',
                         'Coefficients/R2 are exploratory conditional associations, not evidence a model ignored a variable or a new causal mechanism.',
                         'Older personal average includes last response, is correlated with it, and may capture reporting style as well as beliefs.',
                         'No out-of-sample improvement or new successful configuration is claimed; do not add separate single-block increments.',
                         'Sample-only weighted linear fit, few time cells, no p-values or attainable-ceiling estimate.'],
              'source_cases_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'past_file_sha256_by_month': hashes,
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: result[k] for k in ('n', 'baseline_full_r2', 'blocks', 'all_past_blocks_r2', 'all_past_blocks_increment_r2_points')}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', required=True, type=Path)
    p.add_argument('--prepared', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    run(a.folder, a.prepared, a.out)
