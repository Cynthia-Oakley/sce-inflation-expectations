#!/usr/bin/env python3
"""Compare completed wave trial to cached 2018 answers using existing metrics.

This is report orchestration, not a new scorer, simulator or fitted estimator.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
import json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.evaluation import cognition as metrics
from studies.sce_inflation_expectations.evaluation.frozen_trial import paired_intervals
from studies.sce_inflation_expectations.experiments.frozen_batch import read_json, dump, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--old-evaluation', type=Path, default=ROOT/'outputs/sce_psychological_state_evaluation_20261017_v1')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); out = args.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'): raise ValueError('Fresh local ignored output directory required')
    result = read_json(args.evaluation/'summary.json')
    if result['status'] != 'completed_frozen_block_evaluation': raise ValueError('Complete the real trial and evaluation first')
    protocol = result['protocol']; rows = read_json(args.evaluation/'cases_private.json')
    old = read_json(args.old_evaluation/'cases_private.json')
    index = {(r['month'], r['agent_id'], r['repeat']): r for r in old}
    if len(index) != len(old): raise ValueError('Duplicate archived case')
    cases = []
    for row in rows:
        previous = index[row['month'], row['agent_id'], row['repeat']]
        if (previous['userid'] != row['userid'] or previous['profile'] != row['profile'] or previous['real'] != row['real']
                or abs(previous['survey_weight']-row['survey_weight']) > 1e-12):
            raise ValueError('Old/new roster, weights or truth differ')
        r = deepcopy(row)
        r['arms'] = {'baseline': row['arms']['baseline'], 'old_matched': previous['arms']['matched_psychology'],
            'new_matched': row['arms']['matched_psychology'], 'new_permuted': row['arms']['permuted_psychology']}
        cases.append(r)
    arms = ['baseline', 'old_matched', 'new_matched', 'new_permuted']
    repeats, months = protocol['generation_repeats'], protocol['months']
    support9 = metrics._common_person_months(cases, arms, repeats, 'q9')
    support8 = metrics._common_person_months(cases, arms, repeats, 'q8')
    summary = {'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_api_calls': 0,
        'months': months, 'repeats': repeats, 'common_q9_person_months': len(support9), 'common_q8_person_months': len(support8),
        'arms': {a: metrics._summarize_arm(cases, a, months, repeats, support9, support8) for a in arms},
        'source_sha256': {str((folder/file).resolve().relative_to(ROOT)): sha(folder/file)
            for folder in (args.evaluation, args.old_evaluation) for file in ('summary.json', 'cases_private.json')},
        'old_to_new_paired_exploratory': paired_intervals(cases, ['old_matched', 'new_matched'], months, repeats, support9),
        'notes': ['Uses existing scored caches, no refitting Q9 or new calls.',
            'Old/new contrasts are cross-batch and include donor realization/model alias uncertainty, not a pure wave causal effect.',
            'All four arms and both generations use identical valid support and design-survey weights.',
            'The omitted 2020-03 wave is unchanged, not counted as a new mechanism validation month.']}
    out.mkdir(parents=True); dump(out/'summary.json', summary)
    print('Completed cached reference comparison; person-months', len(support9), 'new API 0')


if __name__ == '__main__': main()
