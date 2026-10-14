"""Materialize the audited U1 state/guided inputs; engine checks and budget-gated execution."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from .confidence_trial import protected, check_frozen, sha, dump
from .belief_state_preparation import ARMS, MONTHS, render_state_block
from .model import SCEEnvironmentProvider
from .prior_belief_preparation import MARKER
from .prior_belief_trial import extract_prior, request_bound
from .prior_belief_experiment import message_hash
from .confidence_experiment import build_messages as baseline_messages
from .u1_state_experiment import REF, SCHEMA, LINE, PROMPT_VERSION, build_messages, validate_bundle

PRICE_IN, PRICE_OUT, MAX_TOKENS, CAP = .30, 1.20, 1024, 1.00
PRIOR_TRIAL = 'outputs/sce_prior_trial_20261013_v2'


def _state_block(prepared, u0, state, month, arm):
    """Recover the frozen block from the audited preparation and prove the renderer agrees."""
    before, after = u0[0]['content'].split(MARKER, 1)
    text = prepared[0]['content']
    if not (text.startswith(before) and text.endswith(MARKER + after)):
        raise ValueError('prepared U1 message is not the executed U0 plus one block')
    block = text[len(before):len(text) - len(MARKER + after)]
    guidance = arm == 'own_state_guided' and state['guidance_active']
    if block != render_state_block(state, month, guidance=guidance):
        raise ValueError('prepared state block differs from the frozen renderer')
    if arm == 'own_state_guided' and not state['guidance_active'] and 'One hypothesis' in block:
        raise ValueError('anchor-less case must not carry the guidance sentence')
    return block


def prepare(root, candidate, folder):
    root, candidate, folder = (Path(p).resolve() for p in (root, candidate, folder))
    protected(root)
    if folder.exists() or not folder.is_relative_to(root / 'outputs') or not candidate.is_relative_to(root / 'outputs'):
        raise ValueError('fresh ignored output and local candidate source required')
    draft = json.loads((candidate / 'summary.json').read_text())
    cmanifest = json.loads((candidate / 'manifest.json').read_text())
    if (draft['status'] != 'offline_preparation_completed_no_api_calls' or draft['spec_version'] != 'v2'
            or draft['months'] != list(MONTHS) or draft['selected_cases'] != 48
            or draft['prepared_cases_per_arm'] != {a: 48 for a in ARMS} or draft['dropped_cases']
            or draft['new_api_calls'] != 0):
        raise ValueError('requires the audited 48-case v2 preparation')
    for name, h in cmanifest['output_file_sha256'].items():
        if sha(candidate / name) != h:
            raise ValueError('audited candidate output drift: ' + name)
    for name, h in {**draft['source_sha256'], **draft['code_sha256']}.items():
        if sha(root / name) != h:
            raise ValueError('candidate source drift: ' + name)
    trial = root / PRIOR_TRIAL
    old_plan = json.loads((trial / 'trial_manifest.json').read_text())
    states = json.loads((candidate / 'state_values_private.json').read_text())
    if len(states) != 48 or len({(s['month'], s['base_agent_id']) for s in states}) != 48:
        raise ValueError('duplicate or missing state rows')
    by_case = {(s['month'], s['base_agent_id']): s for s in states}
    folder.mkdir(parents=True)
    sources = {str((candidate / name).relative_to(root)): h
               for name, h in {**cmanifest['output_file_sha256'], 'manifest.json': sha(candidate / 'manifest.json')}.items()}
    sources.update(draft['source_sha256'])
    plan = {'status': 'offline_prepared_not_authorized', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'research_line': LINE, 'months': list(MONTHS), 'n_per_month': 12, 'arms': list(ARMS), 'repeats': [1, 2],
        'planned_answers': 192, 'model': 'deepseek-flash', 'temperature': .5, 'max_tokens': MAX_TOKENS,
        'retry_max': 0, 'normal_expansion': False, 'new_api_calls': 0, 'sampling_seed': 20261013,
        'state_representation': draft['state_definition'],
        'price_input_per_mtok': PRICE_IN, 'price_output_per_mtok': PRICE_OUT,
        'pricing_source': 'https://api-docs.deepseek.com/quick_start/pricing/', 'pricing_verified_date': '2026-10-13',
        'pricing_policy': 'peak cache-miss bound; no assumed cache/discount; usage estimate is not vendor bill',
        'proposed_simulation_cap_usd': CAP, 'simulation_budget_authorization': 'awaiting_explicit_scope_and_cap',
        'preregistered_evaluation': {
            'external_protocol': 'docs/workstreams/20261013_behavior/codex_u1_comparison_protocol_v2.json',
            'protocol_note': 'metrics, contrasts, bootstrap and decision rules registered by the independent evaluator; '
                             'arms own_state/own_state_guided exported per codex_comparison_input_spec.md',
            'candidate_continue_gate': 'both repeats: lower center MAE and cross-section W1 than U0 own_previous, '
                                       'delta W1 no higher, Q9 coverage no lower; also reported against both past-only baselines',
            'truth_isolation': 'current answers and survey weights read only by offline evaluation; no provider file access',
            'no_tuning_during_run': True},
        'source_sha256': sources, 'metadata': {}, 'jobs': [],
        'limitations': [
            'Four previously inspected development periods; independent mechanism holdout remains to be registered.',
            'own_state adds a summary of own earlier answers on top of the raw t-1 answer; the contrast includes extra own history, not pure summarization.',
            'The guidance sentence is a registered hypothesis, not an established household rule; six anchor-less cases share identical prompts across arms.',
            'Same twelve-person age-balanced cohort and frozen P/E as the executed U0 trial; not nationally representative.']}
    links = json.loads((trial / 'evaluation_links_private.json').read_text())
    if sha(trial / 'evaluation_links_private.json') != draft['source_sha256'][f'{PRIOR_TRIAL}/evaluation_links_private.json']:
        raise ValueError('evaluation links drift')
    sources[f'{PRIOR_TRIAL}/evaluation_links_private.json'] = draft['source_sha256'][f'{PRIOR_TRIAL}/evaluation_links_private.json']
    if len(links) != 48:
        raise ValueError('evaluation links coverage')
    for month in MONTHS:
        dest = folder / month
        dest.mkdir()
        rows = [s for s in states if s['month'] == month]
        ids = {s['base_agent_id'] for s in rows}
        if len(rows) != 12 or len(ids) != 12:
            raise ValueError('selected twelve-person roster')
        def frozen(name):
            p = trial / month / name
            if sha(p) != old_plan['prepared_file_sha256'][f'{month}/{name}']:
                raise ValueError('executed U0 trial input changed: ' + name)
            sources[str(p.relative_to(root))] = sha(p)
            return json.loads(p.read_text())
        pop = PopulationBundle.model_validate(frozen('population.json'))
        if {p.agent_id for p in pop.personas} != ids or any(p.weight != 1 for p in pop.personas):
            raise ValueError('fixed equal-weight population')
        env = EnvironmentBundle.model_validate(frozen('environment.json'))
        env.provider_args['persona_by_id'] = {p.agent_id: p.attributes for p in pop.personas}
        cfg = SimulationConfig.model_validate(frozen('simulation_no_prior.json'))
        if cfg.n_steps != 1 or cfg.warm_start is not None:
            raise ValueError('cold-start one-step diagnostic required')
        baseline = deepcopy(cfg.decision_args['prior_bundle']['baseline'])
        executed_u0 = {p['agent_id']: p for p in frozen('preview_own_previous.json')}
        target = env.provider_args['targets'][0]
        if target['target_month'].replace('-', '') != month:
            raise ValueError('month mismatch')
        plan['metadata'][month] = {'as_of': target['as_of'],
                                    'age_counts': dict(Counter(p.attributes['age_group'] for p in pop.personas))}
        dump(dest / 'population.json', pop.model_dump())
        dump(dest / 'environment.json', env.model_dump())
        provider = SCEEnvironmentProvider(env.model_copy(deep=True))
        provider.audit_dir = None
        provider.reset(42)
        provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        prepared = {arm: {p['agent_id']: p['messages'] for p in json.loads(
            (candidate / month / f'preview_{arm}.json').read_text())} for arm in ARMS}
        preview_arms = {}
        for arm in ARMS:
            bundle_rows = {}
            for ob in observations:
                aid = ob.agent_id
                state = by_case[month, aid]
                base = baseline_messages(ob, baseline)
                u0 = executed_u0[aid]['messages']
                if message_hash(u0) != executed_u0[aid]['prompt_sha256']:
                    raise ValueError('executed U0 prompt hash mismatch')
                prior = extract_prior(u0, base, 'own_previous', month)
                block = _state_block(prepared[arm][state['agent_id']], u0, state, month, arm)
                bundle_rows[aid] = {'prior': prior, 'state_block': block,
                    'baseline_messages_sha256': message_hash(base),
                    'prior_messages_sha256': message_hash(u0),
                    'messages_sha256': state['prompt_sha256'][arm]}
            bundle = {'schema_version': SCHEMA, 'research_line': LINE, 'target_month': target['target_month'],
                'as_of': target['as_of'], 'arm': arm, 'baseline': baseline, 'rows': bundle_rows}
            validate_bundle(bundle, pop.personas, target['target_month'], target['as_of'])
            simulation = cfg.model_copy(deep=True)
            simulation.decision_ref = REF
            simulation.decision_args = {'u1_bundle': bundle, 'seed': 42, 'llm_kind': 'scripted',
                                       'prompt_version': PROMPT_VERSION, 'max_prompt_chars': 18000}
            dump(dest / f'simulation_{arm}.json', simulation.model_dump())
            previews = [{'agent_id': ob.agent_id, 'messages': build_messages(ob, bundle)} for ob in observations]
            for p in previews:
                p['prompt_sha256'] = message_hash(p['messages'])
                if p['prompt_sha256'] != bundle['rows'][p['agent_id']]['messages_sha256']:
                    raise ValueError('engine-rebuilt prompt differs from frozen preparation')
                if len(json.dumps(p['messages'], ensure_ascii=False)) > 18000:
                    raise ValueError('prompt exceeds size gate')
            dump(dest / f'preview_{arm}.json', previews)
            preview_arms[arm] = previews
        for repeat in (1, 2):
            offset = (MONTHS.index(month) + repeat - 1) % len(ARMS)
            for arm in list(ARMS)[offset:] + list(ARMS)[:offset]:
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
    files = [root / 'scripts/run_sce_local.py', root / 'scripts/run_sce_u1_trial.py',
             root / 'scripts/export_sce_u1_answers.py'] + sorted((root / 'studies/sce_inflation_expectations').rglob('*.py'))
    plan['code_sha256'] = {str(p.relative_to(root)): sha(p) for p in files}
    plan['prepared_file_sha256'] = {str(p.relative_to(folder)): sha(p) for p in folder.rglob('*.json')}
    dump(folder / 'trial_manifest.json', plan)
    return plan


def dry_run(root, folder):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    plan = json.loads((folder / 'trial_manifest.json').read_text())
    check_frozen(root, folder, plan)
    records = []
    for job in (j for j in plan['jobs'] if j['repeat'] == 1):
        command = list(job['command'])
        command[command.index('openai')] = 'scripted'
        command.remove('--confirm-spend')
        command[command.index('--run-id') + 1] += '-engineering'
        with (folder / f"{job['month']}_{job['arm']}_engineering.log").open('w') as handle:
            result = subprocess.run(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT)
        records.append({'month': job['month'], 'arm': job['arm'], 'exit_code': result.returncode})
        dump(folder / 'engineering_check.json', records)
        if result.returncode:
            raise RuntimeError('engineering run failed; retained log')
    return records


def execute(root, folder, approval_note):
    if not approval_note.strip():
        raise ValueError('fresh explicit scope/budget confirmation required')
    root, folder = Path(root).resolve(), Path(folder).resolve()
    plan = json.loads((folder / 'trial_manifest.json').read_text())
    if (plan['status'] != 'offline_prepared_not_authorized'
            or plan.get('research_line') != LINE or plan.get('planned_answers') != 192
            or plan.get('arms') != list(ARMS) or plan.get('proposed_simulation_cap_usd') != CAP):
        raise ValueError('only this frozen U1 trial is permitted')
    check_frozen(root, folder, plan)
    checks = json.loads((folder / 'engineering_check.json').read_text())
    if (len(checks) != 8
            or {(r['month'], r['arm']) for r in checks} != {(m, a) for m in MONTHS for a in ARMS}
            or any(r['exit_code'] for r in checks)):
        raise ValueError('eight successful engineering cells required')
    if sum(j['job_cap_usd'] for j in plan['jobs']) > plan['proposed_simulation_cap_usd']:
        raise ValueError('aggregate cost protection')
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    host = (os.environ.get('SV_LLM_BASE_URL') or '').rstrip('/')
    if host not in {'https://api.deepseek.com', 'https://api.deepseek.com/v1'}:
        raise ValueError('official DeepSeek endpoint required')
    if any((root / 'outputs/local_runs' / j['run_id']).exists() for j in plan['jobs']):
        raise ValueError('existing real run; no automatic overwrite or restart')
    plan['status'] = 'running'
    plan['simulation_budget_authorization'] = {'user_quote': approval_note,
                                               'recorded_at_utc': datetime.now(timezone.utc).isoformat()}
    dump(folder / 'trial_manifest.json', plan)
    for job in plan['jobs']:
        with (folder / f"{job['month']}_{job['arm']}_r{job['repeat']}_real.log").open('w') as handle:
            process = subprocess.run(job['command'], cwd=root, stdout=handle, stderr=subprocess.STDOUT)
        job['exit_code'] = process.returncode
        if process.returncode:
            plan['status'] = 'stopped_on_error'
            dump(folder / 'trial_manifest.json', plan)
            raise RuntimeError('stopped; no subsequent cells or automatic retries')
        run = root / 'outputs/local_runs' / job['run_id']
        calls = [json.loads(line) for line in (run / 'llm_calls.jsonl').read_text().splitlines()]
        previews = {p['agent_id']: p for p in json.loads((folder / job['month'] / f"preview_{job['arm']}.json").read_text())}
        if (len(calls) != 12 or {c['agent_id'] for c in calls} != set(previews)
                or any(c['prompt_sha256'] != previews[c['agent_id']]['prompt_sha256'] or c['attempt_idx'] != 0 for c in calls)):
            plan['status'] = 'stopped_audit_mismatch'
            dump(folder / 'trial_manifest.json', plan)
            raise RuntimeError('actual calls differ from frozen inputs')
        ledger = json.loads((run / 'cost_ledger.json').read_text())
        job['estimated_cost_usd'] = ledger['estimated_cost_usd']
        job['request_errors'] = sum(bool(c['error']) for c in calls)
        plan['new_api_calls'] += len(calls)
        dump(folder / 'trial_manifest.json', plan)
        print(json.dumps({'completed_cell': f"{job['month']}/{job['arm']}/r{job['repeat']}",
            'calls': len(calls), 'errors': job['request_errors'],
            'estimated_cost_usd': job['estimated_cost_usd']}), flush=True)
        if job['request_errors']:
            plan['status'] = 'stopped_on_request_error'
            dump(folder / 'trial_manifest.json', plan)
            raise RuntimeError('unknown failed-call cost retained; no automatic retry')
    plan['status'] = 'completed_pending_analysis'
    dump(folder / 'trial_manifest.json', plan)


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
        print(json.dumps({k: plan[k] for k in ('planned_answers', 'conservative_simulation_cost_bound_usd',
                          'allocated_job_caps_usd', 'proposed_simulation_cap_usd')}))
    elif args.mode == 'dry-run':
        print(json.dumps(dry_run(root, args.folder)))
    else:
        execute(root, args.folder, args.approval_note)
