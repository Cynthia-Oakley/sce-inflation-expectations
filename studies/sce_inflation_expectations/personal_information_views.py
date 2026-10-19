"""Build sourced news/price menus from an offline ATUS/SCE bridge.

Only fragments and routing audits are produced; no simulation runner is called.
"""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from time import perf_counter

from .evaluation.attention_support import ROOT, sha
from .personal_information_preparation import TRIAL, SEEDS, dump, food_detail_count
from .reference_validation_preparation import completed_news, NEWS_PREP
from .news_exposure import NEWS_KEYS, check_news
from .news_exposure_demo import draw_news, exact_deduplicate, news_tags

REFERENCE = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
ROLE_TEXT = {1:'You do none of the usual grocery shopping for your household.',
    2:'You do a little of the grocery shopping for your household.',
    3:'You do some of the grocery shopping for your household.',
    4:'You do a lot of the grocery shopping for your household.',
    5:'You do all of the usual grocery shopping for your household.'}


def public_fact_text(signal):
    return (f"{signal['measure']}: {signal['value']} {signal['unit']}; "
        f"reference period {signal['reference_period']}; published {signal['published_at']}.")


def prepare(source, out):
    began = perf_counter(); source,out = Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs') or not source.is_relative_to(ROOT/'outputs'):
        raise ValueError('Ignored prepared source and fresh output folder required')
    bridge = json.loads((source/'summary.json').read_text())
    for name,digest in bridge['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Bridge input/source changed: '+name)
    records = json.loads((source/'historical_profiles_and_role_probabilities_private.json').read_text())
    allocations = json.loads((source/'allocations_private.json').read_text())
    by_key = {(r['month'],r['agent_id']):r for r in records}
    labels,label_hashes = completed_news()
    parent = json.loads((REFERENCE/'manifest.json').read_text())
    trial = json.loads((TRIAL/'manifest.json').read_text())
    sources = {str(p.relative_to(ROOT)):sha(p) for p in [source/'summary.json',
        source/'historical_profiles_and_role_probabilities_private.json',source/'allocations_private.json',Path(__file__).resolve()]}
    sources.update(label_hashes)
    article_catalog, price_catalog, menus, inventories, previews = {},{},{},[],[]
    for month in bridge['months']:
        def frozen(root,manifest,name):
            path = root/name
            if sha(path) != manifest['prepared_file_sha256'][name]:
                raise ValueError('Frozen source changed: '+name)
            sources[str(path.relative_to(ROOT))] = sha(path)
            return json.loads(path.read_text())
        environment = frozen(TRIAL,trial,f'{month}/environment.json')['provider_args']
        as_of = environment['targets'][0]['as_of']; cutoff = datetime.fromisoformat(as_of)
        simulation = frozen(REFERENCE,parent,f'{month}/simulation_reference.json')
        base = simulation['decision_args']['reference_validation_bundle']['parent']['parent']['base']['baseline']
        common = base['news']['common_news']; check_news(common,as_of,common=True)
        pool_path = NEWS_PREP/f'pool_{month}.json'
        if sha(pool_path) != parent['source_sha256'][str(pool_path.relative_to(ROOT))]:
            raise ValueError('Frozen public news pool changed')
        sources[str(pool_path.relative_to(ROOT))] = sha(pool_path)
        pool = json.loads(pool_path.read_text())
        enriched=[]
        for item in pool:
            row = {k:item[k] for k in NEWS_KEYS-{'routing_tags','semantic_label'}}
            row.update(routing_tags=news_tags(item),semantic_label=labels.get(item['article_id']))
            if row['placement']!='a1' and row['semantic_label'] and row['semantic_label']['decision']=='keep':
                enriched.append(row)
        personal = exact_deduplicate(enriched); check_news(personal,as_of)
        article_catalog[str(month)] = {r['article_id']:r for r in common+personal}
        signals = environment['signals_by_step']['0']
        if any(datetime.fromisoformat(r['published_at'].replace('Z','+00:00'))>cutoff for r in signals):
            raise ValueError('Future price/statistics signal')
        latest = [r for r in signals if r.get('role')=='latest_release']
        food = [[r for r in latest if r['signal_id'].startswith(prefix)] for prefix in ('bls_cpi_food_yoy_','bls_cpi_food_at_home_yoy_')]
        if any(len(rows)!=1 for rows in food):
            raise ValueError('Exactly one initial-release food and food-at-home signal required')
        food = [rows[0] for rows in food]
        headlines = [r for r in latest if r['signal_id'].startswith(('bls_cpi_u_all_items_yoy_','bls_unemployment_rate_'))]
        price_catalog[str(month)] = {'signals':{r['signal_id']:r for r in signals},
            'public_statistics_menu':{'news_only':[],'latest_headlines':[r['signal_id'] for r in headlines],
                'complete_historical_table':[r['signal_id'] for r in signals]},
            'food_details_in_order':[r['signal_id'] for r in food],
            'notice':'National published category indicators, not individual transactions or perceived price changes.'}
        tag_counts = Counter(tag for r in personal for tag in r['routing_tags'])
        inventories.append({'month':month,'as_of':as_of,'eligible_personal_articles':len(personal),
            'topic_tag_article_counts':dict(tag_counts),'news_40_menu_available':len(personal)>=37,
            'missing_price_domains':['No verified individual receipts or store-level paid prices.',
                'No separate cleaning/paper/personal-care price series in this frozen environment.',
                'No verified respondent driving role; gasoline is not automatically personal exposure.']})
        for seed in SEEDS:
            for allocation in allocations[str(seed)]:
                if allocation['month']!=month:
                    continue
                profile = by_key[month,allocation['agent_id']]['profile']
                for role_arm in ('matched','shuffled'):
                    role = allocation['role_'+role_arm]
                    interests = set()
                    if profile.get('housing_tenure') in ('owner','renter'):
                        interests.add('owned_housing' if profile['housing_tenure']=='owner' else 'rental_housing')
                    if profile.get('employment_status') in ('employed','unemployed','on_leave'):
                        interests.add('labor_income')
                    if role >= 4:
                        interests.add('food')
                    ranked,audit = draw_news(personal,min(37,len(personal)),
                        f'{seed}|{month}|{allocation["userid"]}|personal_information',interests,.5,2.)
                    menu = {str(n):[r['article_id'] for r in common+ranked[:n-3]]
                        for n in (3,8,20,40) if n-3<=len(ranked)}
                    food_ids = [r['signal_id'] for r in food[:food_detail_count(role)]]
                    key = f'{seed}|{month}|{allocation["agent_id"]}|{role_arm}'
                    menus[key] = {'month':month,'agent_id':allocation['agent_id'],'seed':seed,
                        'role_arm':role_arm,'synthetic_role':role,'role_text':ROLE_TEXT[role],
                        'menus_by_news_count':menu,'food_signal_ids':food_ids,
                        'news_count_matched':allocation['news_matched'],
                        'news_count_shuffled':allocation['news_shuffled'],
                        'routing_interests':sorted(interests),'draw_audit':audit,
                        'status':'draft_fragments_not_engine_prompts','strict_B_eligible':False}
                    if seed==SEEDS[0] and len(previews)<6 and allocation['news_matched']==20 and role>=4:
                        previews.append({'month':month,'synthetic_role':role,
                            'text':ROLE_TEXT[role]+'\nFood-related public information encountered:\n'+
                                '\n'.join(public_fact_text(r) for r in food[:food_detail_count(role)])+
                                '\nThese are national category indicators, not your own transaction records.',
                            'news_count':20,'news_headlines':[article_catalog[str(month)][aid]['headline'] for aid in menu['20']],
                            'note':'Source-based experimental fragment; not actually sent to a model.'})
    out.mkdir(parents=True)
    dump(out/'menus_private.json',menus); dump(out/'article_catalog_public_source_local.json',article_catalog)
    dump(out/'price_catalog.json',price_catalog)
    dump(out/'preview_no_identifiers.json',previews)
    result = {'status':'sourced_information_menus_prepared_not_runnable_trial',
        'new_api_calls':0,'new_llm_answers':0,'new_cost_usd':0,'current_SCE_answers_read':False,
        'n_person_months':len(records),'n_role_menus':len(menus),'allocation_seeds':list(SEEDS),
        'monthly_inventory':inventories,'source_sha256':sources,
        'output_sha256':{p.name:sha(p) for p in out.iterdir() if p.is_file()},
        'proposed_factorial_contrasts':['matched/randomized news breadth, same role view',
            'matched/randomized shopping role, same breadth assignment'],
        'not_yet_done':['Engine prompt adapter and timing metadata for new fragments.',
            'Source-year and household-selection sensitivity before freezing a paid trial.',
            'Weighted topic/content/token balance in addition to already balanced counts.',
            'Independent target months, exact request scope and budget approval.'],
        'seconds':perf_counter()-began}
    dump(out/'summary.json',result)
    return result
