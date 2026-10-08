#!/usr/bin/env python3
"""Audit archived DeepSeek responses offline; never reads keys or calls APIs."""
import argparse
import collections
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    'sce-local-openai-20261003T055121Z-1dc7cd15',
    'sce-local-openai-20261005T092656Z-202105-8d2e3b2c',
    'sce-local-openai-20261005T092656Z-202106-e4f49f76',
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_run(run_id):
    folder = ROOT / 'outputs/local_runs' / run_id
    path = folder / 'llm_calls.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    manifest = json.loads((folder / 'run_manifest.json').read_text())
    months = collections.defaultdict(list)
    for row in rows:
        assert row.get('error') is None, 'Archived request failed'
        for field, hash_field in [('prompt_text', 'prompt_sha256'),
                                  ('raw_response_text', 'raw_response_sha256')]:
            assert hashlib.sha256(row[field].encode()).hexdigest() == row[hash_field]
        messages = json.loads(row['prompt_text'])
        assert row['agent_id'] not in json.dumps(messages), 'ID in API message'
        answer = json.loads(row['raw_response_text'])
        bins = answer['q9']
        assert set(bins) == {f'bin{i}' for i in range(1, 11)}
        assert all(math.isfinite(v) and 0 <= v <= 100 for v in bins.values())
        assert abs(sum(bins.values()) - 100) < 1e-7
        assert math.isfinite(answer['point_pct'])
        months[row['target_month']].append(row)
    result = {
        'run_id': run_id, 'response_rows': len(rows),
        'months': {month: len(group) for month, group in sorted(months.items())},
        'unique_persons': len({r['agent_id'] for r in rows}),
        'requested_models': sorted({r['requested_model'] for r in rows}),
        'returned_models': sorted({r['returned_model'] for r in rows}),
        'temperatures': sorted({r['temperature'] for r in rows}),
        'prompt_versions': sorted({r['prompt_version'] for r in rows}),
        'all_prompt_response_hashes_verified': True,
        'all_raw_q9_probabilities_valid': True,
        'source_hashes': {str(p.relative_to(ROOT)): digest(p) for p in
                          [path, folder / 'run_manifest.json']},
        'archived_cost': manifest.get('cost'),
    }
    if run_id == RUNS[0]:
        observations = [json.loads(line) for line in
                        (folder / 'observations.jsonl').read_text().splitlines()]
        result['signal_counts'] = sorted({len(o['observation']['macro_information']['signals'])
                                          for o in observations})
        # Check the actual rendered sentence; generic prior/previous keywords
        # missed "Last month" in the original 2026-10-08 audit.
        result['observations_with_prior_answer'] = sum(bool(
            o['observation']['local_physical'].get('prior_answer')) for o in observations)
        result['prompts_with_prior_language'] = sum(
            bool(re.search(r'Last month you gave a point estimate of', r['prompt_text'], re.I)) for r in rows)
        result['prior_language_detection'] = 'actual Last month questionnaire-memory sentence'
        result['as_of_by_month'] = {month: sorted({
            o['observation']['macro_information']['as_of'] for o in observations
            if o['observation']['macro_information']['target_month'] == month})
            for month in sorted(months)}
        # Outcome-blind stable sample; only aggregate costs leave local data.
        ids = sorted({r['agent_id'] for r in rows}, key=lambda value:
                     hashlib.sha256(f'reuse-seed42:{value}'.encode()).hexdigest())[:20]
        chosen = [r for r in rows if r['agent_id'] in ids]
        assert len(chosen) == 240
        input_tokens = sum(r['usage']['prompt_tokens'] for r in chosen)
        output_tokens = sum(r['usage']['completion_tokens'] for r in chosen)
        result['illustrative_qwen_only_replay'] = {
            'persons': 20, 'months': 12, 'new_calls': 240,
            'new_deepseek_calls': 0, 'sample_selection': 'stable SHA256 priority, seed label 42',
            'reference_input_tokens': input_tokens, 'reference_output_tokens': output_tokens,
            'price_basis': 'Previously verified DeepInfra Qwen72 input .36/output .40 per million',
            'cost_using_deepseek_usage_usd': (input_tokens * .36 + output_tokens * .40) / 1e6,
            'cost_if_input_tokens_1_5x_and_every_output_1024_usd':
                (input_tokens * 1.5 * .36 + 240 * 1024 * .40) / 1e6,
            'warning': 'Model tokenizers/output lengths differ; neither number is a bill or guarantee',
            'authorization': 'proposal only; no new budget or API execution authorized',
        }
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    result = {'audit_date': '2026-10-08', 'real_llm_calls_this_audit': 0,
              'runs': [audit_run(run_id) for run_id in RUNS],
              'annual_four_model_plan': 'suspended by user; $20 not authorized'}
    (args.out / 'summary.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'audited_response_rows': sum(r['response_rows'] for r in result['runs']),
                      'real_llm_calls': 0, 'out': str(args.out)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
