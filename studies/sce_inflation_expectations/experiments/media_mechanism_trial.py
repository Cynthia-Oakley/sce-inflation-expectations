from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import random
import re

from .frozen_batch import ROOT, dump, sha
from .fullperiod_materialization import news_pool_for_prompts
from .information_exposure import NEWS_START, POLICY_START, TIMING_START
from ..news_selection_trial import RecallRules, RULE_FILE
from ..information_update_runtime import publication_status
from ..news_exposure import NEWS_KEYS, interests_for_profile
from ..news_exposure_demo import exact_deduplicate, news_tags, render_news_input
from ..news_label_compat import normalize_label

MONTHS = (202106, 202206)
ARMS = ('R0', 'R1', 'M0', 'M1')
MATERIALIZED = 'outputs/sce_fullperiod_materialized_20261022_v2'
ASSEMBLY = 'outputs/sce_monthly_fine_full_assembly_20261023_v3/prompts'
EXTERNAL = 'outputs/sce_media_mechanism_20261024_v1'
SCE_PATTERN = re.compile(r'(?:ny\s+fed|new york fed).*(?:survey|sce)|纽约联储.*(?:消费者预期|通胀预期)|consumer expectations survey', re.I)
INFLATION_PATTERN = re.compile(r'\binflation\b|\b(?:consumer )?prices?\b|\bcpi\b|物价|通胀', re.I)
ALARMING_PATTERN = re.compile(
    r'\b(?:surges?|soars?|soaring|spikes?|spiking|jumps?|record high|40-year high|'
    r'scorching|hammers?|wiped out|erodes?|erosion|shortages?|fears?|pressure|'
    r'climbs?|skyrockets?|hits? a record|dashing hopes|paying more|sticker shock)\b', re.I)


def read_json(path):
    return json.loads(Path(path).read_text())


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def text_of(row):
    return ' '.join(str(row.get(k) or '') for k in ('headline', 'title', 'abstract', 'excerpt_lead', 'snippet'))


def is_sce_report(row):
    return bool(SCE_PATTERN.search(text_of(row)))


def is_alarming(row):
    label = row.get('semantic_label') or {}
    if label.get('trial_tone'):
        return label['trial_tone'] == 'alarming'
    return bool(ALARMING_PATTERN.search(text_of(row)))


def article_id(url, headline, abstract):
    payload = url + '\n' + headline + '\n' + abstract
    return 'external_' + hashlib.sha256(payload.encode()).hexdigest()[:24]


def external_row(raw):
    headline = raw['title']
    abstract = raw['excerpt_lead']
    row = {
        'article_id': article_id(raw['original_url'], headline, abstract),
        'headline': headline,
        'abstract': abstract,
        'snippet': '',
        'pub_date': raw['published_at'],
        'web_url': raw['original_url'],
        'text_sha256': hashlib.sha256((headline + '\n' + abstract).encode()).hexdigest(),
        'text_vintage_status': raw['text_vintage_status'],
        'print_section': None,
        'print_page': None,
        'placement': 'external_online',
        'routing_tags': [],
        'semantic_label': {
            'decision': 'keep',
            'trial_tone': raw['manual_judgment']['tone'],
            'topics': [raw['manual_judgment']['price_content']],
            'source': raw['source'],
            'article_type': raw['article_type'],
        },
    }
    row['routing_tags'] = news_tags(row)
    if set(row) != NEWS_KEYS:
        raise ValueError('External news schema mismatch')
    return row


def load_external_pool(root, month):
    root = Path(root)
    june = read_json(root / EXTERNAL / 'external_candidates.json')['windows'][str(month)]['candidates']
    may = read_json(root / EXTERNAL / f'external_may_{month // 100}.json')['candidates']
    rows, excluded = [], []
    for raw in may + june:
        if is_sce_report(raw):
            excluded.append({'title': raw['title'], 'url': raw['original_url'], 'reason': 'SCE expectation report'})
        else:
            rows.append(external_row(raw))
    if len({r['article_id'] for r in rows}) != len(rows) or len({r['web_url'] for r in rows}) != len(rows):
        raise ValueError('Duplicate external article')
    rows.sort(key=lambda r: (parse_time(r['pub_date']), r['article_id']))
    receipt = {'raw_candidate_count': len(may) + len(june),
               'eligible_count': len(rows), 'excluded_sce_report_count': len(excluded),
               'excluded': excluded,
               'source_counts': dict(Counter(r['semantic_label']['source'] for r in rows))}
    return rows, receipt


def load_nyt_pool(root, month):
    root = Path(root)
    env = read_json(root / ASSEMBLY / str(month) / 'environment.json')
    cutoff = env['provider_args']['targets'][0]['as_of']
    raw, _, _ = news_pool_for_prompts(root, f'{month // 100}-{month % 100:02}', cutoff, RecallRules(read_json(RULE_FILE)))
    label_index = read_json(root / MATERIALIZED / str(month) / 'news_label_index.json')
    labels = {r['article_id']: normalize_label(r['label']) for r in label_index['pool'] if r['label']}
    pool = []
    for original in raw:
        label = labels.get(original['article_id'])
        if not label or label['decision'] != 'keep':
            continue
        row = {k: original[k] for k in NEWS_KEYS - {'routing_tags', 'semantic_label'}}
        row['routing_tags'] = news_tags(original)
        row['semantic_label'] = dict(label, trial_tone='alarming' if ALARMING_PATTERN.search(text_of(original)) else 'unmarked')
        pool.append(row)
    return exact_deduplicate(pool)


def latest_cpi_release_day(root, month):
    env = read_json(Path(root) / ASSEMBLY / str(month) / 'environment.json')
    cutoff = parse_time(env['provider_args']['targets'][0]['as_of'])
    releases = [parse_time(s['published_at']) for s in env['provider_args']['signals_by_step']['0']
                if s['signal_id'].startswith('bls_cpi_u_all_items_yoy_nsa_') and parse_time(s['published_at']) <= cutoff]
    if not releases:
        raise ValueError('No eligible CPI release')
    return max(releases).date().isoformat()


def select_salient_common(pool, release_day):
    candidates = [r for r in pool if r['placement'] == 'a1']
    direct = [r for r in candidates if INFLATION_PATTERN.search(r['headline'])]
    national = [r for r in direct if r['semantic_label'].get('scope') == 'us_national']
    if len(national) >= 3:
        candidates = national
    elif len(direct) >= 3:
        candidates = direct

    def key(row):
        inflation = bool(INFLATION_PATTERN.search(text_of(row)))
        release = inflation and parse_time(row['pub_date']).date().isoformat() == release_day
        living = bool(set(row['routing_tags']) & {'food', 'road_fuel', 'rental_housing', 'owned_housing', 'labor_income'})
        score = 4 * inflation + 8 * release + 2 * living + 1 * is_alarming(row)
        return (-score, -parse_time(row['pub_date']).timestamp(), row['article_id'])

    selected = sorted(candidates, key=key)[:3]
    if len(selected) != 3:
        raise ValueError('Insufficient A1 candidates')
    return sorted(selected, key=lambda r: (parse_time(r['pub_date']), r['article_id']))


def selection_probabilities(rows, interests, negative_boost=1.):
    if not 1 <= negative_boost <= 2:
        raise ValueError('Negative boost is fixed to the registered [1, 2] range')
    if not rows:
        return []
    scores = [(2. if set(r['routing_tags']) & interests else 1.) *
              (negative_boost if is_alarming(r) else 1.) for r in rows]
    total = sum(scores)
    return [.5 / len(rows) + .5 * score / total for score in scores]


def draw_weighted(rows, count, seed, interests, negative_boost):
    if count > len(rows):
        raise ValueError('Insufficient personal news')
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))
    available = sorted(rows, key=lambda r: r['article_id'])
    chosen = []
    for _ in range(count):
        probabilities = selection_probabilities(available, interests, negative_boost)
        draw = rng.random()
        cumulative = 0.
        index = len(available) - 1
        for i, probability in enumerate(probabilities):
            cumulative += probability
            if draw < cumulative:
                index = i
                break
        chosen.append(available.pop(index))
    return chosen


def external_count(count):
    return int(math.floor(count * .25 + .5))


def draw_personal(nyt, external, count, seed, interests, mixed, negative_boost):
    external_n = external_count(count) if mixed else 0
    chosen = draw_weighted(nyt, count - external_n, seed + '|nyt', interests, negative_boost)
    chosen += draw_weighted(external, external_n, seed + '|external', interests, negative_boost)
    return sorted(chosen, key=lambda r: (parse_time(r['pub_date']), r['article_id']))


def synthetic_news(article_id_value, headline):
    row = {'article_id': article_id_value, 'headline': headline, 'abstract': '', 'snippet': '',
           'pub_date': '2021-06-01T00:00:00-04:00', 'web_url': 'https://example.com/' + article_id_value,
           'text_sha256': hashlib.sha256(headline.encode()).hexdigest(),
           'text_vintage_status': 'synthetic_test', 'print_section': 'B', 'print_page': '2',
           'placement': 'other_recorded_page', 'routing_tags': [],
           'semantic_label': {'decision': 'keep'}}
    row['routing_tags'] = news_tags(row)
    return row


def check_trial_news(rows, as_of, common=False):
    cutoff = parse_time(as_of)
    if len({r['article_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate displayed news')
    for row in rows:
        if set(row) != NEWS_KEYS or parse_time(row['pub_date']) > cutoff or is_sce_report(row):
            raise ValueError('News schema/time/SCE boundary')
        if common and row['placement'] != 'a1':
            raise ValueError('Salient common news must be A1')
        if not common and row['semantic_label']['decision'] != 'keep':
            raise ValueError('Personal news must be keep')


def change_rendered_news(messages, old_common, old_personal, new_common, new_personal, previous_day, as_of):
    if len(messages) != 1 or messages[0]['role'] != 'user':
        raise ValueError('One rendered user message required')
    check_trial_news(new_common, as_of, common=True)
    check_trial_news(new_personal, as_of)
    original = messages[0]['content']
    for marker in (NEWS_START, POLICY_START, TIMING_START):
        if original.count(marker) != 1:
            raise ValueError('News/timing boundaries required')
    old = render_news_input(old_common, old_personal)
    if original.count(old) != 1:
        raise ValueError('Archived news does not reproduce')
    pattern = r'^- Other news, in the order listed above: .*\.$'
    old_status = '- Other news, in the order listed above: ' + '; '.join(
        publication_status(r['pub_date'], previous_day, as_of) for r in old_personal) + '.'
    if re.findall(pattern, original, re.M) != [old_status]:
        raise ValueError('Old news timing mismatch')
    new_status = '- Other news, in the order listed above: ' + '; '.join(
        publication_status(r['pub_date'], previous_day, as_of) for r in new_personal) + '.'
    updated = original.replace(old, render_news_input(new_common, new_personal), 1).replace(old_status, new_status, 1)

    def masked(text):
        return text[:text.index(NEWS_START)] + re.sub(pattern, '<NEWS_TIMING>', text[text.index(POLICY_START):], flags=re.M)

    if masked(updated) != masked(original):
        raise ValueError('A non-news byte changed')
    result = deepcopy(messages)
    result[0]['content'] = updated
    return result


def roster(ids, count=96, seed=20261024):
    return sorted(ids, key=lambda aid: (hashlib.sha256(f'{seed}|{aid}'.encode()).hexdigest(), aid))[:count]


def prepare(out, root=ROOT, months=MONTHS, n=96):
    root = Path(root)
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / 'outputs'):
        raise ValueError('Fresh output under outputs required')
    out.mkdir(parents=True)
    summary = {'schema': 'sce_media_mechanism_trial/v1', 'months': {}, 'arms': list(ARMS),
               'n_per_month': n, 'prompt_position_count': len(months) * len(ARMS) * n,
               'physical_call_cap_two_repeats': 2 * len(months) * len(ARMS) * n,
               'new_api_calls': 0, 'authorization_required': True,
               'source_sha256': {}}
    for month in months:
        base_dir = root / ASSEMBLY / str(month)
        for name in ('initial_previews_private.json', 'timing_context_private.json', 'initial_states_private.json',
                     'news_quantity_frame_private.json', 'baskets_private.json', 'population.json', 'environment.json'):
            summary['source_sha256'][f'{ASSEMBLY}/{month}/{name}'] = sha(base_dir / name)
        for name in ('news_label_index.json', 'environment.json'):
            summary['source_sha256'][f'{MATERIALIZED}/{month}/{name}'] = sha(root / MATERIALIZED / str(month) / name)
        previews = read_json(base_dir / 'initial_previews_private.json')
        timing = read_json(base_dir / 'timing_context_private.json')
        states = read_json(base_dir / 'initial_states_private.json')
        levels = read_json(base_dir / 'news_quantity_frame_private.json')
        baskets = read_json(base_dir / 'baskets_private.json')
        population = read_json(base_dir / 'population.json')
        profiles = {p['agent_id']: p['attributes'] for p in population['personas']}
        ids = roster(list(previews), n)
        nyt = load_nyt_pool(root, month)
        external, external_receipt = load_external_pool(root, month)
        as_of = next(iter(timing.values()))['as_of']
        common = select_salient_common(nyt, latest_cpi_release_day(root, month))
        common_ids = {r['article_id'] for r in common}
        nyt = [r for r in nyt if r['article_id'] not in common_ids]
        month_summary = {'common_news': [{'article_id': r['article_id'], 'headline': r['headline'], 'pub_date': r['pub_date']} for r in common],
                         'external': external_receipt, 'roster_sha256': hashlib.sha256('\n'.join(ids).encode()).hexdigest(),
                         'arms': {}, 'prompt_characters': {}}
        for arm in ARMS:
            mixed = arm.startswith('M')
            negative_boost = 2. if arm.endswith('1') else 1.
            prompts, contexts, sizes, source_counts, tone_counts = {}, {}, [], Counter(), Counter()
            for aid in ids:
                count = levels[aid] - 3
                interests = interests_for_profile(profiles[aid], baskets[aid]['spending_shares'])
                personal = draw_personal(nyt, external, count, f'20261024|{month}|{aid}|{arm}', interests, mixed, negative_boost)
                messages = change_rendered_news(previews[aid]['messages'], timing[aid]['common_news'], timing[aid]['personal_news'],
                                                common, personal, states[aid]['comparison_reference_day'], as_of)
                prompts[aid] = messages
                contexts[aid] = {'article_ids': [r['article_id'] for r in personal],
                                 'sources': [r['semantic_label'].get('source', 'NYT') for r in personal],
                                 'alarming': [is_alarming(r) for r in personal]}
                sizes.append(len(messages[0]['content']))
                source_counts.update(contexts[aid]['sources'])
                tone_counts.update('alarming' if flag else 'unmarked' for flag in contexts[aid]['alarming'])
            dest = out / str(month) / arm
            dest.mkdir(parents=True)
            dump(dest / 'prompts_private.json', prompts)
            dump(dest / 'contexts_private.json', contexts)
            month_summary['arms'][arm] = {'source_exposures': dict(source_counts), 'tone_exposures': dict(tone_counts)}
            month_summary['prompt_characters'][arm] = {'min': min(sizes), 'mean': sum(sizes) / len(sizes), 'max': max(sizes)}
        summary['months'][str(month)] = month_summary
    for relative in (EXTERNAL + '/external_candidates.json', EXTERNAL + '/external_may_2021.json',
                     EXTERNAL + '/external_may_2022.json'):
        summary['source_sha256'][relative] = sha(root / relative)
    dump(out / 'summary.json', summary)
    dump(out / 'protocol.json', {'schema': 'sce_media_mechanism_trial_protocol/v1', 'months': list(months),
                                 'arms': list(ARMS), 'n_per_month': n, 'generation_repeats': [1, 2],
                                 'external_share': .25, 'negative_boost': 2., 'salient_common': True,
                                 'destination': 'https://openrouter.ai/api/v1',
                                 'model': 'deepseek/deepseek-v3.2', 'route': 'siliconflow/fp8',
                                 'expected_provider': 'SiliconFlow', 'temperature': .5,
                                 'thinking': 'disabled', 'response_format': 'json_object',
                                 'max_tokens': 1024, 'retry_max': 0, 'provider_fallback': False,
                                 'price_input_per_mtok': .259, 'price_output_per_mtok': .8,
                                 'request_extra_body': {'provider': {'order': ['siliconflow/fp8'],
                                     'allow_fallbacks': False, 'require_parameters': True,
                                     'max_price': {'prompt': .259, 'completion': .8}},
                                     'reasoning': {'enabled': False}},
                                 'authorized': False, 'new_api_calls': 0})
    return summary
