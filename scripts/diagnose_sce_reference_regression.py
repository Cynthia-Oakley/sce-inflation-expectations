#!/usr/bin/env python3
"""Exploratory regressions on frozen fitted responses; never refits Q9 or calls APIs."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

P_FIELDS = ('age_group', 'education_group', 'household_income_band', 'numeracy',
            'region', 'housing_tenure', 'employment_status')


def fit(x, y, w):
    root = np.sqrt(w)
    coef, _, rank, _ = np.linalg.lstsq(x * root[:, None], y * root, rcond=None)
    residual = y - x @ coef
    sse = float(np.sum(w * residual ** 2))
    tss = float(np.sum(w * (y - np.average(y, weights=w)) ** 2))
    return coef, {'n': len(y), 'rank': int(rank), 'columns': x.shape[1],
                  'weighted_r2_in_sample': 1 - sse / tss,
                  'weighted_rmse_in_sample_pp': float(np.sqrt(sse / w.sum())),
                  'weighted_mae_in_sample_pp': float(np.average(abs(residual), weights=w))}


def run(folder, out):
    if out.exists():
        raise ValueError('New diagnostic output required; never overwrite')
    source = folder / 'cases_private.json'
    raw = json.loads(source.read_text())
    paired = defaultdict(list)
    for row in raw:
        paired[row['month'], row['userid']].append(row)
    rows = []
    for pair in paired.values():
        assert sorted(r['repeat'] for r in pair) == [1, 2]
        good = all(r['arms']['reference']['validation_status'] == 'valid'
                   and all(v is not None and np.isfinite(v) for v in
                           (r['arms']['reference']['mean'], r['real']['q9_mean'],
                            r['real']['q9_iqr'], r['baselines']['copy_previous'])) for r in pair)
        if not good:
            continue
        r = pair[0]
        assert pair[1]['real'] == r['real'] and pair[1]['profile'] == r['profile']
        rows.append({'month': r['month'], 'prior': r['baselines']['copy_previous'],
                     'real': r['real']['q9_mean'],
                     'model': float(np.mean([p['arms']['reference']['mean'] for p in pair])),
                     'weight': r['design_survey_weight'], 'profile': r['profile']})
    months = sorted({r['month'] for r in rows})
    y = np.array([r['real'] for r in rows])
    prior = np.array([r['prior'] for r in rows])
    innovation = np.array([r['model'] - r['prior'] for r in rows])
    w = np.array([r['weight'] for r in rows])
    m = np.array([r['month'] for r in rows])
    for month in months:
        w[m == month] /= w[m == month].sum()
    month_x = np.column_stack([m == month for month in months]).astype(float)
    pcols, pnames = [], []
    for field in P_FIELDS:
        values = [str(r['profile'].get(field, 'missing')) for r in rows]
        for level in sorted(set(values))[1:]:
            pcols.append(np.array([v == level for v in values], dtype=float))
            pnames.append(f'{field}:{level}')
    px = np.column_stack(pcols)
    base = np.column_stack([month_x, prior])
    xp = np.column_stack([base, px])
    specs = {'month_only': month_x,
             'month_prior': base,
             'month_prior_sim_update': np.column_stack([base, innovation]),
             'month_prior_P': xp,
             'month_prior_P_sim_update': np.column_stack([xp, innovation])}
    models = {}
    for name, x in specs.items():
        beta, report = fit(x, y, w)
        if name != 'month_only':
            report['prior_coefficient'] = float(beta[len(months)])
        if name.endswith('_sim_update'):
            report['sim_update_coefficient'] = float(beta[-1])
        models[name] = report
    for full, reduced in [('month_prior_sim_update', 'month_prior'),
                          ('month_prior_P_sim_update', 'month_prior_P')]:
        r2a = models[full]['weighted_r2_in_sample']
        r2b = models[reduced]['weighted_r2_in_sample']
        models[full]['r2_increment_over_reduced'] = r2a - r2b
        models[full]['partial_r2'] = (r2a - r2b) / (1 - r2b)

    # Low-dimensional expanding-time assessment, no unseen month intercepts.
    # Post-hoc on already inspected outputs: not an independent validation claim.
    cv = []
    cv_features = {'prior_only': np.column_stack([np.ones(len(rows)), prior]),
                   'prior_and_sim_update': np.column_stack([np.ones(len(rows)), prior, innovation])}
    years = m // 100
    for year in sorted(set(years))[2:]:
        train, test = years < year, years == year
        reports = {'test_year': int(year), 'train_n': int(train.sum()), 'test_n': int(test.sum())}
        for name, x in cv_features.items():
            beta, _ = fit(x[train], y[train], w[train])
            pred = x[test] @ beta
            sse = float(np.sum(w[test] * (y[test] - pred) ** 2))
            baseline_sse = float(np.sum(w[test] * (y[test] - prior[test]) ** 2))
            reports[name] = {'coefficients': beta.tolist(),
                             'mae_pp': float(np.average(abs(y[test] - pred), weights=w[test])),
                             'rmse_pp': float(np.sqrt(sse / w[test].sum())),
                             'r2_oos_relative_to_copy_previous': 1 - sse / baseline_sse}
        cv.append(reports)
    summary = json.loads((folder / 'summary.json').read_text())
    monthly = []
    for month in months:
        cells = [c for c in summary['cells'] if c['month'] == month]
        monthly.append({'month': month,
                        'model_center': float(np.mean([c['simulated_center_pp'] for c in cells])),
                        'real_center': float(np.mean([c['matched_sample_truth_center_pp'] for c in cells]))})
    macro_x = np.column_stack([np.ones(len(monthly)), [r['model_center'] for r in monthly]])
    macro_b, macro = fit(macro_x, np.array([r['real_center'] for r in monthly]), np.ones(len(monthly)))
    macro['intercept'], macro['slope'] = map(float, macro_b)
    macro['interpretation'] = 'Only12 months, descriptive two-parameter fit; not a calibrated model validation.'
    result = {'status': 'posthoc_exploratory_no_new_API_or_Q9_fitting',
              'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'observations': len(rows), 'months': months, 'new_api_calls': 0,
              'unit': 'one person-month; average two independent model generation Q9 means, not new people',
              'weights': 'design-survey weights normalized within each month, months equally weighted',
              'outcome': 'current actual personal Q9 fitted mean; same frozen scorer',
              'sim_variable': 'model current Q9 mean minus actual previous Q9 mean; conditional on prior this spans same space as model level',
              'P_controls': list(P_FIELDS), 'P_dummy_count': len(pnames),
              'individual_nested_models': models, 'macro_two_parameter_diagnostic': macro,
              'expanding_year_descriptive_checks': cv,
              'limits': ['No causal interpretation or automatic prompt-policy identification.',
                         'Twelve selected months; no p-values or conventional significance claims.',
                         'National macro variables collinear with month fixed effects; not added to individual month-FE fit.',
                         'Two generations collapsed before regression. Same respondent may occur in more than one month.',
                         'R2 is squared-loss variance explanation, not median MAE or W1 success.',
                         'All outputs were previously inspected; expanding-time checks remain retrospective diagnostics, not untouched tests.',
                         'Own previous actual answers remain A-line conditional inputs, not recursive B forecasts.',
                         'No tail trimming or best-specification selection.'],
              'source_cases_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'source_summary_sha256': hashlib.sha256((folder/'summary.json').read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'n': len(rows), 'individual': models, 'macro': macro,
                      'expanding_checks': cv}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    run(a.folder, a.out)
