"""Prepare disjoint unattempted requests and an optional explicitly authorized retry.

No network or automatic retry. The original failed run and its uncertain fee
reservation stay unchanged. Both chunks share the original part's $0.25 cap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .news_exposure_demo import verify_sources
from .news_label_trial import guarded_payload, prior_call_chain

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def prepare(inputs, stopped_run, out):
    inputs, stopped_run, out = map(Path, (inputs, stopped_run, out))
    if out.exists() or not out.resolve().is_relative_to(ROOT / 'outputs'):
        raise ValueError('use a new ignored outputs directory')
    plan = json.loads((inputs / 'summary.json').read_text())
    verify_sources(plan)
    state = json.loads((stopped_run / 'state.json').read_text())
    requests_path = inputs / 'requests_prepared.jsonl'
    if state['input_request_file_sha256'] != sha(requests_path) or state['status'] != 'stopped_on_error':
        raise ValueError('stopped run must match original requests')
    requests = {r['batch_id']: r for r in map(json.loads, requests_path.read_text().splitlines())}
    calls = prior_call_chain(stopped_run)
    attempted = {call['batch_id'] for _, call in calls}
    if len(attempted) != len(calls) or len(calls) != state['batches_attempted']:
        raise ValueError('prior attempted call ledger differs')
    unknown = [call['batch_id'] for folder, call in calls
               if call.get('error_type') == 'IncompleteRead' and not (folder / f"response_{call['batch_id']:03d}.json").exists()]
    if len(unknown) != 1:
        raise ValueError('only the single documented response-less connection failure is supported')
    groups = {'unattempted': [n for n in requests if n not in attempted], 'retry_once_pending_approval': unknown}
    bound = sum(requests[n]['request_usd_reservation'] for ids in groups.values() for n in ids)
    if state['spent_or_reserved_upper_usd'] + bound > plan['proposed_budget_usd']:
        raise ValueError('combined completion chunks exceed original cumulative part cap')
    sources = dict(plan['source_sha256'])
    for path in (requests_path, inputs / 'summary.json', stopped_run / 'state.json', stopped_run / 'calls.jsonl', Path(__file__)):
        sources[str(path.resolve().relative_to(ROOT))] = sha(path)
    out.mkdir(parents=True)
    records = []
    for kind, ids in groups.items():
        folder = out / kind
        folder.mkdir()
        rows = [dict(requests[n], batch_id=i + 1, original_batch_id=n) for i, n in enumerate(ids)]
        for row in rows:
            guarded_payload(row)
        request_file = folder / 'requests_prepared.jsonl'
        request_file.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
        summary = {'status': 'offline_prepared', 'kind': kind,
                   'unique_articles_to_label': sum(len(r['article_ids']) for r in rows), 'batches': len(rows),
                   'request_file_sha256': sha(request_file), 'source_sha256': sources,
                   'system_prompt_sha256': plan['system_prompt_sha256'],
                   'preparation_module_sha256': plan['preparation_module_sha256'],
                   'proposed_budget_usd': .25, 'retry_policy': 'none',
                   'original_part_cumulative_cap_usd': .25,
                   'original_stopped_run': str(stopped_run.resolve().relative_to(ROOT)),
                   'prior_spent_or_reserved_upper_usd': state['spent_or_reserved_upper_usd'],
                   'both_completion_chunks_reservation_usd': bound,
                   'total_usd_reservation_no_retries': sum(r['request_usd_reservation'] for r in rows),
                   'requires_explicit_additional_retry_authorization': kind != 'unattempted'}
        dump(folder / 'summary.json', summary)
        records.append({'kind': kind, 'original_batch_ids': ids, 'articles': summary['unique_articles_to_label'],
                        'requests_sha256': sha(request_file), 'reservation_usd': summary['total_usd_reservation_no_retries']})
    result = {'chunks': records, 'original_part_cap_usd': .25,
              'max_combined_part_upper_usd': state['spent_or_reserved_upper_usd'] + bound,
              'original_unknown_charge_reservation_retained': True, 'new_api_calls': 0}
    dump(out / 'summary.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--stopped-run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.inputs, args.stopped_run, args.out), ensure_ascii=False))


if __name__ == '__main__':
    main()
