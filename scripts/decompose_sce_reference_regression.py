#!/usr/bin/env python3
"""Attribute existing response-regression R2 and diagnose overlapping predictors.

Offline, post-hoc, same common support as the prior diagnostic. No API, no
Q9 fitting, no changes to the frozen simulation or its success criteria.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.linalg import lstsq

FIELDS = ('age_group', 'education_group', 'household_income_band', 'numeracy',
          'region', 'housing_tenure', 'employment_status')


def fit(x, y, w):
    root = np.sqrt(w)
    beta, _, rank, _ = lstsq(x * root[:, None], y * root, lapack_driver='gelsy')
    residual = y - x @ beta
    sse = float(np.sum(w * residual ** 2))
    tss = float(np.sum(w * (y - np.average(y, weights=w)) ** 2))
    return {'r2': 1 - sse / tss, 'rank': int(rank), 'columns': x.shape[1]}, beta, residual


def corr(x, y, w):
    x, y = x - np.average(x, weights=w), y - np.average(y, weights=w)
    return float(np.sum(w * x * y) / np.sqrt(np.sum(w*x*x) * np.sum(w*y*y)))


def run(folder, out):
    if out.exists():
        raise ValueError('Use a new output path; retain previous diagnostics')
    casepath = folder / 'cases_private.json'
    grouped = defaultdict(list)
    for r in json.loads(casepath.read_text()):
        grouped[r['month'], r['userid']].append(r)
    rows = []
    for pair in grouped.values():
        assert sorted(r['repeat'] for r in pair) == [1, 2]
        if not all(r['arms']['reference']['validation_status'] == 'valid'
                   and all(v is not None and np.isfinite(v) for v in
                           (r['arms']['reference']['mean'], r['real']['q9_mean'],
                            r['real']['q9_iqr'], r['baselines']['copy_previous'])) for r in pair):
            continue
        r = pair[0]
        assert r['real'] == pair[1]['real'] and r['profile'] == pair[1]['profile']
        rows.append({'month': r['month'], 'weight': r['design_survey_weight'],
                     'prior': r['baselines']['copy_previous'], 'real': r['real']['q9_mean'],
                     'sim': float(np.mean([p['arms']['reference']['mean'] for p in pair])),
                     'profile': r['profile']})
    m = np.array([r['month'] for r in rows])
    w = np.array([r['weight'] for r in rows])
    months = sorted(set(m.tolist()))
    for month in months:
        w[m == month] /= w[m == month].sum()
    y, prior, sim = (np.array([r[k] for r in rows]) for k in ('real', 'prior', 'sim'))
    monthx = np.column_stack([m == month for month in months]).astype(float)
    pblocks = {}
    for field in FIELDS:
        values = [str(r['profile'].get(field, 'missing')) for r in rows]
        pblocks[field] = np.column_stack([np.array([v == level for v in values], dtype=float)
                                         for level in sorted(set(values))[1:]])
    px = np.column_stack(list(pblocks.values()))
    base = np.column_stack([monthx, prior, sim])
    full = np.column_stack([base, px])
    report, _, residual = fit(full, y, w)
    previous = json.loads((folder / 'regression_diagnostic_20261017.json').read_text())
    frozen_r2 = previous['individual_nested_models']['month_prior_P_sim_update']['weighted_r2_in_sample']
    assert abs(report['r2'] - frozen_r2) < 1e-12

    # Group Shapley = exact average of each P group's increments over every
    # insertion order, conditional on month+prior+sim. All dummy columns in
    # a categorical factor enter/leave as one block. 2**7 =128 fits.
    k = len(FIELDS)
    coalition = {}
    for mask in range(1 << k):
        selected = [pblocks[f] for j, f in enumerate(FIELDS) if mask & (1 << j)]
        coalition[mask] = fit(np.column_stack([base, *selected]), y, w)[0]['r2']
    fullmask = (1 << k) - 1
    factors = []
    for j, field in enumerate(FIELDS):
        value = 0.0
        for mask in range(1 << k):
            if mask & (1 << j):
                continue
            size = mask.bit_count()
            weight = math.factorial(size) * math.factorial(k-size-1) / math.factorial(k)
            value += weight * (coalition[mask | (1 << j)] - coalition[mask])
        factors.append({'factor': field, 'dummy_count': pblocks[field].shape[1],
                        'add_alone_r2_points': 100*(coalition[1 << j] - coalition[0]),
                        'drop_from_full_r2_points': 100*(coalition[fullmask] - coalition[fullmask ^ (1 << j)]),
                        'average_order_r2_points': 100*value})
    total_p = 100*(coalition[fullmask]-coalition[0])
    assert abs(sum(r['average_order_r2_points'] for r in factors)-total_p) < 1e-10

    sequence = {}
    for name, x in [('month', monthx), ('month_P', np.column_stack([monthx, px])),
                    ('month_prior', np.column_stack([monthx, prior])),
                    ('month_prior_P', np.column_stack([monthx, prior, px])),
                    ('month_sim', np.column_stack([monthx, sim])),
                    ('month_sim_P', np.column_stack([monthx, sim, px])),
                    ('month_prior_sim', base), ('full', full)]:
        sequence[name] = fit(x, y, w)[0]

    # VIF is basis dependent. Show actual level and (sim-prior) separately;
    # their residual variance / incremental outcome R2 must be identical.
    controls = np.column_stack([monthx, prior, px])
    aux_level, _, sim_residual = fit(controls, sim, w)
    aux_update, _, update_residual = fit(controls, sim-prior, w)
    assert np.max(abs(sim_residual-update_residual)) < 1e-10
    _, _, y_residual = fit(controls, y, w)
    partial_r = corr(sim_residual, y_residual, w)
    p_r2 = (report['r2']-sequence['month_prior_P']['r2'])/(1-sequence['month_prior_P']['r2'])
    assert abs(partial_r**2 - p_r2) < 1e-12
    _, _, prior_within = fit(monthx, prior, w)
    _, _, sim_within = fit(monthx, sim, w)
    collinearity = {'raw_weighted_prior_sim_correlation': corr(prior, sim, w),
                   'within_month_prior_sim_correlation': corr(prior_within, sim_within, w),
                   'sim_level_explained_by_month_prior_P_r2': aux_level['r2'],
                   'sim_level_weighted_VIF': 1/(1-aux_level['r2']),
                   'sim_update_weighted_VIF': 1/(1-aux_update['r2']),
                   'outcome_sim_partial_correlation': partial_r,
                   'outcome_sim_partial_r2': p_r2,
                   'full_design_rank': report['rank'], 'full_design_columns': report['columns'],
                   'level_update_residual_max_difference': float(np.max(abs(sim_residual-update_residual)))}

    # Exploratory temporal sensitivity, not additional untouched validation.
    halves = []
    for name, pick in [('2020_2022', m < 202300), ('2023_2025', m >= 202300)]:
        t = fit(full[pick], y[pick], w[pick])[0]['r2']
        halves.append({'scope': name, 'n': int(pick.sum()), 'full_r2': t,
                       'drop_one_r2_points': {f: 100*(t-fit(np.column_stack(
                           [base[pick], *[pblocks[g][pick] for g in FIELDS if g != f]]),
                           y[pick], w[pick])[0]['r2']) for f in FIELDS}})

    # Macro regression previously had only a constant and model center.
    # Add only actual previous-person center, retaining just12 observations.
    summary = json.loads((folder/'summary.json').read_text())
    my, ms, mp = [], [], []
    for month in months:
        cells = [c for c in summary['cells'] if c['month'] == month]
        my.append(np.mean([c['matched_sample_truth_center_pp'] for c in cells]))
        ms.append(np.mean([c['simulated_center_pp'] for c in cells]))
        mp.append(np.mean([c['matched_sample_truth_center_pp']+
                           c['scalar_baseline_metrics_same_sample']['copy_previous']['q9_center_bias_pp'] for c in cells]))
    my, ms, mp = map(np.asarray, (my, ms, mp))
    macro = {}
    for name, x in [('prior_center', np.column_stack([np.ones(len(my)), mp])),
                    ('sim_center', np.column_stack([np.ones(len(my)), ms])),
                    ('prior_and_sim', np.column_stack([np.ones(len(my)), mp, ms]))]:
        r, beta, _ = fit(x, my, np.ones(len(my)))
        macro[name] = {**r, 'coefficients': beta.tolist()}
    macro['prior_sim_correlation'] = corr(mp, ms, np.ones(len(my)))
    macro['sim_increment_given_prior_r2_points'] = 100*(macro['prior_and_sim']['r2']-macro['prior_center']['r2'])

    squared = w*residual**2
    order = np.argsort(-abs(residual))
    tail = {f'top_{pct}_percent_rows_squared_error_share': float(squared[order[:math.ceil(len(rows)*pct/100)]].sum()/squared.sum()) for pct in (1, 5)}
    result = {'status': 'posthoc_descriptive_same_frozen_answers',
              'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'n_person_months': len(rows), 'n_months': len(months), 'new_api_calls': 0,
              'outcome': 'actual current personal Q9 fitted mean; two model generations averaged before regression',
              'weight': 'design-survey weights normalized within month; months equally weighted',
              'units': 'r2 is0-1; r2_points is100*(R2 difference), not inflation pp or fraction of all causal influences',
              'population_contributions_base': 'month fixed effects + own actual previous Q9 mean + current Sim Q9 mean',
              'population_factor_contributions': sorted(factors, key=lambda r: -r['average_order_r2_points']),
              'population_total_r2_points_given_base': total_p,
              'population_decomposition_method': 'Exact seven-block Shapley/average ordering over128 subsets. Descriptive allocation of shared linear explanatory power; not causal.',
              'nested_r2': sequence, 'collinearity': collinearity,
              'temporal_drop_one_sensitivity': halves,
              'macro_12_month_descriptive_only': macro, 'squared_error_tail_concentration': tail,
              'checks': {'previous_full_r2_absolute_difference': abs(report['r2']-frozen_r2),
                         'population_sum_r2_points_error': abs(sum(r['average_order_r2_points'] for r in factors)-total_p),
                         'FWL_partial_r2_identity_error': abs(partial_r**2-p_r2)},
              'limits': ['Sample-only, not a nationwide causal or forecast model; all responses already inspected.',
                         'Shared information is allocated by convention; unique drop-one losses cannot be summed.',
                         'Individual residual contains omitted information, nonlinear effects, response noise and scoring/measurement error; no estimated achievable R2 ceiling.',
                         'No p-values: heteroskedastic, overlapping households and only12 time cells.',
                         'National E variables are collinear with month indicators; macro contribution cannot be inferred from individual R2 shares.',
                         'Macro center fits only12 points and must not be advertised as new calibration success.',
                         'Full rank and VIF do not establish stable coefficients or causality.'],
              'method_sources': ['https://www.jstatsoft.org/article/view/v017i01',
                                 'https://www.statsmodels.org/stable/generated/statsmodels.stats.outliers_influence.variance_inflation_factor.html'],
              'source_cases_sha256': hashlib.sha256(casepath.read_bytes()).hexdigest(),
              'source_summary_sha256': hashlib.sha256((folder/'summary.json').read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: result[k] for k in ('population_factor_contributions',
          'population_total_r2_points_given_base', 'nested_r2', 'collinearity',
          'temporal_drop_one_sensitivity', 'macro_12_month_descriptive_only',
          'squared_error_tail_concentration', 'checks')}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    run(a.folder, a.out)
