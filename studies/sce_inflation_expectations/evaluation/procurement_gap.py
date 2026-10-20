"""Post-hoc conditional diagnostics of cached replies; no model calls or fits.

Here 'fits' means no new Q9 density fits. WLS descriptions reuse the existing
control-design helper; they are not causal updating parameters or forecasts.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from . import cognition as shared
from .metrics import quantile
from .response_gap_controls import FIELDS, design, regression, probability_features
from scripts.report_sce_information_exposure import cell_metrics

ROOT = Path(__file__).resolve().parents[3]
PRIOR_LABELS = ('below_2', '2_to_below_4', '4_to_below_8', '8_or_above')


def band(value):
    return PRIOR_LABELS[int(value >= 2)+int(value >= 4)+int(value >= 8)]


def average(rows):
    return {k: float(np.mean([r[k] for r in rows if shared.finite(r.get(k))]))
            if any(shared.finite(r.get(k)) for r in rows) else None for k in rows[0]} if rows else {}


def cell(rows, arm):
    y = np.array([r['real']['q9_mean'] for r in rows])
    p = np.array([r['arms'][arm]['mean'] for r in rows])
    prior = np.array([r['real']['previous_q9_mean'] for r in rows])
    w = np.array([r['survey_weight'] for r in rows])
    result = cell_metrics(y, prior, p, w)
    result.update(truth_mean_pp=float(np.average(y, weights=w)),
        model_mean_pp=float(np.average(p, weights=w)), prior_mean_pp=float(np.average(prior, weights=w)),
        personal_bias_pp=float(np.average(p-y, weights=w)),
        truth_update_mean_pp=float(np.average(y-prior, weights=w)),
        model_update_mean_pp=float(np.average(p-prior, weights=w)),
        prior_above8_share=float(np.average(prior >= 8, weights=w)))
    for label, values in [('truth', y), ('model', p)]:
        for q in (.1, .25, .5, .75, .9):
            result[f'{label}_q{int(100*q)}_pp'] = quantile(values, w, q)
    for label, bins in [('truth', [r['real']['q9_bins'] for r in rows]),
                        ('model', [r['arms'][arm]['q9_bins'] for r in rows])]:
        features = [probability_features(b) for b in bins]
        for k in ('deflation_probability_pct', 'zero_deflation', 'maximum_bin_pct', 'nonzero_bins'):
            result[f'{label}_{k}'] = float(np.average([f[k] for f in features], weights=w))
    return result


def summarize(cases, arms, months, repeats, minimum=1):
    cells = []
    for m in months:
        for rep in repeats:
            rows = [r for r in cases if r['month'] == m and r['repeat'] == rep]
            if len(rows) < minimum:
                continue
            w = np.array([r['survey_weight'] for r in rows])
            cells.append({'month': m, 'repeat': rep, 'n': len(rows),
                'ess': float(w.sum()**2/(w@w)), 'max_weight_share': float(w.max()/w.sum()),
                'arms': {a: cell(rows, a) for a in arms}})
    return {'person_months': len({(r['month'], r['userid']) for r in cases}),
        'cells_used': len(cells), 'months_used': sorted({c['month'] for c in cells}),
        'minimum_cell_n': min((c['n'] for c in cells), default=0),
        'minimum_ess': min((c['ess'] for c in cells), default=None),
        'sparse_or_concentrated_cells': [dict(month=c['month'], repeat=c['repeat'], n=c['n'], ess=c['ess'])
            for c in cells if c['n'] < 8 or c['ess'] < 5 or c['max_weight_share'] > .25],
        'metrics': {a: average([c['arms'][a] for c in cells]) for a in arms}, 'cells': cells}


def regression_report(cases, arms):
    grouped = defaultdict(list)
    for r in cases:
        grouped[r['month'], r['userid']].append(r)
    rows = []
    for (m, uid), rr in grouped.items():
        r = rr[0]
        rows.append({'month': m, 'userid': uid, 'weight': r['survey_weight'], **r['profile'],
            'prior': r['real']['previous_q9_mean'], 'real': r['real']['q9_mean'],
            **{a: float(np.mean([p['arms'][a]['mean'] for p in rr])) for a in arms}})
    for m in {r['month'] for r in rows}:
        mass = sum(r['weight'] for r in rows if r['month'] == m)
        for r in rows:
            if r['month'] == m:
                r['weight'] /= mass
    specs = {}
    for label, subset in [('all', rows), ('prior_abs_le20_sensitivity', [r for r in rows if abs(r['prior']) <= 20])]:
        specs[label] = {}
        for spec, cats in [('month_prior', ()), ('month_prior_P', FIELDS)]:
            x, names, references = design(subset, ('prior',), cats)
            w = [r['weight'] for r in subset]
            fits = {a: regression(x, [r['real'] if a == 'truth' else r[a] for r in subset], w, names)[0]
                    for a in ['truth', *arms]}
            fits['error_fits'] = {a: regression(x, [r[a]-r['real'] for r in subset], w, names)[0] for a in arms}
            specs[label][spec] = {'n_person_months': len(subset), 'references': references, 'fits': fits}
    leave_month, leave_contrasts = {}, {}
    for m in sorted({r['month'] for r in rows}):
        rr = [r for r in rows if r['month'] != m]
        x, names, _ = design(rr, ('prior',), FIELDS)
        fits = {a: regression(x, [r['real'] if a == 'truth' else r[a] for r in rr],
            [r['weight'] for r in rr], names)[0] for a in ['truth', *arms]}
        leave_month[str(m)] = {a: f['coefficients']['prior'] for a, f in fits.items()}
        leave_contrasts[str(m)] = {a: {k: v-fits[arms[0]]['coefficients'][k]
            for k, v in fits[a]['coefficients'].items() if k in ('prior', 'numeracy=low')}
            for a in arms[1:]}
    ncols = specs['all']['month_prior_P']['fits']['truth']['columns']
    return {'specifications': specs, 'leave_one_month_prior_coefficient': leave_month,
        'leave_one_month_vs_first_model_coefficient': leave_contrasts,
        'demographic_coefficient_reliability': {'n': len(rows), 'columns': ncols,
            'n_per_column': len(rows)/ncols,
            'small_sample_warning': len(rows) < 5*ncols,
            'use': 'Do not interpret the many-category coefficients in the 65-person-month same-input sample; retain as numerical diagnostics only.'},
        'interpretation': 'WLS with month fixed effects and demographic categories. Repeats averaged only for regression; months equal weight. Descriptive in-sample associations, no identified update gain, no p-values or causal claims. Prior measurement error, leverage and sparse groups remain.'}


def analyze_scope(cases):
    arms = list(cases[0]['arms']); months = sorted({r['month'] for r in cases}); repeats = sorted({r['repeat'] for r in cases})
    support = shared._common_person_months(cases, arms, repeats, 'q9')
    eligible = [r for r in cases if (r['month'], r['userid']) in support]
    assert all(shared.finite(r['real']['previous_q9_mean']) for r in eligible)
    groups = {}
    for name in ('prior_band', *FIELDS):
        key = lambda r: band(r['real']['previous_q9_mean']) if name == 'prior_band' else str(r['profile'].get(name))
        groups[name] = {v: summarize([r for r in eligible if key(r) == v], arms, months, repeats, minimum=8)
                       for v in sorted({key(r) for r in eligible})}
    # Truth-update groups are ex-post outcomes, never proposed as assignable P.
    groups['observed_truth_update'] = {}
    for label in ('down', 'stable', 'up'):
        def bucket(r):
            d = r['real']['q9_mean']-r['real']['previous_q9_mean']
            return 'up' if d > .5 else 'down' if d < -.5 else 'stable'
        groups['observed_truth_update'][label] = summarize([r for r in eligible if bucket(r) == label], arms, months, repeats, minimum=8)
    total = summarize(eligible, arms, months, repeats)
    monthly = {str(m): summarize([r for r in eligible if r['month'] == m], arms, [m], repeats) for m in months}
    return {'common_person_months': len(support), 'unique_respondents': len({r['userid'] for r in eligible}),
        'arms': arms, 'months': months, 'repeats': repeats, 'total': total, 'monthly': monthly,
        'groups': groups, 'regression': regression_report(eligible, arms),
        'limits': ['All groups and regressions are exploratory, conditional on these inspected months and common complete replies.',
                   'Group summaries average available month/repeat cells with n>=8; compare only within the same subgroup.',
                   'Age, numeracy, income and education overlap; subgroup patterns are not independent mechanisms.',
                   'Current truth update groups are outcome-selected; copy accuracy there is partly mechanical, not a targeting rule.']}


def run(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    files = [ROOT/f'outputs/{name}/cases_private.json' for name in
        ['sce_news_breadth_evaluation_20261019_v1', 'sce_procurement_qwen_evaluation_20261020_v2',
         'sce_qwen_migration_evaluation_20261019_v1']]
    old, new, migration = [json.loads(f.read_text()) for f in files]
    lookup = {(r['month'], r['userid'], r['repeat']): r for r in old}
    combined = []
    for r in new:
        p = lookup[r['month'], r['userid'], r['repeat']]
        if r['real'] != p['real'] or r['profile'] != p['profile'] or r['survey_weight'] != p['survey_weight']:
            raise ValueError('Old/new population, truth or weights differ')
        combined.append({**r, 'arms': {'deepseek_full': p['arms']['baseline'],
            'qwen_food_shared': r['arms']['shared_price'], 'qwen_food_matched': r['arms']['matched_role']}})
    same_input = [{**r, 'arms': {'deepseek_same': r['arms']['baseline'], 'qwen_same': r['arms']['qwen']}} for r in migration]
    result = {'status': 'completed_cached_conditional_diagnostic', 'new_api_calls': 0, 'new_density_fits': 0,
        'six_month_configuration_comparison': analyze_scope(combined),
        'three_month_same_prompt_model_comparison': analyze_scope(same_input),
        'source_sha256': {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in [*files, Path(__file__)]},
        'scope_limit': 'Six-month model and E/format changed together. Three-month same-prompt migration is small, incomplete, nonconcurrent and has original invalid-Q9 exclusions. Neither identifies a clean general model effect.'}
    out.mkdir();(out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return result
