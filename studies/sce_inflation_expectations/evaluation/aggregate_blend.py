"""Offline convex combinations of frozen aggregate SCE predictions.

This module reads aggregate evaluations, not individual Q9 records. Selecting a
weight on already inspected months is descriptive calibration, never validation.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
SUMMARY = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/summary.json'
TRIAL = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
LEDGER = ROOT/'docs/sources/sce_baseline_aggregate_sources_latest_20261007.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metrics(prediction, truth):
    error = np.asarray(prediction, dtype=float)-np.asarray(truth, dtype=float)
    assert error.size and np.isfinite(error).all()
    return {'mae_pp': float(np.abs(error).mean()),
            'mse_pp_squared': float(np.square(error).mean()),
            'rmse_pp': float(np.sqrt(np.square(error).mean())),
            'bias_pp': float(error.mean())}


def fit_weight(truth, anchor, sim, loss):
    """Return the Simulation share; the history share is one minus this."""
    y, a, p = map(lambda z: np.asarray(z, dtype=float), (truth, anchor, sim))
    d = p-a
    if loss == 'mse':
        mass = float(np.dot(d, d))
        return float(np.clip(np.dot(d, y-a)/mass, 0, 1)) if mass else 0.
    if loss != 'mae':
        raise ValueError(loss)
    # Convex piecewise-linear objective: an endpoint or residual-zero knot is
    # optimal. Include both endpoints; among ties prefer less model complexity.
    nonzero = d != 0
    candidates = np.unique(np.r_[0., 1., np.clip((y-a)[nonzero]/d[nonzero], 0, 1)])
    losses = [float(np.abs(a+q*d-y).mean()) for q in candidates]
    best = min(losses)
    return float(next(q for q, value in zip(candidates, losses) if value <= best+1e-12))


def evaluate(rows, weight):
    return metrics([r['anchor_pp']+weight*(r['sim_pp']-r['anchor_pp']) for r in rows],
                   [r['truth_pp'] for r in rows])


def estimate(rows, loss):
    return fit_weight([r['truth_pp'] for r in rows], [r['anchor_pp'] for r in rows],
                      [r['sim_pp'] for r in rows], loss)


def scope_analysis(rows):
    months = sorted({r['month'] for r in rows})
    assert len(months) == 12 and all(sum(r['month'] == m for r in rows) == 2 for m in months)
    all_fit = {}
    for loss in ('mae', 'mse'):
        q = estimate(rows, loss)
        all_fit[loss] = {'simulation_weight': q, 'history_weight': 1-q,
                         'metrics': evaluate(rows, q)}
    early = [r for r in rows if r['month']//100 <= 2021]
    late = [r for r in rows if r['month']//100 >= 2022]
    split, expanding = {}, {}
    for loss in ('mae', 'mse'):
        q = estimate(early, loss)
        split[loss] = {'train_months': sorted({r['month'] for r in early}),
                       'evaluation_months': sorted({r['month'] for r in late}),
                       'simulation_weight': q, 'history_weight': 1-q,
                       'metrics': evaluate(late, q),
                       'carry_metrics': evaluate(late, 0.), 'pure_sim_metrics': evaluate(late, 1.)}
        folds, prediction, truth = [], [], []
        for year in range(2022, 2026):
            train = [r for r in rows if r['month']//100 < year]
            test = [r for r in rows if r['month']//100 == year]
            q = estimate(train, loss)
            folds.append({'test_year': year, 'train_months': sorted({r['month'] for r in train}),
                          'simulation_weight': q, 'history_weight': 1-q,
                          'metrics': evaluate(test, q), 'carry_metrics': evaluate(test, 0.)})
            prediction.extend(r['anchor_pp']+q*(r['sim_pp']-r['anchor_pp']) for r in test)
            truth.extend(r['truth_pp'] for r in test)
        expanding[loss] = {'folds': folds, 'metrics': metrics(prediction, truth),
                            'carry_metrics': evaluate(late, 0.), 'pure_sim_metrics': evaluate(late, 1.)}
    # Separate sensitivity: average the two scalar generations BEFORE fitting.
    averaged = []
    for month in months:
        pair = [r for r in rows if r['month'] == month]
        assert pair[0]['truth_pp'] == pair[1]['truth_pp'] and pair[0]['anchor_pp'] == pair[1]['anchor_pp']
        averaged.append({**pair[0], 'sim_pp': float(np.mean([r['sim_pp'] for r in pair]))})
    sensitivity = {}
    for loss in ('mae', 'mse'):
        q = estimate(averaged, loss)
        sensitivity[loss] = {'simulation_weight': q, 'metrics': evaluate(averaged, q)}
    return {'n_months': 12, 'generations_per_month': 2, 'effective_month_count': 12,
            'pure_sim': evaluate(rows, 1.), 'carry': evaluate(rows, 0.),
            'in_sample_best': all_fit, 'early_four_later_eight': split,
            'expanding_year': expanding, 'average_generations_before_fit_sensitivity': sensitivity,
            'fixed_weight_curve': [{'simulation_weight': float(q), **evaluate(rows, q)}
                                   for q in np.linspace(0, 1, 101)], 'aggregate_rows': rows}


def run(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('A fresh ignored output directory is required')
    source = json.loads(SUMMARY.read_text())
    ledger = json.loads(LEDGER.read_text())['headline_releases']
    index = {r['reference_period']: r for r in ledger}
    assert len(index) == len(ledger)
    official, micro, provenance = [], [], {}
    for month in sorted(source['wave_centers']):
        env_file = TRIAL/month/'environment.json'
        target = json.loads(env_file.read_text())['provider_args']['targets'][0]
        as_of = datetime.fromisoformat(target['as_of'])
        # Ledger stores dates, not intraday timestamps. Admit a release only
        # when the local day is fully elapsed; same-day cutoffs must be EOD.
        available = [r for r in ledger if datetime.fromisoformat(r['published_date']+'T23:59:59')
                     .replace(tzinfo=as_of.tzinfo) <= as_of]
        anchor = max(available, key=lambda r: r['reference_period'])
        truth = index[month[:4]+'-'+month[4:]]
        for release in (anchor, truth):
            path = ROOT/release['source_file']
            assert sha(path) == release['source_sha256']
            provenance[release['source_file']] = release['source_sha256']
        provenance[str(env_file.relative_to(ROOT))] = sha(env_file)
        wave = source['wave_centers'][month]
        for cell in [r for r in source['cells'] if r['month'] == int(month)]:
            common = {'month': int(month), 'repeat': cell['repeat'], 'sim_pp': cell['simulated_center_pp']}
            micro.append({**common, 'truth_pp': wave['full_wave']['center_pp'],
                          'anchor_pp': wave['previous_full_wave']['center_pp']})
            official.append({**common, 'truth_pp': truth['value_pp'], 'anchor_pp': anchor['value_pp'],
                             'as_of': target['as_of'], 'anchor_reference_period': anchor['reference_period'],
                             'anchor_published_date': anchor['published_date'],
                             'truth_published_date': truth['published_date']})
    result = {'status': 'completed_posthoc_aggregate_blend_diagnostic',
              'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_api_calls': 0,
              'formula': '(1 - simulation_weight) * historical_anchor + simulation_weight * current_simulation',
              'constraints': '0 <= simulation_weight <= 1; no intercept; weights sum to 1',
              'score_aggregation': 'equal months and equal generations; score each generation then average',
              'full_wave_recomputed': scope_analysis(micro),
              'official_first_release_public_anchor': scope_analysis(official),
              'source_sha256': {str(SUMMARY.relative_to(ROOT)): sha(SUMMARY),
                                str(LEDGER.relative_to(ROOT)): sha(LEDGER), **provenance},
              'implementation_sha256': sha(__file__),
              'limits': ['All12 months were previously inspected; full-sample best weights are optimistic descriptive fits.',
                         'Forward splits are posthoc time-ordered checks, not new independent blind validation.',
                         'Only aggregate output is blended; individual Q9 and cross-person heterogeneity do not change.',
                         'Full-wave recomputed mean-medians use the frozen approximate scorer, not official headline values.',
                         'Official anchors use the latest release available at each cutoff, sometimes t-2 rather than t-1.',
                         'The underlying simulation uses retrospective current P and actual personal past micro answers; this is not strict forecast B.',
                         'Model repetitions do not create24 independent months. No new simulation or default weight selected.']}
    # Exact-fit sanity checks are independent toy targets with known weights.
    assert fit_weight([1, 3], [0, 2], [2, 4], 'mae') == .5
    assert fit_weight([1, 3], [0, 2], [2, 4], 'mse') == .5
    assert fit_weight([0, 2], [0, 2], [2, 4], 'mae') == 0.
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    for key in ('full_wave_recomputed', 'official_first_release_public_anchor'):
        block = result[key]
        print(json.dumps({'target': key, **{k: v for k, v in block.items()
                          if k in ('pure_sim', 'carry', 'in_sample_best', 'early_four_later_eight', 'expanding_year')}}, ensure_ascii=False))
    return result
