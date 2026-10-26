"""Explicitly authorized continuation of never-attempted state slots only."""
from copy import deepcopy
import json
from pathlib import Path

from .frozen_batch import ROOT, read_json, dump, sha
from .state_continuity_execution import verify, reserve, execute, live_sender, load_inputs


def prepare(parent, calls, out):
    parent, calls, out = map(lambda x: Path(x).resolve(), (parent, calls, out))
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'): raise ValueError('Fresh continuation package required')
    # The original queue implementation remains in its original source snapshot.
    # Only the new explicitly frozen package uses the continuation extension.
    oldp, oldm = verify(parent, allow_frozen_snapshot=True)
    cm = read_json(calls / 'manifest.json'); receipt = read_json(calls / 'receipt.json')
    if receipt['status'] != 'stopped_no_retry' or cm['protocol_sha256'] != oldm['protocol_sha256']:
        raise ValueError('Original stopped authorized batch required')
    for name, digest in cm['files_sha256'].items():
        if sha(calls / name) != digest: raise ValueError('Original ledger changed')
    if not read_json(calls / 'technical_gate.json')['passed']: raise ValueError('Existing technical gate must have passed')
    rows = [json.loads(s) for s in (calls / 'calls_private.jsonl').read_text().splitlines()]
    attempted = {r['reuse_key'] for r in rows}
    intents = [json.loads(s) for s in (calls / 'dispatch_private.jsonl').read_text().splitlines()]
    if len(intents) != len(rows) or {r['reuse_key'] for r in intents} != attempted:
        raise ValueError('Unresolved dispatch intents cannot be called never-attempted')
    nodes = read_json(ROOT / oldp['preparation'] / 'state_dependencies_private.json')
    allkeys = {n['logical_reuse_key'] for n in nodes}
    if len(attempted) != len(rows) or not attempted <= allkeys: raise ValueError('Unique old attempted keys required')
    pending = sorted(allkeys - attempted)
    if len(rows) != receipt['attempts'] or not pending: raise ValueError('Exact nonempty never-attempted scope required')
    accounted = sum(r['api_reported_cost_usd'] if r['api_reported_cost_usd'] is not None
                    else r['request_reservation_usd'] for r in rows)
    p = deepcopy(oldp)
    p.update(continuation_of=str(parent.relative_to(ROOT)), existing_calls=str(calls.relative_to(ROOT)),
             new_planned_calls=len(pending), existing_attempts=len(rows),
             already_spent_or_reserved_usd=accounted,
             concurrency_stages=[{'after_completed': 0, 'workers': 64}],
             continuation_policy='Keep ALL prior attempts including five failures. Send only never-attempted keys once; no retry or fallback. Same stop rules.',
             full_conservative_reservation_usd=accounted + len(pending) * reserve(p, p['max_prompt_bytes']))
    if p['full_conservative_reservation_usd'] > p['budget_cap_usd']: raise ValueError('Original total cap exceeded')
    evidence = dict(oldm['source_sha256'])
    changes = {}
    for name, previous in list(evidence.items()):
        current = sha(ROOT / name)
        if current != previous:
            changes[name] = {'original_sha256': previous, 'continuation_sha256': current}
            evidence[name] = current
    for file in [Path(__file__), ROOT / 'scripts/continue_sce_state_continuity.py']:
        evidence[str(file.relative_to(ROOT))] = sha(file)
    for file in [parent / 'protocol.json', parent / 'manifest.json', parent / 'authorization.json',
                 calls / 'manifest.json', calls / 'technical_gate.json', *[calls / n for n in cm['files_sha256']]]:
        evidence[str(file.relative_to(ROOT))] = sha(file)
    out.mkdir(parents=True); dump(out / 'protocol.json', p); dump(out / 'pending_keys_private.json', pending)
    evidence[str((out / 'pending_keys_private.json').relative_to(ROOT))] = sha(out / 'pending_keys_private.json')
    dump(out / 'manifest.json', dict(protocol_sha256=sha(out / 'protocol.json'), source_sha256=evidence,
         original_source_changes=changes, original_snapshot_retained=True, new_api_calls=0))
    for name in changes:
        dest = out / 'source_snapshot' / name; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / name).read_bytes())
    return dict(existing_attempts=len(rows), old_failures_not_retried=sum(bool(r['error']) for r in rows),
                new_never_attempted=len(pending), max_workers=64,
                combined_conservative_reservation_usd=p['full_conservative_reservation_usd'], budget_cap_usd=p['budget_cap_usd'])


def run(package, out, combined):
    package, out, combined = map(lambda x: Path(x).resolve(), (package, out, combined)); p, m = verify(package)
    auth = read_json(package / 'authorization.json')
    if not auth.get('approved') or auth['protocol_sha256'] != m['protocol_sha256']:
        raise ValueError('Explicit continuation authorization required')
    if any(f.exists() or not f.is_relative_to(ROOT / 'outputs') for f in (out, combined)):
        raise ValueError('Fresh continuation and combined output folders required')
    old = ROOT / p['existing_calls']
    rows = [json.loads(s) for s in (old / 'calls_private.jsonl').read_text().splitlines()]
    send = live_sender(p)
    with (package / 'execution_registration.json').open('x') as handle:
        json.dump({'new_output': str(out.relative_to(ROOT)), 'combined': str(combined.relative_to(ROOT))}, handle)
    nodes = read_json(ROOT / p['preparation'] / 'state_dependencies_private.json')
    inputs = load_inputs(ROOT / p['input_templates'], p['months'])
    receipt = execute(p, nodes, inputs, out, send, completed_calls=rows, emit=lambda s: print(s, flush=True))
    combined.mkdir(parents=True)
    for name in ('calls_private.jsonl', 'positions_private.jsonl', 'dispatch_private.jsonl'):
        (combined / name).write_bytes((old / name).read_bytes() + (out / name).read_bytes())
    total = {**receipt, 'attempts': len(rows) + receipt['attempts'],
             'completed_calls': len(rows) + receipt['completed_calls'], 'protocol_sha256': m['protocol_sha256'],
             'seconds': read_json(old / 'receipt.json')['seconds'] + receipt['seconds'],
             'continuation_new_attempts': receipt['attempts'], 'old_attempts_preserved': len(rows),
             'prior_peak_in_flight': read_json(old / 'receipt.json')['peak_in_flight'],
             'peak_in_flight': max(receipt['peak_in_flight'], read_json(old / 'receipt.json')['peak_in_flight'])}
    dump(combined / 'receipt.json', total)
    dump(combined / 'manifest.json', {'protocol_sha256': m['protocol_sha256'],
         'files_sha256': {n: sha(combined / n) for n in
            ('receipt.json', 'calls_private.jsonl', 'positions_private.jsonl', 'dispatch_private.jsonl')},
         'immutable_components': {str(f.relative_to(ROOT)): sha(f) for f in
            [old / 'calls_private.jsonl', old / 'positions_private.jsonl', out / 'calls_private.jsonl', out / 'positions_private.jsonl']}})
    return total
