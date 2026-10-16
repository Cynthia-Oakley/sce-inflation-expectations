#!/usr/bin/env python3
"""Post-hoc Low-only cognition policy using frozen, independent household replies.

No new responses are generated, and no original reply is edited. Recompute the
whole sample's nonlinear quantiles after selecting one existing reply per person.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.cognition import (
    ARMS, _common_person_months, _q9_cell_metrics, _summarize_arm,
)
from studies.sce_inflation_expectations.evaluation.metrics import quantile, wasserstein1

MONTHS = (202004, 202105, 202111, 202203)
REPEATS = (1, 2)
POLICIES = ('label_only', 'question_answer', 'low_only_question_answer')
KEYS = ('q9_center_mae_pp', 'individual_density_mean_mae_pp', 'cross_section_w1_pp',
        'individual_density_iqr_mae_pp', 'delta_w1_pp', 'probability_tv_pct',
        'cross_person_iqr_pp', 'real_cross_person_iqr_pp')
INTERVAL_METRICS = ('q9_center_mae_pp', 'individual_density_mean_mae_pp', 'cross_section_w1_pp')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_low_only(rows):
    result = deepcopy(rows)
    for row in result:
        if row['numeracy'] not in ('High', 'Low'):
            raise ValueError('Known original High/Low classification required')
        choice = 'question_answer' if row['numeracy'] == 'Low' else 'label_only'
        row['arms']['low_only_question_answer'] = deepcopy(row['arms'][choice])
    return result


def contrasts_bootstrap(rows, support, draws=1000, seed=20261016):
    """Paired respondent clusters retain all months and both original generations."""
    if type(draws) is not int or draws < 1:
        raise ValueError('A positive integer bootstrap count is required')
    people = sorted({r['userid'] for r in rows if (r['month'], r['userid']) in support})
    index = {person: i for i, person in enumerate(people)}
    cells = []
    for month in MONTHS:
        for repeat in REPEATS:
            rs = [r for r in rows if r['month'] == month and r['repeat'] == repeat
                  and (month, r['userid']) in support]
            if not rs:
                raise ValueError('Every frozen month/repeat must have common support')
            cells.append((np.array([index[r['userid']] for r in rs]),
                np.array([r['real']['q9_mean'] for r in rs]),
                {a: np.array([r['arms'][a]['mean'] for r in rs]) for a in POLICIES}))
    rng = np.random.default_rng(seed)
    sampled = {baseline: {k: [] for k in INTERVAL_METRICS} for baseline in POLICIES[:2]}
    attempts = completed = 0
    while completed < draws and attempts < draws * 20:
        attempts += 1
        counts = np.bincount(rng.integers(0, len(people), len(people)), minlength=len(people))
        if any(counts[indices].sum() == 0 for indices, _, _ in cells):
            continue
        values = {a: {k: 0. for k in INTERVAL_METRICS} for a in POLICIES}
        for indices, truth, predictions in cells:
            weights = counts[indices].astype(float)
            real_median = quantile(truth, weights, .5)
            for a, pred in predictions.items():
                values[a]['q9_center_mae_pp'] += abs(quantile(pred, weights, .5) - real_median) / len(cells)
                values[a]['individual_density_mean_mae_pp'] += float(np.average(np.abs(pred-truth), weights=weights)) / len(cells)
                values[a]['cross_section_w1_pp'] += wasserstein1(pred, weights, truth, weights) / len(cells)
        for baseline, metrics in sampled.items():
            for key in metrics:
                metrics[key].append(values['low_only_question_answer'][key] - values[baseline][key])
        completed += 1
    if completed != draws:
        raise ValueError('Insufficient nonempty bootstrap draws')
    return {'seed': seed, 'draws': draws, 'empty_cell_draws': attempts-draws,
        'scope': 'Exploratory unadjusted paired person-cluster intervals conditional on the four selected development months; not independent validation.',
        'comparisons': {f'low_only_minus_{baseline}': {key: {
            'difference_interval_95_pp': np.quantile(values, [.025, .975]).astype(float).tolist()
        } for key, values in metrics.items()} for baseline, metrics in sampled.items()}}


def analyze(evaluation, out, draws=1000):
    evaluation, out = Path(evaluation).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output under outputs required')
    casepath = evaluation / 'cases_private.json'
    pinpath = ROOT / 'docs/workstreams/20261016_cognition/population_weights_sensitivity.json'
    frozenpath = ROOT / 'docs/workstreams/20261016_cognition/results_summary.json'
    pins, frozen = json.loads(pinpath.read_text()), json.loads(frozenpath.read_text())
    if sha(casepath) != pins['case_source_sha256']:
        raise ValueError('Original evaluated replies changed')
    if sha(evaluation/'summary.json') != sha(frozenpath):
        raise ValueError('Original aggregate evidence changed')
    original = json.loads(casepath.read_text())
    q9_support = _common_person_months(original, list(ARMS), list(REPEATS), 'q9')
    q8_support = _common_person_months(original, list(ARMS), list(REPEATS), 'q8')
    rows = select_low_only(original)
    assert len(q9_support) == 92 and len(q8_support) == 96
    assert all(r['arms'] == old['arms'] | {'low_only_question_answer': r['arms']['low_only_question_answer']}
               for r, old in zip(rows, original))
    summaries = {a: _summarize_arm(rows, a, list(MONTHS), list(REPEATS), q9_support, q8_support) for a in POLICIES}
    # Reproduce the two original policies before evaluating the new combination.
    for a in POLICIES[:2]:
        for key in KEYS:
            expected = frozen['arms'][a]['q9']['aggregate_equal_month_repeat_cells'][key]
            actual = summaries[a]['q9']['aggregate_equal_month_repeat_cells'][key]
            if abs(actual-expected) > 1e-10:
                raise ValueError('Original metric did not reproduce: ' + a + '/' + key)
    weighted = {scenario: {a: [] for a in POLICIES} for scenario in (
        'equal_selected_people', 'parent_inverse_inclusion_times_survey_weight',
        'full_sce_numeracy_margin_calibration')}
    for month in MONTHS:
        low_share = pins['full_sce_month_margins'][str(month)]['low_survey_weighted_share']
        target = {'Low': low_share, 'High': 1-low_share}
        for repeat in REPEATS:
            subset = [r for r in rows if r['month'] == month and r['repeat'] == repeat
                      and (month, r['userid']) in q9_support]
            weights = np.array([r['survey_weight'] for r in subset], float)
            groups = np.array([r['numeracy'] for r in subset])
            calibrated = weights.copy()
            for group in ('High', 'Low'):
                mask = groups == group
                if weights[mask].sum() <= 0:
                    raise ValueError('Group without positive supported mass')
                calibrated[mask] *= target[group] / weights[mask].sum()
            assert abs(calibrated.sum()-1) < 1e-12
            for a in POLICIES:
                for scenario, w in zip(weighted, (None, weights, calibrated)):
                    weighted[scenario][a].append({'month': month, 'repeat': repeat,
                        **_q9_cell_metrics(subset, a, w)})
    aggregate = {scenario: {a: {k: float(np.mean([c[k] for c in cells])) for k in KEYS}
                            for a, cells in policies.items()} for scenario, policies in weighted.items()}
    # Existing weighted results must also reproduce, with no new truth weighting.
    for scenario in aggregate:
        for a in POLICIES[:2]:
            for k in pins['aggregate'][scenario][a]:
                if abs(aggregate[scenario][a][k] - pins['aggregate'][scenario][a][k]) > 1e-10:
                    raise ValueError('Original weighted aggregation did not reproduce')
    intervals = contrasts_bootstrap(rows, q9_support, draws=draws)
    for baseline in POLICIES[:2]:
        for k in INTERVAL_METRICS:
            intervals['comparisons'][f'low_only_minus_{baseline}'][k]['point_difference_pp'] = (
                aggregate['equal_selected_people']['low_only_question_answer'][k]
                - aggregate['equal_selected_people'][baseline][k])
    counts = defaultdict(Counter)
    for r in rows:
        if r['repeat'] == 1:
            counts['assigned'][r['numeracy']] += 1
            if (r['month'],r['userid']) in q9_support:
                counts['q9_common'][r['numeracy']] += 1
    result = {'status': 'posthoc_user_proposed_low_only_policy_recombination_not_new_simulation',
        'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_api_calls': 0, 'new_api_cost_usd': 0,
        'policy': 'High: existing label_only reply; Low: existing question_answer reply. Selection depends only on the original numeracy label, not outcomes. No replies edited or averaged.',
        'months': list(MONTHS), 'n_per_month': 24, 'generation_repeats': [1,2],
        'counts': {k:dict(v) for k,v in counts.items()}, 'q9_common_person_months': len(q9_support),
        'q8_common_person_months': len(q8_support), 'arms': summaries,
        'weighting_aggregate': aggregate, 'weighting_cells': weighted, 'paired_bootstrap': intervals,
        'reproduced_original_equal_and_weighted_metrics': True,
        'source_sha256': {str(casepath.relative_to(ROOT)): sha(casepath), str(pinpath.relative_to(ROOT)): sha(pinpath),
            str(frozenpath.relative_to(ROOT)): sha(frozenpath), str(Path(__file__).relative_to(ROOT)): sha(__file__)},
        'limitations': ['Proposed after examining the same development results; effect estimates are exploratory and selected, not independent validation.',
            'Recombination applies because these frozen one-step household responses have no inter-household response interaction; it does not test a population-level interaction policy.',
            'All quantiles/distributions are recomputed from selected individual replies, not averages of subgroup medians.',
            'Low oversampled (10/24); weighting sensitivities match only High/Low margins and do not establish national representativeness.',
            'Current financial Q1 input was absent in all original cognition arms; no evidence for the joint finance-plus-selective-cognition effect.',
            'Model alias, prompt and uncertainty/answer scoring limitations are inherited from the original experiment.',
            'Exploratory unadjusted intervals across multiple metrics; no new success gate or default configuration change.']}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'out':str(out),'new_api_calls':0,'aggregate':aggregate,'paired_bootstrap':intervals},ensure_ascii=False,indent=2))
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation',type=Path,default=ROOT/'outputs/sce_cognition_evaluation_20261016_v1')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--draws',type=int,default=1000)
    args=p.parse_args()
    analyze(args.evaluation,args.out,args.draws)
