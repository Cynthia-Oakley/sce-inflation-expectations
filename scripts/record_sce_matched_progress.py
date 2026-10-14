#!/usr/bin/env python3
"""Describe existing stages on identical person-generation support; no API."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.expanded_state import metrics, sha, dump
from studies.sce_inflation_expectations.evaluation.behavior_comparison import finite

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'outputs/sce_expanded_state_trial_20261014_v3/development_cases_private.json'
NEW = ROOT / 'outputs/sce_information_update_evaluation_20261014_v1/cases_private.json'


def prepare(out):
    out = out.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'): raise ValueError('fresh ignored output required')
    old = {(r['month'], r['repeat'], r['agent_id']): r for r in json.loads(OLD.read_text())}
    cases = []
    for r in json.loads(NEW.read_text()):
        previous = old[r['month'], r['repeat'], r['agent_id']]
        if r['actual'] != previous['actual'] or r['previous'] != previous['previous']:
            raise ValueError('truth/prior changed across archived stages')
        row = dict(r)
        for name, source, key in [('no_personal_history', previous, 'new_signal'),
                                  ('past_answers_original', previous, 'self_update'),
                                  ('explicit_prior_start', r, 'reused_A'),
                                  ('time_index_candidate', r, 'dated_information')]:
            row[name] = source[key]
            for suffix in ['_iqr', '_zero_deflation', '_point']: row[name + suffix] = source.get(key + suffix)
        if r['common'] and all(finite(row[k]) for k in ['no_personal_history', 'past_answers_original', 'explicit_prior_start', 'time_index_candidate']):
            cases.append(row)
    results = {}
    for name in ['no_personal_history', 'past_answers_original', 'explicit_prior_start', 'time_index_candidate']:
        result = metrics(cases, name); result.pop('case_predictions'); results[name] = result
    summary = {'status': 'matched_archived_stage_description_not_causal_or_new_trial', 'new_api_calls': 0,
               'common_generation_rows': len(cases),
               'unique_person_months': len({(r['month'], r['userid']) for r in cases}),
               'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [OLD, NEW]},
               'results': results,
               'interpretation': 'Same selected development people and generation labels. Stages span separate real batches; later inputs add actual private prior/state and timing. Describes restoration, not separate identified causal effects or B recursive success.'}
    out.mkdir(parents=True); dump(out / 'summary.json', summary)
    print(json.dumps({'support': len(cases), 'unique_person_months': summary['unique_person_months'],
                      'stages': {k: {f: v['aggregate'][f] for f in ['sample_center_mae_pp', 'cross_section_w1_pp', 'delta_w1_pp', 'cross_person_iqr_pp']} for k, v in results.items()}}, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    prepare(p.parse_args().out)
