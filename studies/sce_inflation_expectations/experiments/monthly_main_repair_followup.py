"""Six-position follow-up adapter over the frozen first-repair workflow.

Only preparation, cumulative provenance and launch text differ. The prior queue,
field validator, field overlay, supervision and evaluation remain unchanged.
"""
from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

from . import monthly_main_repair as base
from .frozen_batch import ROOT, OFFICIAL, dump, read_json, sha
from ..state_continuity_runtime import render_messages
from ..prior_belief_experiment import message_hash

ENTRY = ROOT / 'scripts/run_sce_monthly_repair_followup.py'


def verify_files(folder):
    manifest = read_json(folder / 'manifest.json')
    for name, digest in manifest['files_sha256'].items():
        if sha(folder / name) != digest:
            raise ValueError('Previous answer archive changed: ' + name)


def prepare(previous, out):
    previous, out = Path(previous).resolve(), Path(out).resolve()
    old_plan = base.checked(previous); main = previous / 'combined'; verify_files(main)
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh private output required')
    targets = []
    for pos in base.records(main / 'positions_private.jsonl'):
        fields = [f for f, ok in pos['state_after']['transition']['field_updated_from_model'].items() if not ok]
        if fields:
            targets.append(dict(reuse_key=pos['reuse_key'], fields=fields,
                                prompt_sha256=pos['prompt_sha256']))
    if Counter(tuple(t['fields']) for t in targets) != {('q8', 'q9'): 3, ('q9',): 3}:
        raise ValueError('Expected the six reviewed residual positions only')
    by_key = {t['reuse_key']: t for t in targets}
    nodes = [n for n in read_json(previous / 'nodes_private.json') if n['logical_reuse_key'] in by_key]
    ids = {(n['month'], n['agent_id']): n['logical_reuse_key'] for n in nodes}
    inputs = [r for r in read_json(previous / 'inputs_private.json') if (r['month'], r['agent_id']) in ids]
    if len(nodes) != 6 or len(inputs) != 6:
        raise ValueError('Complete original inputs required')
    for row in inputs:
        template, state, context = row['values']; key = ids[row['month'], row['agent_id']]
        if message_hash(render_messages(template, state, row['month'], context)) != by_key[key]['prompt_sha256']:
            raise ValueError('Original prompt changed')
    p, _ = base.verify(old_plan['parent']); receipt = read_json(main / 'receipt.json')
    limits = base.budget(receipt, p, 6)
    p.update(planned_calls=6, logical_positions=6, budget_cap_usd=limits['repair_cap_usd'],
             technical_gate=dict(calls=1, minimum_usable=0))
    policy = read_json(previous / 'execution_policy.json')
    policy.update(initial_workers=2, max_workers=4, min_workers=1, scale_up_after_completed=2)
    out.mkdir(parents=True, mode=0o700)
    for name, data in (('nodes_private.json', nodes), ('inputs_private.json', inputs),
                       ('targets_private.json', targets), ('execution_protocol.json', p),
                       ('execution_policy.json', policy)):
        dump(out / name, data)
    plan = dict(version='six_residual_positions_once_v1', parent=old_plan['parent'],
        previous_repair=str(previous), original_main=str(main), protocol_sha256=old_plan['protocol_sha256'],
        maximum_new_requests=6, failed_requests=3, q9_only_repairs=3, **limits,
        estimated_new_cost_usd=receipt['reported_cost_usd'] / receipt['physical_api_attempts'] * 6,
        selection='Only remaining failed-field flags; no truth, loss or density-fit selection.',
        maximum_additional_attempts_per_target=1, automatic_retries=0,
        preserve_original_outputs=True, python=sys.executable)
    dump(out / 'plan.json', plan)
    config = read_json(previous / 'evaluation_config.json')
    old_raw = previous / 'evaluation/raw_output_cases_private.json'
    config.update(old_raw_cases=str(old_raw), old_raw_cases_sha256=sha(old_raw))
    dump(out / 'evaluation_config.json', config)
    files = [Path(__file__), ENTRY, Path(base.__file__), Path(base.robust.__file__), main / 'manifest.json']
    files += list(out.glob('*.json'))
    dump(out / 'manifest.json', dict(files_sha256={str(f.relative_to(ROOT)): sha(f) for f in files},
                                    new_api_calls=0))
    return dict(status='six_position_followup_prepared_not_started', targets=6, **limits, new_api_calls=0)


def materialize(folder):
    folder = Path(folder); plan = base.checked(folder); main = Path(plan['original_main'])
    verify_files(main)
    repair = folder / 'calls'; rr = read_json(repair / 'receipt.json')
    if rr['status'] != 'completed' or not rr.get('actual_model_results'):
        raise ValueError('Complete actual follow-up required')
    targets = {t['reuse_key']: t for t in read_json(folder / 'targets_private.json')}
    rows = {r['reuse_key']: r for r in base.records(repair / 'calls_private.jsonl')}
    if len(rows) != rr['attempts'] or set(rows) != set(targets):
        raise ValueError('Follow-up must cover exactly the selected keys once')
    out = folder / 'combined'; out.mkdir(); seen = set(); merged = set()
    counts = Counter(dict(repaired_q8=0, repaired_q9=0, remaining_q8=0, remaining_q9=0,
                          technical_complete_positions=0))
    with (out / 'positions_private.jsonl').open('x') as dst:
        for pos in base.records(main / 'positions_private.jsonl'):
            if base.node_key(pos) in seen:
                raise ValueError('Duplicate person-month')
            seen.add(base.node_key(pos)); key = pos['reuse_key']
            if key in rows:
                if pos['prompt_sha256'] != rows[key]['prompt_sha256']:
                    raise ValueError('Follow-up prompt changed')
                history = deepcopy(pos.get('manual_repair_history', []))
                if pos.get('manual_repair'):
                    history.append(deepcopy(pos['manual_repair']))
                pos = base.overlay(pos, rows[key], targets[key]); pos['manual_repair_history'] = history
                counts.update('repaired_' + f for f in pos['manual_repair']['accepted_fields']); merged.add(key)
            flags = pos['state_after']['transition']['field_updated_from_model']
            counts['technical_complete_positions'] += all(flags.values())
            counts.update('remaining_' + f for f, ok in flags.items() if not ok)
            dst.write(json.dumps(pos, ensure_ascii=False, allow_nan=False) + '\n')
    previous = read_json(main / 'receipt.json')
    if merged != set(rows) or len(seen) != previous['logical_positions']:
        raise ValueError('Full original roster must be preserved')
    # Keep both prior raw archives, and an explicit third raw ledger.
    for name in ('calls_private.jsonl', 'dispatch_private.jsonl', 'manual_repair_calls_private.jsonl'):
        os.link(main / name, out / name)
    os.link(repair / 'calls_private.jsonl', out / 'residual_repair_calls_private.jsonl')
    receipt = {**previous, **counts,
        'view_type': 'field_overlay_with_two_separate_manual_repair_rounds',
        'this_repair_q8': counts['repaired_q8'], 'this_repair_q9': counts['repaired_q9'],
        'repaired_q8': previous['repaired_q8'] + counts['repaired_q8'],
        'repaired_q9': previous['repaired_q9'] + counts['repaired_q9'],
        'manual_repair_api_attempts': previous['manual_repair_api_attempts'] + rr['attempts'],
        'physical_api_attempts': previous['physical_api_attempts'] + rr['attempts'],
        'last_manual_repair_api_attempts': rr['attempts'], 'last_manual_repair_receipt': rr,
        'reported_cost_usd': previous['reported_cost_usd'] + rr['reported_cost_usd'],
        'spent_or_reserved_usd': previous['spent_or_reserved_usd'] + rr['spent_or_reserved_usd'],
        'manual_repair_status': rr['status'], 'manual_repair_manifest_sha256': sha(repair / 'manifest.json')}
    if receipt['spent_or_reserved_usd'] > plan['original_total_cap_usd'] + 1e-9:
        raise ValueError('Original cumulative budget exceeded')
    dump(out / 'receipt.json', receipt)
    dump(out / 'manifest.json', dict(protocol_sha256=plan['protocol_sha256'],
        ledger_semantics='Original raw calls, first-repair raw calls, residual raw calls and explicit field-overlay positions.',
        original_manifest_sha256=sha(main / 'manifest.json'),
        files_sha256={f.name: sha(f) for f in out.iterdir() if f.is_file()}))
    return receipt


def bind_adapter():
    """New CLI process only: inject its entry/merger into existing orchestration.

    No old source file or old invocation is changed. Subprocesses use this new
    CLI and perform the same binding before calling the existing functions.
    """
    base.ENTRY = ENTRY
    base.materialize = materialize


def run(folder, confirm_six_position_repair=False):
    folder = Path(folder).resolve(); plan = base.checked(folder)
    if not confirm_six_position_repair or plan['maximum_new_requests'] != 6:
        raise ValueError('Manual --confirm-six-position-repair required')
    if any((folder / f).exists() for f in ('launch_lock.json', 'worker_lock.json', 'calls')):
        raise ValueError('Already launched; use watch, never delete locks')
    from ..news_label_trial import dotenv_values
    if not (os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL / '.env').get('OPENROUTER_API_KEY')):
        raise ValueError('OpenRouter key unavailable; do not put it in the command')
    with (folder / 'authorization.json').open('x') as stream:
        json.dump(dict(approved=True, human_confirmation=
            'User requested another attempt for the six residual technical failures and manually invoked --confirm-six-position-repair.',
            plan_sha256=sha(folder / 'plan.json'), repair_cap_usd=plan['repair_cap_usd'],
            total_cap_usd=plan['original_total_cap_usd'], at_utc=base.robust.base.now()), stream)
    with (folder / 'launch_lock.json').open('x') as stream:
        json.dump(dict(at_utc=base.robust.base.now(), automatic_restart=False), stream)
    with (folder / 'terminal_worker.log').open('x') as log:
        child = subprocess.Popen([plan['python'], '-u', str(ENTRY), '_worker', '--run-dir', str(folder)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True)
    print(f'后台PID {child.pid}；仅6个位置各补一次，保留已有成功字段；新增硬上限${plan["repair_cap_usd"]:.2f}，'
          f'仍在原${plan["original_total_cap_usd"]:.0f}累计预算内。', flush=True)
    return base.watch(folder)
