"""Dependency scheduling over the existing SCEOpenAILLM, with no truth access.

Templates, sources and state rules are frozen before authorization. Month waves
are sequential; independent people/repeats within a wave run concurrently. A
failed field carries its explicitly logged input state, never a real refresh.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from threading import local
from time import perf_counter

from .frozen_batch import ROOT, OFFICIAL, dump, read_json, sha
from .state_continuity_dry_run import dry_run
from ..prior_belief_experiment import message_hash
from ..state_continuity_runtime import advance_state, render_messages


def node_key(node):
    return '|'.join(str(node[k]) for k in ('month', 'agent_id', 'repeat', 'arm'))


def load_inputs(prompts, months):
    inputs = {}
    for month in months:
        folder = Path(prompts) / str(month)
        templates = read_json(folder / 'templates_private.json')
        initial = read_json(folder / 'initial_states_private.json')
        contexts = read_json(folder / 'timing_context_private.json')
        if set(templates) != set(initial) or set(initial) != set(contexts):
            raise ValueError('Template/state/context roster mismatch')
        inputs.update({(str(month), aid): (v, initial[aid], contexts[aid])
                       for aid, v in templates.items()})
    return inputs


def reserve(p, byte_count):
    # UTF-8 bytes upper bound text tokens; +1024 covers message framing.
    return ((byte_count + 1024) * p['price_input_per_mtok']
            + p['max_tokens'] * p['price_output_per_mtok']) / 1e6


def prepare(preparation, prompts, core_check, out):
    preparation, prompts, core_check, out = map(lambda x: Path(x).resolve(),
                                               (preparation, prompts, core_check, out))
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored execution package required')
    s = read_json(prompts / 'summary.json')
    core = read_json(core_check / 'summary.json')
    nodes = read_json(preparation / 'state_dependencies_private.json')
    months = sorted({n['month'] for n in nodes})
    replay = dry_run(nodes, load_inputs(prompts, months))
    if core['official_engine_units'] != 12 or core['decisions'] != len(nodes):
        raise ValueError('Complete official Core checks required')
    provider = ROOT / 'data/raw/mcp_checks/2026-10-21_v32_fullperiod_free_v1/deepseek_v32_endpoints.json'
    p = dict(mechanism='state_continuity_v1', months=months, arms=['observed_history', 'simulated_history'],
             generation_repeats=[1, 2], planned_calls=replay['unique_request_slots'],
             randomness={'dispatch_seed': 20261022, 'input_assignments': 'frozen templates and donor/role records',
                         'generation_seed': None, 'note': 'Two independent stochastic calls; no claim of bitwise reproducibility.'},
             logical_positions=len(nodes), destination='https://openrouter.ai/api/v1',
             model='deepseek/deepseek-v3.2', route='siliconflow/fp8', expected_provider='SiliconFlow',
             temperature=.5, thinking='disabled', response_format='json_object', max_tokens=1024,
             timeout_s=120, retry_max=0, provider_fallback=False, budget_cap_usd=5.,
             price_input_per_mtok=.259, price_output_per_mtok=.8,
             max_prompt_chars=s['runtime_character_cap'], max_prompt_bytes=s['runtime_utf8_byte_cap'],
             technical_gate={'calls': 32, 'minimum_usable': 31},
             concurrency_stages=[{'after_completed': 0, 'workers': 32},
                                 {'after_completed': 32, 'workers': 64},
                                 {'after_completed': 128, 'workers': 128}],
             error_policy='No retry. Stop on HTTP errors/provider mismatch/budget violation or three consecutive connection/timeout failures; drain in-flight calls.',
             q9_postprocessing='proportional_nonnegative_v1',
             field_fallback='Invalid/non-stop/failed fields retain that arm/repeat input state, explicitly logged.',
             input_templates=str(prompts.relative_to(ROOT)), preparation=str(preparation.relative_to(ROOT)),
             core_check=str(core_check.relative_to(ROOT)), provider_metadata=str(provider.relative_to(ROOT)),
             evaluation_rules={'primary': 'fixed human-valid roster with explicit per-field input-state fallback',
                               'sensitivity': 'same actual valid-output support in both arms and both repeats',
                               'weights': 'current survey weight / marginal SRS inclusion probability; equal-person sensitivity',
                               'subgroups': ['survey_entry_status', 'core_entry_status', 'continuous_three_months'],
                               'metrics': 'Q9 group-center MAE/RMSE, person MAE, W1, delta W1, cross-person IQR; Q8 evaluated independently',
                               'baselines': 'retain assigned initial state for all; observed prior only where genuinely observed',
                               'limits': 'A-line short chain; 3 months cannot establish time-generalization; no automatic mechanism upgrade'},
             created_at_utc=datetime.now(timezone.utc).isoformat())
    p['request_extra_body'] = {'provider': {'order': [p['route']], 'allow_fallbacks': False,
         'require_parameters': True, 'max_price': {'prompt': .259, 'completion': .8}},
         'reasoning': {'enabled': False}}
    p['full_conservative_reservation_usd'] = p['planned_calls'] * reserve(p, p['max_prompt_bytes'])
    p['estimated_cost_usd'] = s['estimated_cost_usd']
    if p['planned_calls'] != 912 or p['full_conservative_reservation_usd'] > p['budget_cap_usd']:
        raise ValueError('Frozen call count/cap mismatch')
    evidence = {str((preparation / 'state_dependencies_private.json').relative_to(ROOT)):
                sha(preparation / 'state_dependencies_private.json'),
                str((core_check / 'summary.json').relative_to(ROOT)): sha(core_check / 'summary.json'),
                str(provider.relative_to(ROOT)): sha(provider), **s['source_sha256']}
    for file in prompts.rglob('*.json'):
        evidence[str(file.relative_to(ROOT))] = sha(file)
    # Pin the actual Core checks to the current sources, not just a receipt count.
    for file in (core_check / 'source_snapshot').rglob('*.py'):
        relative = file.relative_to(core_check / 'source_snapshot')
        if sha(ROOT / relative) != sha(file):
            raise ValueError('Core-checked source changed: ' + str(relative))
    code = [Path(__file__), Path(__file__).with_name('state_continuity_dry_run.py'),
            Path(__file__).with_name('state_continuity_inputs.py'),
            ROOT / 'studies/sce_inflation_expectations/state_continuity_runtime.py',
            ROOT / 'studies/sce_inflation_expectations/model.py',
            ROOT / 'studies/sce_inflation_expectations/model_counterfactual.py',
            ROOT / 'studies/sce_inflation_expectations/q9_normalization.py',
            ROOT / 'studies/sce_inflation_expectations/evaluation/state_continuity.py',
            ROOT / 'studies/sce_inflation_expectations/evaluation/cognition.py',
            ROOT / 'studies/sce_inflation_expectations/scoring/sce_q9_frozen.py',
            ROOT / 'scripts/run_sce_state_continuity.py', ROOT / 'scripts/evaluate_sce_state_continuity.py']
    evidence.update({str(f.relative_to(ROOT)): sha(f) for f in code})
    out.mkdir(parents=True)
    dump(out / 'protocol.json', p)
    dump(out / 'manifest.json', {'protocol_sha256': sha(out / 'protocol.json'), 'source_sha256': evidence,
                                 'new_api_calls': 0, 'truth_in_execution_inputs': False})
    for file in code:
        dest = out / 'source_snapshot' / file.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(file.read_bytes())
    return {k: p[k] for k in ('planned_calls', 'logical_positions', 'estimated_cost_usd',
                              'full_conservative_reservation_usd', 'budget_cap_usd')}


def verify(folder, *, allow_frozen_snapshot=False):
    folder = Path(folder).resolve(); p = read_json(folder / 'protocol.json'); m = read_json(folder / 'manifest.json')
    if sha(folder / 'protocol.json') != m['protocol_sha256']:
        raise ValueError('Protocol hash changed')
    for path, digest in m['source_sha256'].items():
        if sha(ROOT / path) != digest:
            snapshot = folder / 'source_snapshot' / path
            if not (allow_frozen_snapshot and Path(path).suffix == '.py' and snapshot.exists() and sha(snapshot) == digest):
                raise ValueError('Frozen source changed: ' + path)
    return p, m


def authorize(folder, confirmation):
    p, m = verify(folder)
    if not confirmation.strip(): raise ValueError('Explicit human confirmation required')
    auth = dict(approved=True, human_confirmation=confirmation, protocol_sha256=m['protocol_sha256'],
                planned_calls=p['planned_calls'], budget_cap_usd=p['budget_cap_usd'],
                destination=p['destination'], model=p['model'], route=p['route'],
                at_utc=datetime.now(timezone.utc).isoformat())
    with (Path(folder) / 'authorization.json').open('x') as handle:
        json.dump(auth, handle, ensure_ascii=False, indent=2); handle.write('\n')
    return {'authorization_recorded': True, 'new_api_calls': 0}


def concurrency(p, completed):
    return max((s['workers'] for s in p['concurrency_stages'] if completed >= s['after_completed']), default=1)


def execute(p, nodes, inputs, out, send, *, emit=lambda s: None, engineering_only=False, completed_calls=None):
    """Testable one-attempt queue; caller enforces authorization before live send."""
    out = Path(out)
    if out.exists(): raise ValueError('Fresh call output required; never restart a partial run')
    out.mkdir(parents=True)
    dump(out / 'execution_started.json', {'at_utc': datetime.now(timezone.utc).isoformat(),
          'maximum_requests': p['planned_calls'], 'automatic_retries': 0})
    grouped = defaultdict(list)
    for n in nodes: grouped[n['logical_reuse_key']].append(n)
    if len(grouped) != p['planned_calls'] or len({node_key(n) for n in nodes}) != len(nodes):
        raise ValueError('Unique scope mismatch')
    outputs = {}; count = attempted = 0; accounted = reported = reserved = 0.; consecutive = 0
    previous = {r['reuse_key']: r for r in (completed_calls or [])}
    if len(previous) != len(completed_calls or []) or not set(previous) <= set(grouped):
        raise ValueError('Unique already-attempted scope required')
    for key, row in previous.items():
        if {node_key(n) for n in row['nodes']} != {node_key(n) for n in grouped[key]}:
            raise ValueError('Prior logical aliases changed')
        for n in row['nodes']: outputs[node_key(n)] = row['state_after']
        fee = row.get('api_reported_cost_usd')
        accounted += fee if fee is not None else row['request_reservation_usd']
        reported += fee or 0.
    grouped = {k: v for k, v in grouped.items() if k not in previous}
    new_target = len(grouped)
    budget_mode = p.get('budget_mode', 'full_scope_reservation')
    if budget_mode not in ('full_scope_reservation', 'spent_plus_inflight_reservation'):
        raise ValueError('Unknown budget mode')
    remaining_bound = new_target * reserve(p, p['max_prompt_bytes'])
    if budget_mode == 'full_scope_reservation' and accounted + remaining_bound > p['budget_cap_usd']:
        raise ValueError('Combined existing/remaining reservation exceeds cap')
    halted = None; gate_checked = bool(previous); gate_rows = []; peak = 0; started = perf_counter()

    def one(slot):
        row = {k: v for k, v in slot.items() if k != 'nodes'}
        row.update(nodes=deepcopy(slot['nodes']), attempt_idx=0, error=None, fatal=False,
                   raw_response_text='', api_reported_cost_usd=None, finish_reason=None,
                   timestamp_utc=datetime.now(timezone.utc).isoformat())
        try:
            row.update(send(slot['messages']))
            if row.get('returned_model') != p['model'] or row.get('returned_provider') != p['expected_provider']:
                row.update(error='Locked model/provider mismatch', fatal=True)
            fee = row.get('api_reported_cost_usd')
            if fee is not None and (type(fee) not in (int, float) or not math.isfinite(fee)
                                   or fee < 0 or fee > slot['request_reservation_usd'] + 1e-9):
                row.update(error='Invalid/excess reported charge', fatal=True)
        except Exception as exc:
            # No exception body: SDK errors may echo credentials/request details.
            row.update(error=type(exc).__name__, error_http_status=getattr(exc, 'status_code', None),
                       fatal=type(exc).__name__ not in ('APIConnectionError', 'APITimeoutError'))
        accepted = row['error'] is None and row['finish_reason'] == 'stop'
        raw = row['raw_response_text'] if accepted else ''
        state = advance_state(slot['state_before'], raw, slot['month'], slot['as_of'])
        row.update(state_after=state, raw_response_sha256=hashlib.sha256(row['raw_response_text'].encode()).hexdigest(),
                   technical_usable=accepted and all(state['transition']['field_updated_from_model'].values()),
                   finished_at_utc=datetime.now(timezone.utc).isoformat())
        return row

    with ((out / 'calls_private.jsonl').open('x') as log,
          (out / 'dispatch_private.jsonl').open('x') as intents,
          (out / 'positions_private.jsonl').open('x') as positions,
          ThreadPoolExecutor(max_workers=max(s['workers'] for s in p['concurrency_stages'])) as pool):
        for month in p['months']:
            slots = []
            for key, aliases in grouped.items():
                n = aliases[0]
                if n['month'] != month: continue
                aid = n['agent_id']; template, initial, context = inputs[month, aid]
                def get_state(a):
                    dep = a['dependency']
                    return initial if dep is None else outputs[node_key(dep)]
                state = get_state(n); messages = render_messages(template, state, month, context)
                digest = message_hash(messages)
                if any(message_hash(render_messages(template, get_state(a), month, context)) != digest for a in aliases):
                    raise ValueError('Cannot share unequal initialization prompts')
                size = len(json.dumps(messages, ensure_ascii=False).encode())
                if size > p['max_prompt_bytes'] or len(messages[0]['content']) > p['max_prompt_chars']:
                    halted = 'Rendered prompt exceeds registered size cap'; break
                slots.append(dict(reuse_key=key, month=month, agent_id=aid, nodes=aliases, messages=messages,
                                  state_before=state, as_of=context['as_of'], prompt_sha256=digest,
                                  request_reservation_usd=reserve(p, size)))
            if halted: break
            slots.sort(key=lambda x: hashlib.sha256(('20261022|' + x['reuse_key']).encode()).hexdigest())
            cursor = 0; active = {}
            while cursor < len(slots) or active:
                gate_cap = p['technical_gate']['calls'] if not gate_checked else p['planned_calls']
                while not halted and cursor < len(slots) and attempted < gate_cap and len(active) < concurrency(p, count):
                    slot = slots[cursor]; bound = slot['request_reservation_usd']
                    if attempted >= p['planned_calls'] or accounted + reserved + bound > p['budget_cap_usd'] + 1e-12:
                        halted = 'Call/budget cap reached before dispatch'; break
                    # Log intent before submission; a crash leaves an uncertain billed attempt, never retried.
                    intents.write(json.dumps({'reuse_key': slot['reuse_key'], 'prompt_sha256': slot['prompt_sha256'],
                        'reserved_usd': bound, 'at_utc': datetime.now(timezone.utc).isoformat()}) + '\n'); intents.flush()
                    active[pool.submit(one, slot)] = slot
                    attempted += 1; cursor += 1; reserved += bound; peak = max(peak, len(active))
                if not active:
                    if not gate_checked and attempted == p['technical_gate']['calls']:
                        usable = sum(r['technical_usable'] for r in gate_rows)
                        gate_checked = True
                        passed = usable >= p['technical_gate']['minimum_usable'] and not halted
                        dump(out / 'technical_gate.json', dict(attempted=attempted, usable=usable, passed=passed,
                                                               outcome_truth_read=False))
                        if not passed: halted = 'Technical format gate not passed'
                        emit(f'Technical gate {usable}/{attempted}: ' + ('passed' if passed else 'stopped'))
                        if not halted: continue
                    break
                done, _ = wait(active, return_when=FIRST_COMPLETED)
                for future in done:
                    slot = active.pop(future); row = future.result(); count += 1
                    reserved -= slot['request_reservation_usd']
                    fee = row.get('api_reported_cost_usd')
                    valid_fee = type(fee) in (int, float) and math.isfinite(fee) and fee >= 0
                    accounted += fee if valid_fee else slot['request_reservation_usd']
                    reported += fee if valid_fee else 0.
                    consecutive = consecutive + 1 if row['error'] else 0
                    if row['fatal'] or consecutive >= 3 or accounted + reserved > p['budget_cap_usd'] + 1e-9:
                        halted = halted or row['error'] or 'Budget guard'
                    if not gate_checked: gate_rows.append(row)
                    log.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n'); log.flush()
                    for n in slot['nodes']:
                        outputs[node_key(n)] = row['state_after']
                        position = {**n, 'reuse_key': row['reuse_key'], 'state_before': row['state_before'],
                                    'state_after': row['state_after'], 'response_error': row['error'],
                                    'finish_reason': row['finish_reason'], 'prompt_sha256': row['prompt_sha256']}
                        positions.write(json.dumps(position, ensure_ascii=False, allow_nan=False) + '\n')
                    positions.flush()
                    if count % 100 == 0: emit(f'{count}/{p["planned_calls"]}, reported ${reported:.4f}')
                # Drain existing calls after a fatal error; never dispatch further.
                if halted and not active: break
            if halted: break
            emit(f'{month}: month wave completed')
    receipt = dict(status='completed' if count == new_target else 'stopped_no_retry',
                   attempts=attempted, completed_calls=count, logical_positions=len(outputs),
                   reported_cost_usd=reported, spent_or_reserved_usd=accounted, budget_cap_usd=p['budget_cap_usd'],
                   halt_reason=halted, peak_in_flight=peak, automatic_retries=0,
                   provider_fallbacks=0, seconds=perf_counter() - started,
                   actual_model_results=not engineering_only, truth_read=False,
                   existing_attempts_retained=len(previous), new_planned_calls=new_target)
    receipt.update(budget_mode=budget_mode, remaining_worst_case_at_start_usd=remaining_bound)
    dump(out / 'receipt.json', receipt)
    return receipt


def live_sender(p):
    from ..model_counterfactual import preflight
    from ..model import SCEOpenAILLM
    from ..news_label_trial import dotenv_values
    preflight({'route_candidate': p['route'], 'input_price_per_million': p['price_input_per_mtok'],
               'output_price_per_million': p['price_output_per_mtok']}, read_json(ROOT / p['provider_metadata']))
    secret = os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL / '.env').get('OPENROUTER_API_KEY')
    if not secret: raise ValueError('OpenRouter key missing')
    os.environ['SV_LLM_BASE_URL'] = p['destination']; os.environ['SV_LLM_API_KEY'] = secret
    thread = local()
    def send(messages):
        if not hasattr(thread, 'llm'):
            thread.llm = SCEOpenAILLM(model=p['model'], temperature=p['temperature'], max_tokens=p['max_tokens'],
                extra_body=p['request_extra_body'], response_format='json_object', timeout_s=p['timeout_s'])
        reply, latency = thread.llm.chat(messages); choice = reply.choices[0]; usage = getattr(reply, 'usage', None)
        return dict(returned_model=reply.model, returned_provider=getattr(reply, 'provider', None),
                    request_id=reply.id, finish_reason=choice.finish_reason, latency_ms=latency,
                    system_fingerprint=getattr(reply, 'system_fingerprint', None),
                    usage=usage.model_dump() if usage else None, api_reported_cost_usd=getattr(usage, 'cost', None),
                    raw_response_text=choice.message.content or '')
    return send


def run(folder, out):
    folder, out = Path(folder).resolve(), Path(out).resolve(); p, manifest = verify(folder)
    auth = read_json(folder / 'authorization.json')
    for k in ('planned_calls', 'budget_cap_usd', 'destination', 'model', 'route'):
        if auth.get(k) != p[k]: raise ValueError('Authorization scope mismatch: ' + k)
    if not auth.get('approved') or auth.get('protocol_sha256') != manifest['protocol_sha256']:
        raise ValueError('Exact protocol authorization required')
    if not out.is_relative_to(ROOT / 'outputs') or out.exists(): raise ValueError('Fresh ignored call folder required')
    send = live_sender(p)
    nodes = read_json(ROOT / p['preparation'] / 'state_dependencies_private.json')
    inputs = load_inputs(ROOT / p['input_templates'], p['months'])
    with (folder / 'execution_registration.json').open('x') as handle:
        json.dump({'output': str(out.relative_to(ROOT)), 'protocol_sha256': manifest['protocol_sha256']}, handle)
    receipt = execute(p, nodes, inputs, out, send, emit=lambda s: print(s, flush=True))
    receipt['protocol_sha256'] = manifest['protocol_sha256']
    dump(out / 'receipt.json', receipt)
    dump(out / 'manifest.json', {'protocol_sha256': manifest['protocol_sha256'],
         'files_sha256': {name: sha(out / name) for name in
            ('receipt.json', 'calls_private.jsonl', 'positions_private.jsonl', 'dispatch_private.jsonl')}})
    return receipt
