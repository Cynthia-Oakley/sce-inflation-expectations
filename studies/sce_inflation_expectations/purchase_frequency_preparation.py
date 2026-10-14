"""Freeze frequency-only instruction contrast with identical price/contact data."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from .model import SCEEnvironmentProvider
from .information_update_runtime import build_messages as parent_messages
from .purchase_frequency_runtime import REF, PROMPT, ARMS, transform, build_messages
from .purchase_frequency_matching import CATEGORIES
from .prior_belief_experiment import message_hash
from .evaluation.expanded_state import sha, dump

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'outputs/sce_information_update_trial_20261014_v2'
MATERIAL = ROOT / 'outputs/sce_purchase_frequency_preparation_20261015_v1'
OLD_CASES = ROOT / 'outputs/sce_information_update_evaluation_20261014_v1/cases_private.json'


def prepare(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('fresh ignored output required')
    parent = json.loads((PARENT / 'manifest.json').read_text())
    material = json.loads((MATERIAL / 'summary.json').read_text())
    for name, digest in material['files_sha256'].items():
        if sha(MATERIAL / name) != digest:
            raise ValueError('material changed: ' + name)
    for name, digest in material['source_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('material source changed: ' + name)
    def frozen(name):
        path = PARENT / name
        if sha(path) != parent['prepared_file_sha256'][name]:
            raise ValueError('parent input changed: ' + name)
        return json.loads(path.read_text())
    oldprotocol = frozen('protocol.json')
    links = frozen('evaluation_links_private.json')
    assigned = {(r['month'], r['agent_id']): r for r in json.loads((MATERIAL / 'assignments_private.json').read_text())}
    prices = {int(r['target_month'].replace('-', '')): r for r in json.loads((MATERIAL / 'prices.json').read_text())}
    prepared_previews = {(r['month'], r['agent_id'], r['arm']): r
                         for r in json.loads((MATERIAL / 'preview_messages_private.json').read_text())}
    sources = {str((PARENT / 'manifest.json').relative_to(ROOT)): sha(PARENT / 'manifest.json'),
               str(OLD_CASES.relative_to(ROOT)): sha(OLD_CASES)}
    for name in ['summary.json', 'assignments_private.json', 'prices.json', 'preview_messages_private.json']:
        path = MATERIAL / name; sources[str(path.relative_to(ROOT))] = sha(path)
    for name in ['scripts/run_sce_purchase_frequency_trial.py', 'scripts/export_study_runtime.py']:
        sources[name] = sha(ROOT / name)
    for path in (ROOT / 'studies/sce_inflation_expectations').rglob('*.py'):
        if '__pycache__' not in path.parts and 'evaluation' not in path.relative_to(ROOT / 'studies/sce_inflation_expectations').parts:
            sources[str(path.relative_to(ROOT))] = sha(path)
    reused = [j for j in parent['jobs'] if j['arm'] == 'dated_information']
    oldcalls = {}
    for job in reused:
        directory = ROOT / 'outputs/local_runs' / job['run_id']
        run = json.loads((directory / 'run_manifest.json').read_text())
        if run['llm_kind'] != 'openai' or run['cost']['call_count'] != 48:
            raise ValueError('completed parent C required')
        oldcalls[job['month'], job['repeat']] = [json.loads(line) for line in (directory / 'llm_calls.jsonl').read_text().splitlines()]
        for name in ['run_manifest.json', 'study.duckdb', 'llm_calls.jsonl']:
            path = directory / name; sources[str(path.relative_to(ROOT))] = sha(path)
    out.mkdir(parents=True)
    jobs = []; estimate = reservation = 0.0
    for month in oldprotocol['months']:
        dest = out / str(month); dest.mkdir()
        env = EnvironmentBundle.model_validate(frozen(f'{month}/environment.json'))
        pop = PopulationBundle.model_validate(frozen(f'{month}/population.json'))
        cfg = SimulationConfig.model_validate(frozen(f'{month}/simulation_dated_information.json'))
        original = {r['agent_id']: r for r in frozen(f'{month}/preview_dated_information.json')}
        if len(pop.personas) != 48 or set(original) != {p.agent_id for p in pop.personas}:
            raise ValueError('same 48-person roster required')
        if prices[month]['as_of'] != env.provider_args['targets'][0]['as_of']:
            raise ValueError('price information cutoff mismatch')
        for name in ['population.json', 'environment.json', 'simulation_dated_information.json', 'preview_dated_information.json']:
            sources[str((PARENT / str(month) / name).relative_to(ROOT))] = sha(PARENT / str(month) / name)
        provider = SCEEnvironmentProvider(env.model_copy(deep=True)); provider.audit_dir = None
        provider.reset(42); provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        for arm in ARMS:
            bundle = {'arm': arm, 'parent': deepcopy(cfg.decision_args['information_update_bundle']),
                      'price_bundle': prices[month],
                      'frequency_by_id': {p.agent_id: assigned[month, p.agent_id]['recorded_days_7d'] for p in pop.personas},
                      'messages_sha256': {}}
            previews = []; reserve = 0.0
            for ob in observations:
                old = parent_messages(ob, bundle['parent'])
                if message_hash(old) != original[ob.agent_id]['prompt_sha256']:
                    raise ValueError('parent C message changed')
                days = bundle['frequency_by_id'][ob.agent_id]
                if set(days) != set(CATEGORIES):
                    raise ValueError('frequency whitelist mismatch')
                messages = transform(old, arm, prices[month], days)
                preview = prepared_previews[month, ob.agent_id, arm]
                if message_hash(messages) != preview['messages_sha256']:
                    raise ValueError('material/runtime message mismatch')
                text = messages[0]['content']
                if any(term in text for term in ['"userid"', '"weight"', 'QSP5', 'MIDUS', '"sex"', 'Do not mechanically treat a past price change']):
                    raise ValueError('forbidden/newly removed prompt field')
                bundle['messages_sha256'][ob.agent_id] = message_hash(messages)
                previews.append({'agent_id': ob.agent_id, 'messages': messages, 'prompt_sha256': message_hash(messages)})
                reserve += (len(json.dumps(messages, ensure_ascii=False).encode()) + 256) * .3 / 1e6 + 1024 * 1.2 / 1e6
            for ob in observations:
                build_messages(ob, bundle)
            newcfg = cfg.model_copy(deep=True); newcfg.decision_ref = REF
            newcfg.decision_args = {'purchase_frequency_bundle': bundle, 'prompt_version': PROMPT,
                                   'llm_kind': 'scripted', 'seed': 42, 'max_prompt_chars': 30000}
            dump(dest / f'simulation_{arm}.json', newcfg.model_dump(mode='json'))
            dump(dest / f'preview_{arm}.json', previews)
            byid = {r['agent_id']: r for r in previews}
            for repeat in oldprotocol['generation_repeats']:
                cap = math.ceil((reserve + .000001) * 1e4) / 1e4
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'cap_usd': cap,
                             'run_id': f'{out.name}-{month}-{arm}-r{repeat}'})
                reservation += reserve
                for call in oldcalls[month, repeat]:
                    newbytes = len(json.dumps(byid[call['agent_id']]['messages'], ensure_ascii=False).encode())
                    ratio = newbytes / len(call['prompt_text'].encode())
                    estimate += (call['usage']['prompt_tokens'] * ratio * .3 + call['usage']['completion_tokens'] * 1.2) / 1e6
        dump(dest / 'population.json', pop.model_dump(mode='json'))
        dump(dest / 'environment.json', env.model_dump(mode='json'))
    jobs = [jobs[i] for i in np.random.default_rng(20261017).permutation(len(jobs))]
    cap = math.ceil(sum(j['cap_usd'] for j in jobs) * 2) / 2
    protocol = {k: oldprotocol[k] for k in ['research_line', 'months', 'n_per_month', 'sampling_seed',
                'generation_repeats', 'model', 'official_advertised_version', 'model_identity_limit',
                'temperature', 'max_tokens', 'thinking', 'retry_max', 'price_input_per_mtok',
                'price_output_per_mtok', 'pricing_url', 'baseline_refs', 'q8', 'aggregation', 'intervals']}
    protocol.update(id='sce-purchase-frequency-rule-v1', registered_at_utc=datetime.now(timezone.utc).isoformat(),
        pricing_verified_date='2026-10-15', arms=list(ARMS), budget_cap_usd=cap,
        planned_calls=len(jobs)*48, base_candidate='dated_information',
        removed_instruction='Do not mechanically treat a past price change as your future inflation forecast.',
        comparison='Same parent C, category prices, assigned frequency vector, past beliefs, population and questionnaire; only explicit frequency-influence instruction differs.',
        primary_contrast='frequency_rule minus frequency_data on cross-section W1',
        candidate_gate='Primary W1 paired-person upper 95% bound < 0; center MAE and delta W1 points no worse; new scorable fraction >=99%. Local candidate screening, not overall project success.',
        mechanism_check='Across-person IQR, prior-position slope, rank, category-frequency associations; frequency-rule treatment is instruction increment, not total effect of the new data.',
        exploratory_old_C='Reuse previous C without rerun as descriptive context only; added prices/frequencies and batch differences prevent a clean total-data effect.',
        support='Same truth-scorable person-generations across both new arms and fixed past baselines; explicit failure coverage; no replacement sampling.',
        truth_isolation='Copy frozen roster/sidecar; no current answers read for sampling or prompts. Actual answers and weights confined to evaluation.',
        limits=oldprotocol['limits'][:4]+['Whole-vector conditional CE Diary 2020Q4 proxy, selected supported contacts; not observed respondent shopping or representative full CE frequency distribution.',
          'Existing Interview spending shares and Diary frequencies are from different households; no true joint person link.',
          'No grooming frequency: relevant Diary rows not included for publication. Four categories do not cover all spending.',
          'Parent C is an exploratory candidate, not an approved main-mechanism upgrade; frequency gains need other periods.',
          'Public availability does not establish attention; national category changes do not equal observed store prices.',
          'A returner conditional diagnostic using actual past answers; not recursive B or nationwide causal inference.'],
        no_tuning_after_run=True)
    dump(out / 'protocol.json', protocol); dump(out / 'evaluation_links_private.json', links)
    manifest = {'status': 'prepared_requires_authorization_record_and_dry_run', 'source_sha256': sources,
        'prepared_file_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')},
        'jobs': jobs, 'reused_jobs': reused, 'planned_calls': protocol['planned_calls'],
        'sum_job_caps_usd': sum(j['cap_usd'] for j in jobs), 'conservative_reservation_usd': reservation,
        'estimated_peak_cost_usd': estimate, 'proposed_cap_usd': cap, 'new_api_calls': 0,
        'protocol_sha256': sha(out / 'protocol.json')}
    dump(out / 'manifest.json', manifest)
    return manifest
