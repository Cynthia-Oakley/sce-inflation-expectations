#!/usr/bin/env python3
"""Recompute explicitly exploratory response variation and past-only context, with no API."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.cognition import (
    ARMS, Q9_METRICS, _score_bins, _q9_cell_metrics, _common_person_months,
)


def main(evaluation, out):
    evaluation, out = evaluation.resolve(), out.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output required')
    rows = json.loads((evaluation / 'cases_private.json').read_text())
    summary = json.loads((evaluation / 'summary.json').read_text())
    months = sorted({r['month'] for r in rows})
    repeats = sorted({r['repeat'] for r in rows})
    if repeats != [1, 2] or len(months) != 4 or summary['evaluated_llm_calls'] != 576:
        raise ValueError('Requires the completed registered cognition pilot')
    variation = {}
    for a, b in [('question_answer', 'label_only'), ('faithful_paraphrase', 'label_only'),
                 ('faithful_paraphrase', 'question_answer')]:
        variation[a + '_vs_' + b] = {
            'mean_probability_tv_pct': float(np.mean([
                .5 * np.abs(np.array(r['arms'][a]['q9_bins']) - r['arms'][b]['q9_bins']).sum() for r in rows])),
            'mean_absolute_q9_mean_difference_pp': float(np.mean([
                abs(r['arms'][a]['mean'] - r['arms'][b]['mean']) for r in rows])),
        }
    people = defaultdict(dict)
    for r in rows:
        people[r['month'], r['userid']][r['repeat']] = r
    for arm in ARMS:
        variation['same_' + arm + '_repeat1_vs_repeat2'] = {
            'mean_probability_tv_pct': float(np.mean([
                .5 * np.abs(np.array(r[1]['arms'][arm]['q9_bins']) - r[2]['arms'][arm]['q9_bins']).sum()
                for r in people.values()])),
            'mean_absolute_q9_mean_difference_pp': float(np.mean([
                abs(r[1]['arms'][arm]['mean'] - r[2]['arms'][arm]['mean']) for r in people.values()])),
        }
    response = {'status': 'post_run_descriptive_only_not_preregistered_success_test',
        'n_person_months': len(people),
        'scope': 'All96 assigned person-months; all model outputs valid, human truth not needed. Equal month/repeat weighting. Cross-arm distance is not a causal estimate net of generation noise. No new API.',
        'metrics': variation}
    support = _common_person_months(rows, list(ARMS), repeats, 'q9')
    memo, cells = {}, []
    for r in rows:
        key = r['month'], r['userid']
        if key not in support:
            continue
        if key not in memo:
            memo[key] = _score_bins(r['real']['previous_q9_bins'])
        r['arms']['copy_previous'] = {**memo[key], 'q9_bins': r['real']['previous_q9_bins']}
    for month in months:
        for repeat in repeats:
            subset = [r for r in rows if r['month'] == month and r['repeat'] == repeat
                      and (r['month'], r['userid']) in support]
            cells.append({'month': month, 'repeat': repeat, **_q9_cell_metrics(subset, 'copy_previous')})
    aggregate = {k: float(np.mean([r[k] for r in cells])) for k in Q9_METRICS
                 if all(r[k] is not None for r in cells)}
    reference = {'status': 'descriptive_context_only_no_new_llm_or_primary_gate_change',
        'source_summary_sha256': hashlib.sha256((evaluation / 'summary.json').read_bytes()).hexdigest(),
        'reference': 'Copy each respondents observed previous Q9 ten-bin vector; past-only comparator, no new quiz or current E used',
        'support': 'Same92 Q9 common-support person-months as all three arms; same frozen scorer; equal month/repeat cells',
        'n_person_months': len(support), 'aggregate': aggregate, 'cells': cells}
    out.mkdir(parents=True)
    for name, value in [('response_variation_descriptive', response), ('past_only_reference', reference)]:
        (out / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    main(args.evaluation, args.out)
