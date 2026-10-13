"""Materialize an already-verified A prior trial; audited engine and budget gates."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from .confidence_trial import protected, check_frozen, sha, dump
from .lifetime_trial import dry_run as engine_dry_run, execute as engine_execute
from .model import SCEEnvironmentProvider
from .prior_belief_preparation import ARMS, MONTHS, PRIOR_MARKER, month_offset, add_prior
from .prior_belief_experiment import SCHEMA, LINE, REF, PROMPT_VERSION, message_hash, build_messages, validate_bundle

PRICE_IN, PRICE_OUT, MAX_TOKENS, CAP = .30, 1.20, 1024, 1.00


def request_bound(messages):
    return ((len(json.dumps(messages, ensure_ascii=False).encode()) + 256) * PRICE_IN
            + MAX_TOKENS * PRICE_OUT) / 1e6


def extract_prior(messages, base, arm, month):
    if arm == 'no_prior':
        if messages != base:
            raise ValueError('no-prior preparation differs from original')
        return None
    text = messages[0]['content']
    start = text.index(PRIOR_MARKER)
    line = next(s for s in text[start:].splitlines() if s.startswith('{'))
    prior = {'source_month': month_offset(month, -1), **json.loads(line)}
    if add_prior(base, prior, int(month))[0] != messages:
        raise ValueError('prepared prior cannot be reconstructed exactly')
    return prior


def prepare(root, candidate, folder):
    root, candidate, folder = (Path(p).resolve() for p in (root, candidate, folder))
    protected(root)
    if folder.exists() or not folder.is_relative_to(root / 'outputs') or not candidate.is_relative_to(root / 'outputs'):
        raise ValueError('fresh ignored output and local candidate source required')
    draft = json.loads((candidate / 'summary.json').read_text())
    if draft['candidate_requests'] != 288 or draft['arms'] != list(ARMS):
        raise ValueError('requires the existing 288-case design')
    for name, h in draft['output_file_sha256'].items():
        if sha(candidate / name) != h:
            raise ValueError('original candidate input drift')
    for name, h in {**draft['source_sha256'], **draft['code_sha256']}.items():
        if sha(root / name) != h:
            raise ValueError('candidate source drift')
    source = root / 'outputs/sce_confidence_trial_20261011_v1'
    source_plan = json.loads((source / 'trial_manifest.json').read_text())
    selected = json.loads((candidate / 'selection_links_private.json').read_text())
    cases = [json.loads(s) for s in (candidate / 'candidate_cases_private.jsonl').read_text().splitlines()]
    if len(cases) != 288 or len({c['case_id'] for c in cases}) != 288:
        raise ValueError('duplicate or missing cases')
    by_case = {(c['target_month'], c['agent_id'], c['arm'], c['repeat']): c for c in cases}
    if len(by_case) != 288:
        raise ValueError('nonunique case identity')
    folder.mkdir(parents=True)
    sources = {str((candidate / 'summary.json').relative_to(root)): sha(candidate / 'summary.json')}
    for name, h in draft['output_file_sha256'].items():
        sources[str((candidate / name).relative_to(root))] = h
    sources.update(draft['source_sha256'])
    plan = {'status': 'offline_prepared_not_authorized', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'research_line': LINE, 'months': list(MONTHS), 'n_per_month': 12, 'arms': list(ARMS), 'repeats': [1, 2],
        'planned_answers': 288, 'model': 'deepseek-flash', 'temperature': .5, 'max_tokens': MAX_TOKENS, 'retry_max': 0,
        'common_count': 3, 'personal_count': 5, 'normal_expansion': False, 'new_api_calls': 0,
        'source_sha256': sources, 'metadata': {}, 'jobs': [], 'sampling_seed': 20261013,
        'prior_representation': 'full raw t-1 Q8 and ten-bin Q9; no current answer',
        'price_input_per_mtok': PRICE_IN, 'price_output_per_mtok': PRICE_OUT,
        'pricing_source': 'https://api-docs.deepseek.com/quick_start/pricing/', 'pricing_verified_date': '2026-10-13',
        'pricing_policy': 'peak cache-miss bound; no assumed cache/discount; usage estimate is not vendor bill',
        'proposed_simulation_cap_usd': CAP, 'simulation_budget_authorization': 'awaiting_explicit_real_t_minus_1_scope_and_cap',
        'preregistered_evaluation': {
            'primary': ['Q9 same-sample median absolute error', 'Q9 W1', 'cross-person IQR absolute gap'],
            'primary_contrasts': ['own_previous minus no_prior', 'own_previous minus permuted_previous'],
            'secondary': ['Q8 center error', 'individual Q9 uncertainty', 'raw deflation probability', 'individual error'],
            'learning_checks': ['same-person prior persistence baseline', 'signed update versus actual update',
                                'raw probability exact copying and L1 movement', 'own versus permuted identity value'],
            'comparison': 'same valid people across all three groups; age-balanced equal weights; repeats and months separate',
            'candidate_continue_gate': 'both repeats: own improves mean center error and W1 versus no_prior, both improve in >=3/4 months; identity and persistence checks required; no automatic upgrade',
            'bootstrap': 'paired person within month with seed 42, conditional on frozen inputs; not nationwide inference',
            'truth_isolation': 'current answers and survey weights read only by offline analysis; no provider file access',
            'no_tuning_during_run': True},
        'limitations': draft['limitations'] + ['Full prior reminder is a controlled intervention, not a measurement of natural memory.',
            'Four previously inspected development periods; independent mechanism holdout remains to be registered.',
            'Fresh contemporaneous no-prior arm avoids relying solely on old alias-version responses.']}
    links = []
    for month in MONTHS:
        dest = folder / month
        dest.mkdir()
        rows = [r for r in selected if r['month'] == month]
        ids = {r['base_agent_id'] for r in rows}
        if len(rows) != 12 or len(ids) != 12:
            raise ValueError('selected twelve-person roster')
        def frozen(name):
            p = source / month / name
            if sha(p) != source_plan['prepared_file_sha256'][f'{month}/{name}']:
                raise ValueError('old P/E/config changed')
            sources[str(p.relative_to(root))] = sha(p)
            return json.loads(p.read_text())
        pop = PopulationBundle.model_validate(frozen('population.json'))
        pop.personas = [p for p in pop.personas if p.agent_id in ids]
        if len(pop.personas) != 12 or any(p.weight != 1 for p in pop.personas):
            raise ValueError('fixed equal-weight population')
        env = EnvironmentBundle.model_validate(frozen('environment.json'))
        env.provider_args['persona_by_id'] = {p.agent_id: p.attributes for p in pop.personas}
        cfg = SimulationConfig.model_validate(frozen('simulation_national_confidence.json'))
        if cfg.n_steps != 1 or cfg.warm_start is not None:
            raise ValueError('cold-start one-step diagnostic required')
        baseline = deepcopy(cfg.decision_args['confidence_bundle'])
        baseline['news']['rows'] = {k: v for k, v in baseline['news']['rows'].items() if k in ids}
        baseline['labels'] = {k: v for k, v in baseline['labels'].items() if k in ids}
        originals = {p['agent_id']: p for p in frozen('preview_national_confidence.json')}
        target = env.provider_args['targets'][0]
        plan['metadata'][month] = {'as_of': target['as_of'], 'numerical_signals': len(env.provider_args['signals_by_step']['0']),
                                    'age_counts': dict(Counter(p.attributes['age_group'] for p in pop.personas))}
        dump(dest / 'population.json', pop.model_dump())
        dump(dest / 'environment.json', env.model_dump())
        provider = SCEEnvironmentProvider(env.model_copy(deep=True))
        provider.audit_dir = None
        provider.reset(42)
        provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        preview_arms = {}
        for arm in ARMS:
            bundle_rows = {}
            for row in rows:
                aid, sid = row['base_agent_id'], row['agent_id']
                a, b = (by_case[month, sid, arm, r] for r in (1, 2))
                if a['messages'] != b['messages'] or a['prompt_sha256'] != message_hash(a['messages']):
                    raise ValueError('repeat or prepared message hash mismatch')
                base = originals[aid]['messages']
                bundle_rows[aid] = {'prior': extract_prior(a['messages'], base, arm, month),
                    'baseline_messages_sha256': message_hash(base), 'messages_sha256': a['prompt_sha256']}
            bundle = {'schema_version': SCHEMA, 'research_line': LINE, 'target_month': target['target_month'],
                'as_of': target['as_of'], 'arm': arm, 'baseline': baseline, 'rows': bundle_rows}
            validate_bundle(bundle, pop.personas, target['target_month'], target['as_of'])
            simulation = cfg.model_copy(deep=True)
            simulation.decision_ref = REF
            simulation.decision_args = {'prior_bundle': bundle, 'seed': 42, 'llm_kind': 'scripted',
                                       'prompt_version': PROMPT_VERSION, 'max_prompt_chars': 18000}
            dump(dest / f'simulation_{arm}.json', simulation.model_dump())
            previews = [{'agent_id': ob.agent_id, 'messages': build_messages(ob, bundle)} for ob in observations]
            for p in previews:
                p['prompt_sha256'] = message_hash(p['messages'])
            dump(dest / f'preview_{arm}.json', previews)
            preview_arms[arm] = previews
        for row in rows:
            links.append({'month': month, 'agent_id': row['base_agent_id'], 'prepared_agent_id': row['agent_id'],
                          'source_agent_id': f"sce_u{row['source_userid']}"})
        for repeat in (1, 2):
            offset = (MONTHS.index(month) + repeat - 1) % len(ARMS)
            for arm in ARMS[offset:] + ARMS[:offset]:
                bounds = [request_bound(p['messages']) for p in preview_arms[arm]]
                cap = math.ceil(sum(bounds) * 100) / 100
                run_id = f'{folder.name}-{month}-{arm}-r{repeat}'
                command = [sys.executable, str(root / 'scripts/run_sce_local.py'), '--llm', 'openai',
                    '--model', plan['model'], '--population', str(dest / 'population.json'),
                    '--environment', str(dest / 'environment.json'), '--simulation', str(dest / f'simulation_{arm}.json'),
                    '--prompt-version', PROMPT_VERSION, '--run-id', run_id, '--temperature', '.5',
                    '--max-tokens', str(MAX_TOKENS), '--retry-max', '0', '--max-calls', '12',
                    '--extra-body', '{"thinking":{"type":"disabled"}}', '--price-in', str(PRICE_IN),
                    '--price-out', str(PRICE_OUT), '--cost-cap-usd', str(cap), '--confirm-spend']
                plan['jobs'].append({'month': month, 'arm': arm, 'repeat': repeat, 'run_id': run_id,
                    'command': command, 'conservative_cost_bound_usd': sum(bounds), 'job_cap_usd': cap})
    dump(folder / 'evaluation_links_private.json', links)
    plan['conservative_simulation_cost_bound_usd'] = sum(j['conservative_cost_bound_usd'] for j in plan['jobs'])
    plan['allocated_job_caps_usd'] = sum(j['job_cap_usd'] for j in plan['jobs'])
    if plan['allocated_job_caps_usd'] > CAP + 1e-9:
        raise ValueError('aggregate job caps exceed proposed budget')
    files = [root / 'scripts/run_sce_local.py', root / 'scripts/run_sce_prior_trial.py', root / 'scripts/analyze_sce_prior_trial.py'] + sorted((root / 'studies/sce_inflation_expectations').rglob('*.py'))
    plan['code_sha256'] = {str(p.relative_to(root)): sha(p) for p in files}
    plan['prepared_file_sha256'] = {str(p.relative_to(folder)): sha(p) for p in folder.rglob('*.json')}
    dump(folder / 'trial_manifest.json', plan)
    return plan


def execute(root, folder, approval_note):
    if not approval_note.strip():
        raise ValueError('explicit real t-1 questionnaire sending scope and budget confirmation required')
    plan = json.loads((Path(folder) / 'trial_manifest.json').read_text())
    if plan.get('research_line') != LINE or plan.get('planned_answers') != 288 or plan.get('proposed_simulation_cap_usd') != CAP:
        raise ValueError('only this frozen prior trial is permitted')
    return engine_execute(root, folder, approval_note)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'dry-run', 'run'])
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--approval-note', default='')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    if args.mode == 'prepare':
        if args.candidate is None:
            parser.error('prepare requires --candidate')
        plan = prepare(root, args.candidate, args.folder)
        print(json.dumps({k: plan[k] for k in ('planned_answers', 'conservative_simulation_cost_bound_usd', 'allocated_job_caps_usd', 'proposed_simulation_cap_usd')}))
    elif args.mode == 'dry-run':
        print(json.dumps(engine_dry_run(root, args.folder)))
    else:
        execute(root, args.folder, args.approval_note)
