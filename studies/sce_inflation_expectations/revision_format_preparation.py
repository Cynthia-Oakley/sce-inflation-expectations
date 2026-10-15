"""Freeze a modest contemporaneous response-format pilot without reading targets."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from .model import SCEEnvironmentProvider
from .information_update_runtime import build_messages as parent_messages
from .revision_format_runtime import REF, PROMPT, ARMS, SHARED, REPLY_MARKER, transform, previous_answer, build_messages
from .prior_belief_experiment import message_hash
from .evaluation.expanded_state import sha, dump

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT/'outputs/sce_information_update_trial_20261014_v2'
TRUTH = ROOT/'outputs/sce_information_update_evaluation_20261014_v1/cases_private.json'
MONTHS = (202004, 202105, 202111, 202203)
N = 24
SEED = 20261015


def prepare(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    parent = json.loads((PARENT/'manifest.json').read_text())

    def frozen(name):
        path = PARENT/name
        if sha(path) != parent['prepared_file_sha256'][name]:
            raise ValueError('Frozen parent input drift: '+name)
        return json.loads(path.read_text())

    old = frozen('protocol.json')
    # Only roster and historical traits are read here; no target Q8/Q9 is read.
    links = frozen('evaluation_links_private.json')
    selected_links = []
    sources = {str((PARENT/'manifest.json').relative_to(ROOT)): sha(PARENT/'manifest.json'),
               str(TRUTH.relative_to(ROOT)): sha(TRUTH)}
    for name in ['scripts/run_sce_revision_format_trial.py', 'scripts/export_study_runtime.py']:
        sources[name] = sha(ROOT/name)
    for path in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        if '__pycache__' not in path.parts and 'evaluation' not in path.relative_to(ROOT/'studies/sce_inflation_expectations').parts:
            sources[str(path.relative_to(ROOT))] = sha(path)
    out.mkdir(parents=True)
    jobs = []; reserve_total = estimate_total = 0.; missing = 0; pair_count = 0
    for month in MONTHS:
        dest = out/str(month); dest.mkdir()
        names = ['population.json', 'environment.json', 'simulation_dated_information.json', 'preview_dated_information.json']
        inputs = {}
        for name in names:
            inputs[name] = frozen(f'{month}/{name}')
            path = PARENT/str(month)/name; sources[str(path.relative_to(ROOT))] = sha(path)
        env = EnvironmentBundle.model_validate(inputs['environment.json'])
        pop = PopulationBundle.model_validate(inputs['population.json'])
        cfg = SimulationConfig.model_validate(inputs['simulation_dated_information.json'])
        previews = {r['agent_id']: r for r in inputs['preview_dated_information.json']}
        ids = sorted(p.agent_id for p in pop.personas)
        chosen = sorted(np.random.default_rng(SEED+month).choice(ids, N, replace=False).tolist())
        chosen_set = set(chosen)
        pop.personas = [p for p in pop.personas if p.agent_id in chosen_set]
        if len(pop.personas) != N:
            raise ValueError('Subsample size mismatch')
        selected_links += [r for r in links if r['month'] == month and r['agent_id'] in chosen_set]
        provider = SCEEnvironmentProvider(env.model_copy(deep=True)); provider.audit_dir = None
        provider.reset(42); provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        paired = {}
        for arm in ARMS:
            bundle = {'arm': arm, 'parent': deepcopy(cfg.decision_args['information_update_bundle']),
                      'messages_sha256': {}}
            new_previews = []; reserve = estimate = 0.
            for ob in observations:
                original = parent_messages(ob, bundle['parent'])
                if message_hash(original) != previews[ob.agent_id]['prompt_sha256']:
                    raise ValueError('Original prompt drift')
                prior = previous_answer(original)
                if arm == 'direct':
                    missing += int(prior['point_pct'] is None)
                messages = transform(original, arm)
                before = original[0]['content'].split(REPLY_MARKER, 1)[0]+SHARED
                if not messages[0]['content'].startswith(before):
                    raise ValueError('Common P/E/prior/question/instruction drift')
                if arm == 'direct':
                    paired[ob.agent_id] = before
                elif paired[ob.agent_id] != before:
                    raise ValueError('Arms do not have the same information')
                text = messages[0]['content']
                if any(term in text for term in ['"userid"', '"weight"', '"sex"', 'QSP5', 'MIDUS', 'Do not mechanically treat a past price change']):
                    raise ValueError('Non-whitelisted field in prompt')
                bundle['messages_sha256'][ob.agent_id] = message_hash(messages)
                new_previews.append({'agent_id': ob.agent_id, 'messages': messages,
                                     'prompt_sha256': message_hash(messages)})
                size = len(json.dumps(messages, ensure_ascii=False).encode())
                reserve += (size+256)*.3/1e6+1024*1.2/1e6
                # Explicit planning assumption only: ~four UTF-8 bytes/token,
                # 300 output tokens; budget enforcement uses the byte bound.
                estimate += (size/4*.3+300*1.2)/1e6
            for ob in observations:
                build_messages(ob, bundle)
            new = cfg.model_copy(deep=True); new.decision_ref = REF
            new.decision_args = {'revision_format_bundle': bundle, 'prompt_version': PROMPT,
                                 'llm_kind': 'scripted', 'seed': 42, 'retry_max': 0,
                                 'max_prompt_chars': 30000}
            dump(dest/f'simulation_{arm}.json', new.model_dump(mode='json'))
            dump(dest/f'preview_{arm}.json', new_previews)
            for repeat in [1, 2]:
                cap = math.ceil((reserve+1e-6)*1e4)/1e4
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'cap_usd': cap,
                             'run_id': f'{out.name}-{month}-{arm}-r{repeat}'})
                reserve_total += reserve; estimate_total += estimate
        pair_count += N
        dump(dest/'population.json', pop.model_dump(mode='json'))
        dump(dest/'environment.json', env.model_dump(mode='json'))
    if len(selected_links) != pair_count:
        raise ValueError('Private evaluation roster mismatch')
    jobs = [jobs[i] for i in np.random.default_rng(SEED).permutation(len(jobs))]
    cap = math.ceil(sum(j['cap_usd'] for j in jobs)*2)/2
    protocol = {k: old[k] for k in ['research_line', 'model', 'official_advertised_version',
        'model_identity_limit', 'temperature', 'max_tokens', 'thinking', 'retry_max',
        'price_input_per_mtok', 'price_output_per_mtok', 'pricing_url', 'baseline_refs',
        'q8', 'aggregation', 'intervals']}
    protocol.update(id='sce-revision-format-pilot-v1', registered_at_utc=datetime.now(timezone.utc).isoformat(),
        months=list(MONTHS), n_per_month=N, sampling_seed=SEED,
        sampling='Uniform seeded subsample of the existing frozen 48-person roster; no target answers used.',
        generation_repeats=[1, 2], arms=list(ARMS), planned_calls=len(jobs)*N,
        pricing_verified_date='2026-10-15', budget_cap_usd=cap,
        comparison='Same P/E, actual previous Q8/Q9 and earlier summaries, questionnaire and shared state instruction; response representation only differs.',
        primary_contrast='revision minus direct on cross-section W1',
        candidate_gate='Primary W1 paired-person upper 95% bound < 0; center MAE and delta W1 points no worse; new scorable fraction >=99%. Pilot continuation only, not overall success.',
        missing_previous_Q8='Report absolute point_pct for that respondent, still revise Q9; no imputation from Q9 mean, no exclusion.',
        missing_previous_Q8_selected_count=missing,
        neutral_question='No required adjustment size/direction, no fixed inertia parameter or forced dispersion.',
        no_information_change='Common context including prior and forecast window verified for every pair. Two repeated generations measure same-message variation; not a behavioural no-news causal test.',
        support='Common truth/prior/scorable support for both arms and past baselines; failures counted explicitly, never replaced or normalized.',
        truth_isolation='Only existing roster/preview/P/E read in preparation; current Q8/Q9 enter evaluation only.',
        limits=['All four months are previously inspected development periods; no independent validation claim.',
                'Conditional returner A using real past answers; not recursive B or a national headline.',
                'Uniform subsample of an earlier selected roster, not a fresh nationally representative population.',
                'Old 2020Q4 synthetic CE shares are retrospective for 2020-04; this is an A diagnostic, not strict real-time B.',
                'Delta-format arithmetic may fail or alter anchoring. Invalid mass is rejected, never clipped/normalized.',
                'Model alias may change; returned IDs/fingerprints are recorded but do not verify training cutoff.',
                'Engine seeds do not fix API random draws; old batches are descriptive background only.',
                'Modified response format is not the unmodified official survey interface.'],
        no_tuning_after_run=True)
    dump(out/'protocol.json', protocol); dump(out/'evaluation_links_private.json', selected_links)
    manifest = {'status': 'prepared_requires_authorization_record_and_dry_run',
        'source_sha256': sources, 'prepared_file_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')},
        'jobs': jobs, 'planned_calls': protocol['planned_calls'], 'same_context_pairs_verified': pair_count,
        'sum_job_caps_usd': sum(j['cap_usd'] for j in jobs), 'conservative_reservation_usd': reserve_total,
        'estimated_peak_cost_usd': estimate_total, 'estimate_assumption': 'UTF-8 bytes/4 input tokens and 300 output tokens; planning only',
        'proposed_cap_usd': cap, 'new_api_calls': 0, 'protocol_sha256': sha(out/'protocol.json')}
    dump(out/'manifest.json', manifest)
    return manifest
