#!/usr/bin/env python3
"""Budgeted exact-message annual questionnaire replay; offline unless confirmed.

This produces raw questionnaire logs, not full SocioVerse engine trajectories.
Core/Normal expansion and evaluation are separate offline stages.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from socioverse.external_events import _parse_dotenv
from studies.sce_inflation_expectations.model_counterfactual import billing, preflight, request_bound
from studies.sce_inflation_expectations.annual_model_comparison import (
    guarded_annual_payload, repair_messages, validated_answer, prior_annual_calls,
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, obj):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, default=ROOT / 'docs/sources/sce_annual_models_preparation_20261008.json')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--months', default=','.join(str(m) for m in range(202101, 202113)))
    parser.add_argument('--models', nargs='+', default=['deepseek-flash', 'qwen/qwen-2.5-72b-instruct',
        'meta-llama/llama-3.1-70b-instruct', 'meta-llama/llama-3.3-70b-instruct'])
    parser.add_argument('--confirm-spend', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--authorization-note')
    parser.add_argument('--dotenv', type=Path, default=ROOT.parent / 'socioverse2_repo/.env')
    args = parser.parse_args()
    plan = json.loads((args.inputs / 'summary.json').read_text())
    receipt = json.loads(args.receipt.read_text())
    if sha(args.inputs / 'requests_prepared.jsonl') != receipt['requests_sha256'] or sha(args.inputs / 'summary.json') != receipt['preparation_summary_sha256']:
        raise ValueError('annual preparation differs from pinned receipt')
    for rel, expected in plan['source_sha256'].items():
        if sha(ROOT / rel) != expected:
            raise ValueError('annual source changed')
    for rel, expected in plan['code_sha256'].items():
        if sha(ROOT / rel) != expected:
            raise ValueError('annual source code changed')
    for rel, expected in receipt['execution_code_sha256'].items():
        if sha(ROOT / rel) != expected:
            raise ValueError('execution code differs from reviewed receipt')
    months = set(map(int, args.months.split(',')))
    if not months or not months.issubset(range(202101, 202113)) or len(set(args.models)) != len(args.models) or not set(args.models).issubset(plan['models']):
        raise ValueError('unregistered annual window/models')
    rows = [json.loads(line) for line in (args.inputs / 'requests_prepared.jsonl').read_text().splitlines()]
    if len(rows) != 14400 or Counter(r['payload']['model'] for r in rows) != Counter({m: 3600 for m in plan['models']}):
        raise ValueError('incomplete annual input')
    for r in rows:
        guarded_annual_payload(r)
    chosen = [r for r in rows if r['month'] in months and r['payload']['model'] in args.models]
    print(json.dumps({'status': 'offline validated', 'planned_answers': len(chosen),
        'new_annual_cap_usd': 20., 'models': args.models, 'months': sorted(months)}, ensure_ascii=False), flush=True)
    if not args.confirm_spend:
        return
    if not args.authorization_note:
        raise ValueError('new annual destination/data/budget confirmation required')
    if args.out.exists() and not args.resume:
        raise ValueError('refuse overwrite; use prior logs for a separately pinned missing-case continuation')
    config = _parse_dotenv(args.dotenv) if args.dotenv.exists() else {}
    keys = {'https://openrouter.ai/api/v1': os.environ.get('OPENROUTER_API_KEY') or config.get('OPENROUTER_API_KEY'),
        'https://api.deepseek.com/v1': os.environ.get('SV_LLM_API_KEY') or config.get('SV_LLM_API_KEY')}
    destinations = {r['destination'] for r in chosen}
    if any(not keys.get(d) for d in destinations):
        raise ValueError('missing destination-specific API credential')
    # Never send a configured non-DeepSeek key to the official DeepSeek endpoint.
    if 'https://api.deepseek.com/v1' in destinations:
        configured_url = os.environ.get('SV_LLM_BASE_URL') or config.get('SV_LLM_BASE_URL')
        if configured_url and configured_url.rstrip('/') not in {'https://api.deepseek.com', 'https://api.deepseek.com/v1'}:
            raise ValueError('SV_LLM credential host cannot be established as DeepSeek')
    state = {'run_id': args.out.name, 'status': 'running', 'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'authorization': args.authorization_note, 'new_annual_cap_usd': 20., 'per_model_cap_usd': 8.,
        'spent_or_reserved_usd': 0., 'paid_attempts': 0, 'valid_answers': 0,
        'requests_sha256': plan['requests_sha256'], 'format_protocol': 'probability-total-feedback-v1; one retry',
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'models': {}, 'months': sorted(months), 'mode': 'stateless fixed P/E replay, not engine trajectory',
        'temperature': .5, 'prompt_version': plan['prompt_version'],
        'receipt_sha256': sha(args.receipt), 'selected_models': args.models}
    previous_calls = []
    if args.resume:
        if (args.out / 'pending_request.json').exists():
            raise ValueError('interrupted in-flight request requires billing audit before resume')
        prior = json.loads((args.out / 'run_summary.json').read_text())
        if any(prior.get(k) != state[k] for k in ['requests_sha256', 'receipt_sha256', 'months', 'selected_models', 'new_annual_cap_usd']):
            raise ValueError('resume changed frozen scope or receipt')
        for rel, expected in receipt['execution_code_sha256'].items():
            if sha(args.out / 'source_snapshot' / Path(rel).name) != expected:
                raise ValueError('resume execution snapshot changed')
        log = args.out / 'llm_calls.jsonl'
        previous_calls = [json.loads(s) for s in log.read_text().splitlines()] if log.exists() else []
        state = prior
        state.update(status='running', resumed_at_utc=datetime.now(timezone.utc).isoformat())
    else:
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / 'source_snapshot').mkdir()
        for rel in receipt['execution_code_sha256']:
            (args.out / 'source_snapshot' / Path(rel).name).write_bytes((ROOT / rel).read_bytes())
    spent, done, prior_attempts, costs, last_calls = prior_annual_calls(previous_calls, state)
    dump(args.out / 'run_summary.json', state)
    blocked = set()
    last_started = 0.
    with httpx.Client(timeout=90., follow_redirects=False) as client:
        for model in args.models:
            selected = [r for r in chosen if r['payload']['model'] == model]
            item = {'status': 'running', 'paid_attempts': sum(n for (m, _), n in prior_attempts.items() if m == model),
                'valid_answers': sum(m == model for m, _ in done), 'spent_or_reserved_usd': costs.get(model, 0.)}
            state['models'][model] = item
            if selected[0]['destination'].endswith('openrouter.ai/api/v1'):
                try:
                    directory = client.get(f'https://openrouter.ai/api/v1/models/{model}/endpoints')
                    directory.raise_for_status()
                    metadata = directory.json()
                    endpoint = preflight(selected[0], metadata, allow_degraded=True)
                    item['endpoint'] = {k: endpoint.get(k) for k in ['tag', 'status', 'pricing', 'uptime_last_30m', 'quantization']}
                    dump(args.out / (model.replace('/', '__') + '_directory.json'), metadata)
                except Exception as exc:
                    item.update(status='preflight_blocked', error=type(exc).__name__)
                    continue
            else:
                reviewed = receipt.get('deepseek_price_review', {})
                if reviewed.get('model') != 'deepseek-flash' or reviewed.get('peak_input_usd_per_million') != .30 or reviewed.get('peak_output_usd_per_million') != 1.20:
                    raise ValueError('DeepSeek current official price review missing')
                try:
                    directory = client.get('https://api.deepseek.com/models',
                        headers={'Authorization': 'Bearer ' + keys['https://api.deepseek.com/v1']})
                    directory.raise_for_status()
                    metadata = directory.json()
                    if 'deepseek-flash' not in {m.get('id') for m in metadata.get('data', [])}:
                        raise ValueError('requested DeepSeek alias not listed')
                    dump(args.out / 'deepseek_directory.json', metadata)
                except Exception as exc:
                    item.update(status='preflight_blocked', error=type(exc).__name__)
                    continue
            for index, row in enumerate(selected):
                case_key = (model, row['case_id'])
                if case_key in done or prior_attempts[case_key] >= 2:
                    continue
                payload = guarded_annual_payload(row)
                if payload.get('provider'):
                    payload['provider']['max_price'] = {'prompt': row['input_price_per_million'], 'completion': row['output_price_per_million']}
                protected_point = None
                if prior_attempts[case_key] == 1:
                    previous = last_calls[case_key]
                    content = ((previous.get('response') or {}).get('choices') or [{}])[0].get('message', {}).get('content')
                    if content and previous.get('http_status') == 200:
                        payload['messages'], protected_point = repair_messages(row['payload']['messages'], content)
                for attempt in range(prior_attempts[case_key] + 1, 3):
                    priced = {**row, 'payload': payload}
                    bound = request_bound(payload, row['input_price_per_million'], row['output_price_per_million'])
                    if state['spent_or_reserved_usd'] + bound > 20. or item['spent_or_reserved_usd'] + bound > 8.:
                        item['status'] = 'budget_stopped'
                        blocked.add(model)
                        break
                    delay = 3. - (time.monotonic() - last_started)
                    if delay > 0:
                        time.sleep(delay)
                    last_started = time.monotonic()
                    call = {'case_id': row['case_id'], 'month': row['month'], 'requested_model': model,
                        'attempt': attempt, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
                        'payload_sha256': hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                        'request_cost_bound_usd': bound, 'format_feedback_used': protected_point is not None}
                    response_data = {}
                    dump(args.out / 'pending_request.json', {**call, 'previous_spent_or_reserved_usd': state['spent_or_reserved_usd']})
                    try:
                        response = client.post(row['destination'] + '/chat/completions',
                            headers={'Authorization': 'Bearer ' + keys[row['destination']]}, json=payload)
                        call['http_status'] = response.status_code
                        if response.status_code != 200:
                            call['error'] = 'http_' + str(response.status_code)
                        else:
                            response_data = response.json()
                            call['response'] = response_data
                            if response_data.get('model') != model or (row.get('route_candidate') and response_data.get('provider') != 'DeepInfra'):
                                call['error'] = 'returned_identity_mismatch'
                            else:
                                raw = response_data['choices'][0]['message']['content']
                                answer, error = validated_answer(raw, protected_point)
                                if error:
                                    call['error'] = error
                                    if attempt == 1:
                                        payload['messages'], protected_point = repair_messages(row['payload']['messages'], raw)
                                else:
                                    call['answer'] = answer
                    except Exception as exc:
                        call['error'] = type(exc).__name__
                    call['billing'] = billing(response_data, priced, bound)
                    fee = call['billing']['charged_or_reserved_usd']
                    item['paid_attempts'] += 1
                    item['spent_or_reserved_usd'] += fee
                    state['paid_attempts'] += 1
                    state['spent_or_reserved_usd'] += fee
                    if 'answer' in call:
                        item['valid_answers'] += 1
                        state['valid_answers'] += 1
                    with (args.out / 'llm_calls.jsonl').open('a') as log:
                        log.write(json.dumps(call, ensure_ascii=False, allow_nan=False) + '\n')
                        log.flush()
                        os.fsync(log.fileno())
                    dump(args.out / 'run_summary.json', state)
                    (args.out / 'pending_request.json').unlink()
                    if call['billing']['uncertain'] or fee > bound + 1e-9 or call.get('http_status') != 200 or call.get('error') == 'returned_identity_mismatch':
                        item['status'] = 'audit_stopped'
                        blocked.add(model)
                        break
                    if 'answer' in call:
                        break
                if model in blocked:
                    break
                # Early gate uses only structure/identity/cost, never fit to truth.
                if index == 9 and item['valid_answers'] < 9:
                    item['status'] = 'format_probe_stopped'
                    break
                if (index + 1) % 25 == 0:
                    print(json.dumps({'model': model, 'processed': index + 1, 'valid': item['valid_answers'],
                        'spent_or_reserved_usd': state['spent_or_reserved_usd']}), flush=True)
            if item['status'] == 'running':
                item['status'] = 'complete' if item['valid_answers'] == len(selected) else 'finished_with_invalid_answers'
            dump(args.out / 'run_summary.json', state)
    state.update(status='finished', finished_at_utc=datetime.now(timezone.utc).isoformat())
    dump(args.out / 'run_summary.json', state)


if __name__ == '__main__':
    main()
