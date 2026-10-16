"""Prepare a Q1-only conditional reconstruction pilot without reading targets."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig

from .household_finance_input import ARMS, SCHEMA_VERSION, validate_household_finance_record
from .household_finance_runtime import REF, PROMPT, transform, build_messages
from .information_update_runtime import build_messages as parent_messages
from .model import SCEEnvironmentProvider
from .prior_belief_experiment import message_hash
from .evaluation.expanded_state import dump, sha

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'outputs/sce_cognition_trial_20261016_v4'
FRAME = ROOT / 'outputs/sce_population_associations_20261015_v1/analysis_frame_private.parquet'
TRUTH = ROOT / 'outputs/sce_information_update_evaluation_20261014_v1/cases_private.json'
TRUTH_BINS = ROOT / 'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'
MONTHS = (202004, 202105, 202111, 202203)
SEED = 20261016
N = 24


def previous_month(month):
    return month - 1 if month % 100 > 1 else (month // 100 - 1) * 100 + 12


def q1_records(links, frame, cache_sha256):
    """Only same-person current/adjacent Q1; no outcome columns accepted."""
    if set(frame.columns) != {'date', 'userid', 'financial_change'}:
        raise ValueError('Only identifier/month/Q1 whitelist may enter preparation')
    if frame.duplicated(['date', 'userid']).any():
        raise ValueError('Duplicate Q1 source person-month')
    lookup = frame.set_index(['date', 'userid'])['financial_change']

    def code(month, person):
        raw = lookup.get((month, person), None)
        if raw is None or pd.isna(raw):
            return None
        if isinstance(raw, (bool, np.bool_)) or not math.isfinite(float(raw)) or float(raw) != int(raw) or not 1 <= int(raw) <= 5:
            raise ValueError('Q1 source value is not an allowed category')
        return int(raw)

    result = {}
    for link in links:
        month, person = int(link['month']), int(link['userid'])
        prior_month = previous_month(month)
        current, prior = code(month, person), code(prior_month, person)
        record = {'schema_version': SCHEMA_VERSION,
            'research_line': 'A_conditional_returner_reconstruction', 'target_month': month,
            'current_q1_code': current, 'current_q1_source_month': month if current is not None else None,
            'previous_q1_code': prior, 'previous_q1_source_month': prior_month if prior is not None else None,
            'current_source_sha256': cache_sha256 if current is not None else None,
            'previous_source_sha256': cache_sha256 if prior is not None else None}
        validate_household_finance_record(record)
        key = (month, link['agent_id'])
        if key in result:
            raise ValueError('Duplicate input roster')
        result[key] = record
    return result


def prepare(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output required')
    parent = json.loads((PARENT / 'manifest.json').read_text())
    sources = {str((PARENT / 'manifest.json').relative_to(ROOT)): sha(PARENT / 'manifest.json')}

    def frozen(name):
        path = PARENT / name
        if sha(path) != parent['prepared_file_sha256'][name]:
            raise ValueError('Frozen parent input drift: ' + name)
        sources[str(path.relative_to(ROOT))] = sha(path)
        return json.loads(path.read_text())

    old = frozen('protocol.json')
    links = frozen('evaluation_links_private.json')
    if Counter(r['month'] for r in links) != Counter({m: N for m in MONTHS}):
        raise ValueError('Existing 4 x 24 fixed roster required')
    summary = json.loads((FRAME.parent / 'summary.json').read_text())
    cache_sha = sha(FRAME)
    if cache_sha != summary['analysis_frame_sha256']:
        raise ValueError('Q1 source cache changed')
    sources[str(FRAME.relative_to(ROOT))] = cache_sha
    sources[str((FRAME.parent / 'summary.json').relative_to(ROOT))] = sha(FRAME.parent / 'summary.json')
    # Physical column projection: neither current Q8/Q9 nor extra beliefs are read.
    frame = pd.read_parquet(FRAME, columns=['date', 'userid', 'financial_change'])
    records = q1_records(links, frame, cache_sha)
    sources[str(TRUTH.relative_to(ROOT))] = sha(TRUTH)  # pin only, not parse
    sources[str(TRUTH_BINS.relative_to(ROOT))] = sha(TRUTH_BINS)
    for name in ('scripts/run_sce_household_finance_trial.py', 'scripts/export_study_runtime.py'):
        sources[name] = sha(ROOT / name)
    for path in (ROOT / 'studies/sce_inflation_expectations').rglob('*.py'):
        relative = path.relative_to(ROOT / 'studies/sce_inflation_expectations')
        if '__pycache__' not in relative.parts and 'evaluation' not in relative.parts:
            sources[str(path.relative_to(ROOT))] = sha(path)

    out.mkdir(parents=True)
    jobs, coverage, sample_text = [], {}, []
    reserve_total = estimate_total = 0.
    for month in MONTHS:
        dest = out / str(month)
        dest.mkdir()
        pop = PopulationBundle.model_validate(frozen(f'{month}/population.json'))
        env = EnvironmentBundle.model_validate(frozen(f'{month}/environment.json'))
        cfg = SimulationConfig.model_validate(frozen(f'{month}/simulation_label_only.json'))
        old_previews = {r['agent_id']: r for r in frozen(f'{month}/preview_label_only.json')}
        ids = {p.agent_id for p in pop.personas}
        if len(ids) != N or ids != set(old_previews):
            raise ValueError('Frozen parent population/preview mismatch')
        month_records = {aid: records[month, aid] for aid in sorted(ids)}
        payload_path = dest / 'household_finance_payloads.json'
        dump(payload_path, month_records)
        counts = Counter(r['current_q1_code'] for r in month_records.values())
        coverage[str(month)] = {'n': N,
            'numeracy': dict(Counter(p.attributes['numeracy'] for p in pop.personas)),
            'current_q1_counts': {str(k): v for k, v in sorted(counts.items(), key=lambda x: str(x[0]))},
            'current_q1_known': sum(r['current_q1_code'] is not None for r in month_records.values()),
            'previous_q1_known': sum(r['previous_q1_code'] is not None for r in month_records.values())}
        provider = SCEEnvironmentProvider(env.model_copy(deep=True))
        provider.audit_dir = None
        provider.reset(42)
        provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        for arm in ARMS:
            bundle = {'arm': arm, 'parent': deepcopy(cfg.decision_args['cognition_bundle']['parent']),
                'messages_sha256': {}}
            previews, reserve, estimate = [], 0., 0.
            for ob in observations:
                original = parent_messages(ob, bundle['parent'])
                messages = transform(original, arm, month_records[ob.agent_id])
                if transform(original, 'baseline', month_records[ob.agent_id]) != old_previews[ob.agent_id]['messages']:
                    raise ValueError('Baseline differs from latest frozen direct/label-only input')
                content = messages[0]['content']
                if any(term in content for term in ('"userid"', '"weight"', '"sex"', 'QSP5', 'MIDUS', 'Your earlier survey responses:')):
                    raise ValueError('Non-whitelisted prompt information')
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
            new.decision_args = {'household_finance_bundle': bundle, 'prompt_version': PROMPT,
                'household_finance_payloads_file': str(payload_path),
                'household_finance_payloads_sha256': sha(payload_path), 'llm_kind': 'scripted',
                'seed': 42, 'retry_max': 0, 'max_prompt_chars': 40000}
            dump(dest / f'simulation_{arm}.json', new.model_dump(mode='json'))
            dump(dest / f'preview_{arm}.json', previews)
            sample_text.append(f'{month} / {arm}\n'+previews[0]['messages'][0]['content'])
            for repeat in (1, 2):
                cap = math.ceil((reserve + 1e-6) * 1e4) / 1e4
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'cap_usd': cap,
                    'run_id': f'{out.name}-{month}-{arm}-r{repeat}'})
                reserve_total += reserve
                estimate_total += estimate
        dump(dest / 'population.json', pop.model_dump(mode='json'))
        dump(dest / 'environment.json', env.model_dump(mode='json'))

    jobs = [jobs[i] for i in np.random.default_rng(SEED + 10).permutation(len(jobs))]
    cap = math.ceil(sum(j['cap_usd'] for j in jobs) * 2) / 2
    protocol = {k: old[k] for k in ('research_line', 'model', 'official_advertised_version',
        'model_identity_limit', 'temperature', 'max_tokens', 'thinking', 'retry_max',
        'price_input_per_mtok', 'price_output_per_mtok', 'pricing_url', 'baseline_refs', 'q8', 'aggregation',
        'sampling_seed', 'stratum_n', 'auxiliary_weights')}
    protocol.update(id='sce-household-finance-pilot-v1', registered_at_utc=datetime.now(timezone.utc).isoformat(),
        months=list(MONTHS), n_per_month=N, generation_repeats=[1, 2], arms=list(ARMS),
        planned_calls=len(jobs) * N, budget_cap_usd=cap, pricing_verified_date='2026-10-16',
        sampling='Reuse fixed 24-person cognition roster:14 High and10 Low; Low oversampled; not a national or Q1-stratified sample. No current inflation answer used for selection.',
        primary_metric='individual_density_mean_mae_pp', primary_contrast='financial_facts minus baseline',
        secondary_contrasts=['financial_perspective minus financial_facts', 'financial_perspective minus baseline'],
        update_mae_identity='Against the same observed prior, individual update absolute error equals current individual density-mean absolute error algebraically; these are not independent successes.',
        comparison='Facts minus baseline changes the Q1 information package. Perspective minus facts adds only a non-directional household-viewpoint instruction. No invented events or coefficient offsets.',
        primary_direction='Smaller is better; all intervals exploratory paired person-cluster bootstrap.',
        intervals='1000 paired person-cluster draws retaining all months and both generations; equal month/repeat cells; no confirmatory multiplicity claim.',
        guardrails=['valid_fraction >= 0.99 and scorable_fraction >= 0.99 in every arm',
                    'q9_center_mae_pp and cross_section_w1_pp point changes <= 0'],
        candidate_gate='Detailed-vs-baseline individual-density-mean-MAE upper exploratory95% bound<0, center and W1 point changes<=0, all-arm coverage>=99%. Pilot continuation only.',
        support='All three arms and both repeats scorable for a retained person-month; report human missingness separately from model failures. Q8 support separate.',
        financial_groups='Current Q1 worse=1/2, same=3, better=4/5. Same-person group medians compared with real groups per month/repeat; suppress a gap if either group has fewer than3 common people. Five codes descriptive only.',
        truth_isolation='Preparation projects only date/userid/financial_change from hash-verified cache; no current Q8/Q9 parsed. Runtime receives anonymous Q1 sidecar, existing P/E and observed historical prior only.',
        information_boundary='Current Q1 is contemporaneous private household assessment, explicit A auxiliary condition; public E retains existing cutoff. Does not certify Q1 or prior answers as available inputs to real-time B.',
        reused_paid_calls=0,
        old_direct_reference='Old identical baseline messages may be compared descriptively; all primary arms are newly generated contemporaneously.',
        no_tuning_after_run=True,
        limits=['Four inspected development months; not independent validation.',
                'Q1 is subjective finances relative to12 months earlier; adjacent category shifts are not measured month-on-month income shocks.',
                'Current Q1 can itself reflect inflation beliefs; not a causal Q1 experiment or strict B forecast.',
                'Prompt length and explicit instruction effects cannot be separated from household-memory mechanisms by this pilot alone.',
                '24-person fixed roster has only2 much-worse person-months; no claim for that subgroup or national representativeness.',
                'Two generations are model variability, not additional respondents or a provider-enforced RNG seed.',
                'Observed and model raw Q9 use the same frozen approximate fitter; official derived fields auxiliary only.'])
    dump(out / 'protocol.json', protocol)
    dump(out / 'evaluation_links_private.json', links)
    dump(out / 'coverage.json', coverage)
    (out / 'prompt_preview.txt').write_text('\n\n'.join(sample_text)+'\n')
    manifest = {'status': 'prepared_requires_authorization_record_and_dry_run',
        'parent_folder': str(PARENT.relative_to(ROOT)), 'source_sha256': sources,
        'prepared_file_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()},
        'jobs': jobs, 'planned_calls': protocol['planned_calls'], 'same_context_pairs_verified': N * len(MONTHS),
        'sum_job_caps_usd': sum(j['cap_usd'] for j in jobs), 'conservative_reservation_usd': reserve_total,
        'estimated_peak_cost_usd': estimate_total,
        'estimate_assumption': 'UTF-8 bytes/4 input tokens and300 output tokens; reservation bytes+256 and max1024 output at peak uncached rates',
        'proposed_cap_usd': cap, 'new_api_calls': 0, 'protocol_sha256': sha(out / 'protocol.json')}
    dump(out / 'manifest.json', manifest)
    return manifest
