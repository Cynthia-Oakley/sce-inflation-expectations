"""Prepare weekly P/E, public-release priors and tokenized messages offline.

The independent monthly and autonomous monthly experiments remain immutable.
No recent target value, key or model endpoint is opened by this preparation.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, time
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .frozen_batch import ROOT, read_json as read, dump, sha
from .weekly_preflight import PE, BASE, REPAIR
from .weekly_release_protocol import aware
from .recent_b_sampled_dates import load_repair, merge_labels, archive_view, check_frozen_core
from .recent_b_news_refresh import _load_labels, _news_pools
from .fullperiod_materialization import news_pool_for_prompts
from .full_a_personal_inputs import _food_snapshot, _policy_snapshot
from .media_timing_inputs import FOOD, BASKET, NEWS, food_text, policy_text
from .weekly_state import initialize_state, reset_state, advance_state, render_state
from ..news_exposure import interests_for_profile
from ..news_exposure_demo import render_news_input
from ..news_selection_trial import RecallRules, RULE_FILE
from ..coverage_preparation import latest_wave, national_confidence
from ..belief_trial_preparation import confidence_block
from ..prior_belief_experiment import message_hash
from ..submission_tools.reproduce import no_network

STATE = '[[SCE_WEEKLY_STATE]]'
QUESTIONS = 'Question 1 (point estimate):'
POLICY_ARCHIVE = ROOT / 'data/raw/sce_weekly_policy_20261026_v1'


def step_key(cutoff):
    return 'w' + aware(cutoff).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).strftime('%Y%m%d')


def render(template, state, cutoff):
    if len(template) != 1 or template[0]['role'] != 'user' or template[0]['content'].count(STATE) != 1:
        raise ValueError('One weekly template and one state token required')
    text = template[0]['content'].replace(STATE, render_state(state, cutoff))
    if state['agent_id'] in text:
        raise ValueError('Household identity must not be transmitted')
    return [dict(role='user', content=text)]


def build_template(root_template, *, cutoff, role, aid, facts, policy, confidence, context):
    text = root_template[0]['content']
    persona = text[:text.index('You are answering a monthly survey')]
    basket = text[text.index(BASKET):text.index(NEWS)]
    questions = text[text.index(QUESTIONS):]
    questions = questions.replace('Use your earlier survey response as a starting state.',
                                  'Use the earlier belief state as a starting state.')
    questions = questions.replace('advanced by one month', 'advanced since the earlier dated state')
    questions = questions.replace("differs from last month's", 'differs from the earlier one')
    body = (persona + f'You are answering a survey as of {cutoff}. You only know information publicly available by this cutoff.\n'
        'The questions concern inflation over the next 12 months, not inflation over the next week.\n\n'
        + food_text(role, aid, facts) + basket
        + 'The following are newly encountered articles in this simulation step. Previously seen article IDs are not presented again.\n'
        + render_news_input(context['common_news'], context['personal_news']) + '\n\n'
        + policy_text(policy) + confidence
        + '\nSimulation provenance: fixed proxy household based on the archived 2025-01 population frame. '
          'The declared nine-month publication-lag assumption is used; its exact historical file version is unverified. '
          'Starting beliefs are synthetic intact donor answers, calibrated only to an earlier publicly released national statistic. '
          'Between releases, the dated belief state comes from this same simulated household. No actual recent interview is claimed.\n\n'
        + STATE + '\n\n' + questions)
    # Release dates remain explicit even when a monthly numeric value is carried forward.
    body = body.replace('see the timing comparison below', 'available by the dated cutoff above')
    return [dict(role='user', content=body)]


def prepare(preflight, out, *, official_core=True):
    from .weekly_news import advance_weekly_news
    from .weekly_priors import prepare_cycles
    preflight, out = Path(preflight).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored preparation directory required')
    sources = {}

    def load(path):
        path = Path(path).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Project-local source required')
        sources[str(path.relative_to(ROOT))] = sha(path)
        return read(path)

    with no_network():
        m = load(preflight / 'manifest.json')
        for name, digest in m['source_sha256'].items():
            if sha(ROOT / name) != digest:
                raise ValueError('Preflight source changed: ' + name)
            sources[name] = digest
        for name, digest in m['files_sha256'].items():
            if sha(preflight / name) != digest:
                raise ValueError('Preflight output changed: ' + name)
        roster = load(preflight / 'roster_private.json')
        points = load(preflight / 'weekly_environment_inventory.json')
        people = {r['persona']['agent_id']: r['persona'] for r in roster}
        if len(people) != 300 or len(points) != 47:
            raise ValueError('Registered 300 households and 47 weekly points required')
        roots = load(PE / '202511/templates_private.json')
        baskets = load(PE / 'baskets_private.json'); roles = load(PE / 'roles_private.json')
        foods = load(ROOT / 'outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json')
        policies = load(ROOT / 'data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json')
        evidence = load(POLICY_ARCHIVE / 'source.json')
        policy_file = POLICY_ARCHIVE / 'monetary20260916a.html'
        if sha(policy_file) != evidence['sha256']:
            raise ValueError('New public policy evidence changed')
        sources[str(policy_file.relative_to(ROOT))] = evidence['sha256']
        policies['2026-09-16'] = dict(published_at=evidence['published_at'],
            source_url=evidence['source_url'], file=str(policy_file.relative_to(ROOT)), sha256=evidence['sha256'],
            facts=['The federal funds target range was raised by 0.25 percentage point to 3.75–4 percent.',
                   'The statement described inflation as elevated and economic activity as expanding at a solid pace.',
                   'The Committee reaffirmed its 2 percent inflation goal and said the action would support a timelier return to it.'])
        waves = load(ROOT / 'docs/workstreams/20261017_reference_scaleup/confidence_sources.json')['waves']
        waves += load(ROOT / 'data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json')['waves']
        overrides, extra = load_repair(REPAIR, sources)
        labels = merge_labels(_load_labels(load(BASE / 'summary.json'), sources), extra)
        rules = RecallRules(load(RULE_FILE))
        out.mkdir()
        cycles = prepare_cycles(roster, points, out / 'priors')
        dump(out / 'priors/cycles_private.json', cycles)
        sources.update(read(out / 'priors/manifest.json')['source_sha256'])
        required = load(preflight / 'archive_aliases.json')
        view, aliases = archive_view(out, required, overrides)
        bymonth = {}
        for point in points:
            target = point['target_reference_period']
            bymonth.setdefault(target, []).append(point['cutoff'])
        raw_cache = {}
        for target, cutoffs in bymonth.items():
            raw, _, hashes = news_pool_for_prompts(view, target, max(cutoffs, key=aware), rules)
            raw_cache[target] = raw
            for name, digest in hashes.items():
                sources[aliases[Path(name).stem]] = digest
        states = {}; news_memory = {}; coverage = []; maximum_chars = maximum_bytes = 0; sum_chars = 0
        fixture = json.dumps(dict(point_pct=3., q9={f'bin{i}': 10. for i in range(1, 11)}))
        population = deepcopy(load(PE / 'population_private.json'))
        population['personas'] = [people[a] for a in sorted(people)]
        population['materialized_count'] = 300
        envroot = load(PE / '202511/environment.json')
        for point in points:
            cutoff = point['cutoff']; month = point['target_reference_period'].replace('-', '')
            key = step_key(cutoff); cycle = cycles[point['cycle_key']]
            donor_available = datetime.combine(datetime.fromisoformat(
                cycle['diagnostics']['source_wave_inferred_available_date']).date()+timedelta(days=1),
                time(0), ZoneInfo('America/New_York'))
            effective = max(aware(point['anchor_known_from']),donor_available).isoformat()
            if aware(effective)>aware(cutoff): raise ValueError('Joint prior is not yet available')
            folder = out / 'weeks' / key / month; folder.mkdir(parents=True)
            eligible = [r for r in raw_cache[point['target_reference_period']] if aware(r['pub_date']) <= aware(cutoff)]
            foodkey, facts = _food_snapshot(foods, cutoff); policy = _policy_snapshot(policies, cutoff)
            confidence = latest_wave(waves, cutoff)
            common, _, poolaudit = _news_pools(eligible, labels, cutoff, facts['food_at_home']['published_at'][:10])
            # Make the full eligible pool explicit; retain A1 keep candidates for later personal slots.
            from .media_mechanism_trial import is_sce_report, text_of
            from .recent_b_news_refresh import B_SCE_PATTERN
            from ..news_exposure_demo import news_tags, exact_deduplicate
            from ..news_exposure import NEWS_KEYS
            pool = []
            for r in eligible:
                if is_sce_report(r) or B_SCE_PATTERN.search(text_of(r)):
                    continue
                item = {k: r[k] for k in NEWS_KEYS - {'routing_tags', 'semantic_label'}}
                item.update(routing_tags=news_tags(r), semantic_label=labels.get(r['article_id'],
                    dict(article_id=r['article_id'], decision='background_only', topics=[], scope='unclear')))
                pool.append(item)
            pool = exact_deduplicate(pool)
            templates = {}; contexts = {}; previews = {}; before = {}; afternews = {}
            for r in roster:
                aid = r['persona']['agent_id']; prior = cycle['states'][aid]
                previous = states.get(aid)
                if previous is None:
                    state = initialize_state(aid, point['cycle_key'], effective, prior['fields'], center=prior['center'])
                elif point['reset_required']:
                    state = reset_state(previous, point['cycle_key'], effective, prior['fields'], center=prior['center'])
                else:
                    state = previous
                exposure = advance_weekly_news(candidate_pool=pool, common_candidates=common, cutoff=cutoff,
                    household_id=aid, attention_tier=r['attention_tier'],
                    interests=interests_for_profile(people[aid]['attributes'], baskets[aid]['spending_shares']),
                    state=news_memory.get(aid), seed=20261026)
                context = dict(as_of=cutoff, common_news=exposure['common_news'], personal_news=exposure['personal_news'],
                    food_published_at=facts['food_at_home']['published_at'], policy_published_at=policy['published_at'],
                    confidence_wave_id=confidence['wave_id'], exposure_audit=exposure['audit'])
                template = build_template(roots[aid], cutoff=cutoff, role=roles[aid], aid=aid, facts=facts,
                    policy=policy, confidence=confidence_block(national_confidence(aid, 42, confidence)), context=context)
                messages = render(template, state, cutoff)
                text = json.dumps(messages, ensure_ascii=False); sum_chars += len(text)
                maximum_chars = max(maximum_chars, len(text)); maximum_bytes = max(maximum_bytes, len(text.encode()))
                templates[aid] = template; contexts[aid] = context; before[aid] = state
                previews[aid] = dict(messages=messages, prompt_sha256=message_hash(messages))
                afternews[aid] = exposure['memory_after']; news_memory[aid] = exposure['memory_after']
                nextstate = advance_state(state, fixture, cutoff, center=0.)
                nextstate['news_memory'] = exposure['memory_after']; states[aid] = nextstate
            pop = deepcopy(population)
            pop['provider_args'].update(target_month=point['target_reference_period'], as_of=cutoff)
            env = deepcopy(envroot)
            env['provider_args'] = dict(targets=[dict(target_month=point['target_reference_period'], as_of=cutoff)],
                persona_by_id={a: p['attributes'] for a, p in people.items()},
                evidence_class='weekly_frozen_message_view_only')
            # Official Core transports only the frozen message view, not old monthly macro rows.
            env['provider_args']['signals_by_step'] = {'0': [], '1': []}
            for name, value in [('population', pop), ('environment', env), ('templates_private', templates),
                                ('timing_context_private', contexts), ('initial_previews_private', previews),
                                ('fixture_states_before_private', before), ('news_memory_after_private', afternews)]:
                dump(folder / (name + '.json'), value)
            dump(folder.parent / 'summary.json', dict(coverage=[dict(month=month)], runtime_character_cap=maximum_chars+24000))
            coverage.append(dict(step_key=key, month=month, cutoff=cutoff, cycle_key=point['cycle_key'],
                reset_required=point['reset_required'], anchor_known_from=point['anchor_known_from'],
                calibration_effective_at=effective,
                anchor_reference_period=point['anchor_reference_period'], anchor_pp=point['anchor_pp'],
                food_snapshot=foodkey, policy_published_at=policy['published_at'], pool_audit=poolaudit,
                newly_seen_counts=dict(Counter(len(c['common_news'])+len(c['personal_news']) for c in contexts.values()))))
            print(key + ': 300 weekly P/E messages, cycle ' + point['anchor_reference_period'], flush=True)
        population['provider_args'].update(target_month=points[0]['target_reference_period'], as_of=points[0]['cutoff'])
        dump(out / 'population_private.json', population)
        dump(out / 'weights_private.json', {r['persona']['agent_id']: r['weekly_design']['poststratified_weight'] for r in roster})
        dump(out / 'weekly_plan.json', coverage)
        dump(out / 'policies_weekly_overlay.json', policies['2026-09-16'])
        core = []
        if official_core:
            core_root = out / 'core_engineering'; core_root.mkdir()
            for point in coverage:
                key = point['step_key']
                cell = core_root / (out.name + '-' + key)
                cell.mkdir()
                core.append(check_frozen_core(out / 'weeks' / key, cell / 'check'))
        result = dict(status='weekly_inputs_and_scripted_core_ready' if official_core else 'weekly_inputs_core_pending',
            weekly_points=47, n_per_week=300, planned_main_calls=14100,
            calibration_cycles=len(cycles), official_core_units=sum(r['official_engine_units'] for r in core),
            new_API_calls=0, selected_model_answers_read=False, fixtures_are_not_forecasts=True,
            max_prompt_chars=maximum_chars+24000, max_prompt_bytes=maximum_bytes+48000,
            estimated_main_cost_usd=(sum_chars/4*.259+14100*300*.8)/1e6,
            target_truth_in_inputs=False, source_sha256=sources,
            pending=['runtime full replay and independent review', 'precise data-scope/budget approval'])
        dump(out / 'summary.json', result)
        for name in ('weekly_inputs.py','weekly_state.py','weekly_news.py','weekly_priors.py','weekly_release_protocol.py'):
            path = Path(__file__).with_name(name); sources[str(path.relative_to(ROOT))] = sha(path)
        dump(out / 'manifest.json', dict(source_sha256=sources,
            files_sha256={str(p.relative_to(out)): sha(p) for p in out.rglob('*.json') if 'archive_view' not in p.parts},
            new_API_calls=0, live_authorization_written=False))
    return result
