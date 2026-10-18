#!/usr/bin/env python3
"""Report all preregistered six-arm contrasts from already-scored answers.

No API or density fits. This adapter leaves the frozen shared executor and
scorer unchanged. Bootstrap uses household clusters, not separate generations.
"""
import argparse
from datetime import datetime
from pathlib import Path
from time import perf_counter
import sys

import numpy as np
from scipy.stats import wasserstein_distance

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.experiments.frozen_batch import read_json, dump, sha, verify
from studies.sce_inflation_expectations.evaluation.cognition import _common_person_months

METRICS = ('center_mae_pp', 'personal_mae_pp', 'w1_pp', 'delta_w1_pp')


def batch_quantile(x, w, q=.5):
    order = np.argsort(x, kind='stable')
    index = np.argmax(np.cumsum(w[:, order], axis=1) >= q*w.sum(axis=1)[:, None], axis=1)
    return np.asarray(x)[order[index]]


def batch_w1(x, y, w):
    grid = np.unique(np.concatenate((x, y)))
    if len(grid) == 1:
        return np.zeros(len(w))
    differences = ((np.asarray(x)[None, :] <= grid[:-1, None]).astype(float)
                   -(np.asarray(y)[None, :] <= grid[:-1, None]).astype(float))
    return np.abs(w@differences.T/w.sum(axis=1)[:, None])@np.diff(grid)


def cell_metrics(y, prior, p, w):
    w = np.asarray(w, float)[None, :]
    real_center, pred_center = batch_quantile(y, w)[0], batch_quantile(p, w)[0]
    delta, real_delta = p-prior, y-prior
    stable = np.abs(real_delta) <= .5
    moving = ~stable
    rate = lambda condition, eligible: float(np.average(condition[eligible], weights=w[0, eligible])) if eligible.any() else None
    return {'center_mae_pp': abs(pred_center-real_center), 'center_bias_pp': pred_center-real_center,
        'predicted_center_pp': pred_center, 'truth_center_pp': real_center,
        'personal_mae_pp': float(np.average(np.abs(p-y), weights=w[0])),
        'w1_pp': float(wasserstein_distance(p, y, w[0], w[0])),
        'delta_w1_pp': float(wasserstein_distance(delta, real_delta, w[0], w[0])),
        'across_person_iqr_pp': float((batch_quantile(p, w, .75)-batch_quantile(p, w, .25))[0]),
        'truth_across_person_iqr_pp': float((batch_quantile(y, w, .75)-batch_quantile(y, w, .25))[0]),
        'wrong_move_given_true_stable': rate(np.abs(delta) > .5, stable),
        'missed_move_given_true_moving': rate(np.abs(delta) <= .5, moving),
        'opposite_direction_given_true_moving': rate((delta*real_delta < 0)&(np.abs(delta) > .5), moving)}


def summarize(cells, arms):
    return {arm: {key: float(np.mean([c['arms'][arm][key] for c in cells if c['arms'][arm][key] is not None]))
        for key in cells[0]['arms'][arm]} for arm in arms}


def report(folder, evaluation, out):
    begin = perf_counter()
    folder, evaluation, out = map(lambda p: Path(p).resolve(), (folder, evaluation, out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('New ignored report directory required')
    manifest, protocol = verify(folder)
    scored = read_json(evaluation/'summary.json')
    if scored['protocol'] != protocol or len(protocol['arms']) != 6:
        raise ValueError('Matching completed six-arm evaluation required')
    cases = read_json(evaluation/'cases_private.json')
    support = _common_person_months(cases, protocol['arms'], protocol['generation_repeats'], 'q9')
    arms = ['carry', *protocol['arms']]
    cells, arrays, verified = [], [], 0
    for month in protocol['months']:
        for repeat in protocol['generation_repeats']:
            rows = [r for r in cases if r['month'] == month and r['repeat'] == repeat and (month, r['userid']) in support]
            if not rows:
                raise ValueError('Empty common-support cell')
            y = np.array([r['real']['q9_mean'] for r in rows])
            prior = np.array([r['real']['previous_q9_mean'] for r in rows])
            w = np.array([r['survey_weight'] for r in rows])
            predictions = {a: prior if a == 'carry' else np.array([r['arms'][a]['mean'] for r in rows]) for a in arms}
            cell = {'month': month, 'repeat': repeat, 'n': len(rows),
                'effective_n': float(w.sum()**2/(w@w)), 'maximum_weight_share': float(w.max()/w.sum()),
                'arms': {a: cell_metrics(y, prior, p, w) for a, p in predictions.items()}}
            for arm in protocol['arms']:
                original = next(c for c in scored['arms'][arm]['auxiliary_survey_weighted']['q9']['cells']
                                if c['month'] == month and c['repeat'] == repeat)
                for left, right in [('center_mae_pp', 'q9_center_mae_pp'), ('personal_mae_pp', 'individual_density_mean_mae_pp'), ('w1_pp', 'cross_section_w1_pp')]:
                    if abs(cell['arms'][arm][left]-original[right]) > 1e-8:
                        raise ValueError('Independent aggregation failed')
                    verified += 1
            cells.append(cell)
            arrays.append({'people': [r['userid'] for r in rows], 'y': y, 'prior': prior, 'w': w, 'p': predictions})
    aggregate = summarize(cells, arms)
    monthly = [{'month': month, 'n': next(c['n'] for c in cells if c['month'] == month),
                'arms': summarize([c for c in cells if c['month'] == month], arms)} for month in protocol['months']]
    people = sorted({uid for cell in arrays for uid in cell['people']})
    index = {uid: i for i, uid in enumerate(people)}
    rng = np.random.default_rng(20261028)
    draws = 1000
    counts = np.array([np.bincount(rng.integers(len(people), size=len(people)), minlength=len(people)) for _ in range(draws)])
    # One full-sample row followed by matched bootstrap rows; values and sorts
    # reused across all contrasts rather than rescoring or refitting densities.
    sample_scores = {arm: np.zeros((draws+1, len(METRICS))) for arm in arms}
    for cell in arrays:
        w = np.vstack((cell['w'], counts[:, [index[uid] for uid in cell['people']]]*cell['w']))
        if (w.sum(axis=1) == 0).any():
            raise ValueError('Bootstrap emptied a month; preserve rather than silently change draws')
        y, prior = cell['y'], cell['prior']
        truth_center = batch_quantile(y, w)
        for arm in arms:
            p = cell['p'][arm]
            val = np.column_stack((np.abs(batch_quantile(p, w)-truth_center),
                w@np.abs(p-y)/w.sum(axis=1), batch_w1(p, y, w), batch_w1(p-prior, y-prior, w)))
            sample_scores[arm] += val/len(arrays)
    for arm in arms:
        if not np.allclose(sample_scores[arm][0], [aggregate[arm][key] for key in METRICS], atol=1e-8):
            raise ValueError('Vectorized interval point estimate differs')
    contrasts = {}
    for base, alternative in protocol['prespecified_contrasts']:
        delta = sample_scores[alternative]-sample_scores[base]
        key = alternative+'_minus_'+base
        contrasts[key] = {'difference': dict(zip(METRICS, delta[0].tolist())),
            'person_cluster_interval95': dict(zip(METRICS, np.quantile(delta[1:], [.025, .975], axis=0).T.tolist()))}
    interactions = {}
    for n in (3, 20):
        effect = (sample_scores[f'news_{n}_reduced']-sample_scores[f'news_{n}_complete']
                  -(sample_scores['news_8_reduced']-sample_scores['baseline']))
        interactions[f'macro_visibility_at_{n}_minus_at_8'] = {
            'difference': dict(zip(METRICS, effect[0].tolist())),
            'person_cluster_interval95': dict(zip(METRICS, np.quantile(effect[1:], [.025, .975], axis=0).T.tolist()))}
    factor_effects = {}
    macro_effect = sum(sample_scores[f'news_{n}_reduced']-sample_scores['baseline' if n == 8 else f'news_{n}_complete'] for n in (3, 8, 20))/3
    marginal = {'reduced_minus_complete_equal_weight_three_news_levels': macro_effect}
    for n in (3, 20):
        marginal[f'news_{n}_minus_8_equal_weight_two_macro_modes'] = (
            sample_scores[f'news_{n}_complete']-sample_scores['baseline']
            +sample_scores[f'news_{n}_reduced']-sample_scores['news_8_reduced'])/2
    for name, effect in marginal.items():
        factor_effects[name] = {'difference': dict(zip(METRICS, effect[0].tolist())),
            'person_cluster_interval95': dict(zip(METRICS, np.quantile(effect[1:], [.025, .975], axis=0).T.tolist()))}
    screens = {}
    for arm in protocol['arms'][1:]:
        nonworse = sum(m['arms'][arm]['center_mae_pp'] <= m['arms']['baseline']['center_mae_pp'] for m in monthly)
        screens[arm] = {'monthly_center_nonworse': nonworse,
            'development_screen_passed': bool(not scored['accuracy_descriptive_only'] and nonworse >= 4
                and aggregate[arm]['center_mae_pp'] < aggregate['baseline']['center_mae_pp']
                and aggregate[arm]['w1_pp'] < aggregate['baseline']['w1_pp']),
            'leave_one_month_out_center_difference_vs_baseline': {str(m): float(np.mean([q['arms'][arm]['center_mae_pp']-q['arms']['baseline']['center_mae_pp']
                for q in monthly if q['month'] != m])) for m in protocol['months']}}
    groups = {}
    for feature in protocol['population_groups']:
        groups[feature] = {}
        for label in sorted({str(r['profile'].get(feature)) for r in cases}):
            group_cells = []
            for month in protocol['months']:
                for repeat in protocol['generation_repeats']:
                    rows = [r for r in cases if r['month'] == month and r['repeat'] == repeat and (month, r['userid']) in support
                            and str(r['profile'].get(feature)) == label]
                    if len(rows) < 3:
                        continue
                    y = np.array([r['real']['q9_mean'] for r in rows]); prior = np.array([r['real']['previous_q9_mean'] for r in rows]); w = np.array([r['survey_weight'] for r in rows])
                    group_cells.append({'month': month, 'repeat': repeat, 'n': len(rows), 'arms': {
                        a: cell_metrics(y, prior, prior if a == 'carry' else np.array([r['arms'][a]['mean'] for r in rows]), w) for a in arms}})
            if group_cells:
                groups[feature][label] = {'cells_used': len(group_cells), 'descriptive_only': True,
                    'weighted_metrics': summarize(group_cells, arms)}
    receipts, returned, temperatures = [], set(), set()
    for job in manifest['jobs']:
        path = ROOT/'outputs/local_runs'/job['run_id']
        receipt = read_json(path/'run_manifest.json')
        if receipt['status'] != 'completed' or receipt['cost']['call_count'] != protocol['n_per_month']:
            raise ValueError('Incomplete real job')
        receipts.append(receipt)
        for line in (path/'llm_calls.jsonl').read_text().splitlines():
            call = __import__('json').loads(line)
            returned.add(str(call.get('returned_model')))
            temperatures.add(call.get('temperature'))
    cost = sum(r['cost']['estimated_cost_usd'] for r in receipts)
    if cost > protocol['budget_cap_usd']:
        raise ValueError('Budget exceeded')
    start = min(r['started_at_utc'] for r in receipts); end = max(r['finished_at_utc'] for r in receipts)
    result = {'status': 'completed_six_arm_information_exposure_readout', 'protocol_sha256': manifest['protocol_sha256'],
        'new_api_calls_from_reporting': 0, 'new_q9_fits_from_reporting': 0, 'independent_numeric_checks': verified,
        'common_person_months': len(support), 'independent_people': len(people), 'weighted_metrics': aggregate,
        'weighted_monthly': monthly, 'weighted_cells': cells, 'prespecified_contrasts': contrasts, 'interactions': interactions,
        'factor_effects_design_level_equal_weight_not_population_frequency': factor_effects,
        'development_screens': screens, 'group_metrics': groups,
        'unweighted_metrics': {a: scored['arms'][a]['q9']['aggregate_equal_month_repeat_cells'] for a in protocol['arms']},
        'q8_weighted_metrics': {a: scored['arms'][a]['auxiliary_survey_weighted']['q8']['aggregate_equal_month_repeat_cells'] for a in protocol['arms']},
        'coverage': scored['coverage'], 'accuracy_descriptive_only': scored['accuracy_descriptive_only'],
        'planned_and_actual_calls': sum(r['cost']['call_count'] for r in receipts), 'estimated_cost_usd_not_bill': cost,
        'cap_usd': protocol['budget_cap_usd'], 'started_at_utc': start, 'finished_at_utc': end,
        'parallel_window_seconds': (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds(),
        'returned_model_ids': sorted(returned), 'request_temperatures': sorted(temperatures), 'automatic_retries': 0,
        'interval_scope': '1000 paired household-cluster draws, selected months fixed, unadjusted multiple contrasts; not time-generalization or confirmatory significance.',
        'automatic_upgrade': False, 'seconds': perf_counter()-begin,
        'source_sha256': {str((evaluation/n).relative_to(ROOT)): sha(evaluation/n) for n in ('summary.json', 'cases_private.json')}}
    out.mkdir(parents=True)
    dump(out/'summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True, type=Path)
    parser.add_argument('--evaluation', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = report(args.folder, args.evaluation, args.out)
    print({k: result[k] for k in ('common_person_months', 'weighted_metrics', 'development_screens', 'estimated_cost_usd_not_bill', 'seconds')})
