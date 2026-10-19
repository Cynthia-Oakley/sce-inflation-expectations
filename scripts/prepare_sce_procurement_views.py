#!/usr/bin/env python3
"""Prepare three offline procurement/price-proxy arms from frozen local inputs.

No network, target answers, scoring, model execution or authorization is opened.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from pypdf import PdfReader

from studies.sce_inflation_expectations.procurement_price_views import (
    FOOD_CATEGORIES, ROLE_TEXT, balanced_bundle_shuffle, choose_categories,
    extract_categories, render_view, transform_prompt, validate_cutoff)

BRIDGE = ROOT/'outputs/sce_atus_sce_matching_20261019_v1'
MENUS = ROOT/'outputs/sce_personal_information_menus_20261019_v1'
PARENT = ROOT/'outputs/sce_news_breadth_trial_20261019_v2'
ARMS = ('shared_price', 'matched_role', 'shuffled_role')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def timing(text, fact):
    date = datetime.fromisoformat(fact['published_at']).date().isoformat()
    pattern = rf'^- CPI figures, reference {re.escape(fact["reference_period"])}, released {date}: (earlier|later|same-day uncertain)\.$'
    found = re.findall(pattern, text, re.M)
    if len(found) != 1:
        raise ValueError('Unique existing CPI availability tag required')
    return found[0]


def prepare(out):
    start = perf_counter(); out = out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    parent, bridge, menu = read(PARENT/'manifest.json'), read(BRIDGE/'summary.json'), read(MENUS/'summary.json')
    sources = {}

    def pinned(path, expected=None):
        digest = sha(path)
        if expected is not None and digest != expected:
            raise ValueError('Pinned input changed: '+str(path))
        sources[str(path.relative_to(ROOT))] = digest
        return read(path)

    def frozen(name):
        return pinned(PARENT/name, parent['prepared_file_sha256'][name])

    for path in (PARENT/'manifest.json', BRIDGE/'summary.json', MENUS/'summary.json'):
        pinned(path)
    assignments = pinned(BRIDGE/'allocations_private.json', menu['source_sha256'][str((BRIDGE/'allocations_private.json').relative_to(ROOT))])
    profiles = pinned(BRIDGE/'historical_profiles_and_role_probabilities_private.json', menu['source_sha256'][str((BRIDGE/'historical_profiles_and_role_probabilities_private.json').relative_to(ROOT))])
    catalog = pinned(MENUS/'price_catalog.json', menu['output_sha256']['price_catalog.json'])
    articles = pinned(MENUS/'article_catalog_public_source_local.json', menu['output_sha256']['article_catalog_public_source_local.json'])
    profile = {(r['month'], r['agent_id']): r for r in profiles}
    seeds = bridge['allocation_seeds']; inventories = []; previews = []; allocations = []
    out.mkdir(parents=True); price_catalog = {}; prompt_count = 0
    for month in bridge['months']:
        dest = out/str(month); dest.mkdir()
        original = frozen(f'{month}/prompts_baseline.json')['rows']
        env = frozen(f'{month}/environment.json')['provider_args']
        as_of = env['targets'][0]['as_of']
        signal = next(v for v in catalog[str(month)]['signals'].values() if v['signal_id'].startswith('bls_cpi_food_at_home_yoy_'))
        date = signal['published_at'][:10]
        path = ROOT/'data/raw/bls_initial_releases'/signal['reference_period']/(
            'cpi_'+signal['reference_period'].replace('-', '_')+'_released_'+date.replace('-', '_')+'.pdf')
        reader = PdfReader(path); pages = [p.extract_text() for p in reader.pages]
        if signal['source_version'] not in '\n'.join(pages):
            raise ValueError('Release identifier missing from original PDF')
        values = extract_categories(pages)
        if values['food_at_home']['yoy_nsa_percent'] != signal['value']:
            raise ValueError('New table parse disagrees with frozen first-release E')
        sources[str(path.relative_to(ROOT))] = sha(path)
        for fact in values.values():
            fact.update(reference_period=signal['reference_period'], published_at=signal['published_at'],
                vintage=signal['source_version'], source_url=signal['source_url'],
                source_file=str(path.relative_to(ROOT)), source_sha256=sha(path),
                historical_release_archive=True, strict_B_eligible=False,
                strict_B_note='Release-time and archive recorded; strict-B source/version approval is separate.')
        validate_cutoff(values.values(), as_of)
        price_catalog[str(month)] = values
        words = {
            'additional_food_candidates': r'\b(eggs?|dairy|cheese|cereals?|bakery|bakeries|fruits?|vegetables?|supermarkets?|chicken)\b',
            'household_goods_candidates': r'\b(cleaning products?|laundry detergent|toilet paper|paper towels?|toiletries|personal care)\b'}
        pool = list(articles[str(month)].values())
        route_counts = {'existing_food_tag': sum('food' in r.get('routing_tags',[]) for r in pool)}
        route_ids = {}
        for label, expression in words.items():
            hits = [r for r in pool if re.search(expression, ' '.join(r.get(k) or '' for k in ('headline','abstract','snippet')), re.I)]
            route_counts[label] = len(hits); route_ids[label] = [r['article_id'] for r in hits]
        dump(dest/'news_route_candidates_private.json', route_ids)
        month_balance = []
        for seed in seeds:
            wave = {r['agent_id']:r for r in assignments[str(seed)] if r['month']==month}
            ids = sorted(original)
            if set(ids) != set(wave):
                raise ValueError('Frozen prompt / role roster mismatch')
            bundles = []
            for aid in ids:
                row = profile[month,aid]; role = wave[aid]['role_matched']
                categories = choose_categories(role, str(row['userid']), seed)
                bundles.append({'role':role, 'categories':categories,
                    'view':render_view(role,categories,values,'recipient-specific tag added at rendering')})
            weights = [profile[month,aid]['design_weight'] for aid in ids]
            ix, balance = balanced_bundle_shuffle(bundles, weights, seed+month)
            balances = {**balance, 'seed':seed}; month_balance.append(balances)
            arms = {a:{} for a in ARMS}; detail_counts = Counter()
            for i,aid in enumerate(ids):
                old = original[aid]['messages']; status = timing(old[0]['content'], values['food_at_home'])
                for arm in ARMS:
                    b = None if arm=='shared_price' else bundles[i if arm=='matched_role' else ix[i]]
                    view = render_view(None if b is None else b['role'], [] if b is None else b['categories'], values, status)
                    messages = transform_prompt(old,view)
                    # Same byte convention as shared FrozenPromptDecision.message_hash.
                    digest = hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()
                    arms[arm][aid] = {'messages':messages,'prompt_sha256':digest}
                    prompt_count += 1
                    if seed==seeds[0] and b is not None and arm=='matched_role' and len(previews)<6:
                        previews.append({'month':month,'role':b['role'],'price_fragment':view})
                detail_counts[bundles[i]['role']] += 1
                allocations.append({'month':month,'seed':seed,'agent_id':aid,
                    'matched_role':bundles[i]['role'],'matched_categories':bundles[i]['categories'],
                    'shuffled_role':bundles[ix[i]]['role'],'shuffled_categories':bundles[ix[i]]['categories'],
                    'price_publication_status':status})
            for arm,rows in arms.items():
                # Seed is in path/audit, not an extra field rejected by shared loader.
                dump(dest/f'prompts_{arm}_s{seed}.json', {'month':month,'arm':arm,'rows':rows})
        inventories.append({'month':month,'as_of':as_of,'person_months':len(original),
            'categories_extracted':len(values),'grocery_detail_categories':len(FOOD_CATEGORIES),
            'reserve_categories_not_assigned':3,'existing_news_count_per_person':8,
            'news_candidates_audit_only':route_counts,'balance':month_balance})
    dump(out/'category_prices.json',price_catalog)
    dump(out/'allocations_private.json',allocations)
    dump(out/'price_preview_no_identifiers.json',previews)
    # Full realistic prompts stay private; a single intact example is local only.
    m = str(bridge['months'][2]); first = read(out/m/f'prompts_matched_role_s{seeds[0]}.json')
    (out/'full_prompt_example_private.txt').write_text(next(iter(first['rows'].values()))['messages'][0]['content'])
    for path in (Path(__file__).resolve(), ROOT/'studies/sce_inflation_expectations/procurement_price_views.py'):
        sources[str(path.relative_to(ROOT))] = sha(path)
    summary = {'status':'offline_complete_prompts_not_engine_or_paid_trial',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'new_api_calls':0,'new_cost_usd':0,
        'current_target_answers_read':False,'model_or_run_config_changed':False,
        'months':bridge['months'],'n_person_months':len(profiles), 'allocation_seeds':seeds,
        'arms':list(ARMS),'complete_prompt_variants':prompt_count,
        'price_facts':sum(len(v) for v in price_catalog.values()),
        'inventory':inventories,'source_sha256':sources,
        'gates_remaining':['Official same-input GPT transport and budget not confirmed.',
            'No official-engine dry run has been executed for these new prompts.',
            'Months are already explored, not an independent validation set.',
            'Proposed future sample/repeats/one primary allocation seed not frozen.',
            'No known personal receipts or observed SCE shopping roles; proxy validity unproven.',
            'ATUS2022 for earlier months is retrospective A-only structural assumption.'],
        'seconds':perf_counter()-start}
    dump(out/'summary.json',summary)
    dump(out/'manifest.json',{'source_sha256':sources,
        'output_sha256':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()},
        'paid_execution_supported':False})
    print(json.dumps({k:summary[k] for k in ['status','n_person_months','complete_prompt_variants','price_facts','seconds']},ensure_ascii=False))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    prepare(parser.parse_args().out)
