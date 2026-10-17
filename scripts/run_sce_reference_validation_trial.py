#!/usr/bin/env python3
"""Reference scale-up; isolated worker plus the existing gated fail-stop dispatch."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import runpy
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT.parent/'socioverse2_repo'
PROTOCOL_ID = 'sce-reference-scaleup-v1'
MONTHS = (202003, 202009, 202103, 202109, 202206, 202212,
          202306, 202312, 202404, 202410, 202503, 202509)
N_PER_MONTH = 192
PLANNED_CALLS = 4608
_loaded = runpy.run_path(str(ROOT/'scripts/run_sce_household_finance_trial.py'),
                        run_name=__name__+'._inherited')
_inherited = _loaded['dispatch'].__globals__
sha, dump = _inherited['sha'], _inherited['dump']
authorization_gate = _inherited['authorization_gate']


def verify(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder/'manifest.json').read_text())
    for name, digest in manifest['source_sha256'].items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError('source changed: '+name)
    for name, digest in manifest['prepared_file_sha256'].items():
        path = (folder/name).resolve()
        if not path.is_relative_to(folder) or sha(path) != digest:
            raise ValueError('prepared input changed: '+name)
    if sha(folder/'protocol.json') != manifest['protocol_sha256']:
        raise ValueError('protocol changed')
    protocol = json.loads((folder/'protocol.json').read_text())
    expected = {'id': PROTOCOL_ID, 'research_line': 'A_conditional_returner_reconstruction',
        'months': list(MONTHS), 'n_per_month': N_PER_MONTH, 'arms': ['reference'],
        'generation_repeats': [1, 2], 'planned_calls': PLANNED_CALLS, 'model': 'deepseek-flash',
        'temperature': .5, 'max_tokens': 1024, 'retry_max': 0,
        'price_input_per_mtok': .3, 'price_output_per_mtok': 1.2}
    if any(protocol.get(key) != value for key, value in expected.items()):
        raise ValueError('Frozen reference protocol scope/settings mismatch')
    if (protocol.get('thinking') not in ('disabled', {'type': 'disabled'})
            or type(protocol['n_per_month']) is not int or type(protocol['planned_calls']) is not int
            or manifest['planned_calls'] != PLANNED_CALLS
            or protocol.get('budget_cap_usd') != manifest['proposed_cap_usd']):
        raise ValueError('Frozen reference thinking/request/budget scope mismatch')
    jobs = manifest['jobs']
    expected_cells = Counter((month, 'reference', repeat) for month in MONTHS for repeat in (1, 2))
    if (Counter((job['month'], job['arm'], job['repeat']) for job in jobs) != expected_cells
            or any(type(job['month']) is not int or type(job['repeat']) is not int for job in jobs)
            or len({job['run_id'] for job in jobs}) != 24):
        raise ValueError('All 24 unique reference cells required')
    for job in jobs:
        if (not job['run_id'] or Path(job['run_id']).name != job['run_id']
                or not math.isfinite(job['cap_usd']) or job['cap_usd'] <= 0):
            raise ValueError('Invalid reference run identifier/budget')
    if (not math.isfinite(manifest['proposed_cap_usd']) or manifest['proposed_cap_usd'] <= 0
            or sum(job['cap_usd'] for job in jobs) > manifest['proposed_cap_usd']+1e-9):
        raise ValueError('Reference total budget mismatch')
    dependencies = {'scripts/run_sce_reference_validation_trial.py',
        'scripts/run_sce_household_finance_trial.py', 'scripts/export_study_runtime.py',
        'studies/sce_inflation_expectations/reference_validation_runtime.py'}
    if not dependencies <= set(manifest['source_sha256']):
        raise ValueError('Reference runner/runtime/export sources must be frozen')
    required = {'protocol.json'}
    for month in MONTHS:
        required.update(f'{month}/{name}' for name in ('population.json', 'environment.json',
                         'simulation_reference.json', 'preview_reference.json'))
        personas = json.loads((folder/str(month)/'population.json').read_text())['personas']
        identifiers = [p['agent_id'] for p in personas]
        if (len(personas) != N_PER_MONTH or len(set(identifiers)) != N_PER_MONTH
                or any(not isinstance(aid, str) or not aid for aid in identifiers)):
            raise ValueError('Exactly 192 distinct personas required per month')
    if not required <= set(manifest['prepared_file_sha256']):
        raise ValueError('Reference runtime inputs/previews must be frozen')
    return manifest


def worker(folder, index, scripted):
    folder = Path(folder).resolve()
    manifest = verify(folder)
    if type(index) is not int or not 0 <= index < len(manifest['jobs']):
        raise ValueError('Valid reference job index required')
    if not scripted:
        authorization_gate(folder, manifest)
    sys.path.insert(0, str(OFFICIAL))
    from socioverse.engine import build_simulator
    from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
    from studies.sce_inflation_expectations.reference_validation_runtime import ReferenceValidationDecision
    from studies.sce_inflation_expectations.model import SCEEnvironmentProvider
    from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
    job = manifest['jobs'][index]
    run_id = job['run_id']+('-engineering' if scripted else '')
    audit = ROOT/'outputs/local_runs'/run_id
    audit.mkdir(parents=True, exist_ok=False)
    runtime = OFFICIAL/'studies/sce_inflation_expectations'
    prefix = 'studies/sce_inflation_expectations/'
    for name, digest in manifest['source_sha256'].items():
        if name.startswith(prefix) and name.endswith('.py') and sha(runtime/name[len(prefix):]) != digest:
            raise ValueError('Exported runtime source changed: '+name)
    snapshot = audit/'source_snapshot'
    snapshot.mkdir()
    hashes = {}
    for source in runtime.rglob('*.py'):
        if '__pycache__' in source.parts:
            continue
        relative = source.relative_to(runtime)
        dest = snapshot/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        hashes[str(relative)] = sha(source)
    shutil.copy2(Path(__file__), audit/'runner_source.py')
    shutil.copy2(ROOT/'scripts/run_sce_household_finance_trial.py', audit/'inherited_runner_source.py')
    dest = folder/str(job['month'])
    env = EnvironmentBundle.model_validate_json((dest/'environment.json').read_text())
    pop = PopulationBundle.model_validate_json((dest/'population.json').read_text())
    cfg = SimulationConfig.model_validate_json((dest/'simulation_reference.json').read_text())
    n = len(pop.personas)
    if n != N_PER_MONTH:
        raise ValueError('192-person frozen reference population required')
    env.provider_args.update(audit_dir=str(audit), run_id=run_id,
                            persona_by_id={p.agent_id: p.attributes for p in pop.personas})
    cfg.seed = 41+job['repeat']
    cfg.decision_args.update(llm_kind='scripted' if scripted else 'openai', seed=cfg.seed,
        run_id=run_id, audit_dir=str(audit), model='deepseek-flash', temperature=.5, max_tokens=1024,
        retry_max=0, max_calls=n, extra_body={'thinking': {'type': 'disabled'}},
        price_input_per_mtok=.3, price_output_per_mtok=1.2, cost_cap_usd=job['cap_usd'])
    check = SCEEnvironmentProvider(env.model_copy(deep=True))
    check.audit_dir = None
    check.reset(cfg.seed)
    check.advance_to(1)
    decision = ReferenceValidationDecision(**{**cfg.decision_args, 'llm_kind': 'scripted'})
    previews = {row['agent_id']: row['prompt_sha256']
                for row in json.loads((dest/'preview_reference.json').read_text())}
    if set(previews) != {p.agent_id for p in pop.personas}:
        raise ValueError('Reference preview roster mismatch')
    for ob in check.observe_batch([p.agent_id for p in pop.personas], 1):
        if message_hash(decision.build_llm_messages(ob)) != previews[ob.agent_id]:
            raise ValueError('Actual reference message drift')
    shutil.copy2(dest/'preview_reference.json', audit/'frozen_preview.json')
    for name, bundle in [('population_effective', pop), ('environment_effective', env), ('simulation_effective', cfg)]:
        dump(audit/(name+'.json'), bundle.model_dump(mode='json'))
    sim = build_simulator(env_bundle=env, pop_bundle=pop, sim_config=cfg, store_path=audit/'study.duckdb')
    statuses = Counter()
    base = sim.decision.decide_batch
    def counted(obs, memories):
        actions = base(obs, memories)
        statuses.update(str(action.payload.get('validation_status')) for action in actions)
        return actions
    sim.decision.decide_batch = counted
    started, completed = datetime.now(timezone.utc).isoformat(), False
    try:
        sim.run()
        cost = sim.decision.cost_summary()
        if sum(statuses.values()) != n or cost['call_count'] != (0 if scripted else n):
            raise RuntimeError('Incomplete reference job; preserve without retry')
        completed = True
    finally:
        cost = sim.decision.cost_summary()
        result = {'run_id': run_id, 'month': job['month'], 'arm': 'reference', 'repeat': job['repeat'],
            'n': n, 'llm_kind': 'scripted' if scripted else 'openai', 'started_at_utc': started,
            'finished_at_utc': datetime.now(timezone.utc).isoformat(), 'cost': cost,
            'decisions_by_validation_status': dict(statuses), 'source_snapshot_sha256': hashes,
            'status': 'completed' if completed else 'stopped_partial_no_retry',
            'actual_input_hashes_match': True, 'protocol_sha256': manifest['protocol_sha256'],
            'new_api_calls': cost['call_count']}
        dump(audit/'run_manifest.json', result)
        dump(audit/'cost_ledger.json', cost)
    print(json.dumps({'month': job['month'], 'arm': 'reference', 'repeat': job['repeat'],
                     'statuses': dict(statuses), 'cost': cost['estimated_cost_usd']}), flush=True)


_inherited.update(verify=verify, worker=worker, __file__=str(Path(__file__).resolve()))
dispatch = _inherited['dispatch']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'dry-run', 'run', 'worker'])
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--job-index', type=int)
    parser.add_argument('--scripted', action='store_true')
    args = parser.parse_args()
    folder = args.folder.resolve()
    if args.action == 'prepare':
        from studies.sce_inflation_expectations.reference_validation_preparation import prepare
        manifest = prepare(folder)
        verify(folder)
        print('prepared', manifest['planned_calls'], 'requests; reserve',
              round(manifest['conservative_reservation_usd'], 4), 'cap', manifest['proposed_cap_usd'])
        return
    if args.action == 'worker':
        return worker(folder, args.job_index, args.scripted)
    return dispatch(folder, args.action == 'dry-run', args.workers)


if __name__ == '__main__':
    main()
