"""Assemble state-ready templates from existing news, price and persona blocks.

Only the state/timing insertion points change during recursive generation.
No current target responses or scored model responses are read in preparation.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import csv
import hashlib
import json
from zipfile import ZipFile

import numpy as np
import pandas as pd
from socioverse.schemas import PopulationBundle, EnvironmentBundle

from .frozen_batch import ROOT, read_json, dump, sha
from .post2025_trial import unique_public_signals
from .news_matching import change_news
from ..coverage_preparation import build_news_pool, latest_wave, national_confidence
from ..news_selection_trial import RecallRules, RULE_FILE
from ..news_label_compat import normalize_label
from ..news_exposure import NEWS_KEYS, SCHEMA as NEWS_SCHEMA, interests_for_profile
from ..news_exposure_demo import draw_news, exact_deduplicate, news_tags
from ..confidence_experiment import SCHEMA as CONF_SCHEMA, validate_bundle, build_messages
from ..price_experience import BasketAssigner, prepare_ce_donors, profile_hash
from ..personal_information_preparation import past_state, conditional_roles, draw_role, DONORS
from ..evaluation.heterogeneous_news import allocate
from ..news_quantity import random_quantities
from ..prior_belief_preparation import add_prior, MARKER, PRIOR_MARKER, month_offset
from ..behavior_prompt_blocks import insert_block, ANCHOR_BLOCK
from ..information_update_runtime import time_index, transform as dated_transform
from ..reference_validation_runtime import transform as direct_transform
from ..procurement_price_views import choose_categories, render_view, transform_prompt
from ..output_format_example import append_format_example
from ..prior_belief_experiment import message_hash
from ..state_continuity_runtime import STATE_TOKEN, TIMING_TOKEN, initialize_state, render_messages

TIMING_START = 'Publication timing for the same information above:\n'


def prepare(preparation, history, environments, out, *, family_projection=None, policy_supplement=None,
            delivery=None, mode='state_continuity', confidence_supplement=None):
    preparation, history, environments, out = map(Path, (preparation, history, environments, out))
    if out.exists(): raise ValueError('Fresh prompt preparation folder required')
    chosen = read_json(preparation / 'selected_private.json')
    dependencies = read_json(preparation / 'state_dependencies_private.json')
    if mode not in {'state_continuity', 'monthly_reconstruction'}:
        raise ValueError('Declared continuity or independent-monthly preparation required')
    if mode == 'monthly_reconstruction' and any(n['dependency'] is not None for n in dependencies):
        raise ValueError('Independent reconstruction cannot import recursive model histories')
    sources = {}

    def pin(path):
        path = Path(path).resolve(); sources[str(path.relative_to(ROOT))] = sha(path)
        return read_json(path)

    prior_summary = pin(preparation / 'summary.json')
    family_path = (Path(family_projection) / 'profiles_private.json' if family_projection is not None
                   else ROOT / 'outputs/sce_v32_new2025_household_profiles_20261022_v1/profiles_private.json')
    families = defaultdict(list)
    for row in pin(family_path): families[int(row['userid'])].append((int(row['date']), row))
    # IDs only; present/future answers are not needed to recover the delivery identity mapping.
    from .state_continuity_inputs import FRAME, anonymous_id
    delivery = Path(delivery) if delivery is not None else ROOT / 'outputs/sce_fullperiod_data_20261021_v1'
    salt = read_json(delivery / next(iter(chosen)) / 'population_state_private.json')['anon_salt']
    identity = {anonymous_id(u, salt): int(u) for u in pd.read_parquet(FRAME, columns=['userid']).userid.unique()}
    role_meta, role_features = [], []
    for month, people in chosen.items():
        for item in people:
            person = item['persona']; aid = person['agent_id']
            family = past_state(families.get(identity[aid], []), int(month))
            size = family.get('whole_residence_size')
            features = dict(age_group={'Under 40': 'under_40', '40 to 60': '40_to_60', 'Over 60': 'over_60'}.get(person['attributes'].get('age_group'), 'missing'),
                            household_size_group='missing' if size is None else 'one' if size == 1 else 'two' if size == 2 else 'three_plus',
                            children_group=family.get('children_group', 'missing'))
            role_meta.append(dict(month=month, agent_id=aid, family=family, features=features)); role_features.append(features)
    role_path = DONORS / 'role_donors_2022_private.parquet'
    sources[str(role_path.relative_to(ROOT))] = sha(role_path)
    probabilities, supports = conditional_roles(pd.read_parquet(role_path), pd.DataFrame(role_features), 'EUGROSHP2', 5)
    roles = {}
    for i, row in enumerate(role_meta):
        role = draw_role(probabilities[i], row['agent_id'], 20261019)
        row.update(role=role, matching_support=supports[i]); roles[row['month'], row['agent_id']] = role
    receipt = pin(ROOT / 'outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/experience.json')['source']
    archive_path = ROOT / 'data/raw/ce_experience/20261006/intrvw20.zip'
    sources[str(archive_path.relative_to(ROOT))] = sha(archive_path)
    if sha(archive_path) != receipt['data_sha256']: raise ValueError('CE source changed')
    with ZipFile(archive_path) as archive: payload = archive.read(receipt['member'])
    if hashlib.sha256(payload).hexdigest() != receipt['member_sha256']: raise ValueError('CE donor member changed')
    donors, _ = prepare_ce_donors(csv.DictReader(StringIO(payload.decode('utf-8-sig'))))
    assigner = BasketAssigner(donors, receipt, seed=42, min_pool=25)
    waves = pin(ROOT / 'docs/workstreams/20261017_reference_scaleup/confidence_sources.json')['waves']
    if confidence_supplement is not None:
        waves = waves + pin(confidence_supplement)['waves']
    policies = pin(ROOT / 'docs/workstreams/20261021_fullperiod/new2025_policy_sources.json')
    if policy_supplement is not None:
        policies.update(pin(policy_supplement))
    foods = pin(environments / 'food_catalog.json')
    # Validate full-period metadata before spending time rendering the first
    # thousands of people. These are the existing prompt contract, not new
    # numerical performance gates.
    for month in chosen:
        meta=read_json(environments/month/'environment.json')['provider_args']
        cutoff=meta['targets'][0]['as_of']
        eligible=[v for v in policies.values() if datetime.fromisoformat(v['published_at'])<=datetime.fromisoformat(cutoff)]
        if not eligible or len(max(eligible,key=lambda v:v['published_at'])['facts'])!=3:
            raise ValueError('Three eligible public policy facts required for '+month)
        latest_wave(waves,cutoff)
        if month not in foods or set(choose_categories(5,'preflight',20261019)) - set(foods[month]):
            raise ValueError('Complete grocery-category metadata required for '+month)
    rules = RecallRules(pin(RULE_FILE)); out.mkdir(parents=True)
    dump(out / 'role_assignments_private.json', role_meta)
    coverage, static_by_key, preview_sizes = [], {}, []
    for month, people in chosen.items():
        target = f'{month[:4]}-{month[4:]}'
        dest = out / month; dest.mkdir()
        population = pin(delivery / month / 'population.json')
        full_frame_ids = [p['agent_id'] for p in population['personas']]
        population.update(personas=[item['persona'] for item in people], materialized_count=len(people))
        pop = PopulationBundle.model_validate(population)
        env = pin(environments / month / 'environment.json')
        env['provider_args']['signals_by_step']['0'], removed = unique_public_signals(env['provider_args']['signals_by_step']['0'])
        env['provider_args']['events_by_step'] = {'0': []}; env['information_program']['broadcasts'] = []
        env['provider_args']['persona_by_id'] = {p.agent_id: p.attributes for p in pop.personas}
        cutoff = env['provider_args']['targets'][0]['as_of']
        if any(datetime.fromisoformat(s['published_at']) > datetime.fromisoformat(cutoff)
               for s in env['provider_args']['signals_by_step']['0']): raise ValueError('Future signal')
        from ..model import SCEEnvironmentProvider
        provider = SCEEnvironmentProvider(EnvironmentBundle.model_validate(env))
        provider.audit_dir = None; provider.reset(42); provider.advance_to(1)
        resolved = pin(history / f'{month}_resolved_private.json')
        label_index = pin(delivery / month / 'news_label_index.json')
        labels = {r['article_id']: normalize_label(r['label']) for r in label_index['pool'] if r['label']}
        if mode == 'monthly_reconstruction':
            from .fullperiod_materialization import news_pool_for_prompts
            raw, _, hashes = news_pool_for_prompts(ROOT, target, cutoff, rules)
        else:
            raw, _, hashes = build_news_pool(ROOT, target, cutoff, rules)
        sources.update(hashes)
        pool = []
        for r in raw:
            v = {k: r[k] for k in NEWS_KEYS - {'routing_tags', 'semantic_label'}}
            v.update(routing_tags=news_tags(r), semantic_label=labels.get(r['article_id'])); pool.append(v)
        if any(r['new_hits'] and r['article_id'] not in labels for r in raw): raise ValueError('Unlabeled news')
        general = exact_deduplicate([r for r in pool if r['placement'] == 'a1'])
        personal_pool = exact_deduplicate([r for r in pool if r['placement'] != 'a1' and r['semantic_label'] and r['semantic_label']['decision'] == 'keep'])
        if len(personal_pool) < 17: raise ValueError('Insufficient eligible personal articles')
        common, _ = draw_news(general, 3, f'104729|{month}|common-a1'); common.sort(key=lambda r: (r['pub_date'], r['article_id']))
        ids = [p.agent_id for p in pop.personas]
        # Exchangeable random quotas; neither demographics nor model outcomes enter.
        quantity_ids = full_frame_ids if mode == 'monthly_reconstruction' else ids
        levels = (random_quantities(quantity_ids, 20261022) if mode == 'monthly_reconstruction'
                  else allocate(quantity_ids, np.full((len(quantity_ids), 6), 1 / 6), 20261022))
        eligible_policy = [v for v in policies.values() if datetime.fromisoformat(v['published_at']) <= datetime.fromisoformat(cutoff)]
        sp = max(eligible_policy, key=lambda v: v['published_at'])
        if sha(ROOT / sp['file']) != sp['sha256']: raise ValueError('Policy archive changed')
        sources[sp['file']] = sp['sha256']
        wave = latest_wave(waves, cutoff); sources[wave['local_file']] = sha(ROOT / wave['local_file'])
        news_rows, baskets, confidence, selected_news = {}, {}, {}, {}
        for p in pop.personas:
            aid = p.agent_id; basket = assigner.assign(aid, p.attributes); baskets[aid] = basket
            personal, _ = draw_news(personal_pool, 17, f'104729|{month}|{aid}|personal', interests_for_profile(p.attributes, basket['spending_shares']), .5, 2.)
            selected_news[aid] = sorted(personal[:levels[aid] - 3], key=lambda r: (r['pub_date'], r['article_id']))
            news_rows[aid] = dict(profile_sha256=profile_hash(p.attributes), spending_shares=basket['spending_shares'],
                                  personal_news=sorted(personal[:5], key=lambda r: (r['pub_date'], r['article_id'])))
            confidence[aid] = national_confidence(aid, 42, wave)
        base = dict(schema_version=CONF_SCHEMA, arm='national_confidence', wave_id=wave['wave_id'], labels=confidence,
                    policy={k: sp[k] for k in ('published_at', 'source_url', 'source_sha256', 'facts')},
                    news=dict(schema_version=NEWS_SCHEMA, research_line='A_historical_reconstruction', target_month=target,
                              as_of=cutoff, arm='matched', mixing_weight=.5, affinity_boost=2., common_news=common,
                              rows=news_rows, source_sha256={}, pool_status='complete_coarse_candidate_labels'))
        validate_bundle(base, pop.personas, target, cutoff)
        templates, previews, timing_contexts = {}, {}, {}
        for ob in provider.observe_batch(ids, 1):
            aid = ob.agent_id; state = initialize_state(resolved[aid]); fields = state['fields']
            messages = build_messages(ob, base)
            # Temporary legacy bridge is removed before saving; real source dates are rendered later.
            prior = dict(source_month=month_offset(int(month), -1), point_pct=fields['q8']['value'],
                         q9={f'bin{i}': v for i, v in enumerate(fields['q9']['value'], 1)})
            messages, _ = add_prior(messages, prior, int(month)); messages = insert_block(messages, ANCHOR_BLOCK, require_prior=True)
            timing, _ = time_index(env['provider_args']['signals_by_step']['0'], common, news_rows[aid]['personal_news'],
                                   base['policy'], state['comparison_reference_day'], cutoff)
            messages = direct_transform(dated_transform(messages, 'dated_information', timing))
            role = roles[month, aid]; categories = choose_categories(role, aid, 20261019)
            view = render_view(role, categories, foods[month], 'see timing comparison below')
            view = view.replace(f"BLS release {foods[month]['food_at_home']['published_at']}; availability relative to your previous survey: see timing comparison below.",
                                f"BLS release {foods[month]['food_at_home']['published_at']}; see the timing comparison below.")
            messages = append_format_example(transform_prompt(messages, view))
            messages = change_news(messages, common, news_rows[aid]['personal_news'], selected_news[aid],
                                   state['comparison_reference_day'], cutoff)
            text = messages[0]['content']; start, end = text.index(TIMING_START), text.index(MARKER)
            template = [{'role': 'user', 'content': text[:start] + TIMING_TOKEN + '\n\n' + STATE_TOKEN + '\n\n' + text[end:]}]
            context = dict(as_of=cutoff, common_news=common, personal_news=selected_news[aid],
                           policy_published_at=sp['published_at'], food_published_at=foods[month]['food_at_home']['published_at'])
            preview = render_messages(template, state, month, context)
            if any(token in preview[0]['content'] for token in (aid, '"userid"', 'Q9_mean', 'QSP5', '"weight"')):
                raise ValueError('Private identifier/target field reached prompt')
            templates[aid] = template; previews[aid] = dict(messages=preview, prompt_sha256=message_hash(preview))
            preview_sizes.append(len(json.dumps(preview, ensure_ascii=False).encode()))
            timing_contexts[aid] = context
            static_by_key[month, aid] = (template, state, context)
        for name, obj in [('population.json', population), ('environment.json', env), ('templates_private.json', templates),
                          ('initial_states_private.json', {a: initialize_state(r) for a, r in resolved.items()}),
                          ('timing_context_private.json', timing_contexts), ('initial_previews_private.json', previews),
                          ('baskets_private.json', baskets)]: dump(dest / name, obj)
        if mode == 'monthly_reconstruction':
            dump(dest / 'news_quantity_frame_private.json', levels)
        selected_levels = [levels[aid] for aid in ids]
        coverage.append(dict(month=month, n=len(ids), news_quantity=dict(Counter(selected_levels)),
                             mean_articles=sum(selected_levels) / len(ids), eligible_personal_news=len(personal_pool),
                             quantity_assignment_frame_n=len(quantity_ids),
                             policy_published_at=sp['published_at'], policy_age_days=(datetime.fromisoformat(cutoff)-datetime.fromisoformat(sp['published_at'])).days,
                             household_structure_available=sum(r['family']['available'] for r in role_meta if r['month']==month),
                             confidence_wave=wave['wave_id'], duplicate_signals_removed=removed))
        print(f'{month}: {len(ids)} state-ready templates; news average {sum(selected_levels)/len(ids):.3f}', flush=True)
    from .state_continuity_dry_run import dry_run
    dry = dry_run(dependencies, static_by_key)
    dump(out / 'dry_previews_private.json', dry.pop('preview_rows_private'))
    dump(out / 'dry_run_summary.json', dry)
    max_chars = dry['max_rendered_characters']
    # Conservative byte budget allows state/timing growth; this is not paid-run authorization.
    unique = prior_summary['potential_unique_calls_before_prompt_hash']
    reserve_per_call = ((dry['max_rendered_utf8_bytes'] + 4096) * .259 + 1024 * .8) / 1e6
    estimate = (sum(preview_sizes) / len(preview_sizes) / 4 * .259 / 1e6 + 180 * .8 / 1e6) * unique
    summary = dict(status=('offline_templates_and_recursive_dry_run_complete_not_authorized' if mode == 'state_continuity'
                           else 'offline_independent_monthly_templates_complete_not_authorized'),
                   preparation_mode=mode, new_api_calls=0,
                   logical_positions=len(dependencies), planned_unique_requests=unique,
                   conservative_reservation_usd=reserve_per_call * unique, estimated_cost_usd=estimate,
                   max_dry_prompt_chars=max_chars, runtime_character_cap=max_chars+1024,
                   runtime_utf8_byte_cap=dry['max_rendered_utf8_bytes']+4096,
                   source_sha256=sources, coverage=coverage, dry_run=dry,
                   remaining=['Register existing-client execution/recording and fail-safe budgets for dynamic prompts; official-engine offline checks still required',
                              'Assemble isolated current truth and cached evaluation adapter',
                              'Freeze exact prompt-size/call cap, concurrency, cost and new data authorization'],
                   limits=[('Short A-line continuity diagnostic, not a completed strict B forecast' if mode == 'state_continuity'
                            else 'Independent A-line monthly reconstruction; no recursive dependencies or strict B eligibility claim'),
                           ('Quantity quotas applied to selected pilot roster' if mode == 'state_continuity'
                            else 'Quantity quotas assigned on complete monthly P then subset Core; selected average may differ from 8'),
                           'Random quantities use the adopted quota with exchangeable ID-only assignment; no demographic affinity for quantities',
                           'Archived policy registry is reused by last eligible date; later still-missing policy statements are not fabricated',
                           'Household structure is missing for some newly selected people; existing conditional-role model marginalizes missing dimensions'])
    dump(out / 'summary.json', summary)
    return summary
