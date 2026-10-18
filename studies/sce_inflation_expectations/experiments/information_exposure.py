"""Local information-view preparation, reusing archived P/E and news labels.

Produces prompts and an inventory only. No executor, API, current truth reads,
authorization, or modifications to the archived eight-news reference.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from time import perf_counter
import json

from ..evaluation.attention_support import MONTHS
from ..reference_population_preparation import sample_strata
from ..reference_validation_preparation import completed_news, NEWS_PREP
from ..news_exposure import NEWS_KEYS, interests_for_profile, check_news
from ..news_exposure_demo import draw_news, exact_deduplicate, news_tags, render_news_input
from ..prior_belief_experiment import message_hash
from ..information_update_runtime import publication_status
from .frozen_batch import ROOT, read_json, sha, dump

PARENT = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
NUMERICAL_START = 'Recent official statistics:\n'
BASKET_START = 'Synthetic household spending context (not your observed receipts):\n'
NEWS_START = 'General news you encountered:\n'
POLICY_START = 'Public policy news brief ('
TIMING_START = 'Publication timing for the same information above:\n'
PRIOR_START = 'Your earlier survey response ('


def change_view(messages, common, old_personal, new_personal, full_timing, previous_day, as_of, complete=True):
    """Change displayed news/timing and optionally remove both numerical blocks."""
    if len(messages) != 1 or messages[0]['role'] != 'user':
        raise ValueError('One user-message contract required')
    check_news(common, as_of, common=True)
    check_news(new_personal, as_of)
    original = messages[0]['content']
    for marker in (NUMERICAL_START, BASKET_START, NEWS_START, POLICY_START, TIMING_START, PRIOR_START):
        if original.count(marker) != 1:
            raise ValueError('Expected unique original boundary: '+marker)
    old_news = render_news_input(common, old_personal)
    if original.count(old_news) != 1 or original.count(full_timing) != 1:
        raise ValueError('Archived news/timing text not reproduced exactly')
    text = original.replace(old_news, render_news_input(common, new_personal), 1)
    lines = full_timing.rstrip('\n').splitlines()
    replacement = '- Other news, in the order listed above: ' + '; '.join(
        publication_status(r['pub_date'], previous_day, as_of) for r in new_personal) + '.'
    found = 0
    for index, line in enumerate(lines):
        if line.startswith('- Other news, in the order listed above:'):
            lines[index] = replacement
            found += 1
    if found != 1:
        raise ValueError('Missing unique personal-news timing line')
    if not complete:
        # Remove facts plus their release metadata: no hidden statistical side path.
        start, end = text.index(NUMERICAL_START), text.index(BASKET_START)
        if start >= end:
            raise ValueError('Statistical block boundary reversed')
        text = text[:start]+text[end:]
        lines = [line for line in lines if not line.startswith(('- CPI figures,', '- employment figures,', '- gasoline price figures,'))]
        lines = [line.replace(' The rolling trends above span both earlier and later releases.', '') for line in lines]
    updated_timing = '\n'.join(lines)+'\n\n'
    text = text.replace(full_timing, updated_timing, 1)
    if not complete and ('Recent trends (' in text or NUMERICAL_START in text or '- CPI figures, reference ' in text):
        raise ValueError('Hidden statistical block survived')
    # Everything from the observed prior onward must remain byte-identical.
    if text[text.index(PRIOR_START):] != original[original.index(PRIOR_START):]:
        raise ValueError('Personal prior, state, update instruction or questionnaire changed')
    result = deepcopy(messages)
    result[0]['content'] = text
    return result


def prepare(out):
    began = perf_counter()
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    parent = read_json(PARENT/'manifest.json')
    sources = {str((PARENT/'manifest.json').relative_to(ROOT)): sha(PARENT/'manifest.json')}
    def frozen(name):
        p = PARENT/name
        if sha(p) != parent['prepared_file_sha256'][name]:
            raise ValueError('Archived input changed: '+name)
        sources[str(p.relative_to(ROOT))] = sha(p)
        return read_json(p)
    labels, hashes = completed_news()
    sources.update(hashes)
    links = frozen('evaluation_links_private.json')
    # Only previously recorded survey date is needed; do not open current answers.
    date_path = ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
    import pandas as pd
    date_receipt = read_json(date_path.parent/'summary.json')
    if sha(date_path) != date_receipt['output_file_sha256'][date_path.name]:
        raise ValueError('Prior date source changed')
    dates = pd.read_parquet(date_path, columns=['date', 'userid', 'survey_date']).set_index(['date', 'userid'])['survey_date']
    sources[str(date_path.relative_to(ROOT))] = sha(date_path)
    out.mkdir(parents=True)
    inventory = {}
    example = []
    selected_links = []
    totals = {'unique_prompts': 0, 'generation_repeats': 2, 'planned_requests_if_authorized': 6912,
              'estimated_input_bytes_times_two': 0, 'conservative_reservation_at_last_recorded_prices_usd': 0.}
    for month in MONTHS:
        dest = out/str(month)
        dest.mkdir()
        population = frozen(f'{month}/population.json')
        allocation_personas = deepcopy(population['personas'])
        for p in allocation_personas:
            for key in ('age_group', 'household_income_band'):
                if p['attributes'].get(key) is None:
                    p['attributes'][key] = 'unknown'
        selected, pi2, sampling = sample_strata(allocation_personas, month, n=96, seed=20261018)
        population['personas'] = [p for p in population['personas'] if p['agent_id'] in selected]
        population['materialized_count'] = len(selected)
        dump(dest/'population.json', population)
        env = frozen(f'{month}/environment.json')
        as_of = env['provider_args']['targets'][0]['as_of']
        simulation = frozen(f'{month}/simulation_reference.json')
        reference_bundle = simulation['decision_args']['reference_validation_bundle']
        timed = reference_bundle['parent']
        base = timed['parent']['base']['baseline']
        common = base['news']['common_news']
        pool_path = NEWS_PREP/f'pool_{month}.json'
        pool_name = str(pool_path.relative_to(ROOT))
        # Parent manifest pins these raw materialized pools independently of our source code.
        if sha(pool_path) != parent['source_sha256'][pool_name]:
            raise ValueError('Archived news pool changed')
        sources[pool_name] = sha(pool_path)
        pool = read_json(pool_path)
        missing = [r for r in pool if r['new_hits'] and r['article_id'] not in labels]
        if missing:
            raise ValueError('Missing already-paid labels')
        enriched = []
        for row in pool:
            item = {k: row[k] for k in NEWS_KEYS-{'routing_tags', 'semantic_label'}}
            item.update(routing_tags=news_tags(row), semantic_label=labels.get(row['article_id']))
            if datetime.fromisoformat(item['pub_date'].replace('Z', '+00:00')) > datetime.fromisoformat(as_of):
                raise ValueError('Future news')
            enriched.append(item)
        personal_pool = exact_deduplicate([r for r in enriched if r['placement'] != 'a1'
            and r['semantic_label'] and r['semantic_label']['decision'] == 'keep'])
        if len(personal_pool) < 17 or len(common) != 3:
            raise ValueError('Insufficient unique eligible articles')
        source_ids = read_json(ROOT/'outputs/sce_reference_population_20261017_v1'/str(month)/'profile_index_private.json')
        source_map = {r['agent_id']: r['source_id'] for r in source_ids}
        map_path = ROOT/'outputs/sce_reference_population_20261017_v1'/str(month)/'profile_index_private.json'
        pop_manifest = read_json(map_path.parent.parent/'manifest.json')
        if sha(map_path) != pop_manifest['prepared_file_sha256'][str(map_path.relative_to(map_path.parent.parent))]:
            raise ValueError('Original persona index changed')
        sources[str(map_path.relative_to(ROOT))] = sha(map_path)
        previews = {r['agent_id']: r for r in frozen(f'{month}/preview_reference.json')}
        chosen = [deepcopy(r) for r in links if r['month'] == month and r['agent_id'] in selected]
        by_id = {r['agent_id']: r for r in chosen}
        for row in chosen:
            row['inclusion_probability'] *= pi2[row['agent_id']]
            row['design_survey_weight'] = row['survey_weight']/row['inclusion_probability']
        selected_links.extend(chosen)
        arms = {f'news_{n}_{mode}': {} for n in (3, 8, 20) for mode in ('complete', 'reduced')}
        for persona in population['personas']:
            aid = persona['agent_id']
            old_personal = base['news']['rows'][aid]['personal_news']
            interests = interests_for_profile(persona['attributes'], base['news']['rows'][aid]['spending_shares'])
            ranked, _ = draw_news(personal_pool, 17, f'104729|{month}|{source_map[aid]}|personal', interests, .5, 2.)
            sort_news = lambda rows: sorted(rows, key=lambda r: (r['pub_date'], r['article_id']))
            if sort_news(ranked[:5]) != old_personal:
                raise ValueError('Eight-news reference content drift')
            original = previews[aid]['messages']
            if message_hash(original) != previews[aid]['prompt_sha256']:
                raise ValueError('Original prompt changed')
            prior_month = month-1 if month % 100 > 1 else (month//100-1)*100+12
            previous_day = pd.Timestamp(dates.loc[(prior_month, by_id[aid]['userid'])]).date().isoformat()
            for n in (3, 8, 20):
                personal = sort_news(ranked[:n-3])
                for mode in ('complete', 'reduced'):
                    messages = change_view(original, common, old_personal, personal,
                        timed['time_index_by_id'][aid], previous_day, as_of, complete=mode == 'complete')
                    if n == 8 and mode == 'complete' and messages != original:
                        raise ValueError('Concurrent control not byte-identical to archived prompt')
                    arm = f'news_{n}_{mode}'
                    arms[arm][aid] = {'messages': messages, 'prompt_sha256': message_hash(messages)}
                    size = len(json.dumps(messages, ensure_ascii=False).encode())
                    totals['unique_prompts'] += 1
                    totals['estimated_input_bytes_times_two'] += size*2
                    totals['conservative_reservation_at_last_recorded_prices_usd'] += 2*((size+256)*.3+1024*1.2)/1e6
                    if aid == population['personas'][0]['agent_id']:
                        example.append(f'\n=== {month} / {arm} / synthetic display index 1 ===\n'+messages[0]['content'])
        for arm, rows in arms.items():
            dump(dest/f'prompts_{arm}.json', {'month': month, 'arm': arm, 'rows': rows})
        weights = [r['design_survey_weight'] for r in chosen]
        inventory[str(month)] = {'as_of': as_of, 'selected_n': len(chosen), 'sampling': sampling,
            'raw_window_articles': len(pool), 'coarse_candidates': sum(bool(r['new_hits']) for r in pool),
            'unlabelled_coarse_candidates': len(missing), 'eligible_personal_articles_after_exact_dedup': len(personal_pool),
            'common_frontpage_candidates': len(exact_deduplicate([r for r in enriched if r['placement'] == 'a1'])),
            'eight_complete_byte_identity_checks': len(selected),
            'weight_ess': sum(weights)**2/sum(w*w for w in weights),
            'attribute_counts': {key: dict(Counter(str(p['attributes'].get(key)) for p in population['personas']))
                for key in ('age_group', 'household_income_band', 'education_group', 'numeracy', 'region')},
            'prompt_bytes_by_arm': {arm: {'min': min(len(json.dumps(r['messages'], ensure_ascii=False).encode()) for r in rows.values()),
                'max': max(len(json.dumps(r['messages'], ensure_ascii=False).encode()) for r in rows.values())} for arm, rows in arms.items()}}
    if totals['unique_prompts'] != 3456:
        raise ValueError('Preparation count mismatch')
    dump(out/'evaluation_links_private.json', selected_links)
    (out/'input_examples_private.txt').write_text('\n'.join(example))
    totals['rough_input_cost_using_four_bytes_per_token_usd'] = totals['estimated_input_bytes_times_two']/4*.3/1e6
    result = {'status': 'offline_views_prepared_not_authorized_not_engine_dry_run',
        'new_api_calls': 0, 'current_target_answers_read': False, 'months': list(MONTHS),
        'inventory': inventory, 'totals': totals, 'source_sha256': sources,
        'boundaries': ['Same P/prior/history/CE/confidence/policy/questionnaire in every arm.',
            'Reduced removes official-statistics and trends blocks and their release-group timing, not numbers naturally appearing in identical news or policy.',
            'First five of seventeen personalized draws reproduce archived eight-news control, after chronological display.',
            'No Andre donor rows or synthetic attention/channel personality are included in prompts.',
            'No paid authorization, run jobs or engineering receipts are produced by this preparation.'],
        'seconds': perf_counter()-began}
    dump(out/'summary.json', result)
    return result
