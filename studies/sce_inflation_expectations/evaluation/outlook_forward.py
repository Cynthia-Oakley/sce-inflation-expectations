"""Cached-data Q2 diagnostics, using existing temporal scoring and WLS helpers."""
from collections import defaultdict
from pathlib import Path
from time import perf_counter
import json
import numpy as np

from .history_forward import load_rows, metric_cells, ROOT
from .history_mechanism import FIELDS, regress
from ..experiments.financial_outlook import q2_lookup, previous, Q2_CACHE, Q2_RECEIPT
from ..experiments.frozen_batch import sha, dump


def load_frame():
    rows, sources = load_rows(); lookup = q2_lookup()
    groups = defaultdict(list)
    for row in json.loads((ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json').read_text()):
        groups[row['month'], row['userid']].append(row)
    good = []
    for (month, uid), pair in sorted(groups.items()):
        if all(r['arms']['reference']['validation_status'] == 'valid' and all(v is not None and np.isfinite(v)
               for v in (r['arms']['reference']['mean'], r['real']['q9_mean'], r['real']['q9_iqr'], r['baselines']['copy_previous'])) for r in pair):
            good.append(((month, uid), pair))
    result = []
    for i, ((month, uid), pair) in enumerate(good):
        pair = sorted(pair, key=lambda r: r['repeat']); base = rows[2*i]
        assert base['month'] == month and abs(base['truth']-pair[0]['real']['q9_mean']) < 1e-12
        result.append({**base, **pair[0]['profile'], 'repeat': 1, 'sim': np.mean([r['arms']['reference']['mean'] for r in pair]),
            'real': base['truth'], 'anchor_gap': base['older']-base['prior'],
            'anchor_available': int(base['history_n'] >= 2),
            'outlook_previous': lookup.get((previous(month), uid))})
    sources.update({str(p.relative_to(ROOT)): sha(p) for p in (Q2_CACHE, Q2_RECEIPT)})
    return result, sources


def design(rows, levels, with_q2):
    columns = [np.ones(len(rows))]
    columns += [np.array([r[k] for r in rows], dtype=float) for k in ('prior', 'sim', 'anchor_gap', 'anchor_available', 'history_n')]
    for key, values in levels.items():
        columns += [np.array([str(r.get(key)) == v for r in rows], dtype=float) for v in values[1:]]
    if with_q2:
        columns += [np.array([r['outlook_previous'] == c for r in rows], dtype=float) for c in (1, 2, 4, 5, None)]
    return np.column_stack(columns)


def run(out):
    start = perf_counter(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'): raise ValueError('Fresh ignored output required')
    rows, sources = load_frame(); loaded = perf_counter()
    temporal = {}
    numeric = ('prior', 'sim', 'anchor_gap', 'anchor_available', 'history_n')
    for name, choose in [('2020_2022', lambda m: m < 202300), ('2023_2025', lambda m: m >= 202300)]:
        a = [r for r in rows if choose(r['month'])]
        baseline = regress(a, numeric); q2 = regress(a, numeric, (*FIELDS, 'outlook_previous'))
        temporal[name] = {'n': len(a), 'baseline_r2': baseline['r2'], 'with_q2_r2': q2['r2'],
                         'r2_increment_points': 100*(q2['r2']-baseline['r2']),
                         'q2_coefficients': {k: v for k, v in q2['coefficients'].items() if k.startswith('outlook_previous')},
                         'rank': q2['rank'], 'columns': q2['columns']}
    folds = []
    for year in range(2022, 2026):
        train = [r for r in rows if r['month']//100 < year]; test = [r for r in rows if r['month']//100 == year]
        levels = {key: sorted({str(r.get(key)) for r in train}) for key in FIELDS}
        w = np.array([r['weight'] for r in train]); y = np.array([r['truth'] for r in train])
        outputs = {}
        for name, with_q2 in [('base_history_sim_P', False), ('plus_previous_Q2', True)]:
            x = design(train, levels, with_q2); xt = design(test, levels, with_q2)
            b, _, rank, _ = np.linalg.lstsq(x*np.sqrt(w)[:, None], y*np.sqrt(w), rcond=None)
            outputs[name] = {**metric_cells(test, xt@b), 'rank': int(rank), 'columns': x.shape[1]}
        folds.append({'test_year': year, 'train_months': sorted({r['month'] for r in train}),
                      'test_months': sorted({r['month'] for r in test}), 'results': outputs})
    summary = {}
    for method in ('base_history_sim_P', 'plus_previous_Q2'):
        cells = [c for f in folds for c in f['results'][method]['cells']]
        keys = [k for k in cells[0] if k not in ('month', 'repeat', 'n')]
        summary[method] = {k: float(np.mean([c[k] for c in cells])) for k in keys}
        summary[method]['personal_rmse_pp'] = float(np.sqrt(summary[method]['personal_mse_pp_squared']))
    out.mkdir(parents=True)
    result = {'status': 'completed_posthoc_Q2_diagnostic', 'n_person_months': len(rows), 'new_api_calls': 0,
        'generation_handling': 'Average the two Sim individual centers, as in earlier association diagnostics.',
        'period_models': temporal, 'expanding_folds': folds, 'expanding_summary': summary,
        'forward_model': 'Train WLS intercept/P/prior/Sim/older gap/availability/count, then add categorical previous Q2. No held-out month dummies or current Q2.',
        'limits': ['Selected months already inspected; not causal, blind, nationwide or strict B.',
                   'Unconstrained regression is a diagnostic, not a proposed prompt or production prediction.',
                   'Training MSE and macro-median/W1 objectives differ; do not tune to this evaluation.'],
        'source_sha256': sources, 'implementation_sha256': sha(__file__),
        'timing_seconds': {'load_cached_inputs': loaded-start, 'fit_and_score': perf_counter()-loaded}}
    dump(out/'summary.json', result); return result
