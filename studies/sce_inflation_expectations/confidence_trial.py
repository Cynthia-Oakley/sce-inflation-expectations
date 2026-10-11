"""Prepare, freeze and execute paired multi-period confidence trials."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from .model import SCEEnvironmentProvider
from .confidence_experiment import ARMS, SCHEMA, REF, PROMPT_VERSION, build_messages, validate_bundle
from .belief_trial_preparation import confidence_block
from .news_exposure import SCHEMA as NEWS_SCHEMA, interests_for_profile
from .news_exposure_demo import draw_news
from .price_experience import profile_hash, PROFILE_KEYS

MONTHS = ('202203', '202209', '202303', '202403')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def protected(root):
    data = json.loads((root / 'docs/sources/sol_handoff_protected_files_20261010.json').read_text())['files_sha256']
    if any(sha(root / name) != expected for name, expected in data.items()):
        raise ValueError('protected pending files changed')


def check_frozen(root, folder, plan):
    protected(root)
    for name, expected in plan['source_sha256'].items() | plan['code_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('frozen source changed: ' + name)
    for name, expected in plan['prepared_file_sha256'].items():
        if sha(folder / name) != expected:
            raise ValueError('prepared input changed: ' + name)


def prepare(root, folder):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    protected(root)
    if folder.exists() or not folder.is_relative_to(root / 'outputs'):
        raise ValueError('fresh ignored output required')
    monthly = root / 'outputs/monthly_inputs_20261011T124521Z_77e69c5a'
    materials = root / 'outputs/sce_multiperiod_preparation_20261011_v3'
    news_root = root / 'outputs/sce_multiperiod_news_label_analysis_20261011_v1'
    monthly_plan = json.loads((monthly / 'manifest.json').read_text())
    source_hashes = {}
    def track(p):
        source_hashes[str(p.relative_to(root))] = sha(p)
        return json.loads(p.read_text())
    track(monthly / 'manifest.json')
    track(materials / 'summary.json')
    track(news_root / 'summary.json')
    waves = track(root / 'docs/literature/sce/belief_proxies/gallup_waves_20261011.json')
    for wave in waves['waves']:
        p, h = wave['local_file'], wave['sha256']
        if sha(root / p) != h:
            raise ValueError('confidence source changed')
        source_hashes[p] = h
    folder.mkdir()
    plan = {'status': 'offline_prepared_not_authorized', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'research_line': 'A_historical_reconstruction', 'months': list(MONTHS), 'n_per_month': 48,
            'arms': list(ARMS), 'repeats': [1, 2], 'planned_answers': 768, 'normal_expansion': False,
            'model': 'deepseek-flash', 'temperature': .5, 'max_tokens': 1024, 'retry_max': 0,
            'news_seed': 104729, 'confidence_seed': 42, 'common_count': 3, 'personal_count': 5,
            'mixing_weight': .5, 'affinity_boost': 2., 'source_sha256': source_hashes,
            'metadata': {}, 'jobs': [], 'new_api_calls': 0,
            'policy_design': 'same three short official facts to every sample in both arms; controlled policy-news exposure, not estimated real awareness',
            'preregistered_evaluation': {
                'primary': ['Q9 sample median absolute error', 'Q9 W1 distribution distance', 'Q9 cross-person IQR gap'],
                'secondary': ['Q8 median error', 'individual uncertainty', 'raw deflation probability', 'housing/age/numeracy groups'],
                'comparisons': 'same valid people, weights and inputs; report both generations separately, then equal-weight monthly averages',
                'repetition_rule': 'independent model generations with identical messages; repeat index is not a provider random seed',
                'upgrade_rule': 'candidate only if both median error and distribution distance improve in both repetitions, in at least three of four months each; no automatic production change',
                'intervals': 'paired person bootstrap conditional on fixed news/confidence assignment; not population or period generalization',
                'truth_isolation': 'raw answers and survey weights read only by separate offline analysis',
                'no_target_tuning': True},
            'limitations': ['48-person samples and four previously examined periods are mechanism diagnostics, not nationwide or blind prediction.',
                'Annual Gallup adult confidence is a synthetic proxy, not SCE household-head attitudes or measured trust in inflation control.',
                'Gallup waves are about 5–11 months old; no political traits or government/Fed joint distribution inferred.',
                'CE2020Q4 synthetic baskets are held fixed; cross-year spending stability unverified.',
                'Gasoline vintage and NYT historical text/paper dates remain incompletely verified; not strict forecast B.',
                'Common policy brief assumes controlled awareness; comparison with old runs cannot isolate this information change.',
                'No own prior answer, panel memory, core/normal projection or interpersonal interaction.']}
    links = []
    for month in MONTHS:
        dest = folder / month
        dest.mkdir()
        src = monthly / 'n48' / month
        package = next(p for p in monthly_plan['packages'] if p['path'] == f'n48/{month}')
        for name, h in package['sha256'].items():
            if sha(src / name) != h:
                raise ValueError('monthly preparation changed')
        pop = PopulationBundle.model_validate(track(src / 'population.json'))
        env = EnvironmentBundle.model_validate(track(src / 'environment.json'))
        template = SimulationConfig.model_validate(track(src / 'simulation.json'))
        library = track(news_root / month / 'library.json')
        assignments = track(materials / month / 'confidence_assignments_private.json')
        baskets = track(materials / month / 'synthetic_ce_baskets_private.json')
        policy = track(materials / month / 'public_policy_candidate.json')
        if sha(root / policy['file']) != policy['sha256']:
            raise ValueError('policy source changed')
        source_hashes[policy['file']] = policy['sha256']
        if len(pop.personas) != 48 or template.n_steps != 1 or template.warm_start is not None:
            raise ValueError('single-month 48-person cold start required')
        target = env.provider_args['targets'][0]
        if target['target_month'].replace('-', '') != month or library['stats']['as_of'] != target['as_of']:
            raise ValueError('month/time mismatch')
        wave_id = assignments[0]['wave_id']
        wave = next(w for w in waves['waves'] if w['wave_id'] == wave_id)
        if wave['published_date'] > target['as_of'][:10] or len({a['wave_id'] for a in assignments}) != 1:
            raise ValueError('future/mixed confidence waves')
        label_map = {a['agent_id']: a['label'] for a in assignments}
        if set(label_map) != {p.agent_id for p in pop.personas}:
            raise ValueError('confidence coverage')
        common, _ = draw_news(library['common_a1'], 3, f'104729|{month}|common-a1')
        common.sort(key=lambda a: (a['pub_date'], a['article_id']))
        rows, labels, delivery = {}, {}, []
        for index, person in enumerate(pop.personas, 1):
            source_id = person.agent_id
            profile = person.attributes
            if set(profile) - PROFILE_KEYS or person.weight != 1 or baskets[source_id]['profile_sha256'] != profile_hash(profile):
                raise ValueError('profile/CE whitelist or binding')
            shares = deepcopy(baskets[source_id]['spending_shares'])
            interests = interests_for_profile(profile, shares)
            personal, _ = draw_news(library['personal_keep'], 5, f'104729|{month}|{source_id}|personal', interests, .5, 2.)
            personal.sort(key=lambda a: (a['pub_date'], a['article_id']))
            aid = f'belief_{month}_{index:03d}'
            links.append({'month': month, 'agent_id': aid, 'source_agent_id': source_id})
            labels[aid] = label_map[source_id]
            person.agent_id, person.group_key, person.init_state = aid, None, {}
            rows[aid] = {'profile_sha256': profile_hash(profile), 'spending_shares': shares, 'personal_news': personal}
            text = ' '.join(a['headline'] + ' ' + a['abstract'] for a in common + personal)
            delivery.append(bool(re.search(r'\b(?:fed|federal reserve|fomc|monetary policy)\b', text, re.I)))
        for key in ('audit_dir', 'run_id', 'household_state_by_id', 'price_experience_mechanism', 'experience_by_id', 'information_exposure'):
            env.provider_args.pop(key, None)
        env.provider_args.update(events_by_step={}, persona_by_id={p.agent_id: p.attributes for p in pop.personas})
        env.information_program.broadcasts = []
        env.scheduled_events = []
        dump(dest / 'population.json', pop.model_dump())
        dump(dest / 'environment.json', env.model_dump())
        news = {'schema_version': NEWS_SCHEMA, 'research_line': plan['research_line'],
                'target_month': target['target_month'], 'as_of': target['as_of'], 'arm': 'matched',
                'mixing_weight': .5, 'affinity_boost': 2., 'common_news': common, 'rows': rows,
                'source_sha256': {str((news_root / month / 'library.json').relative_to(root)): sha(news_root / month / 'library.json')},
                'pool_status': library['stats']['pool_status']}
        policy_input = {'published_at': policy['published_at'], 'source_url': policy['source_url'],
                        'source_sha256': policy['sha256'], 'facts': policy['candidate_plain_language_facts']}
        provider = SCEEnvironmentProvider(env.model_copy(deep=True))
        provider.audit_dir = None
        provider.reset(42)
        provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        all_previews = {}
        for arm in ARMS:
            bundle = {'schema_version': SCHEMA, 'arm': arm, 'news': news, 'labels': labels,
                      'policy': policy_input, 'wave_id': wave_id}
            validate_bundle(bundle, pop.personas, target['target_month'], target['as_of'])
            cfg = template.model_copy(deep=True)
            cfg.seed = 42
            cfg.decision_ref = REF
            cfg.decision_args = {'confidence_bundle': bundle, 'seed': 42, 'llm_kind': 'scripted',
                                 'prompt_version': PROMPT_VERSION, 'max_prompt_chars': 18000}
            dump(dest / f'simulation_{arm}.json', cfg.model_dump())
            previews = []
            for ob in observations:
                messages = build_messages(ob, bundle)
                text = json.dumps(messages, ensure_ascii=False)
                if len(text) > 18000 or any(l['source_agent_id'] in text for l in links) or 'Recent news headlines' in text:
                    raise ValueError('prompt size/IDs/duplicate old news')
                previews.append({'agent_id': ob.agent_id, 'messages': messages,
                                 'prompt_sha256': hashlib.sha256(text.encode()).hexdigest()})
            dump(dest / f'preview_{arm}.json', previews)
            all_previews[arm] = {p['agent_id']: p for p in previews}
        for aid, label in labels.items():
            base = all_previews[ARMS[0]][aid]['messages'][0]['content']
            added = all_previews[ARMS[1]][aid]['messages'][0]['content']
            if added != base.replace('Question 1 (point estimate):', confidence_block(label) + 'Question 1 (point estimate):', 1):
                raise ValueError('paired prompts differ beyond confidence')
        plan['metadata'][month] = {'as_of': target['as_of'], 'frame_n': package['frame_n'],
            'confidence_counts': dict(Counter(labels.values())), 'identical_prompt_DK_count': sum(not confidence_block(v) for v in labels.values()),
            'wave_id': wave_id, 'policy_published_at': policy['published_at'], 'natural_news_fed_mentions_n': sum(delivery),
            'controlled_policy_brief_n': 48, 'numerical_signals': len(env.provider_args['signals_by_step']['0'])}
        for repeat in (1, 2):
            arm_order = ARMS if (MONTHS.index(month) + repeat) % 2 else ARMS[::-1]
            for arm in arm_order:
                run_id = f'{folder.name}-{month}-{arm}-r{repeat}'
                previews = list(all_previews[arm].values())
                bounds = [(len(json.dumps(p['messages'], ensure_ascii=False).encode()) + 256) * .30 / 1e6 + 1024 * 1.20 / 1e6 for p in previews]
                cap = math.ceil(48 * max(bounds) * 100) / 100
                command = [sys.executable, str(root / 'scripts/run_sce_local.py'), '--llm', 'openai', '--model', 'deepseek-flash',
                    '--population', str(dest / 'population.json'), '--environment', str(dest / 'environment.json'),
                    '--simulation', str(dest / f'simulation_{arm}.json'), '--prompt-version', PROMPT_VERSION,
                    '--run-id', run_id, '--temperature', '0.5', '--max-tokens', '1024', '--retry-max', '0', '--max-calls', '48',
                    '--extra-body', '{"thinking":{"type":"disabled"}}', '--price-in', '0.30', '--price-out', '1.20',
                    '--cost-cap-usd', str(cap), '--confirm-spend']
                plan['jobs'].append({'month': month, 'arm': arm, 'repeat': repeat, 'run_id': run_id, 'command': command,
                                     'conservative_cost_bound_usd': sum(bounds), 'job_cap_usd': cap})
    dump(folder / 'evaluation_links_private.json', links)
    plan['conservative_simulation_cost_bound_usd'] = sum(j['conservative_cost_bound_usd'] for j in plan['jobs'])
    plan['proposed_simulation_cap_usd'] = math.ceil(sum(j['job_cap_usd'] for j in plan['jobs']) * 2) / 2
    plan['simulation_budget_authorization'] = 'awaiting_concrete_scope_and_budget'
    files = [root / 'scripts/run_sce_local.py', root / 'scripts/run_sce_confidence_trial.py'] + sorted((root / 'studies/sce_inflation_expectations').rglob('*.py'))
    plan['code_sha256'] = {str(p.relative_to(root)): sha(p) for p in files}
    plan['prepared_file_sha256'] = {str(p.relative_to(folder)): sha(p) for p in folder.rglob('*.json')}
    dump(folder / 'trial_manifest.json', plan)
    return plan


def dry_run(root, folder):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    plan = json.loads((folder / 'trial_manifest.json').read_text())
    check_frozen(root, folder, plan)
    records = []
    # Identical repeats need no second scripted execution: one for each month/arm.
    for job in [j for j in plan['jobs'] if j['repeat'] == 1]:
        command = list(job['command'])
        command[command.index('openai')] = 'scripted'
        command.remove('--confirm-spend')
        command[command.index('--run-id') + 1] += '-engineering'
        with (folder / f"{job['month']}_{job['arm']}_engineering.log").open('w') as handle:
            result = subprocess.run(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT)
        records.append({'month': job['month'], 'arm': job['arm'], 'exit_code': result.returncode})
        dump(folder / 'engineering_check.json', records)
        if result.returncode:
            raise RuntimeError('engineering run failed; inspect local log')
    return records


def execute(root, folder, approval_note):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    plan = json.loads((folder / 'trial_manifest.json').read_text())
    if not approval_note.strip() or plan['status'] != 'offline_prepared_not_authorized':
        raise ValueError('fresh trial with explicit scope/budget approval required; no automatic restart')
    check_frozen(root, folder, plan)
    checks = json.loads((folder / 'engineering_check.json').read_text())
    if len(checks) != 8 or any(r['exit_code'] for r in checks):
        raise ValueError('eight engineering cells required')
    if sum(j['job_cap_usd'] for j in plan['jobs']) > plan['proposed_simulation_cap_usd']:
        raise ValueError('aggregate budget')
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    host = (os.environ.get('SV_LLM_BASE_URL') or os.environ.get('OPENAI_BASE_URL') or '').rstrip('/')
    if host not in {'https://api.deepseek.com', 'https://api.deepseek.com/v1'}:
        raise ValueError('registered official DeepSeek endpoint only')
    if any((root / 'outputs/local_runs' / j['run_id']).exists() for j in plan['jobs']):
        raise ValueError('existing real run; no overwrite or automatic duplicate')
    plan['status'] = 'running'
    plan['simulation_budget_authorization'] = {'user_quote': approval_note, 'recorded_at_utc': datetime.now(timezone.utc).isoformat()}
    dump(folder / 'trial_manifest.json', plan)
    for job in plan['jobs']:
        with (folder / f"{job['month']}_{job['arm']}_r{job['repeat']}_real.log").open('w') as handle:
            process = subprocess.run(job['command'], cwd=root, stdout=handle, stderr=subprocess.STDOUT)
        job['exit_code'] = process.returncode
        if process.returncode:
            plan['status'] = 'stopped_on_error'
            dump(folder / 'trial_manifest.json', plan)
            raise RuntimeError('run stopped; audit before any continuation')
        run = root / 'outputs/local_runs' / job['run_id']
        calls = [json.loads(line) for line in (run / 'llm_calls.jsonl').read_text().splitlines()]
        previews = {p['agent_id']: p for p in json.loads((folder / job['month'] / f"preview_{job['arm']}.json").read_text())}
        if len(calls) != 48 or {c['agent_id'] for c in calls} != set(previews) or any(c['prompt_sha256'] != previews[c['agent_id']]['prompt_sha256'] or c['attempt_idx'] != 0 for c in calls):
            plan['status'] = 'stopped_audit_mismatch'
            dump(folder / 'trial_manifest.json', plan)
            raise RuntimeError('actual call coverage/prompt mismatch')
        ledger = json.loads((run / 'cost_ledger.json').read_text())
        job['estimated_cost_usd'] = ledger['estimated_cost_usd']
        job['request_errors'] = sum(bool(c['error']) for c in calls)
        dump(folder / 'trial_manifest.json', plan)
        print(json.dumps({'completed_cell': job['month'] + '/' + job['arm'] + '/r' + str(job['repeat']),
                          'calls': len(calls), 'errors': job['request_errors'], 'estimated_cost_usd': job['estimated_cost_usd']}), flush=True)
        if job['request_errors']:
            plan['status'] = 'stopped_on_request_error'
            dump(folder / 'trial_manifest.json', plan)
            raise RuntimeError('request error retained, no subsequent cells dispatched')
    plan['status'] = 'completed_pending_analysis'
    dump(folder / 'trial_manifest.json', plan)


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
        print(json.dumps({k: result[k] for k in ('planned_answers', 'conservative_simulation_cost_bound_usd', 'proposed_simulation_cap_usd')}))
    elif args.mode == 'dry-run':
        print(json.dumps(dry_run(root, args.folder)))
    else:
        execute(root, args.folder, args.approval_note)
