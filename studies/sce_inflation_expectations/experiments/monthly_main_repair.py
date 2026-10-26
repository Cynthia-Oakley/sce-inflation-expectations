"""One human-authorized extra attempt on failed fields; original run is immutable.

Selection uses transport/format flags only, never truth or fit errors. Raw calls
remain separate. A field-level overlay supplies one answer per original person
to the unchanged evaluator. Physical attempts and costs include both ledgers.
"""
from copy import deepcopy
from collections import Counter
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from . import monthly_main_resilient as robust
from .monthly_main_background import Progress, atomic_json
from .monthly_main_console import watch
from .state_continuity_execution import load_inputs, live_sender, reserve, verify, node_key
from .frozen_batch import ROOT, OFFICIAL, read_json, dump, sha
from ..state_continuity_runtime import render_messages
from ..prior_belief_experiment import message_hash

ENTRY = ROOT / 'scripts/run_sce_monthly_repair.py'


def records(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def failed_fields(row):
    """Only declared, unsuccessfully produced fields qualify for a single repair."""
    if row.get('error'):
        if row['error'] not in ('APIConnectionError', 'APITimeoutError', 'InternalServerError'):
            raise ValueError('Unexpected main-run error requires separate review')
        if row['error'] == 'InternalServerError' and row.get('error_http_status') != 502:
            raise ValueError('Unexpected server error status')
        return ['q8', 'q9']
    changed = row['state_after']['transition']['field_updated_from_model']
    return [field for field in ('q8', 'q9') if not changed[field]]


def budget(original, protocol, count):
    old = original['spent_or_reserved_usd']
    bound = count * reserve(protocol, protocol['max_prompt_bytes'])
    cap = math.ceil((bound + 1e-9) * 100) / 100
    if not math.isfinite(old) or old < 0 or old + cap > protocol['budget_cap_usd']:
        raise ValueError('Original total budget cannot cover this bounded repair')
    return dict(original_accounted_usd=old, original_reported_usd=original['reported_cost_usd'],
                original_total_cap_usd=protocol['budget_cap_usd'], repair_cap_usd=cap,
                repair_full_reservation_usd=bound,
                combined_max_accounted_usd=old + cap)


def prepare(parent, main, out):
    parent, main, out = [Path(v).resolve() for v in (parent, main, out)]
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored repair folder required')
    p, manifest = verify(parent)
    receipt = read_json(main / 'receipt.json'); cm = read_json(main / 'manifest.json')
    if (receipt['status'] != 'completed' or receipt['attempts'] != p['planned_calls']
            or not receipt['actual_model_results'] or cm['protocol_sha256'] != manifest['protocol_sha256']):
        raise ValueError('Complete original main run required')
    for name, digest in cm['files_sha256'].items():
        if sha(main / name) != digest:
            raise ValueError('Main ledger changed: ' + name)
    nodes = read_json(ROOT / p['preparation'] / 'state_dependencies_private.json')
    expected = {n['logical_reuse_key']: n for n in nodes}
    if len(expected) != len(nodes) or any(n['dependency'] is not None for n in nodes):
        raise ValueError('Repair supports independent single-position main nodes only')
    seen = set(); targets = {}; old_rows = {}
    for row in records(main / 'calls_private.jsonl'):
        key = row['reuse_key']
        if key in seen or key not in expected or row['nodes'] != [expected[key]]:
            raise ValueError('Duplicate or changed original request scope')
        seen.add(key); fields = failed_fields(row)
        if fields:
            targets[key] = dict(reuse_key=key, fields=fields, prompt_sha256=row['prompt_sha256'],
                                original_error=row.get('error'))
            old_rows[key] = row
    if seen != set(expected) or len(targets) != 361:
        raise ValueError('Expected exactly the 361 already reviewed technical failures')
    counts = Counter(tuple(t['fields']) for t in targets.values())
    if counts != {('q8', 'q9'): 351, ('q9',): 10}:
        raise ValueError('Reviewed field-repair scope changed')
    selected = [n for n in nodes if n['logical_reuse_key'] in targets]
    inputs = []
    for month in p['months']:
        subset = [n for n in selected if n['month'] == month]
        if not subset:
            continue
        loaded = load_inputs(ROOT / p['input_templates'], [month])
        for n in subset:
            triple = loaded[month, n['agent_id']]; old = old_rows[n['logical_reuse_key']]
            messages = render_messages(*triple[:2], month, triple[2])
            if (triple[1] != old['state_before'] or messages != old['messages']
                    or message_hash(messages) != old['prompt_sha256']):
                raise ValueError('Repair must replay the exact original input')
            inputs.append(dict(month=month, agent_id=n['agent_id'], values=triple))
    limits = budget(receipt, p, len(selected))
    execution = deepcopy(p)
    execution.update(planned_calls=len(selected), logical_positions=len(selected),
                     budget_cap_usd=limits['repair_cap_usd'],
                     technical_gate=dict(calls=1, minimum_usable=0),
                     technical_gate_note='Original format gate already passed; no new outcome-dependent gate.')
    policy = deepcopy(robust.POLICY)
    policy.update(initial_workers=16, max_workers=32, min_workers=4,
                  scale_up_after_completed=32, max_total_recoveries=10,
                  max_unhealthy_recoveries=3, max_total_cooldown_seconds=600)
    out.mkdir(parents=True, mode=0o700)
    dump(out / 'nodes_private.json', selected); dump(out / 'inputs_private.json', inputs)
    dump(out / 'targets_private.json', list(targets.values()))
    dump(out / 'execution_protocol.json', execution); dump(out / 'execution_policy.json', policy)
    plan = dict(version='manual_failed_fields_once_v1', parent=str(parent), original_main=str(main),
                protocol_sha256=manifest['protocol_sha256'], maximum_new_requests=len(selected),
                failed_requests=351, q9_only_repairs=10, **limits,
                estimated_new_cost_usd=receipt['reported_cost_usd'] / receipt['attempts'] * len(selected),
                selection='Transport/field-validity flags only; no truth, fit errors or scalar score failures.',
                merge='Replace only originally failed fields when the extra answer is valid; keep all good fields.',
                automatic_retries=0, maximum_additional_attempts_per_target=1,
                preserve_original_outputs=True, python=sys.executable)
    dump(out / 'plan.json', plan)
    prior_config = read_json(main.parent / 'supervisor/config.json')
    old_raw = main.parent / 'evaluation/raw_output_cases_private.json'
    dump(out / 'evaluation_config.json', dict(truth=prior_config['paths']['truth'],
         registry=prior_config['paths']['registry'], old_raw_cases=str(old_raw),
         old_raw_cases_sha256=sha(old_raw)))
    pin = {str(f.relative_to(ROOT)): sha(f) for f in
           (Path(__file__), ENTRY, Path(robust.__file__))}
    pin.update({str(f.relative_to(ROOT)): sha(f) for f in out.glob('*.json')})
    pin[str(main / 'manifest.json')] = sha(main / 'manifest.json')
    dump(out / 'manifest.json', dict(files_sha256=pin, new_api_calls=0))
    return dict(status='prepared_not_started', targets=len(selected), **limits, new_api_calls=0)


def checked(folder):
    folder = Path(folder).resolve(); plan = read_json(folder / 'plan.json')
    for name, digest in read_json(folder / 'manifest.json')['files_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('Frozen repair source changed: ' + name)
    _, original = verify(plan['parent'])
    if original['protocol_sha256'] != plan['protocol_sha256']:
        raise ValueError('Original scientific protocol changed')
    return plan


def overlay(position, reply, target):
    """Field-level union; never replace an original successful field."""
    result = deepcopy(position); state = result['state_after']; old = deepcopy(state)
    fresh = reply['state_after']; changed = fresh['transition']['field_updated_from_model']
    fields = [f for f in target['fields'] if changed[f] and reply.get('error') is None
              and reply.get('finish_reason') == 'stop']
    for field in fields:
        state['fields'][field] = deepcopy(fresh['fields'][field])
        state['transition']['field_updated_from_model'][field] = True
        state['transition']['field_retained_as_explicit_fallback'][field] = False
    if 'q9' in fields:
        for name in ('history_centers', 'comparison_reference_day', 'comparison_day_source'):
            state[name] = deepcopy(fresh[name])
        state['transition']['q9_proportional_normalization'] = fresh['transition']['q9_proportional_normalization']
    for field in ('q8', 'q9'):
        if field not in fields and state['fields'][field] != old['fields'][field]:
            raise ValueError('Repair changed an unselected field')
    result['manual_repair'] = dict(reuse_key=reply['reuse_key'], attempted_fields=target['fields'],
                                  accepted_fields=fields, original_response_error=position['response_error'],
                                  repair_response_error=reply.get('error'), raw_calls_in_separate_ledgers=True)
    if fields and all(state['transition']['field_updated_from_model'].values()):
        result.update(response_error=None, finish_reason='stop')
    return result


def materialize(folder):
    folder = Path(folder); plan = checked(folder); main = Path(plan['original_main'])
    repair = folder / 'calls'; rr = read_json(repair / 'receipt.json')
    if rr['status'] != 'completed' or not rr.get('actual_model_results'):
        raise ValueError('Only a completed actual repair can enter the production overlay')
    targets = {r['reuse_key']: r for r in read_json(folder / 'targets_private.json')}
    rows = {r['reuse_key']: r for r in records(repair / 'calls_private.jsonl')}
    if len(rows) != rr['attempts'] or not set(rows) <= set(targets):
        raise ValueError('Repair scope/duplicates mismatch')
    out = folder / 'combined'; out.mkdir()
    stats = Counter(dict(repaired_q8=0, repaired_q9=0, remaining_q8=0, remaining_q9=0,
                         technical_complete_positions=0))
    repaired_positions = set()
    with (out / 'positions_private.jsonl').open('x') as dst:
        seen = set()
        for pos in records(main / 'positions_private.jsonl'):
            key = pos['reuse_key']
            if node_key(pos) in seen:
                raise ValueError('Duplicate logical position')
            seen.add(node_key(pos))
            if key in rows:
                if pos['prompt_sha256'] != rows[key]['prompt_sha256']:
                    raise ValueError('Repair prompt mismatch')
                pos = overlay(pos, rows[key], targets[key]); repaired_positions.add(key)
                stats.update('repaired_' + f for f in pos['manual_repair']['accepted_fields'])
            updated = pos['state_after']['transition']['field_updated_from_model']
            stats['technical_complete_positions'] += all(updated.values())
            stats.update('remaining_' + f for f, ok in updated.items() if not ok)
            dst.write(json.dumps(pos, ensure_ascii=False, allow_nan=False) + '\n')
    original = read_json(main / 'receipt.json')
    if repaired_positions != set(rows) or len(seen) != original['logical_positions']:
        raise ValueError('Repair did not preserve the full unique roster')
    # These names remain raw-source ledgers, not a fabricated single fused reply.
    for src, name in ((main / 'calls_private.jsonl', 'calls_private.jsonl'),
                      (main / 'dispatch_private.jsonl', 'dispatch_private.jsonl'),
                      (repair / 'calls_private.jsonl', 'manual_repair_calls_private.jsonl')):
        os.link(src, out / name)
    receipt = dict(original, **stats,
                   view_type='field_overlay_of_original_main_and_one_manual_repair',
                   attempts_semantics='Original one-per-person logical records, for frozen evaluator compatibility; physical API attempts separately counted.',
                   original_api_attempts=original['attempts'], manual_repair_api_attempts=rr['attempts'],
                   physical_api_attempts=original['attempts'] + rr['attempts'],
                   reported_cost_usd=original['reported_cost_usd'] + rr['reported_cost_usd'],
                   spent_or_reserved_usd=original['spent_or_reserved_usd'] + rr['spent_or_reserved_usd'],
                   manual_repair_status=rr['status'], manual_repair_manifest_sha256=sha(repair / 'manifest.json'))
    if receipt['spent_or_reserved_usd'] > plan['original_total_cap_usd'] + 1e-9:
        raise ValueError('Cumulative original budget exceeded')
    dump(out / 'receipt.json', receipt)
    dump(out / 'manifest.json', dict(protocol_sha256=plan['protocol_sha256'],
         ledger_semantics='Original raw calls retained; separate repair raw calls; positions are an explicit field overlay.',
         files_sha256={f.name: sha(f) for f in out.iterdir() if f.is_file()},
         original_manifest_sha256=sha(main / 'manifest.json')))
    return receipt


def generate(folder):
    folder = Path(folder); plan = checked(folder)
    auth = read_json(folder / 'authorization.json')
    if (not auth.get('approved') or auth.get('plan_sha256') != sha(folder / 'plan.json')
            or auth.get('repair_cap_usd') != plan['repair_cap_usd']
            or auth.get('total_cap_usd') != plan['original_total_cap_usd']):
        raise ValueError('Manual repair authorization required')
    p = read_json(folder / 'execution_protocol.json'); nodes = read_json(folder / 'nodes_private.json')
    inputs = {(r['month'], r['agent_id']): r['values'] for r in read_json(folder / 'inputs_private.json')}
    expected = {t['prompt_sha256'] for t in read_json(folder / 'targets_private.json')}
    live = live_sender(p)
    def send(messages):
        if message_hash(messages) not in expected:
            raise ValueError('Attempt to send a changed repair prompt')
        return live(messages)
    rr = robust.execute_segments(p, nodes, inputs, [], folder / 'calls', send,
         read_json(folder / 'execution_policy.json'), emit=lambda s: print(s, flush=True))
    dump(folder / 'calls/manifest.json', dict(protocol_sha256=plan['protocol_sha256'],
         files_sha256={f.name: sha(f) for f in (folder / 'calls').glob('*.json*') if f.is_file()}))
    if rr['status'] != 'completed':
        return dict(status='repair_stopped_no_automatic_restart', receipt=rr)
    return dict(status='repair_attempts_complete', receipt=materialize(folder))


def evaluate(folder):
    """Separate offline process; reuse exact old fitted vectors, fit new ones only."""
    folder = Path(folder); plan = checked(folder)
    from ..evaluation import monthly_reconstruction as evaluation
    from ..evaluation.cognition import provenance
    config = read_json(folder / 'evaluation_config.json')
    old_raw = Path(config['old_raw_cases'])
    if sha(old_raw) != config['old_raw_cases_sha256']:
        raise ValueError('Frozen original score cache changed')
    old_summary = read_json(old_raw.parent / 'summary.json')
    if old_summary['scorer'] != provenance():
        raise ValueError('Original scorer no longer compatible')
    cached = {}
    for case in read_json(old_raw):
        for view in case['arms'].values():
            if len(view['q9_bins']) == 10:
                score = {k: v for k, v in view.items() if k not in ('point', 'q9_bins')}
                key = tuple(view['q9_bins'])
                if key in cached and cached[key] != score:
                    raise ValueError('Conflicting cached score for same vector')
                cached[key] = score
    evaluation.install_score_cache(cached)
    result = evaluation.evaluate(plan['parent'], folder / 'combined', config['truth'], folder / 'evaluation')
    dump(folder / 'evaluation/cache_reuse.json', dict(reused_frozen_vectors=len(cached), new_api_calls=0))
    return result


def pipeline(folder):
    folder = Path(folder); plan = checked(folder); config = read_json(folder / 'evaluation_config.json')
    commands = [[plan['python'], '-u', str(ENTRY), name, '--run-dir', str(folder)]
                for name in ('_generate', '_evaluate')]
    commands.append([plan['python'], '-u', str(ROOT / 'scripts/readout_sce_monthly_main.py'),
        '--package', plan['parent'], '--evaluation', str(folder / 'evaluation'),
        '--truth', config['truth'], '--registry', config['registry'], '--out', str(folder / 'readout')])
    for i, command in enumerate(commands):
        with (folder / f'phase_{i+1}.log').open('x') as log:
            proc = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if proc.returncode or (i == 0 and not (folder / 'combined/manifest.json').exists()):
            return dict(status='repair_phase_stopped', phase=i+1, exit_code=proc.returncode,
                        see_log=str(folder / f'phase_{i+1}.log'))
    return dict(status='repair_and_separate_evaluation_complete',
                receipt=read_json(folder / 'combined/receipt.json'))


def worker(folder):
    folder = Path(folder); plan = checked(folder); wake = None
    with (folder / 'worker_lock.json').open('x') as f:
        json.dump(dict(pid=os.getpid(), at_utc=robust.base.now()), f)
    try:
        if sys.platform == 'darwin':
            wake = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())])
        with (folder / 'pipeline.log').open('x') as log:
            child = subprocess.Popen([plan['python'], '-u', str(ENTRY), '_pipeline', '--run-dir', str(folder)],
                                     cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            empty = folder / 'empty_progress_source'; empty.mkdir(); old = Progress(empty); trackers = {}
            while True:
                code = child.poll(); v = robust.poll_segments(old, trackers, folder / 'calls')
                phase = ('aggregate_readout_written' if (folder / 'readout/summary.json').exists() else
                         'macro_readout' if (folder / 'evaluation/summary.json').exists() else
                         'micro_evaluation' if (folder / 'combined/manifest.json').exists() else
                         'generation_or_initial_validation')
                v.update(at_utc=robust.base.now(), phase=phase, planned_calls=plan['maximum_new_requests'],
                         new_attempts=v['completed'], old_accounted_usd=plan['original_accounted_usd'])
                atomic_json(folder / 'progress.json', v)
                if code is not None:
                    answer = (read_json(folder / 'pipeline_receipt.json') if (folder / 'pipeline_receipt.json').exists()
                              else dict(status='repair_worker_failed', exit_code=code))
                    atomic_json(folder / 'worker_receipt.json', answer)
                    return answer
                time.sleep(5)
    except Exception as exc:
        answer = dict(status='repair_worker_failed', error=type(exc).__name__,
                      see_log=str(folder / 'terminal_worker.log'))
        atomic_json(folder / 'worker_receipt.json', answer)
        raise
    finally:
        if wake is not None:
            wake.terminate()


def run(folder, confirm_one_time_repair=False):
    folder = Path(folder).resolve(); plan = checked(folder)
    if not confirm_one_time_repair:
        raise ValueError('Manual --confirm-one-time-repair required')
    if any((folder / f).exists() for f in ('launch_lock.json', 'worker_lock.json', 'calls')):
        raise ValueError('Already launched; use watch, never remove locks')
    from ..news_label_trial import dotenv_values
    if not (os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL / '.env').get('OPENROUTER_API_KEY')):
        raise ValueError('OpenRouter key unavailable; do not put credentials in the command')
    if not (folder / 'authorization.json').exists():
        dump(folder / 'authorization.json', dict(approved=True, human_confirmation=
             'User requested one additional attempt for 361 technical failures and manually invoked --confirm-one-time-repair.',
             plan_sha256=sha(folder / 'plan.json'), total_cap_usd=plan['original_total_cap_usd'],
             repair_cap_usd=plan['repair_cap_usd'], at_utc=robust.base.now()))
    with (folder / 'launch_lock.json').open('x') as f:
        json.dump(dict(at_utc=robust.base.now(), manual_start=True, automatic_restart=False), f)
    with (folder / 'terminal_worker.log').open('x') as log:
        child = subprocess.Popen([plan['python'], '-u', str(ENTRY), '_worker', '--run-dir', str(folder)],
             cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
             start_new_session=True, close_fds=True)
    print(f'后台PID {child.pid}；只补361个位置一次，16→32并发；补跑上限${plan["repair_cap_usd"]:.2f}，'
          f'累计仍不超过原${plan["original_total_cap_usd"]:.0f}。进度显示仅计本次补跑。', flush=True)
    return watch(folder)
