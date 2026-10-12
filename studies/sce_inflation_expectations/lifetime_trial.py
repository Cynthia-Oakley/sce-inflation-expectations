"""Frozen lifetime experience inputs, engine checks and budget-gated execution."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from .confidence_trial import MONTHS, sha, dump, protected, check_frozen
from .lifetime_experiment import ARMS, REF, SCHEMA, PROMPT_VERSION, build_messages, validate_bundle
from .lifetime_experience import json_hash
from .model import SCEEnvironmentProvider


def prepare(root, folder):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    protected(root)
    if folder.exists() or not folder.is_relative_to(root / 'outputs'):
        raise ValueError('fresh ignored output directory required')
    bank = root / 'outputs/sce_lifetime_episodes_20261012_v7'
    base = root / 'outputs/sce_confidence_trial_20261011_v1'
    summary = json.loads((bank / 'summary.json').read_text())
    old = json.loads((base / 'trial_manifest.json').read_text())
    source_hashes = {}
    def track(p):
        source_hashes[str(p.relative_to(root))] = sha(p)
        return json.loads(p.read_text())
    track(bank / 'summary.json')
    track(base / 'trial_manifest.json')
    for name, expected in summary['sources_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('lifetime source changed: ' + name)
        source_hashes[name] = expected
    if sha(root / 'studies/sce_inflation_expectations/lifetime_episodes.py') != summary['code_sha256']:
        raise ValueError('lifetime generation code changed')
    for name, expected in summary['prepared_file_sha256'].items():
        if sha(bank / name) != expected:
            raise ValueError('lifetime draft changed: ' + name)
    for name, expected in old['prepared_file_sha256'].items():
        if sha(base / name) != expected:
            raise ValueError('previous confidence input changed: ' + name)
    catalogue = track(root / 'docs/literature/sce/heterogeneity_and_probability/episode_catalogue_20261012.json')
    if source_hashes['docs/literature/sce/heterogeneity_and_probability/episode_catalogue_20261012.json'] != summary['catalogue_sha256']:
        raise ValueError('catalogue changed')
    pricing = track(root / 'data/raw/model_pricing/20261012_lifetime/receipt.json')
    price_page = root / 'data/raw/model_pricing/20261012_lifetime/deepseek_pricing.html'
    if pricing['http_status'] != 200 or sha(price_page) != pricing['sha256']:
        raise ValueError('pricing evidence missing/drifted')
    source_hashes[str(price_page.relative_to(root))] = sha(price_page)
    cases_path = bank / 'main_cases_private.jsonl'
    source_hashes[str(cases_path.relative_to(root))] = sha(cases_path)
    cases = [json.loads(line) for line in cases_path.read_text().splitlines()]
    if len(cases) != 144 or summary['main_start_age_candidate'] != 6:
        raise ValueError('registered 144-message, age-6 trial required')
    all_links = track(base / 'evaluation_links_private.json')
    folder.mkdir()
    plan = {'status': 'offline_prepared_not_authorized', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'module_name': 'Lifetime Inflation Experience', 'research_line': 'A_historical_reconstruction',
        'months': list(MONTHS), 'arms': list(ARMS), 'n_per_month': 12, 'repeats': [1, 2],
        'planned_answers': 288, 'normal_expansion': False, 'start_age': 6,
        'model': 'deepseek-flash', 'documented_model_version': 'DeepSeek-V4.1-Flash',
        'temperature': .5, 'max_tokens': 1024, 'retry_max': 0,
        'price_input_per_mtok': .30, 'price_output_per_mtok': 1.20,
        'pricing_evidence': pricing, 'price_rule': 'peak no-cache rates; not a vendor quote',
        'source_sha256': source_hashes, 'metadata': {}, 'jobs': [], 'new_api_calls': 0,
        'preregistered_evaluation': {
            'primary': ['Q9 sample median absolute error', 'Q9 W1 distribution distance', 'Q9 cross-person IQR gap'],
            'secondary': ['Q8', 'personal uncertainty', 'raw deflation probability', 'age groups'],
            'contrasts': ['age_matched_episodes minus original', 'common_episodes minus original', 'age_matched_episodes minus common_episodes'],
            'common_valid': 'same valid people across all three arms; report rates independently',
            'aggregation': 'each repeat separately, equal-weight averages over four periods; survey weights auxiliary',
            'age_groups': 'four selected per age group; descriptive only, no significance claim',
            'bootstrap': 'paired people conditional on fixed P/E/history; 1000 draws, seed 42; not population or period generalization',
            'repetition_rule': 'independent generations; repeat index is not a provider random seed',
            'candidate_gate': 'both repeats: matched has lower average Q9 median error and W1 than original, both improve in >=3/4 periods; no automatic production upgrade',
            'truth_isolation': 'analysis only; official answers/weights not read during preparation or execution',
            'no_target_tuning': True},
        'limitations': summary['limits'] + [
            '12-person age-balanced samples, four previously examined periods, no independent holdout.',
            'All existing confidence/CE/news assumptions retained; no new shopping weights or probability reporting instructions.',
            'No own prior answers, panel memory, core/normal expansion or social interaction.',
            'Equal count in three age groups is not a nationally representative age distribution.',
            'Historical context and compression differ between common and age-matched arms; not a pure matching causal effect.']}
    links = []
    for month in MONTHS:
        dest = folder / month
        dest.mkdir()
        subset = [c for c in cases if c['month'] == month]
        ids = {c['local_agent_id'] for c in subset}
        if len(ids) != 12 or len(subset) != 36 or len({c['case_id'] for c in subset}) != 36:
            raise ValueError('paired case counts')
        pop = PopulationBundle.model_validate(track(base / month / 'population.json'))
        pop.personas = [p for p in pop.personas if p.agent_id in ids]
        if {p.agent_id for p in pop.personas} != ids or any(p.weight != 1 or p.init_state for p in pop.personas):
            raise ValueError('exact clean equal-weight subset required')
        env = EnvironmentBundle.model_validate(track(base / month / 'environment.json'))
        env.provider_args['persona_by_id'] = {p.agent_id: p.attributes for p in pop.personas}
        cfg = SimulationConfig.model_validate(track(base / month / 'simulation_national_confidence.json'))
        target = env.provider_args['targets'][0]
        if cfg.n_steps != 1 or cfg.warm_start is not None or target['target_month'].replace('-', '') != month:
            raise ValueError('single-month cold start')
        baseline = deepcopy(cfg.decision_args['confidence_bundle'])
        baseline['news']['rows'] = {k: v for k, v in baseline['news']['rows'].items() if k in ids}
        baseline['labels'] = {k: v for k, v in baseline['labels'].items() if k in ids}
        by_id = {r['local_agent_id']: r for r in track(bank / month / 'episodes_private.json')}
        common = track(bank / month / 'shared_episodes_public.json')['cards']
        originals = {c['local_agent_id']: c for c in subset if c['arm'] == 'original'}
        dump(dest / 'population.json', pop.model_dump())
        dump(dest / 'environment.json', env.model_dump())
        links.extend(r for r in all_links if r['month'] == month and r['agent_id'] in ids)
        provider = SCEEnvironmentProvider(env.model_copy(deep=True))
        provider.audit_dir = None
        provider.reset(42)
        provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        previews_by_arm = {}
        for arm in ARMS:
            expected = {c['local_agent_id']: c for c in subset if c['arm'] == arm}
            rows = {aid: {'cards': [] if arm == 'original' else common if arm == 'common_episodes' else by_id[aid]['candidates']['6']['cards'],
                'baseline_messages_sha256': originals[aid]['messages_sha256'],
                'messages_sha256': expected[aid]['messages_sha256']} for aid in ids}
            bundle = {'schema_version': SCHEMA, 'arm': arm, 'baseline': baseline,
                'history_end': summary['per_month'][month]['history_end'], 'start_age': 6,
                'intro': catalogue['prompt_intro'], 'rows': rows, 'research_line': plan['research_line']}
            validate_bundle(bundle, pop.personas, target['target_month'], target['as_of'])
            simulation = cfg.model_copy(deep=True)
            simulation.decision_ref = REF
            simulation.decision_args = {'lifetime_bundle': bundle, 'seed': 42, 'llm_kind': 'scripted',
                                       'prompt_version': PROMPT_VERSION, 'max_prompt_chars': 18000}
            dump(dest / f'simulation_{arm}.json', simulation.model_dump())
            previews = []
            for ob in observations:
                messages = build_messages(ob, bundle)
                if messages != expected[ob.agent_id]['messages'] or len(json.dumps(messages, ensure_ascii=False)) > 18000:
                    raise ValueError('exact message/size check failed')
                if any(link['source_agent_id'] in json.dumps(messages, ensure_ascii=False) for link in all_links):
                    raise ValueError('original identifier in prompt')
                previews.append({'agent_id': ob.agent_id, 'messages': messages,
                                 'prompt_sha256': hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()})
            dump(dest / f'preview_{arm}.json', previews)
            previews_by_arm[arm] = previews
        plan['metadata'][month] = {'as_of': target['as_of'], 'history_end': bundle['history_end'],
            'age_group_counts': {g: sum(p.attributes['age_group'] == g for p in pop.personas) for g in sorted({p.attributes['age_group'] for p in pop.personas})},
            'unchanged_messages_match_draft': True}
        for repeat in (1, 2):
            offset = (MONTHS.index(month) + repeat - 1) % 3
            order = ARMS[offset:] + ARMS[:offset]
            for arm in order:
                run_id = f'{folder.name}-{month}-{arm}-r{repeat}'
                bounds = [(len(json.dumps(p['messages'], ensure_ascii=False).encode())+256)*.30/1e6 + 1024*1.20/1e6 for p in previews_by_arm[arm]]
                cap = math.ceil(sum(bounds)*100)/100
                command = [sys.executable, str(root/'scripts/run_sce_local.py'), '--llm', 'openai', '--model', plan['model'],
                    '--population', str(dest/'population.json'), '--environment', str(dest/'environment.json'),
                    '--simulation', str(dest/f'simulation_{arm}.json'), '--prompt-version', PROMPT_VERSION,
                    '--run-id', run_id, '--temperature', '.5', '--max-tokens', '1024', '--retry-max', '0', '--max-calls', '12',
                    '--extra-body', '{"thinking":{"type":"disabled"}}', '--price-in', '.30', '--price-out', '1.20',
                    '--cost-cap-usd', str(cap), '--confirm-spend']
                plan['jobs'].append({'month': month, 'arm': arm, 'repeat': repeat, 'run_id': run_id,
                    'command': command, 'conservative_cost_bound_usd': sum(bounds), 'job_cap_usd': cap})
    if len(links) != 48:
        raise ValueError('evaluation links coverage')
    dump(folder/'evaluation_links_private.json', links)
    plan['conservative_simulation_cost_bound_usd'] = sum(j['conservative_cost_bound_usd'] for j in plan['jobs'])
    plan['proposed_simulation_cap_usd'] = math.ceil(sum(j['job_cap_usd'] for j in plan['jobs'])*2)/2
    plan['simulation_budget_authorization'] = 'awaiting_concrete_scope_and_budget'
    files = [root/'scripts/run_sce_local.py', root/'scripts/run_sce_lifetime_trial.py', root/'scripts/analyze_sce_lifetime_trial.py'] + sorted((root/'studies/sce_inflation_expectations').rglob('*.py'))
    plan['code_sha256'] = {str(p.relative_to(root)): sha(p) for p in files}
    plan['prepared_file_sha256'] = {str(p.relative_to(folder)): sha(p) for p in folder.rglob('*.json')}
    dump(folder/'trial_manifest.json', plan)
    return plan


def dry_run(root, folder):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    plan = json.loads((folder/'trial_manifest.json').read_text())
    check_frozen(root, folder, plan)
    records = []
    for job in (j for j in plan['jobs'] if j['repeat'] == 1):
        command = list(job['command'])
        command[command.index('openai')] = 'scripted'
        command.remove('--confirm-spend')
        command[command.index('--run-id')+1] += '-engineering'
        with (folder/f"{job['month']}_{job['arm']}_engineering.log").open('w') as handle:
            result = subprocess.run(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT)
        records.append({'month': job['month'], 'arm': job['arm'], 'exit_code': result.returncode})
        dump(folder/'engineering_check.json', records)
        if result.returncode:
            raise RuntimeError('engineering run failed; retained log')
    return records


def execute(root, folder, approval_note):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    plan = json.loads((folder/'trial_manifest.json').read_text())
    if not approval_note.strip() or plan['status'] != 'offline_prepared_not_authorized':
        raise ValueError('fresh explicit scope/budget confirmation required')
    check_frozen(root, folder, plan)
    checks = json.loads((folder/'engineering_check.json').read_text())
    if len(checks) != 12 or {(r['month'],r['arm']) for r in checks} != {(m,a) for m in MONTHS for a in ARMS} or any(r['exit_code'] for r in checks):
        raise ValueError('twelve successful engineering cells required')
    if sum(j['job_cap_usd'] for j in plan['jobs']) > plan['proposed_simulation_cap_usd']:
        raise ValueError('aggregate cost protection')
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    host = (os.environ.get('SV_LLM_BASE_URL') or '').rstrip('/')
    if host not in {'https://api.deepseek.com', 'https://api.deepseek.com/v1'}:
        raise ValueError('official DeepSeek endpoint required')
    if any((root/'outputs/local_runs'/j['run_id']).exists() for j in plan['jobs']):
        raise ValueError('existing real run; no automatic overwrite or restart')
    plan['status'] = 'running'
    plan['simulation_budget_authorization'] = {'user_quote': approval_note, 'recorded_at_utc': datetime.now(timezone.utc).isoformat()}
    dump(folder/'trial_manifest.json', plan)
    for job in plan['jobs']:
        with (folder/f"{job['month']}_{job['arm']}_r{job['repeat']}_real.log").open('w') as handle:
            process = subprocess.run(job['command'], cwd=root, stdout=handle, stderr=subprocess.STDOUT)
        job['exit_code'] = process.returncode
        if process.returncode:
            plan['status'] = 'stopped_on_error'
            dump(folder/'trial_manifest.json', plan)
            raise RuntimeError('stopped; no subsequent cells or automatic retries')
        run = root/'outputs/local_runs'/job['run_id']
        calls = [json.loads(line) for line in (run/'llm_calls.jsonl').read_text().splitlines()]
        previews = {p['agent_id']: p for p in json.loads((folder/job['month']/f"preview_{job['arm']}.json").read_text())}
        if len(calls) != 12 or {c['agent_id'] for c in calls} != set(previews) or any(c['prompt_sha256'] != previews[c['agent_id']]['prompt_sha256'] or c['attempt_idx'] != 0 for c in calls):
            plan['status'] = 'stopped_audit_mismatch'
            dump(folder/'trial_manifest.json', plan)
            raise RuntimeError('actual calls differ from frozen inputs')
        ledger = json.loads((run/'cost_ledger.json').read_text())
        job['estimated_cost_usd'] = ledger['estimated_cost_usd']
        job['request_errors'] = sum(bool(c['error']) for c in calls)
        plan['new_api_calls'] += len(calls)
        dump(folder/'trial_manifest.json', plan)
        print(json.dumps({'completed_cell': f"{job['month']}/{job['arm']}/r{job['repeat']}",
            'calls': len(calls), 'errors': job['request_errors'], 'estimated_cost_usd': job['estimated_cost_usd']}), flush=True)
        if job['request_errors']:
            plan['status'] = 'stopped_on_request_error'
            dump(folder/'trial_manifest.json', plan)
            raise RuntimeError('unknown failed-call cost retained; no automatic retry')
    plan['status'] = 'completed_pending_analysis'
    dump(folder/'trial_manifest.json', plan)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'dry-run', 'run'])
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--approval-note', default='')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    if args.mode == 'prepare':
        result = prepare(root, args.folder)
        print(json.dumps({k: result[k] for k in ('planned_answers','conservative_simulation_cost_bound_usd','proposed_simulation_cap_usd')}))
    elif args.mode == 'dry-run':
        print(json.dumps(dry_run(root, args.folder)))
    else:
        execute(root, args.folder, args.approval_note)
