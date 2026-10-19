"""Reusable manifest-gated batch executor. Uses SocioVerse2, not a new simulator."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
OFFICIAL = ROOT.parent/'socioverse2_repo'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def read_json(path):
    return json.loads(Path(path).read_text())


def verify(folder):
    folder = Path(folder).resolve(); manifest = read_json(folder/'manifest.json')
    protocol = read_json(folder/'protocol.json')
    if sha(folder/'protocol.json') != manifest['protocol_sha256']:
        raise ValueError('Protocol changed')
    for name, digest in manifest['prepared_file_sha256'].items():
        path = (folder/name).resolve()
        if not path.is_relative_to(folder) or sha(path) != digest:
            raise ValueError('Prepared input changed: '+name)
    for name, digest in manifest['source_sha256'].items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError('Source changed: '+name)
    expected = Counter((month, arm, repeat) for month in protocol['months']
                       for arm in protocol['arms'] for repeat in protocol['generation_repeats'])
    if (type(protocol['n_per_month']) is not int or protocol['n_per_month'] < 1
            or not math.isfinite(protocol['budget_cap_usd']) or protocol['budget_cap_usd'] <= 0
            or not 0 <= protocol['temperature'] <= 2 or not 1 <= protocol['max_tokens'] <= 4096
            or protocol['thinking'] != 'disabled'
            or any(not math.isfinite(protocol[k]) or protocol[k] < 0
                   for k in ('price_input_per_mtok', 'price_output_per_mtok'))):
        raise ValueError('Invalid model/count/price/budget configuration')
    jobs = manifest['jobs']
    if Counter((j['month'], j['arm'], j['repeat']) for j in jobs) != expected:
        raise ValueError('Incomplete or duplicated configured cells')
    if len({j['run_id'] for j in jobs}) != len(jobs) or any(Path(j['run_id']).name != j['run_id'] for j in jobs):
        raise ValueError('Unsafe/nonunique run identifiers')
    if any(not math.isfinite(j['cap_usd']) or j['cap_usd'] <= 0 for j in jobs):
        raise ValueError('Positive finite job caps required')
    if (protocol['retry_max'] != 0 or protocol['planned_calls'] != len(jobs)*protocol['n_per_month']
            or manifest['planned_calls'] != protocol['planned_calls']
            or sum(j['cap_usd'] for j in jobs) > protocol['budget_cap_usd']+1e-9):
        raise ValueError('Scope/retry/budget mismatch')
    return manifest, protocol


def authorize(folder, manifest, protocol):
    auth = read_json(folder/'authorization.json')
    expected = {'approved': True, 'protocol_sha256': manifest['protocol_sha256'],
                'cap_usd': protocol['budget_cap_usd'], 'planned_calls': protocol['planned_calls'],
                'destination': protocol['destination']}
    if any(auth.get(k) != v for k, v in expected.items()) or not auth.get('user_confirmation'):
        raise ValueError('Explicit matching data-scope/destination/budget authorization required')
    checks = read_json(folder/'engineering_checks.json')
    if len(checks) != len(manifest['jobs']) or {c['job_index'] for c in checks} != set(range(len(manifest['jobs']))):
        raise ValueError('All configured offline cells required')
    for check in checks:
        job = manifest['jobs'][check['job_index']]
        receipt = read_json(ROOT/'outputs/local_runs'/(job['run_id']+'-engineering')/'run_manifest.json')
        if (check['exit_code'] or check['run_id'] != job['run_id']
                or receipt.get('protocol_sha256') != manifest['protocol_sha256']
                or receipt.get('status') != 'completed' or receipt.get('llm_kind') != 'scripted'
                or receipt.get('cost', {}).get('call_count') != 0 or receipt.get('actual_input_hashes_match') is not True):
            raise ValueError('Invalid offline engine receipt')
    from ..news_label_trial import dotenv_values
    values = dotenv_values(OFFICIAL/'.env')
    destination = (os.environ.get('SV_LLM_BASE_URL') or values.get('SV_LLM_BASE_URL') or '').rstrip('/')
    if destination not in (protocol['destination'], protocol['destination']+'/v1') or not (os.environ.get('SV_LLM_API_KEY') or values.get('SV_LLM_API_KEY')):
        raise ValueError('Authorized endpoint/credential unavailable')


def worker(folder, index, scripted):
    started = perf_counter(); folder = Path(folder).resolve()
    manifest, protocol = verify(folder)
    if type(index) is not int or not 0 <= index < len(manifest['jobs']):
        raise ValueError('Valid job index required')
    if not scripted:
        authorize(folder, manifest, protocol)
    sys.path.insert(0, str(OFFICIAL))
    from socioverse.engine import build_simulator
    from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
    from ..frozen_prompt_runtime import FrozenPromptDecision, REF, PROMPT
    if protocol['mechanism'] == 'q8_delta_absolute_q9':
        from ..q8_delta_runtime import Q8DeltaDecision as FrozenPromptDecision, REF, PROMPT
    from ..model import SCEEnvironmentProvider
    from ..prior_belief_experiment import message_hash
    job = manifest['jobs'][index]; month = folder/str(job['month'])
    run_id = job['run_id']+('-engineering' if scripted else '')
    audit = ROOT/'outputs/local_runs'/run_id; audit.mkdir(parents=True, exist_ok=False)
    env = EnvironmentBundle.model_validate_json((month/'environment.json').read_text())
    pop = PopulationBundle.model_validate_json((month/'population.json').read_text())
    cfg = SimulationConfig.model_validate_json((month/'simulation.json').read_text())
    if len(pop.personas) != protocol['n_per_month'] or cfg.n_steps != 1:
        raise ValueError('Single-month configured roster required')
    prompt_file = month/f"prompts_{job['arm']}.json"
    cfg.seed = job['seed']; cfg.decision_ref = REF
    cfg.decision_args = dict(llm_kind='scripted' if scripted else 'openai', prompt_version=PROMPT,
        model_version=protocol['model'], seed=cfg.seed, run_id=run_id, audit_dir=str(audit),
        prompts_file=str(prompt_file), prompts_sha256=sha(prompt_file), model=protocol['model'],
        temperature=protocol['temperature'], max_tokens=protocol['max_tokens'],
        max_prompt_chars=protocol['max_prompt_chars'], retry_max=0, max_calls=len(pop.personas),
        extra_body={'thinking': {'type': protocol['thinking']}},
        price_input_per_mtok=protocol['price_input_per_mtok'],
        price_output_per_mtok=protocol['price_output_per_mtok'], cost_cap_usd=job['cap_usd'])
    env.provider_args.update(audit_dir=str(audit), run_id=run_id,
                            persona_by_id={p.agent_id: p.attributes for p in pop.personas})
    decision = FrozenPromptDecision(**{**cfg.decision_args, 'llm_kind': 'scripted'})
    if set(decision.bundle['rows']) != {p.agent_id for p in pop.personas}:
        raise ValueError('Prompt/roster mismatch')
    check = SCEEnvironmentProvider(env.model_copy(deep=True)); check.audit_dir = None
    check.reset(cfg.seed); check.advance_to(1)
    for ob in check.observe_batch([p.agent_id for p in pop.personas], 1):
        if message_hash(decision.build_llm_messages(ob)) != decision.bundle['rows'][ob.agent_id]['prompt_sha256']:
            raise ValueError('Actual message drift')
    for name, value in [('population', pop), ('environment', env), ('simulation', cfg)]:
        dump(audit/(name+'_effective.json'), value.model_dump(mode='json'))
    sim = build_simulator(env_bundle=env, pop_bundle=pop, sim_config=cfg, store_path=audit/'study.duckdb')
    statuses = Counter(); base = sim.decision.decide_batch
    def counted(obs, memories):
        actions = base(obs, memories); statuses.update(a.payload['validation_status'] for a in actions); return actions
    sim.decision.decide_batch = counted
    timestamp = datetime.now(timezone.utc).isoformat(); complete = False
    try:
        sim.run()
        if sum(statuses.values()) != len(pop.personas) or sim.decision.call_count != (0 if scripted else len(pop.personas)):
            raise RuntimeError('Incomplete run; no retry')
        complete = True
    finally:
        cost = sim.decision.cost_summary()
        dump(audit/'run_manifest.json', {'run_id': run_id, 'month': job['month'], 'arm': job['arm'],
            'repeat': job['repeat'], 'n': len(pop.personas), 'status': 'completed' if complete else 'stopped_partial_no_retry',
            'llm_kind': 'scripted' if scripted else 'openai', 'cost': cost,
            'started_at_utc': timestamp, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
            'wall_seconds': perf_counter()-started, 'protocol_sha256': manifest['protocol_sha256'],
            'actual_input_hashes_match': True, 'decisions_by_validation_status': dict(statuses),
            'prompts_sha256': sha(prompt_file), 'new_api_calls': cost['call_count']})
        dump(audit/'cost_ledger.json', cost)


def dispatch(folder, scripted=True, workers=4):
    folder = Path(folder).resolve(); manifest, protocol = verify(folder)
    if not 1 <= workers <= 4:
        raise ValueError('Workers must be 1..4')
    if not scripted:
        authorize(folder, manifest, protocol)
    for job in manifest['jobs']:
        if (ROOT/'outputs/local_runs'/(job['run_id']+('-engineering' if scripted else ''))).exists():
            raise ValueError('Existing job; no automatic rerun or resume')
    # One shared source export per batch; reuse official Core and legacy audit.
    subprocess.run([sys.executable, str(ROOT/'scripts/export_study_runtime.py')], cwd=ROOT,
                   capture_output=True, text=True, check=True)
    results = []; next_index = 0; failed = False
    def one(index):
        job = manifest['jobs'][index]
        command = [sys.executable, str(ROOT/'scripts/run_sce_frozen_trial.py'), 'worker',
                   '--folder', str(folder), '--job-index', str(index)]
        if scripted: command.append('--scripted')
        suffix = '-engineering' if scripted else ''
        with (folder/(job['run_id']+suffix+'.log')).open('x') as log:
            rc = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')).returncode
        print(job['month'], job['arm'], job['repeat'], 'completed' if not rc else 'stopped', flush=True)
        return {'job_index': index, 'run_id': job['run_id'], 'exit_code': rc}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = {}
        while next_index < len(manifest['jobs']) and len(active) < workers:
            active[pool.submit(one, next_index)] = next_index; next_index += 1
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                active.pop(future); result = future.result(); results.append(result); failed |= bool(result['exit_code'])
            dump(folder/('engineering_checks.json' if scripted else 'real_dispatch.json'), results)
            while not failed and next_index < len(manifest['jobs']) and len(active) < workers:
                active[pool.submit(one, next_index)] = next_index; next_index += 1
    if failed:
        raise RuntimeError('Batch stopped; preserve results, no automatic retry')
