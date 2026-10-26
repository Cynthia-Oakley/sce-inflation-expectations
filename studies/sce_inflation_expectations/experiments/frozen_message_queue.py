"""One-attempt queue for already frozen messages; no population or truth loading.

Reuse the established bounded cooldown policy, but never render or alter a prompt.
An intent is fsynced before sending. Unresolved intents consume scope and their
full fee reservation on manual continuation; they are never silently resent.
"""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

from .frozen_batch import dump, read_json, sha
from .monthly_main_background import atomic_json
from .monthly_main_resilient import POLICY, cooldown, recoverable, safe_sender
from .state_continuity_execution import reserve
from ..prior_belief_experiment import message_hash
from ..q9_normalization import response_point, response_view


def now():
    return datetime.now(timezone.utc).isoformat()


def lines(path):
    """A torn final crash line stays on disk, never mistaken for a valid record."""
    path = Path(path)
    if not path.exists():
        return []
    data = path.read_bytes().splitlines(keepends=True)
    rows = []
    for i, line in enumerate(data):
        if not line.endswith(b'\n'):
            if i != len(data) - 1:
                raise ValueError('Non-final incomplete ledger line')
            break
        rows.append(json.loads(line))
    return rows


def fields(row):
    raw = row.get('raw_response_text', '')
    accepted = not row.get('error') and row.get('finish_reason') == 'stop'
    q8 = response_point(raw) if accepted else None
    try:
        q9 = response_view(raw) if accepted else None
    except (ValueError, TypeError, KeyError):
        q9 = None
    return {'q8': q8 is not None, 'q9': q9 is not None}


def account(intents, replies):
    keys = [r['key'] for r in intents]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate dispatch: this queue never retries')
    answers = {r['key']: r for r in replies}
    if len(answers) != len(replies) or not set(answers) <= set(keys):
        raise ValueError('Duplicate or unregistered reply')
    reported = spent = 0.
    for intent in intents:
        row = answers.get(intent['key'], {})
        if row and row.get('prompt_sha256') != intent['prompt_sha256']:
            raise ValueError('Reply/intent prompt mismatch')
        fee = row.get('api_reported_cost_usd')
        valid = type(fee) in (int, float) and math.isfinite(fee) and fee >= 0
        reported += fee if valid else 0.
        spent += fee if valid else intent['reserved_usd']
    return {'attempts': len(intents), 'completed': len(replies),
            'usable': sum(all(fields(r).values()) for r in replies),
            'unresolved': len(intents) - len(replies),
            'reported_cost_usd': reported, 'spent_or_reserved_usd': spent,
            'unknown_fee_reservation_usd': spent - reported}


def archive(folder):
    intents, replies = [], []
    for segment in sorted(Path(folder).glob('round_*/segment_*')):
        manifest = segment/'manifest.json'
        if manifest.exists():
            for name,digest in read_json(manifest)['files_sha256'].items():
                target = (segment/name).resolve()
                if not target.is_relative_to(segment.resolve()) or sha(target) != digest:
                    raise ValueError('Immutable segment changed: '+str(target))
        intents.extend(lines(segment / 'dispatch_private.jsonl'))
        replies.extend(lines(segment / 'calls_private.jsonl'))
    account(intents, replies)
    return intents, replies


def execute_segment(p, slots, out, send, *, workers, max_workers, scale_after,
                    prior_intents=(), prior_replies=(), publish=lambda x: None, engineering_only=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    prior = account(prior_intents, prior_replies)
    registered = {s['key']: s for s in slots}
    if len(registered) != len(slots):
        raise ValueError('Unique frozen slots required')
    if {r['key'] for r in prior_intents} & set(registered):
        raise ValueError('Attempted or uncertain positions must not be resent')
    spent = prior['spent_or_reserved_usd']
    in_flight = 0.
    replies, intents = [], []
    halted = None
    peak = 0
    cursor = 0
    started = time.monotonic()

    def one(slot):
        row = {k: slot[k] for k in ('key', 'month', 'arm', 'repeat', 'agent_id', 'prompt_sha256')}
        row.update(error=None, fatal=False, raw_response_text='', finish_reason=None,
                   api_reported_cost_usd=None, request_reservation_usd=slot['reserved_usd'],
                   started_at_utc=now(), attempt_idx=0, actual_model_results=not engineering_only)
        try:
            row.update(send(slot['messages']))
            if row.get('returned_model') != p['model'] or row.get('returned_provider') != p['expected_provider']:
                row.update(error='Locked model/provider mismatch', fatal=True)
            fee = row.get('api_reported_cost_usd')
            if fee is not None and (type(fee) not in (int, float) or not math.isfinite(fee)
                                   or fee < 0 or fee > slot['reserved_usd'] + 1e-9):
                row.update(error='Invalid/excess reported charge', fatal=True)
        except Exception as exc:
            row.update(error=type(exc).__name__, error_http_status=getattr(exc, 'status_code', None), fatal=True)
        row.update(raw_response_sha256=hashlib.sha256(row['raw_response_text'].encode()).hexdigest(),
                   finished_at_utc=now())
        row['field_usable'] = fields(row)
        row['technical_usable'] = all(row['field_usable'].values())
        return row

    def write(stream, row):
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        # Durability before dispatch, also preserve each response immediately.
        import os
        os.fsync(stream.fileno())

    with ((out / 'dispatch_private.jsonl').open('x') as dispatch,
          (out / 'calls_private.jsonl').open('x') as log,
          ThreadPoolExecutor(max_workers=max_workers) as pool):
        active = {}
        while cursor < len(slots) or active:
            capacity = max_workers if len(replies) >= scale_after else workers
            while not halted and cursor < len(slots) and len(active) < capacity:
                slot = slots[cursor]
                if message_hash(slot['messages']) != slot['prompt_sha256']:
                    halted = 'Frozen prompt mismatch'
                    break
                if spent + in_flight + slot['reserved_usd'] > p['budget_cap_usd'] + 1e-12:
                    halted = 'Budget cap reached before dispatch'
                    break
                intent = {k: slot[k] for k in ('key', 'prompt_sha256', 'reserved_usd')}
                intent['at_utc'] = now()
                write(dispatch, intent)
                intents.append(intent)
                active[pool.submit(one, slot)] = slot
                in_flight += slot['reserved_usd']
                cursor += 1
                peak = max(peak, len(active))
            publish({'phase': 'generation', 'attempts': prior['attempts'] + len(intents),
                     'completed': prior['completed'] + len(replies), 'in_flight': len(active),
                     'usable': prior['usable'] + sum(r['technical_usable'] for r in replies),
                     'reported_cost_usd': prior['reported_cost_usd'] + sum(
                         r.get('api_reported_cost_usd') or 0 for r in replies
                         if type(r.get('api_reported_cost_usd')) in (int,float)
                         and math.isfinite(r['api_reported_cost_usd']) and r['api_reported_cost_usd'] >= 0),
                     'spent_or_reserved_usd': spent + in_flight, 'at_utc': now()})
            if not active:
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                slot = active.pop(future)
                row = future.result()
                write(log, row)
                replies.append(row)
                in_flight -= slot['reserved_usd']
                fee = row.get('api_reported_cost_usd')
                valid = type(fee) in (int, float) and math.isfinite(fee) and fee >= 0
                spent += fee if valid else slot['reserved_usd']
                if row.get('error'):
                    halted = halted or row['error']
                if spent + in_flight > p['budget_cap_usd'] + 1e-9:
                    halted = halted or 'Budget guard'
    result = account([*prior_intents, *intents], [*prior_replies, *replies])
    result.update(halt_reason=halted, peak_in_flight=peak, seconds=time.monotonic() - started,
                  new_attempts=len(intents), actual_model_results=not engineering_only,
                  status='completed' if cursor == len(slots) and not halted else 'stopped')
    dump(out / 'receipt.json', result)
    dump(out / 'manifest.json', {'files_sha256': {n: sha(out/n) for n in
         ('dispatch_private.jsonl', 'calls_private.jsonl', 'receipt.json')}})
    return result, intents, replies


def run_segments(p, slots, folder, round_dir, send, policy=POLICY, *,
                 cool=cooldown, publish=lambda x: None, engineering_only=False):
    """Only never-dispatched keys can enter a later segment or manual round."""
    folder, round_dir = Path(folder), Path(round_dir)
    sender = safe_sender(send)
    workers = min(8, policy['initial_workers'])
    total_cooling = recoveries = unhealthy = 0
    while True:
        intents, replies = archive(folder)
        attempted = {r['key'] for r in intents}
        pending = [s for s in slots if s['key'] not in attempted]
        initial = len(intents) < 32
        if initial:
            pending = pending[:32-len(intents)]
        elif len(intents) >= 32:
            first_keys = {r['key'] for r in intents[:32]}
            usable = sum(all(fields(r).values()) for r in replies if r['key'] in first_keys)
            gate = {'attempts': 32, 'usable': usable, 'minimum_usable': 31, 'passed': usable >= 31}
            atomic_json(folder/'technical_gate.json', gate)
            if not gate['passed']:
                return {'status': 'stopped', 'halt_reason': 'Technical format gate not passed', **account(intents, replies)}
        if not pending:
            return {'status': 'completed', 'halt_reason': None, **account(intents, replies)}
        segment = round_dir/f'segment_{len(list(round_dir.glob("segment_*")))+1:04d}'
        sender.retry_after_s = 0.
        receipt, new_intents, rows = execute_segment(p, pending, segment, sender,
            workers=8 if initial else workers, max_workers=8 if initial else policy['max_workers'],
            scale_after=policy['scale_up_after_completed'], prior_intents=intents,
            prior_replies=replies, publish=publish, engineering_only=engineering_only)
        if receipt['halt_reason'] is None:
            workers = policy['initial_workers']
            continue
        # A hard error anywhere in drained responses wins over transient errors.
        hard = [r for r in rows if r.get('error') and not recoverable(r, policy)]
        if hard or not rows or not any(r.get('error') for r in rows):
            return {**receipt, 'status': 'stopped'}
        if len(intents) + len(new_intents) == len(slots):
            return {**receipt, 'status': 'completed', 'halt_reason': None}
        healthy = sum(not r.get('error') for r in rows)
        if healthy >= policy['healthy_segment_min_successes'] and healthy/len(rows) >= policy['healthy_segment_min_ratio']:
            unhealthy = 0
        unhealthy += 1
        if unhealthy > policy['max_unhealthy_recoveries'] or recoveries >= policy['max_total_recoveries']:
            return {**receipt, 'status': 'stopped', 'halt_reason': 'Bounded recovery limit reached'}
        delay = max(policy['cooldown_seconds'][min(unhealthy-1, len(policy['cooldown_seconds'])-1)], sender.retry_after_s)
        if total_cooling + delay > policy['max_total_cooldown_seconds']:
            return {**receipt, 'status': 'stopped', 'halt_reason': 'Cooldown cap reached'}
        recoveries += 1
        total_cooling += delay
        workers = max(policy['min_workers'], receipt['peak_in_flight']//2)
        details = {'recovery_cycles': recoveries, 'workers': workers,
                   'total_cooldown_seconds': total_cooling, 'last_error': receipt['halt_reason']}
        cool(delay, folder/'scheduler_status.json', details)
