#!/usr/bin/env python3
"""Prepare an outcome-blind, 20-person annual Qwen replay. Offline only."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = 'sce-local-openai-20261003T055121Z-1dc7cd15'
MODEL = 'qwen/qwen-2.5-72b-instruct'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    source = ROOT / 'outputs/local_runs' / RUN / 'llm_calls.jsonl'
    calls = [json.loads(s) for s in source.read_text().splitlines()]
    ids = sorted({r['agent_id'] for r in calls}, key=lambda value:
                 hashlib.sha256(f'reuse-seed42:{value}'.encode()).hexdigest())[:20]
    identity = {value: f'person_{i+1:02d}' for i, value in enumerate(ids)}
    selected = sorted([r for r in calls if r['agent_id'] in ids],
                      key=lambda r: (r['target_month'], identity[r['agent_id']]))
    assert len(selected) == 240 and len({(r['target_month'], r['agent_id']) for r in selected}) == 240
    requests, references = [], []
    for r in selected:
        assert r['prompt_version'] == 'sce-q8-q9-llm-en-v1' and r['temperature'] == .5
        assert r['max_tokens'] == 1024 and r['error'] is None
        assert hashlib.sha256(r['prompt_text'].encode()).hexdigest() == r['prompt_sha256']
        assert hashlib.sha256(r['raw_response_text'].encode()).hexdigest() == r['raw_response_sha256']
        messages = json.loads(r['prompt_text'])
        assert r['agent_id'] not in r['prompt_text']
        case = r['target_month'] + '_' + identity[r['agent_id']]
        row = {'case_id': case, 'month': int(r['target_month'].replace('-', '')),
               'destination': 'https://openrouter.ai/api/v1', 'route_candidate': 'deepinfra/fp8',
               'input_price_per_million': .36, 'output_price_per_million': .40,
               'payload': {'model': MODEL, 'messages': messages, 'temperature': .5,
                   'max_tokens': 1024, 'response_format': {'type': 'json_object'},
                   'provider': {'order': ['deepinfra/fp8'], 'allow_fallbacks': False,
                                'require_parameters': True}}}
        requests.append(row)
        references.append({'case_id': case, 'month': row['month'], 'panel_case': identity[r['agent_id']],
                           'source_agent_id': r['agent_id'], 'source_run_id': RUN,
                           'reference_response': r['raw_response_text'], 'prompt_sha256': r['prompt_sha256']})
    args.out.mkdir(parents=True, exist_ok=False)
    for name, rows in [('requests_prepared.jsonl', requests),
                       ('deepseek_reference_private.jsonl', references)]:
        (args.out / name).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    code = [Path(__file__).resolve(), ROOT / 'scripts/run_sce_reuse_probe.py',
            ROOT / 'studies/sce_inflation_expectations/model_counterfactual.py',
            ROOT / 'studies/sce_inflation_expectations/annual_model_comparison.py',
            ROOT / 'studies/sce_inflation_expectations/model.py']
    plan = {'status': 'offline prepared', 'source_run_id': RUN, 'model': MODEL,
            'persons': 20, 'months': list(range(202101, 202113)), 'target_answers': 240,
            'budget_cap_usd': .5, 'temperature': .5, 'prompt_version': 'sce-q8-q9-llm-en-v1',
            'max_attempts_per_case': 2, 'retry_protocol': 'identical original messages; no feedback',
            'source_sha256': {str(source.relative_to(ROOT)): sha(source)},
            'execution_code_sha256': {str(p.relative_to(ROOT)): sha(p) for p in code},
            'requests_sha256': sha(args.out / 'requests_prepared.jsonl'),
            'reference_sha256': sha(args.out / 'deepseek_reference_private.jsonl'),
            'scope': 'old P/E model sensitivity, not latest P/E or nationally representative simulation',
            'real_llm_calls': 0}
    (args.out / 'summary.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'out': str(args.out), 'planned_answers': 240, 'real_calls': 0}))


if __name__ == '__main__':
    main()
