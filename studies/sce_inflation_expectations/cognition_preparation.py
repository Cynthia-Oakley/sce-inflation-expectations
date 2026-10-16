"""Prepare a frozen cognition-information pilot; current answers stay in evaluation."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig

from .model import SCEEnvironmentProvider
from .information_update_runtime import build_messages as parent_messages
from .cognition_input import load_records, question_catalog, SOURCE_SPECS, FIELDS, validate_cognition_record
from .cognition_runtime import ARMS, PROMPT, REF, transform, build_messages
from .prior_belief_experiment import message_hash
from .evaluation.expanded_state import dump, sha

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'outputs/sce_information_update_trial_20261014_v2'
TRUTH = ROOT / 'outputs/sce_information_update_evaluation_20261014_v1/cases_private.json'
TRUTH_BINS = ROOT / 'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'
MONTHS = (202004, 202105, 202111, 202203)
N = 24
SEED = 20261016
STRATUM_N = {'high': 14, 'low': 10}


def cached_history(folder, selected_links):
    """Reuse exact immutable records; bind the private person linkage and all source bytes."""
    folder = Path(folder).resolve()
    if not folder.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Only local ignored history cache allowed')
    manifest = json.loads((folder / 'manifest.json').read_text())
    used = {}

    def read(name):
        path = folder / name
        if sha(path) != manifest['prepared_file_sha256'][name]:
            raise ValueError('Historical cache changed: ' + name)
        used[str(path.relative_to(ROOT))] = sha(path)
        return json.loads(path.read_text())

    old_links = read('evaluation_links_private.json')
    identities = {(r['month'], r['agent_id']): r['userid'] for r in old_links}
    payloads = {month: read(f'{month}/cognition_payloads.json') for month in MONTHS}
    result = []
    checked_source_hashes = {}
    for link in selected_links:
        if identities.get((link['month'], link['agent_id'])) != link['userid']:
            raise ValueError('Cached cognition record belongs to a different respondent')
        record = payloads[link['month']][link['agent_id']]
        validate_cognition_record(record)
        if record['target_month'] != link['month']:
            raise ValueError('Cached historical month mismatch')
        for item in record['items']:
            path = item['source_path']
            if path is not None:
                if path not in checked_source_hashes:
                    checked_source_hashes[path] = sha(ROOT / path)
                if checked_source_hashes[path] != item['source_sha256']:
                    raise ValueError('Historical raw source changed')
        result.append(record)
    used[str((folder / 'manifest.json').relative_to(ROOT))] = sha(folder / 'manifest.json')
    return result, used


def prepare(out, history_cache=None):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output required')
    parent = json.loads((PARENT / 'manifest.json').read_text())

    def frozen(name):
        path = PARENT / name
        if sha(path) != parent['prepared_file_sha256'][name]:
            raise ValueError('Frozen parent input drift: ' + name)
        return json.loads(path.read_text())

    old = frozen('protocol.json')
    links = frozen('evaluation_links_private.json')  # roster, never current responses
    inputs = {}
    selected_links = []
    for month in MONTHS:
        inputs[month] = {name: frozen(f'{month}/{name}') for name in (
            'population.json', 'environment.json', 'simulation_dated_information.json',
            'preview_dated_information.json')}
        pop = inputs[month]['population.json']
        chosen, design_weights = set(), {}
        rng = np.random.default_rng(SEED + month)
        for label, count in STRATUM_N.items():
            ids = sorted(p['agent_id'] for p in pop['personas'] if p['attributes']['numeracy'] == label)
            if len(ids) < count:
                raise ValueError('Insufficient cognition stratum: ' + str(month) + label)
            picked = rng.choice(ids, count, replace=False).tolist()
            chosen.update(picked)
            design_weights.update({aid: len(ids) / count for aid in picked})
        for r in links:
            if r['month'] == month and r['agent_id'] in chosen:
                selected_links.append({**deepcopy(r), 'raw_parent_survey_weight': r['survey_weight'],
                    'sampling_weight': design_weights[r['agent_id']],
                    'survey_weight': r['survey_weight'] * design_weights[r['agent_id']]})
    if len(selected_links) != N * len(MONTHS):
        raise ValueError('Roster cardinality mismatch')

    requests = [{'userid': r['userid'], 'month': r['month']} for r in selected_links]
    if history_cache is None:
        records, cached_sources = load_records(requests, root=ROOT), {}
    else:
        records, cached_sources = cached_history(history_cache, selected_links)
    if len(records) != len(requests):
        raise ValueError('History loader cardinality mismatch')
    lookup = {(r['month'], r['agent_id']): record for r, record in zip(selected_links, records)}
    sources = {**cached_sources, str((PARENT / 'manifest.json').relative_to(ROOT)): sha(PARENT / 'manifest.json'),
               str(TRUTH.relative_to(ROOT)): sha(TRUTH),
               str(TRUTH_BINS.relative_to(ROOT)): sha(TRUTH_BINS)}  # hash only; never parse truth
    catalog = question_catalog()
    sources[catalog['questionnaire_path']] = sha(ROOT / catalog['questionnaire_path'])
    for spec in SOURCE_SPECS:
        if spec['start'] < max(MONTHS):
            sources[spec['path']] = sha(ROOT / spec['path'])
    for name in ('scripts/run_sce_cognition_trial.py', 'scripts/export_study_runtime.py'):
        sources[name] = sha(ROOT / name)
    for path in (ROOT / 'studies/sce_inflation_expectations').rglob('*.py'):
        if '__pycache__' not in path.parts and 'evaluation' not in path.relative_to(ROOT / 'studies/sce_inflation_expectations').parts:
            sources[str(path.relative_to(ROOT))] = sha(path)

    out.mkdir(parents=True)
    jobs = []
    reserve_total = estimate_total = 0.0
    coverage = {}
    for month in MONTHS:
        dest = out / str(month)
        dest.mkdir()
        chosen = {r['agent_id'] for r in selected_links if r['month'] == month}
        pop = PopulationBundle.model_validate(inputs[month]['population.json'])
        pop.personas = [p for p in pop.personas if p.agent_id in chosen]
        env = EnvironmentBundle.model_validate(inputs[month]['environment.json'])
        cfg = SimulationConfig.model_validate(inputs[month]['simulation_dated_information.json'])
        parent_preview = {r['agent_id']: r['prompt_sha256'] for r in inputs[month]['preview_dated_information.json']}
        month_records = {aid: lookup[month, aid] for aid in sorted(chosen)}
        payload_path = dest / 'cognition_payloads.json'
        dump(payload_path, month_records)
        coverage[str(month)] = {'n': N, 'numeracy': dict(Counter(p.attributes['numeracy'] for p in pop.personas)),
            'item_statuses': {field: dict(Counter(item['status'] for record in month_records.values()
                 for item in record['items'] if item['field'] == field)) for field in FIELDS},
            'fully_answered': sum(all(item['status'] == 'answered' for item in record['items'])
                                  for record in month_records.values())}
        provider = SCEEnvironmentProvider(env.model_copy(deep=True))
        provider.audit_dir = None
        provider.reset(42)
        provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        for arm in ARMS:
            bundle = {'arm': arm, 'parent': deepcopy(cfg.decision_args['information_update_bundle']),
                      'messages_sha256': {}}
            previews = []
            reserve = estimate = 0.0
            for ob in observations:
                original = parent_messages(ob, bundle['parent'])
                if message_hash(original) != parent_preview[ob.agent_id]:
                    raise ValueError('Parent message drift')
                messages = transform(original, arm, month_records[ob.agent_id])
                content = messages[0]['content']
                forbidden = ('"userid"', '"weight"', '"sex"', 'QSP5', 'MIDUS')
                if any(term in content for term in forbidden):
                    raise ValueError('Non-whitelisted prompt field')
                digest = message_hash(messages)
                bundle['messages_sha256'][ob.agent_id] = digest
                previews.append({'agent_id': ob.agent_id, 'messages': messages, 'prompt_sha256': digest})
                size = len(json.dumps(messages, ensure_ascii=False).encode())
                reserve += (size + 256) * .3 / 1e6 + 1024 * 1.2 / 1e6
                estimate += (size / 4 * .3 + 300 * 1.2) / 1e6
            for ob in observations:
                build_messages(ob, bundle, month_records)
            new = cfg.model_copy(deep=True)
            new.decision_ref = REF
            new.decision_args = {'cognition_bundle': bundle, 'prompt_version': PROMPT,
                'cognition_payloads_file': str(payload_path), 'cognition_payloads_sha256': sha(payload_path),
                'llm_kind': 'scripted', 'seed': 42, 'retry_max': 0, 'max_prompt_chars': 40000}
            dump(dest / f'simulation_{arm}.json', new.model_dump(mode='json'))
            dump(dest / f'preview_{arm}.json', previews)
            for repeat in (1, 2):
                cap = math.ceil((reserve + 1e-6) * 1e4) / 1e4
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'cap_usd': cap,
                             'run_id': f'{out.name}-{month}-{arm}-r{repeat}'})
                reserve_total += reserve
                estimate_total += estimate
        dump(dest / 'population.json', pop.model_dump(mode='json'))
        dump(dest / 'environment.json', env.model_dump(mode='json'))
    jobs = [jobs[i] for i in np.random.default_rng(SEED).permutation(len(jobs))]
    cap = math.ceil(sum(j['cap_usd'] for j in jobs) * 2) / 2
    protocol = {k: old[k] for k in ('research_line', 'model', 'official_advertised_version',
        'model_identity_limit', 'temperature', 'max_tokens', 'thinking', 'retry_max',
        'price_input_per_mtok', 'price_output_per_mtok', 'pricing_url', 'baseline_refs',
        'q8', 'aggregation')}
    protocol.update(id='sce-cognition-pilot-v1', registered_at_utc=datetime.now(timezone.utc).isoformat(),
        months=list(MONTHS), n_per_month=N, sampling_seed=SEED, generation_repeats=[1, 2],
        arms=list(ARMS), planned_calls=len(jobs) * N, budget_cap_usd=cap,
        pricing_verified_date='2026-10-16',
        sampling='Fixed-seed subsample of each frozen 48-person roster:14 High and10 Low; Low oversampled for mechanism coverage, no current target answers used.',
        stratum_n=STRATUM_N,
        auxiliary_weights='Original SCE weight multiplied by within-parent stratum inverse inclusion probability; main paired analysis unweighted and equal-month. Neither implies national representativeness.',
        comparison='All arms retain original High/Low. Detailed arms add seven historical actual quiz responses. Only detailed-arm contrast isolates presentation.',
        primary_contrast='faithful_paraphrase minus question_answer on individual density-IQR paired MAE',
        secondary_contrasts=['question_answer minus label_only', 'faithful_paraphrase minus label_only'],
        primary_metric='individual_density_iqr_mae_pp',
        exploratory_probability_shape='Half the L1 distance between respondent ten-bin probability vectors, in probability percentage points (0-100); not inflation-rate percentage points. Also retain per-cell mean-bin profiles.',
        guardrails=['valid_fraction >= 0.99 in every arm', 'scorable_fraction >= 0.99 in every arm',
                    'sample_center_mae_pp and cross_section_w1_pp point changes <= 0'],
        candidate_gate='For a given detailed-vs-label contrast: IQR-MAE upper exploratory 95% bound <0, center MAE and cross-section W1 point changes <=0, each arm valid/scorable >=99%. Pilot continuation, not confirmed success.',
        intervals='Paired person-cluster bootstrap, same person retained across months and both generation repeats; equal month and repeat weights. All contrast intervals exploratory, no confirmatory multiplicity claim.',
        support='All three arms and both repeats must be scorable for each retained person-month; report excluded assigned rows. Validity below99%: accuracy descriptions only, no successful-effect inference.',
        truth_isolation='Preparation reads only existing roster/P/E/previous beliefs and whitelist historical quiz columns; current Q8/Q9 are never parsed here. Truth file is pinned by hash for separate evaluation.',
        cognitive_sources='Each item taken from the same respondent strictly before target month; missing/unmapped is explicit; no standard answer, feedback, correct/incorrect labels or invented psychology.',
        reused_paid_calls=0,
        old_direct_reference='Existing identical label-only prompt hashes may be compared descriptively; no mixing old model batches into contemporaneous randomized contrasts.',
        no_tuning_after_run=True,
        limits=['Four previously inspected development months; not independent validation.',
                'A conditional reconstruction with real historical priors, not autonomous B forecasting.',
                '24-person subset per month is not a national probability sample.',
                'Label versus detailed arms differ in information quantity and include two extra financial items; not a pure wording effect.',
                'Actual incorrect quiz answers are persona evidence; adding them can itself expose numerical anchors. Effects do not prove a human cognitive mechanism.',
                'Two generations measure API variability, not two independent respondents or provider-fixed sampling seeds.',
                'Both model and observed ten-bin answers use the same frozen approximate Q9 fitter. Official derived fields are auxiliary fitting diagnostics, not mixed into the primary score.',
                'Past CE and historical-answer availability follow the existing A protocol and are not newly certified strict B inputs.'])
    dump(out / 'protocol.json', protocol)
    dump(out / 'evaluation_links_private.json', selected_links)
    dump(out / 'coverage.json', coverage)
    dump(out / 'question_catalog.json', catalog)
    manifest = {'status': 'prepared_requires_authorization_record_and_dry_run',
        'source_sha256': sources,
        'prepared_file_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')},
        'jobs': jobs, 'planned_calls': protocol['planned_calls'], 'same_context_pairs_verified': N * len(MONTHS),
        'sum_job_caps_usd': sum(j['cap_usd'] for j in jobs),
        'conservative_reservation_usd': reserve_total, 'estimated_peak_cost_usd': estimate_total,
        'estimate_assumption': 'UTF-8 bytes/4 input tokens and300 output tokens; reservation uses bytes+256 and max1024 output at peak uncached rates',
        'proposed_cap_usd': cap, 'new_api_calls': 0, 'protocol_sha256': sha(out / 'protocol.json')}
    dump(out / 'manifest.json', manifest)
    return manifest
