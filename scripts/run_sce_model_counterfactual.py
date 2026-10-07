#!/usr/bin/env python3
"""Replay prepared model-only messages; default is offline validation, not spending.

Original study configurations and .env are never edited. Secret values never log.
Each real attempt persists immediately; no SDK retries or provider fallbacks.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.model import parse_sce_response, validate_sce_bins
from studies.sce_inflation_expectations.model_counterfactual import (
    billing, fits_budget, guarded_payload, preflight, request_bound,
)

BASE = 'https://openrouter.ai/api/v1'
MODELS = ['qwen/qwen-2.5-72b-instruct', 'meta-llama/llama-3.1-70b-instruct']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def credential(path):
    from socioverse.external_events import _parse_dotenv
    # Specifically OpenRouter: never send the default DeepSeek key to this host.
    key = os.environ.get('OPENROUTER_API_KEY')
    if not key and path.exists():
        key = _parse_dotenv(path).get('OPENROUTER_API_KEY')
    if not key:
        raise RuntimeError('OPENROUTER_API_KEY_missing')
    return key


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--dotenv', type=Path, default=ROOT.parent / 'socioverse2_repo/.env')
    ap.add_argument('--confirm-spend', action='store_true')
    ap.add_argument('--authorization-note', default=None,
                    help='record the human confirmation of data destination and the $0.50 cap')
    args = ap.parse_args()
    summary = json.loads((args.inputs / 'summary.json').read_text())
    rows = [json.loads(s) for s in (args.inputs / 'requests_prepared.jsonl').read_text().splitlines()]
    if len(rows) != 80 or Counter(r['payload']['model'] for r in rows) != Counter({m: 40 for m in MODELS}):
        raise ValueError('need prepared 40-per-model requests')
    for p, expected in summary['source_hashes'].items():
        if sha(ROOT / p) != expected:
            raise ValueError('reference source changed')
    # Compare against the committed preparation receipt, not a self-declared hash.
    receipt = json.loads((ROOT / 'docs/sources/sce_macro_population_model_status_20261007.json').read_text())
    expected = receipt['artifact_hashes']['outputs/sce_model_counterfactual_20261007/requests_prepared.jsonl']
    if sha(args.inputs / 'requests_prepared.jsonl') != expected:
        raise ValueError('prepared request bytes changed')
    for r in rows:
        guarded_payload(r)
    if not args.confirm_spend:
        print('OFFLINE: 80 request contracts and source hashes valid; no credential/network access.')
        return
    if not args.authorization_note:
        raise ValueError('explicit_data_destination_and_budget_authorization_record_required')

    key = credential(args.dotenv)
    args.out.mkdir(parents=True, exist_ok=False)
    state = {'status': 'running', 'run_id': args.out.name, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
             'total_cap_usd': .5, 'model_cap_usd': .25, 'total_charged_or_reserved_usd': 0.,
             'paid_attempts': 0, 'valid_answers': 0, 'models': {},
             'input_sha256': sha(args.inputs / 'requests_prepared.jsonl'),
             'prompt_version': summary['prompt_version'], 'temperature': .5, 'max_tokens': 1024,
             'mode': 'exact-message model probe; not a new full SocioVerse engine trajectory',
             'authorization': args.authorization_note,
             'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
             'git_dirty_diff_sha256': hashlib.sha256(subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT)).hexdigest(),
             'code_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__).resolve(), ROOT / 'studies/sce_inflation_expectations/model_counterfactual.py']}}
    write(args.out / 'run_summary.json', state)
    # Freeze only relevant sources/config. No secret files or true answers.
    (args.out / 'source_snapshot').mkdir()
    for p in [Path(__file__).resolve(), ROOT / 'studies/sce_inflation_expectations/model_counterfactual.py', ROOT / 'studies/sce_inflation_expectations/model.py']:
        (args.out / 'source_snapshot' / p.name).write_bytes(p.read_bytes())
    (args.out / 'requests_prepared.jsonl').write_bytes((args.inputs / 'requests_prepared.jsonl').read_bytes())
    with httpx.Client(timeout=60., follow_redirects=False) as client:
        for model in MODELS:
            selected = [r for r in rows if r['payload']['model'] == model]
            item = {'status': 'preflight', 'valid_answers': 0, 'attempts': 0, 'charged_or_reserved_usd': 0.}
            state['models'][model] = item
            try:
                metadata = client.get(f'{BASE}/models/{model}/endpoints')
                if metadata.status_code != 200:
                    raise ValueError('directory_http_' + str(metadata.status_code))
                directory = metadata.json()
                write(args.out / (model.split('/')[0] + '_endpoint_directory.json'),
                      {'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'data': directory['data']})
                endpoint = preflight(selected[0], directory)
                item['endpoint'] = {'tag': endpoint['tag'], 'status': endpoint['status'],
                                    'pricing': endpoint['pricing'], 'quantization': endpoint.get('quantization')}
            except Exception as exc:
                item.update(status='preflight_blocked', reason=str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
                write(args.out / 'run_summary.json', state)
                print(model, 'preflight blocked:', item['reason'], flush=True)
                continue

            item['status'] = 'running'
            stop = False
            for i, row in enumerate(selected):
                payload = guarded_payload(row)
                bound = request_bound(payload, row['input_price_per_million'], row['output_price_per_million'])
                for attempt in range(2):
                    if not fits_budget(state['total_charged_or_reserved_usd'], item['charged_or_reserved_usd'], bound):
                        item.update(status='budget_stopped', reason='conservative_next_request_reservation')
                        stop = True
                        break
                    record = {'case_id': row['case_id'], 'requested_model': model,
                              'route_requested': row['route_candidate'], 'attempt': attempt + 1,
                              'started_at_utc': datetime.now(timezone.utc).isoformat(),
                              'payload_sha256': hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                              'request_cost_bound_usd': bound}
                    t0 = time.perf_counter()
                    reply = {}
                    try:
                        response = client.post(f'{BASE}/chat/completions', headers={'Authorization': 'Bearer ' + key}, json=payload)
                        record['http_status'] = response.status_code
                        if response.status_code != 200:
                            # Error messages/headers may contain sensitive content: do not store them.
                            record['error'] = 'completion_http_' + str(response.status_code)
                        else:
                            reply = response.json()
                            record['response'] = reply
                    except Exception as exc:
                        record['error'] = type(exc).__name__
                    record['latency_ms'] = (time.perf_counter() - t0) * 1000
                    charge = billing(reply, row, bound)
                    record['billing'] = charge
                    state['paid_attempts'] += 1
                    item['attempts'] += 1
                    item['charged_or_reserved_usd'] += charge['charged_or_reserved_usd']
                    state['total_charged_or_reserved_usd'] += charge['charged_or_reserved_usd']
                    parsed = None
                    if not record.get('error'):
                        if reply.get('model') != model or reply.get('provider') != 'DeepInfra':
                            record['error'] = 'returned_model_or_provider_unverified'
                        else:
                            try:
                                content = reply['choices'][0]['message']['content']
                                parsed, error = parse_sce_response(content or '')
                                if not error and not math.isfinite(parsed['point_pct']):
                                    error = 'nonfinite_point'
                                if not error:
                                    valid, error, _ = validate_sce_bins(parsed['bins'])
                                if error:
                                    record['error'] = error
                                else:
                                    record['answer'] = parsed
                            except (KeyError, TypeError, IndexError):
                                record['error'] = 'missing_response_content'
                    if charge['uncertain'] or charge['charged_or_reserved_usd'] > bound + 1e-9 or record.get('error') in ['returned_model_or_provider_unverified'] or record.get('http_status') != 200:
                        item.update(status='audit_stopped', reason=record.get('error', 'cost_envelope_violation'))
                        stop = True
                    if not record.get('error'):
                        item['valid_answers'] += 1
                        state['valid_answers'] += 1
                    with (args.out / 'llm_calls.jsonl').open('a') as f:
                        f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
                        f.flush()
                        os.fsync(f.fileno())
                    write(args.out / 'run_summary.json', state)
                    if stop or not record.get('error'):
                        break
                if stop:
                    break
                if (i + 1) % 5 == 0 or i < 2:
                    print(model, f"valid {item['valid_answers']}/40", f"total ${state['total_charged_or_reserved_usd']:.5f}", flush=True)
                if i == 1 and item['valid_answers'] < 2:
                    item.update(status='probe_stopped', reason='first_two_frozen_cases_did_not_validate')
                    break
            if item['status'] == 'running':
                item['status'] = 'complete' if item['valid_answers'] == 40 else 'partial_invalid'
            write(args.out / 'run_summary.json', state)
    state['status'] = 'complete' if state['valid_answers'] == 80 else 'partial_or_blocked'
    state['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    write(args.out / 'run_summary.json', state)
    print('Summary:', args.out / 'run_summary.json', flush=True)


if __name__ == '__main__':
    main()
