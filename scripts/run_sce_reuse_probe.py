#!/usr/bin/env python3
"""One-model, $0.50 capped archived-message replay; defaults to no network."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.model_counterfactual import billing, guarded_payload, preflight, request_bound
from studies.sce_inflation_expectations.annual_model_comparison import prior_annual_calls, validated_answer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def load_inputs(folder, receipt):
    plan = json.loads((folder / 'summary.json').read_text())
    seal = json.loads(receipt.read_text())
    assert sha(folder / 'summary.json') == seal['summary_sha256']
    assert sha(folder / 'requests_prepared.jsonl') == seal['requests_sha256'] == plan['requests_sha256']
    for rel, expected in {**plan['source_sha256'], **plan['execution_code_sha256']}.items():
        assert sha(ROOT / rel) == expected, 'Pinned source changed'
    rows = [json.loads(s) for s in (folder / 'requests_prepared.jsonl').read_text().splitlines()]
    assert len(rows) == 240 and len({r['case_id'] for r in rows}) == 240
    assert plan['model'] == 'qwen/qwen-2.5-72b-instruct' and plan['budget_cap_usd'] == .5
    for row in rows:
        assert row['payload']['model'] == plan['model'] and row['route_candidate'] == 'deepinfra/fp8'
        assert row['destination'] == 'https://openrouter.ai/api/v1'
        assert row['input_price_per_million'] == .36 and row['output_price_per_million'] == .40
        guarded_payload(row)
    assert all(sum(r['month'] == month for r in rows) == 20 for month in range(202101, 202113))
    return plan, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs', type=Path, required=True)
    ap.add_argument('--receipt', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--confirm-spend', action='store_true')
    ap.add_argument('--authorization-note')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--dotenv', type=Path, default=ROOT.parent / 'socioverse2_repo/.env')
    args = ap.parse_args(argv)
    plan, rows = load_inputs(args.inputs, args.receipt)
    print(json.dumps({'status': 'offline validated', 'answers': 240, 'cap_usd': .5}), flush=True)
    if not args.confirm_spend:
        return
    if not args.authorization_note:
        raise ValueError('Human authorization record required')
    from socioverse.external_events import _parse_dotenv
    key = os.environ.get('OPENROUTER_API_KEY')
    if not key and args.dotenv.exists():
        key = _parse_dotenv(args.dotenv).get('OPENROUTER_API_KEY')
    if not key:
        raise ValueError('OPENROUTER_API_KEY missing')
    state = {'run_id': args.out.name, 'status': 'running', 'paid_attempts': 0, 'valid_answers': 0,
             'spent_or_reserved_usd': 0., 'budget_cap_usd': .5, 'new_deepseek_calls': 0,
             'started_at_utc': datetime.now(timezone.utc).isoformat(),
             'authorization': args.authorization_note, 'requests_sha256': plan['requests_sha256'],
             'receipt_sha256': sha(args.receipt), 'prompt_version': plan['prompt_version'],
             'temperature': .5, 'retry_protocol': plan['retry_protocol'],
             'source_run_id': plan['source_run_id'], 'mode': plan['scope']}
    old_calls = []
    if args.resume:
        if (args.out / 'pending_request.json').exists():
            raise ValueError('In-flight billing must be audited before resume')
        old = json.loads((args.out / 'run_summary.json').read_text())
        assert all(old[k] == state[k] for k in ['requests_sha256', 'receipt_sha256', 'budget_cap_usd'])
        old_calls = [json.loads(s) for s in (args.out / 'llm_calls.jsonl').read_text().splitlines()]
        state = old
        state.update(status='running', resumed_at_utc=datetime.now(timezone.utc).isoformat())
    else:
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / 'requests_prepared.jsonl').write_bytes((args.inputs / 'requests_prepared.jsonl').read_bytes())
        snapshot = args.out / 'source_snapshot'
        snapshot.mkdir()
        for rel in plan['execution_code_sha256']:
            (snapshot / Path(rel).name).write_bytes((ROOT / rel).read_bytes())
    _, done, attempts, _, _ = prior_annual_calls(old_calls, state)
    dump(args.out / 'run_summary.json', state)
    stopped = False
    last_started = 0.
    with httpx.Client(timeout=90., follow_redirects=False) as client:
        try:
            directory = client.get('https://openrouter.ai/api/v1/models/' + plan['model'] + '/endpoints')
            directory.raise_for_status()
            metadata = directory.json()
            endpoint = preflight(rows[0], metadata, allow_degraded=True)
            dump(args.out / 'endpoint_directory.json', metadata)
            state['endpoint'] = {k: endpoint.get(k) for k in ['tag', 'status', 'pricing', 'uptime_last_30m']}
        except Exception as exc:
            state.update(status='preflight_blocked', error=type(exc).__name__)
            dump(args.out / 'run_summary.json', state)
            return
        for i, row in enumerate(rows):
            pair = (plan['model'], row['case_id'])
            if pair in done:
                continue
            payload = guarded_payload(row)
            bound = request_bound(payload, row['input_price_per_million'], row['output_price_per_million'])
            for attempt in range(attempts[pair] + 1, 3):
                if state['spent_or_reserved_usd'] + bound > .5:
                    state['status'] = 'budget_stopped'
                    stopped = True
                    break
                delay = 3. - (time.monotonic() - last_started)
                if delay > 0:
                    time.sleep(delay)
                last_started = time.monotonic()
                record = {'case_id': row['case_id'], 'month': row['month'], 'attempt': attempt,
                          'requested_model': plan['model'], 'request_cost_bound_usd': bound,
                          'payload_sha256': hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                          'started_at_utc': datetime.now(timezone.utc).isoformat()}
                dump(args.out / 'pending_request.json', record)
                reply = {}
                try:
                    response = client.post(row['destination'] + '/chat/completions',
                        headers={'Authorization': 'Bearer ' + key}, json=payload)
                    record['http_status'] = response.status_code
                    if response.status_code != 200:
                        record['error'] = 'http_' + str(response.status_code)
                    else:
                        reply = response.json()
                        record['response'] = reply
                        if reply.get('model') != plan['model'] or reply.get('provider') != 'DeepInfra':
                            record['error'] = 'identity_mismatch'
                        else:
                            answer, error = validated_answer(reply['choices'][0]['message']['content'])
                            if error:
                                record['error'] = error
                            else:
                                record['answer'] = answer
                except Exception as exc:
                    record['error'] = type(exc).__name__
                record['billing'] = billing(reply, row, bound)
                fee = record['billing']['charged_or_reserved_usd']
                state['spent_or_reserved_usd'] += fee
                state['paid_attempts'] += 1
                if 'answer' in record:
                    done.add(pair)
                    state['valid_answers'] += 1
                with (args.out / 'llm_calls.jsonl').open('a') as log:
                    log.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
                    log.flush()
                    os.fsync(log.fileno())
                dump(args.out / 'run_summary.json', state)
                (args.out / 'pending_request.json').unlink()
                if record['billing']['uncertain'] or fee > bound + 1e-9 or record.get('http_status') != 200 or record.get('error') == 'identity_mismatch':
                    state['status'] = 'audit_stopped'
                    stopped = True
                    break
                if 'answer' in record:
                    break
            if stopped:
                break
            if i == 9 and state['valid_answers'] < 9:
                state['status'] = 'format_stopped'
                stopped = True
                break
            if (i + 1) % 20 == 0:
                print(json.dumps({'processed': i + 1, 'valid': state['valid_answers'],
                                  'cost_usd': state['spent_or_reserved_usd']}), flush=True)
    if not stopped:
        state['status'] = 'complete' if state['valid_answers'] == 240 else 'finished_with_missing'
    state['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    dump(args.out / 'run_summary.json', state)
    print(json.dumps({k: state[k] for k in ['status', 'paid_attempts', 'valid_answers', 'spent_or_reserved_usd']}), flush=True)


if __name__ == '__main__':
    main()
