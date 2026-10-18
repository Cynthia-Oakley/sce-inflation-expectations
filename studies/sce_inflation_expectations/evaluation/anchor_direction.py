"""Describe alignment with personal history versus common references.

No runtime, API, or density fits. These outcome-based diagnostics do not
identify information weights or a causal regression-to-the-mean mechanism.
"""
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from .response_gap_controls import (ROOT, FIELDS, load_pairs, design, regression,
                                    environment_summary, sha)
from .metrics import quantile
from .history_forward import metric_cells

SOURCE = ROOT / 'outputs/sce_reference_validation_evaluation_20261017_v1'
PREPARED = ROOT / 'outputs/sce_reference_validation_trial_20261017_v2'


def older_center(mean, n, previous):
    """Recover the older-only center; a single prior cannot supply it."""
    if mean is None or n < 2:
        return None
    return (float(mean)*n-previous)/(n-1)


def alignment(previous, outcome, personal, common, threshold=.5):
    """Disjoint directions only when both anchor gaps are meaningful/opposed."""
    a, b, d = personal-previous, common-previous, outcome-previous
    opposed = abs(a) > threshold and abs(b) > threshold and a*b < 0
    label = 'not_identifiable'
    if opposed:
        label = 'stable' if abs(d) <= threshold else ('personal_direction' if a*d > 0 else 'common_direction')
    return {'opposed': bool(opposed), 'label': label,
            'personal_distance_change_pp': abs(outcome-personal)-abs(previous-personal),
            'common_distance_change_pp': abs(outcome-common)-abs(previous-common)}


def weighted_summary(rows, reference, threshold, model_average=True):
    counts, values = defaultdict(int), defaultdict(list)
    totals = defaultdict(float)
    for r in rows:
        if r['older'] is None:
            counts['no_older_history'] += 1
            continue
        h, c, p, w = r['older'], r[reference], r['prior'], r['weight']
        a, b = h-p, c-p
        if abs(a) <= threshold or abs(b) <= threshold:
            group = 'near_either_anchor'
        else:
            group = 'opposed' if a*b < 0 else 'same_direction'
        counts[group] += 1
        totals[group] += w
        outcomes = [('truth', r['real'])]
        if model_average:
            outcomes += [('model', r['sim'])]
        else:
            outcomes += [('model', float(record['arms']['reference']['mean'])) for record in r['records']]
        for name, y in outcomes:
            weight = w/(2 if name == 'model' and not model_average else 1)
            v = alignment(p, y, h, c, threshold)
            values[group, name].append((weight, y-p, v))
    result = {'threshold_pp': threshold, 'n_person_months': len(rows), 'counts': dict(counts),
              'weighted_share_of_full_support': {k: v/sum(r['weight'] for r in rows) for k,v in totals.items()},
              'model_basis': 'mean_of_two_generations' if model_average else 'each_generation_then_average', 'groups': {}}
    for group in ('opposed', 'same_direction', 'near_either_anchor'):
        result['groups'][group] = {}
        for name in ('truth', 'model'):
            v = values.get((group, name), [])
            if not v:
                continue
            w = np.array([x[0] for x in v]); w /= w.sum()
            result['groups'][group][name] = {
                'average_absolute_update_pp': float(w@np.array([abs(x[1]) for x in v])),
                'personal_distance_change_pp': float(w@np.array([x[2]['personal_distance_change_pp'] for x in v])),
                'common_distance_change_pp': float(w@np.array([x[2]['common_distance_change_pp'] for x in v]))}
            if group == 'opposed':
                result['groups'][group][name]['direction_shares'] = {
                    label: float(w@np.array([x[2]['label'] == label for x in v]))
                    for label in ('stable', 'personal_direction', 'common_direction')}
    return result


def associations(rows):
    selected = [r for r in rows if r['older'] is not None]
    for r in selected:
        r['older_gap'] = r['older']-r['prior']
    x, names, _ = design(selected, ('prior', 'older_gap', 'history_n'), FIELDS)
    result = {}
    w = [r['weight'] for r in selected]
    for outcome in ('real', 'sim'):
        fit, _ = regression(x, [r[outcome] for r in selected], w, names)
        result[outcome] = {'n': len(selected), 'months': len({r['month'] for r in selected}),
                          'prior_and_history_common_level_slope': fit['coefficients']['prior'],
                          'older_only_slope_holding_prior_fixed': fit['coefficients']['older_gap'],
                          'rank': fit['rank'], 'columns': fit['columns']}
    base, _, _ = design(selected, ('prior',), ())
    gap = np.array([r['latest_cpi_yoy_pp']-r['prior'] for r in selected])
    fit = np.linalg.lstsq(base, gap, rcond=None)[0]
    result['cpi_gap_collinear_with_month_and_prior_max_error_pp'] = float(np.max(abs(base@fit-gap)))
    return result


def run(out):
    begin = perf_counter(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('A fresh ignored output directory is required')
    rows, archived, sources = load_pairs(SOURCE, PREPARED)
    months = sorted({r['month'] for r in rows})
    environments = environment_summary(PREPARED, months)
    cpi = {r['month']: r['stored_latest_signals']['cpi_yoy']['value'] for r in environments}
    for item in environments:
        if datetime.fromisoformat(item['stored_latest_signals']['cpi_yoy']['published_at']) > datetime.fromisoformat(item['target']['as_of']):
            raise ValueError('CPI was not published before the frozen cutoff')
        sources['environment_'+str(item['month'])] = item['source_sha256']
    past = {m: json.loads((PREPARED/str(m)/'past_private.json').read_text()) for m in months}
    for r in rows:
        state = past[r['month']][r['records'][0]['agent_id']]['state']
        r['older'] = older_center(state['anchor'], state['n_earlier_valid'], r['prior'])
        r['latest_cpi_yoy_pp'] = cpi[r['month']]
    for m in months:
        group = [r for r in rows if r['month'] == m]
        for r in group:
            others = [v for v in group if v['userid'] != r['userid']]
            r['other_model_center_pp'] = quantile([v['sim'] for v in others], [v['weight'] for v in others], .5)
    scored = []
    for r in rows:
        for record in r['records']:
            scored.append({'month': r['month'], 'repeat': record['repeat'], 'weight': r['weight'],
                           'truth': r['real'], 'prior': r['prior'], 'sim': record['arms']['reference']['mean']})
    original_metrics = {name: metric_cells(scored, np.array([r[name] for r in scored]))['summary']
                        for name in ('prior', 'sim')}
    result = {'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_api_calls': 0,
              'new_density_fits': 0, 'n_person_months': len(rows), 'months': months,
              'n_with_older_history': sum(r['older'] is not None for r in rows),
              'n_with_at_least_four_past_answers': sum(r['history_n'] >= 4 for r in rows),
              'original_same_support_scores': original_metrics,
              'reference_definitions': {
                  'latest_cpi_yoy_pp': 'Official latest eligible CPI: past inflation, not a year-ahead household forecast or rational target.',
                  'other_model_center_pp': 'Leave-one-person-out weighted median of averaged generated outcomes. Evaluation-only and mechanically outcome-related; not an exogenous news signal.',
                  'older': 'Exact frozen personal historical mean excluding t-1; never imputed for one-answer histories.'},
              'weighting': 'Original design-survey weights normalized within each month, then months equally weighted. Subgroup summaries condition on these weights, not an equal mean of subgroup-month cells.',
              'profiles': {}, 'associations': {}, 'sources_sha256': sources,
              'limitations': ['All twelve months inspected: exploratory, not independent validation.',
                'No news-reception or interpretation-type labels are measured for these SCE people.',
                'All alignment gaps share the prior; association and mathematical coupling are not causal update weights.',
                'CPI and SCE forecast horizons differ; model consensus is endogenous.',
                'Two-repeat average profiles do not replace official per-repeat MAE.',
                'No old prompts, populations, scorer, or simulation configuration changed.']}
    variants = {'all': rows, 'at_least_four_past_answers': [r for r in rows if r['history_n'] >= 4],
                'prior_between_zero_and_ten': [r for r in rows if 0 <= r['prior'] <= 10]}
    for variant, subset in variants.items():
        result['profiles'][variant] = {reference: weighted_summary(subset, reference, .5)
            for reference in ('latest_cpi_yoy_pp', 'other_model_center_pp')}
        result['associations'][variant] = associations(subset)
    result['threshold_sensitivity'] = {str(t): weighted_summary(rows, 'latest_cpi_yoy_pp', t)
                                       for t in (.25, 1.)}
    result['per_generation_sensitivity'] = weighted_summary(rows, 'latest_cpi_yoy_pp', .5, False)
    result['per_month'] = {str(m): weighted_summary([r for r in rows if r['month'] == m], 'latest_cpi_yoy_pp', .5)
                           for m in months}
    result['leave_one_year_out'] = {str(year): weighted_summary([r for r in rows if r['month']//100 != year], 'latest_cpi_yoy_pp', .5)
                                   for year in sorted({m//100 for m in months})}
    assert len(rows) == 2284
    assert abs(original_metrics['sim']['center_mae_pp']-.459191301053) < 1e-8
    assert abs(original_metrics['prior']['center_mae_pp']-.239480557278) < 1e-8
    assert max(v['cpi_gap_collinear_with_month_and_prior_max_error_pp'] for v in result['associations'].values()) < 1e-10
    result['elapsed_seconds'] = perf_counter()-begin
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'out': str(out), 'n': len(rows), 'older_history': result['n_with_older_history'],
                      'cpi_opposed': result['profiles']['all']['latest_cpi_yoy_pp']['counts'].get('opposed', 0),
                      'seconds': result['elapsed_seconds'], 'new_api_calls': 0}, ensure_ascii=False))
    return result
