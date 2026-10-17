"""Past-only, time-ordered diagnostics on frozen personal SCE trajectories.

This is retrospective evaluation, not a new LLM trial or independent validation.
Only personal Q9 centers are combined; no synthetic Q9 density is constructed.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.stats import wasserstein_distance

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
HISTORY = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
RECEIPT = ROOT/'docs/workstreams/20261017_reference_scaleup/regression_diagnostic_20261017.json'
METHODS = ('carry', 'pure_sim', 'older_mean', 'history_fit', 'sim_fit', 'history_sim_fit')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def convex_weights(y, prior, older, sim, weight, use_history=True, use_sim=True):
    """Exact weighted quadratic minimum over a>=0,b>=0,a+b<=1.

    Enumerate the three simplex edges and its unconstrained interior solution.
    The coefficients multiply older-prior and sim-prior, respectively.
    """
    y, prior, older, sim, weight = map(lambda x: np.asarray(x, dtype=float),
                                      (y, prior, older, sim, weight))
    x = np.column_stack((older-prior if use_history else np.zeros_like(prior),
                         sim-prior if use_sim else np.zeros_like(prior)))
    target = y-prior
    candidates = [np.zeros(2)]
    for j, enabled in enumerate((use_history, use_sim)):
        if enabled:
            denominator = float(np.dot(weight*x[:, j], x[:, j]))
            coefficient = np.clip(np.dot(weight*x[:, j], target)/denominator, 0, 1) if denominator else 0.
            value = np.zeros(2); value[j] = coefficient; candidates.append(value)
    if use_history and use_sim:
        d = x[:, 0]-x[:, 1]
        denominator = float(np.dot(weight*d, d))
        a = np.clip(np.dot(weight*d, target-x[:, 1])/denominator, 0, 1) if denominator else 0.
        candidates.append(np.array([a, 1-a]))
        solution = np.linalg.lstsq(x*np.sqrt(weight)[:, None], target*np.sqrt(weight), rcond=None)[0]
        if np.all(solution >= 0) and solution.sum() <= 1:
            candidates.append(solution)
    losses = [float(np.dot(weight, (target-x@c)**2)) for c in candidates]
    best = min(losses)
    tied = [c for c, loss in zip(candidates, losses) if loss <= best+1e-12]
    return min(tied, key=lambda c: (c.sum(), c[1], c[0]))


def quantile(values, weights, q):
    order = np.argsort(values, kind='stable')
    return float(np.asarray(values)[order][np.searchsorted(np.cumsum(np.asarray(weights)[order]),
                                                          q*np.sum(weights), side='left')])


def metric_cells(rows, predictions):
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[row['month'], row['repeat']].append(i)
    cells = []
    for (month, repeat), indices in sorted(groups.items()):
        w = np.array([rows[i]['weight'] for i in indices]); w /= w.sum()
        y = np.array([rows[i]['truth'] for i in indices])
        p = np.asarray(predictions)[indices]
        prior = np.array([rows[i]['prior'] for i in indices])
        e = p-y
        cells.append({'month': month, 'repeat': repeat, 'n': len(indices),
                      'center_mae_pp': abs(quantile(p, w, .5)-quantile(y, w, .5)),
                      'personal_mae_pp': float(np.dot(w, abs(e))),
                      'personal_mse_pp_squared': float(np.dot(w, e*e)),
                      'cross_person_w1_pp': wasserstein_distance(p, y, w, w),
                      'update_w1_pp': wasserstein_distance(p-prior, y-prior, w, w),
                      'predicted_cross_person_iqr_pp': quantile(p, w, .75)-quantile(p, w, .25),
                      'real_cross_person_iqr_pp': quantile(y, w, .75)-quantile(y, w, .25)})
    keys = [key for key in cells[0] if key not in ('month', 'repeat', 'n')]
    summary = {key: float(np.mean([cell[key] for cell in cells])) for key in keys}
    summary['personal_rmse_pp'] = float(np.sqrt(summary['personal_mse_pp_squared']))
    return {'summary': summary, 'cells': cells}


def load_rows():
    receipt = json.loads(RECEIPT.read_text())
    assert sha(CASES) == receipt['source_cases_sha256']
    groups = defaultdict(list)
    for row in json.loads(CASES.read_text()):
        groups[row['month'], row['userid']].append(row)
    snapshots, rows, hashes = {}, [], {str(CASES.relative_to(ROOT)): sha(CASES)}
    for (month, _), pair in sorted(groups.items()):
        assert sorted(row['repeat'] for row in pair) == [1, 2]
        if not all(row['arms']['reference']['validation_status'] == 'valid'
                   and all(value is not None and np.isfinite(value) for value in
                           (row['arms']['reference']['mean'], row['real']['q9_mean'],
                            row['real']['q9_iqr'], row['baselines']['copy_previous'])) for row in pair):
            continue
        if month not in snapshots:
            path = HISTORY/str(month)/'past_private.json'
            snapshots[month] = json.loads(path.read_text()); hashes[str(path.relative_to(ROOT))] = sha(path)
        state = snapshots[month][pair[0]['agent_id']]['state']
        n, prior = state['n_earlier_valid'], pair[0]['baselines']['copy_previous']
        expected_previous = month-1 if month % 100 > 1 else (month//100-1)*100+12
        assert state['source_month'] == expected_previous and abs(prior-state['center']) < 1e-9
        older = (state['anchor']*n-state['center'])/(n-1) if state['anchor'] is not None else prior
        assert (state['anchor'] is not None) == (n >= 2)
        for row in pair:
            rows.append({'month': month, 'repeat': row['repeat'], 'weight': row['design_survey_weight'],
                         'truth': row['real']['q9_mean'], 'prior': prior, 'older': older,
                         'history_n': n, 'sim': row['arms']['reference']['mean']})
    mass = defaultdict(float)
    for row in rows:
        mass[row['month'], row['repeat']] += row['weight']
    for row in rows:
        row['weight'] /= mass[row['month'], row['repeat']]
    assert len(rows) == 4568
    return rows, hashes


def run(out):
    started = perf_counter(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Use a new ignored outputs directory')
    out.mkdir(parents=True)
    rows, sources = load_rows(); loaded = perf_counter()
    folds = []
    for label, train_months, test_months in [
            ('early_four_later_eight', sorted({r['month'] for r in rows if r['month']//100 <= 2021}),
             sorted({r['month'] for r in rows if r['month']//100 >= 2022})),
            *[(f'expanding_{year}', sorted({r['month'] for r in rows if r['month']//100 < year}),
               sorted({r['month'] for r in rows if r['month']//100 == year})) for year in range(2022, 2026)]]:
        train = [r for r in rows if r['month'] in train_months]
        test = [r for r in rows if r['month'] in test_months]
        arrays = [np.array([r[key] for r in train]) for key in ('truth', 'prior', 'older', 'sim', 'weight')]
        coefficients = {'history_fit': convex_weights(*arrays, use_sim=False),
                        'sim_fit': convex_weights(*arrays, use_history=False),
                        'history_sim_fit': convex_weights(*arrays)}
        results = {}
        for method in METHODS:
            if method in ('carry', 'pure_sim', 'older_mean'):
                key = {'carry': 'prior', 'pure_sim': 'sim', 'older_mean': 'older'}[method]
                pred = [r[key] for r in test]
            else:
                a, b = coefficients[method]
                pred = [r['prior']+a*(r['older']-r['prior'])+b*(r['sim']-r['prior']) for r in test]
            results[method] = metric_cells(test, pred)
        folds.append({'name': label, 'train_months': train_months, 'test_months': test_months,
                      'n_train_person_months': len(train)//2, 'n_test_person_months': len(test)//2,
                      'weights': {key: {'older': float(v[0]), 'simulation': float(v[1]),
                                        'previous': float(1-v.sum())} for key, v in coefficients.items()},
                      'results': results})
    expanding = {}
    for method in METHODS:
        cells = [c for fold in folds[1:] for c in fold['results'][method]['cells']]
        keys = [k for k in cells[0] if k not in ('month', 'repeat', 'n')]
        summary = {k: float(np.mean([c[k] for c in cells])) for k in keys}
        summary['personal_rmse_pp'] = float(np.sqrt(summary['personal_mse_pp_squared']))
        expanding[method] = {'summary': summary, 'cells': cells}
    finished = perf_counter()
    result = {'status': 'completed_posthoc_time_ordered_diagnostic', 'new_api_calls': 0,
              'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'n_person_months': len(rows)//2, 'n_generated_rows': len(rows),
              'history_counts_person_months': {str(n): sum(r['history_n'] == n for r in rows)//2
                                               for n in sorted({r['history_n'] for r in rows})},
              'objective': 'Training person-level weighted MSE; nonnegative weights sum to one; no intercept.',
              'older_mean_definition': 'Unrounded Q9-derived personal mean, excluding t-1; fallback to t-1 if unavailable.',
              'evaluation': 'Same returning-person support, weights normalized per month; score repeats separately then average.',
              'limits': ['All months previously inspected; this is not new blind validation or a causal mechanism test.',
                         'True personal prior questionnaires are A conditioning, not a strict B forecast.',
                         'Only scalar personal Q9 means are predicted; no full Q9 density or uncertainty reconstruction.',
                         'Cross-person distributions concern selected returning respondents, not all nationwide entrants.',
                         'No confidence intervals: eight inspected test months cannot establish general superiority.'],
              'folds': folds, 'expanding_evaluation': expanding,
              'timing_seconds': {'load_frozen_data': loaded-started, 'fit_and_evaluate': finished-loaded,
                                 'total_before_writing': finished-started},
              'source_sha256': sources, 'implementation_sha256': sha(__file__)}
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    return result
