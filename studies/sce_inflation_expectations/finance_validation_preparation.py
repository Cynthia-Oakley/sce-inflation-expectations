"""Freeze a two-arm Q1 replication in other months; no current inflation targets read.

Reuse audited P/E and observed past beliefs. This is conditional historical
reconstruction, not an untouched holdout or a real-time forecast.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig

from .household_finance_input import render_household_finance_block
from .household_finance_preparation import q1_records, previous_month
from .household_finance_runtime import REF, PROMPT, transform, build_messages
from .expanded_state_runtime import build_messages as expanded_messages
from .anchor_role_runtime import build_messages as anchor_messages
from .behavior_prompt_blocks import ANCHOR_BLOCK, insert_block
from .information_update_runtime import time_index, transform as dated_transform
from .model import SCEEnvironmentProvider
from .prior_belief_experiment import message_hash
from .revision_format_runtime import REPLY_MARKER
from .evaluation.expanded_state import dump, sha

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'outputs/sce_expanded_state_trial_20261014_v3'
FRAME = ROOT / 'outputs/sce_population_associations_20261015_v1/analysis_frame_private.parquet'
REFERENCE = ROOT / 'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'
MONTHS = (202206, 202306, 202410, 202509)
ARMS = ('baseline', 'financial_facts')
N, SEED = 48, 20261017


def proportional_sample(personas, month, n=N, seed=SEED):
    """Largest-remainder numeracy allocation; no outcomes or Q1 used to select.

    Sampling is conditional on the archived first-stage SRS of 96. Returned
    second-stage probabilities are conditional; do not call these unconditional
    population inclusion probabilities.
    """
    groups = {}
    for persona in personas:
        groups.setdefault(persona.attributes.get('numeracy', 'unknown'), []).append(persona.agent_id)
    total = sum(map(len, groups.values()))
    if len({p.agent_id for p in personas}) != total or not 0 < n <= total:
        raise ValueError('Unique nonempty sampling frame and feasible size required')
    raw = {key: n * len(ids) / total for key, ids in groups.items()}
    sizes = {key: math.floor(value) for key, value in raw.items()}
    order = sorted(groups, key=lambda key: (-(raw[key] - sizes[key]), key))
    for key in order[:n - sum(sizes.values())]:
        sizes[key] += 1
    if any(size < 1 for size in sizes.values()):
        raise ValueError('Each observed numeracy stratum must have positive inclusion')
    selected, probabilities = set(), {}
    for index, key in enumerate(sorted(groups)):
        ids = sorted(groups[key])
        rng = np.random.default_rng(np.random.SeedSequence([seed, month, index]))
        chosen = rng.choice(ids, sizes[key], replace=False).tolist()
        selected.update(chosen)
        probabilities.update({aid: sizes[key] / len(ids) for aid in chosen})
    if len(selected) != n:
        raise ValueError('Sampling failed to fill the registered roster')
    return selected, probabilities, {
        'parent_stratum_n': {key: len(ids) for key, ids in sorted(groups.items())},
        'selected_stratum_n': dict(sorted(sizes.items())),
        'tie_rule': 'largest fractional remainder, then alphabetic category',
    }


def registered_protocol(cap):
    return {
        'id': 'sce-household-finance-crossmonth-v1',
        'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'research_line': 'A_conditional_returner_reconstruction',
        'months': list(MONTHS), 'n_per_month': N, 'arms': list(ARMS),
        'generation_repeats': [1, 2], 'planned_calls': N * len(MONTHS) * len(ARMS) * 2,
        'sampling_seed': SEED, 'dispatch_order_seed': SEED + 10,
        'model': 'deepseek-flash', 'official_advertised_version': 'DeepSeek-V4.1-Flash',
        'model_identity_limit': 'Mutable alias; no verified fixed weights or training cutoff',
        'temperature': .5, 'max_tokens': 1024, 'thinking': 'disabled', 'retry_max': 0,
        'price_input_per_mtok': .3, 'price_output_per_mtok': 1.2,
        'pricing_url': 'https://api-docs.deepseek.com/quick_start/pricing/',
        'pricing_verified_date': '2026-10-17', 'budget_cap_usd': cap,
        'comparison': 'Exact financial_facts block from the completed pilot versus the same base without it; no perspective cue, cognition answer block or purchase-frequency block.',
        'month_selection': 'The four archived eight-period evaluation months, chosen for coverage across high inflation and later periods; none was used to tune Q1 wording. Previously inspected old simulations and full-sample associations exist. Not a pristine project-level blind holdout.',
        'sampling': 'Within each archived SRS96 roster, proportionally sample48 by numeracy with largest-remainder rounding and fixed seed. No current Q8/Q9 or Q1 used to select; no missing-target replacement.',
        'primary_metric': 'q9_center_mae_pp', 'primary_weight': 'design_survey_weight',
        'primary_contrast': 'financial_facts minus baseline',
        'aggregation': 'Per month/repeat weighted median of fitted individual Q9 means for both model and observed same roster, then absolute error; equal average of8 month/repeat cells. Left-inverse empirical CDF throughout.',
        'auxiliary_weights': 'Equal-person results reported separately. Primary evaluation weight=survey_weight / ((96/eligible_returners)*(selected_stratum_n/parent_stratum_n)); this is a sequential two-stage design weight, not proof of national representativeness.',
        'secondary_metrics': ['individual_density_mean_mae_pp', 'cross_section_w1_pp', 'delta_w1_pp', 'across_person_iqr_pp', 'individual_iqr_mae_pp', 'q8_sample_center_mae_pp'],
        'macro_replication_screen': 'Primary center point contrast<0 and at least3 of4 monthly mean contrasts<=0; exploratory replication screen only.',
        'overall_upgrade_rule': 'Macro screen alone is insufficient. Any worsening of personal density-mean MAE or cross-sectional W1 is explicitly a tradeoff; no overall upgrade. Report paired intervals and monthly results, never select another weight/prompt after inspecting results.',
        'coverage_rule': 'Model valid and scorable fractions>=.99 in each arm; human missingness separate. All-arm/both-repeat common Q9 support, Q8 separate. Never resample to replace a missing or extreme current outcome.',
        'intervals': '1000 paired person-cluster resamples retaining all available months/repeats for a person; exploratory.4 selected calendar months do not support a population claim over time. Monthly/repeat values always shown.',
        'baseline_refs': ['copy_previous', 'history_anchor_half'],
        'baseline_history': 'Same own valid prior bins and strict earlier histories, coefficient.5 fixed from existing baseline, not fitted to new months; scalar history anchor has no invented density.',
        'q8': 'Separate secondary signed point response; abs<=100 sensitivity as in the existing evaluator; report exclusions.',
        'financial_groups': 'worse Q1=1/2, same=3, better=4/5; other groups age/numeracy/income/region. Suppress group gaps unless both groups have>=3 common people in a cell; no subgroup claim from tiny samples.',
        'truth_isolation': 'Only date/userid/financial_change/survey_date projected from hash-verified cache. Current Q8/Q9 are not loaded in preparation; only reference hash pinned. Actual current targets first read by the evaluation stage after frozen execution.',
        'information_boundary': 'Current real Q1 and current demographics are explicitly retrospective A conditions; actual own prior Q8/Q9 and older summaries are supplied. Public E uses existing cutoffs. Not strict B, nationwide forecast, or free recursive belief simulation.',
        'generations': 'Two repeats are API variability, not additional people. Engine seeds42/43 do not imply provider-enforced identical random seeds.',
        'scorer': 'Same frozen approximate Q9 scorer for model and human raw bins; cannot claim exact official fitting.',
        'reused_paid_calls': 0, 'no_tuning_after_run': True,
        'limits': ['Returner-only conditional sample; four months are not enough to prove stability over all periods.',
                   'Q1 is subjective finances versus12 months earlier; current Q1 is not an identified exogenous income shock.',
                   'CE spending and Fed confidence remain synthetic proxies; NYT/gas snapshots do not gain strict historical-vintage certification from reuse.',
                   'Current target datasets have been explored in earlier aggregate research; only this preparation is target-isolated.'],
    }


def prepare(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output directory required')
    parent = json.loads((PARENT / 'manifest.json').read_text())
    sources = {str((PARENT / 'manifest.json').relative_to(ROOT)): sha(PARENT / 'manifest.json')}

    def frozen(name):
        path = PARENT / name
        if sha(path) != parent['prepared_file_sha256'][name]:
            raise ValueError('Archived input changed: ' + name)
        sources[str(path.relative_to(ROOT))] = sha(path)
        return json.loads(path.read_text())

    parent_links = frozen('evaluation_links_private.json')
    summary = json.loads((FRAME.parent / 'summary.json').read_text())
    cache_sha = sha(FRAME)
    if cache_sha != summary['analysis_frame_sha256']:
        raise ValueError('Q1 source cache changed')
    for path in (FRAME, FRAME.parent / 'summary.json', REFERENCE):
        sources[str(path.relative_to(ROOT))] = sha(path)
    frame = pd.read_parquet(FRAME, columns=['date', 'userid', 'financial_change', 'survey_date'])
    if frame.duplicated(['date', 'userid']).any():
        raise ValueError('Duplicate projected source row')
    q1frame = frame[['date', 'userid', 'financial_change']]
    dates = frame.set_index(['date', 'userid'])['survey_date']
    metadata = {row['month']: row for row in parent['months']}
    out.mkdir(parents=True)
    links, jobs, coverage, examples = [], [], {}, []
    total_reserve = total_estimate = 0.
    for month in MONTHS:
        dest = out / str(month)
        dest.mkdir()
        pop = PopulationBundle.model_validate(frozen(f'{month}/population.json'))
        if len(pop.personas) != 96 or metadata[month]['selected_n'] != 96:
            raise ValueError('Archived SRS96 first stage required')
        selected, pi2, allocation = proportional_sample(pop.personas, month)
        pop.personas = [p for p in pop.personas if p.agent_id in selected]
        pop.materialized_count = N
        env = EnvironmentBundle.model_validate(frozen(f'{month}/environment.json'))
        env.provider_args['persona_by_id'] = {p.agent_id: p.attributes for p in pop.personas}
        cfg = SimulationConfig.model_validate(frozen(f'{month}/simulation_self_update.json'))
        base = deepcopy(cfg.decision_args['expanded_bundle'])
        base['rows'] = {aid: base['rows'][aid] for aid in selected}
        base['baseline']['news']['rows'] = {aid: base['baseline']['news']['rows'][aid] for aid in selected}
        base['baseline']['labels'] = {aid: base['baseline']['labels'][aid] for aid in selected}
        originals = {p['agent_id']: p for p in frozen(f'{month}/preview_self_update.json')}
        past = {aid: row for aid, row in frozen(f'{month}/past_private.json').items() if aid in selected}
        chosen = [deepcopy(row) for row in parent_links if row['month'] == month and row['agent_id'] in selected]
        if len(chosen) != N or set(past) != selected:
            raise ValueError('Roster/past sidecar mismatch')
        pi1 = 96 / metadata[month]['eligible_n']
        for row in chosen:
            aid = row['agent_id']
            weight = float(row['survey_weight'])
            if not math.isfinite(weight) or weight <= 0:
                raise ValueError('Finite positive survey weight required')
            row.update(first_stage_probability=pi1, second_stage_probability=pi2[aid],
                       inclusion_probability=pi1 * pi2[aid],
                       design_survey_weight=weight / (pi1 * pi2[aid]))
        links.extend(chosen)
        records = {aid: record for (m, aid), record in q1_records(chosen, q1frame, cache_sha).items()}
        payload_path = dest / 'household_finance_payloads.json'
        dump(payload_path, records)
        dump(dest / 'past_private.json', past)
        provider = SCEEnvironmentProvider(env.model_copy(deep=True))
        provider.audit_dir = None
        provider.reset(42)
        provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        anchor = {'arm': 'belief_start', 'base': base, 'messages_sha256': {}}
        information = {'arm': 'dated_information', 'parent': anchor,
                       'time_index_by_id': {}, 'messages_sha256': {}}
        by_id = {row['agent_id']: row for row in chosen}
        for ob in observations:
            original = expanded_messages(ob, base)
            if original != originals[ob.agent_id]['messages']:
                raise ValueError('Reused P/E/prior no longer reproduces original message')
            anchored = insert_block(original, ANCHOR_BLOCK, require_prior=True)
            anchor['messages_sha256'][ob.agent_id] = message_hash(anchored)
        timing_audit = []
        for ob in observations:
            aid, uid = ob.agent_id, by_id[ob.agent_id]['userid']
            previous_day = pd.Timestamp(dates.loc[(previous_month(month), uid)])
            if pd.isna(previous_day) or previous_day.year * 100 + previous_day.month != previous_month(month):
                raise ValueError('Own adjacent previous response date required')
            news, policy = base['baseline']['news'], base['baseline']['policy']
            timing, detail = time_index(env.provider_args['signals_by_step']['0'], news['common_news'],
                news['rows'][aid]['personal_news'], policy, previous_day.date().isoformat(),
                env.provider_args['targets'][0]['as_of'])
            information['time_index_by_id'][aid] = timing
            dated = dated_transform(anchor_messages(ob, anchor), 'dated_information', timing)
            information['messages_sha256'][aid] = message_hash(dated)
            timing_audit.append({'agent_id': aid, **detail})
        dump(dest / 'publication_timing_audit_private.json', timing_audit)
        baseline_previews = None
        for arm in ARMS:
            bundle = {'arm': arm, 'parent': deepcopy(information), 'messages_sha256': {}}
            previews, reserve, estimate = [], 0., 0.
            for ob in observations:
                original = dated_transform(anchor_messages(ob, anchor), 'dated_information',
                                            information['time_index_by_id'][ob.agent_id])
                messages = transform(original, arm, records[ob.agent_id])
                text = messages[0]['content']
                if any(term in text for term in ('"userid"', '"weight"', '"sex"', 'QSP5', 'MIDUS', 'Q9_mean')):
                    raise ValueError('Non-whitelisted message field')
                if len(text) > 40000 or text.count(REPLY_MARKER) != 1:
                    raise ValueError('Message length/response boundary')
                digest = message_hash(messages)
                bundle['messages_sha256'][ob.agent_id] = digest
                previews.append({'agent_id': ob.agent_id, 'messages': messages, 'prompt_sha256': digest})
                size = len(json.dumps(messages, ensure_ascii=False).encode())
                reserve += (size + 256) * .3 / 1e6 + 1024 * 1.2 / 1e6
                estimate += (size / 4 * .3 + 300 * 1.2) / 1e6
            if arm == 'baseline':
                baseline_previews = {r['agent_id']: r['messages'] for r in previews}
            else:
                for row in previews:
                    expected = deepcopy(baseline_previews[row['agent_id']])
                    block = render_household_finance_block(arm, records[row['agent_id']])
                    expected[0]['content'] = expected[0]['content'].replace(REPLY_MARKER, block + REPLY_MARKER, 1)
                    if expected != row['messages']:
                        raise ValueError('More than the frozen Q1 block differs across arms')
            for ob in observations:
                build_messages(ob, bundle, records)
            config = cfg.model_copy(deep=True)
            config.decision_ref = REF
            config.decision_args = {'household_finance_bundle': bundle, 'prompt_version': PROMPT,
                'household_finance_payloads_file': str(payload_path),
                'household_finance_payloads_sha256': sha(payload_path), 'llm_kind': 'scripted',
                'seed': 42, 'retry_max': 0, 'max_prompt_chars': 40000}
            dump(dest / f'simulation_{arm}.json', config.model_dump(mode='json'))
            dump(dest / f'preview_{arm}.json', previews)
            examples.append(f'{month} / {arm}\n' + previews[0]['messages'][0]['content'])
            for repeat in (1, 2):
                cap = math.ceil((reserve + 1e-6) * 1e4) / 1e4
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'cap_usd': cap,
                             'run_id': f'{out.name}-{month}-{arm}-r{repeat}'})
                total_reserve += reserve
                total_estimate += estimate
        dump(dest / 'population.json', pop.model_dump(mode='json'))
        dump(dest / 'environment.json', env.model_dump(mode='json'))
        weights = np.array([row['design_survey_weight'] for row in chosen])
        coverage[str(month)] = {'n': N, 'eligible_returners_n': metadata[month]['eligible_n'],
            'as_of': env.provider_args['targets'][0]['as_of'], **allocation,
            'current_q1_known': sum(r['current_q1_code'] is not None for r in records.values()),
            'previous_q1_known': sum(r['previous_q1_code'] is not None for r in records.values()),
            'current_q1_counts': dict(Counter(str(r['current_q1_code']) for r in records.values())),
            'effective_weight_n': float(weights.sum() ** 2 / (weights @ weights)),
            'reused_public_E_and_news': True, 'fresh_news_or_MCP_calls': 0}
    cap = math.ceil(sum(job['cap_usd'] for job in jobs) * 2) / 2
    protocol = registered_protocol(cap)
    dump(out / 'protocol.json', protocol)
    dump(out / 'evaluation_links_private.json', links)
    dump(out / 'coverage.json', coverage)
    (out / 'prompt_preview.txt').write_text('\n\n'.join(examples) + '\n')
    for name in ('scripts/run_sce_finance_validation_trial.py', 'scripts/run_sce_household_finance_trial.py',
                 'scripts/export_study_runtime.py'):
        sources[name] = sha(ROOT / name)
    for path in (ROOT / 'studies/sce_inflation_expectations').rglob('*.py'):
        relative = path.relative_to(ROOT / 'studies/sce_inflation_expectations')
        if '__pycache__' not in relative.parts and 'evaluation' not in relative.parts:
            sources[str(path.relative_to(ROOT))] = sha(path)
    jobs = [jobs[index] for index in np.random.default_rng(SEED + 10).permutation(len(jobs))]
    manifest = {'status': 'prepared_requires_authorization_record_and_dry_run',
        'parent_folder': str(PARENT.relative_to(ROOT)), 'source_sha256': sources,
        'prepared_file_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()},
        'jobs': jobs, 'planned_calls': protocol['planned_calls'],
        'same_context_pairs_verified': N * len(MONTHS),
        'sum_job_caps_usd': sum(j['cap_usd'] for j in jobs),
        'conservative_reservation_usd': total_reserve, 'estimated_peak_cost_usd': total_estimate,
        'estimate_assumption': 'UTF8 bytes/4 input and300 output tokens; upper reservation bytes+256 and1024 output, peak uncached prices',
        'proposed_cap_usd': cap, 'new_api_calls': 0, 'protocol_sha256': sha(out / 'protocol.json')}
    dump(out / 'manifest.json', manifest)
    return manifest
