#!/usr/bin/env python3
"""Offline audit of identities, original payloads, retries and cumulative fees."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.model_counterfactual import guarded_payload
from studies.sce_inflation_expectations.annual_model_comparison import prior_annual_calls, validated_answer


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs', type=Path, required=True)
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    plan = json.loads((args.inputs / 'summary.json').read_text())
    state = json.loads((args.run / 'run_summary.json').read_text())
    assert state['status'] != 'running' and not (args.run / 'pending_request.json').exists()
    assert state['budget_cap_usd'] == .5 and state['new_deepseek_calls'] == 0
    assert sha(args.run / 'requests_prepared.jsonl') == plan['requests_sha256'] == state['requests_sha256']
    for rel, expected in plan['execution_code_sha256'].items():
        assert sha(args.run / 'source_snapshot' / Path(rel).name) == expected
    rows = {r['case_id']: r for r in (json.loads(s) for s in
            (args.inputs / 'requests_prepared.jsonl').read_text().splitlines())}
    calls = [json.loads(s) for s in (args.run / 'llm_calls.jsonl').read_text().splitlines()]
    spent, done, attempts, _, _ = prior_annual_calls(calls, state)
    assert all(n <= 2 for n in attempts.values()) and len(done) == state['valid_answers']
    assert math.isfinite(spent) and spent <= .5
    errors, valid_months, kinds = Counter(), Counter(), Counter()
    costs = Counter()
    for call in calls:
        row = rows[call['case_id']]
        assert call['month'] == row['month'] and call['requested_model'] == plan['model']
        payload = guarded_payload(row)
        assert hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest() == call['payload_sha256']
        fee = call['billing']['charged_or_reserved_usd']
        assert 0 <= fee <= call['request_cost_bound_usd'] + 1e-9
        kinds[call['billing']['kind']] += 1
        costs[call['billing']['kind']] += fee
        if call.get('error'):
            errors[call['error']] += 1
        if 'answer' in call:
            assert call['response']['provider'] == 'DeepInfra' and call['response']['model'] == plan['model']
            answer, error = validated_answer(call['response']['choices'][0]['message']['content'])
            assert not error and answer == call['answer']
            valid_months[str(row['month'])] += 1
    result = {'status': state['status'], 'real_attempts': len(calls), 'valid_unique_cases': len(done),
              'valid_cases_by_month': dict(sorted(valid_months.items())),
              'first_attempt_successes': sum(c['attempt'] == 1 and 'answer' in c for c in calls),
              'cases_with_second_attempt': sum(n == 2 for n in attempts.values()),
              'failures': dict(errors), 'billing_kind_counts': dict(kinds),
              'billing_by_kind_usd': dict(costs), 'spent_or_reserved_usd': spent,
              'cap_usd': .5, 'original_messages_and_generation_parameters_verified': True,
              'returned_model_and_provider_verified': True, 'no_duplicate_valid_cases': True,
              'new_deepseek_calls': 0, 'scoring_or_llm_calls_in_audit': 0,
              'artifact_sha256': {str(p.resolve().relative_to(ROOT)): sha(p) for p in
                                 [args.run / 'run_summary.json', args.run / 'llm_calls.jsonl',
                                  args.run / 'requests_prepared.jsonl', Path(__file__).resolve()]}}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
