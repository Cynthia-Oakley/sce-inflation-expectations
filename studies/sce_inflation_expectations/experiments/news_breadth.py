"""Freeze a news-breadth allocation trial using existing, timed prompt views.

No network or target-answer reads. Existing whole prompts supply both article
text and release timing; only the choice of an individual's 3/8/20 view changes.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import re
from time import perf_counter

import numpy as np

from .frozen_batch import ROOT, dump, read_json, sha, verify
from .information_exposure import PRIOR_START, POLICY_START, NEWS_START
from ..news_exposure_demo import TERMS
from ..prior_belief_experiment import message_hash

PARENT = ROOT/'outputs/sce_information_exposure_trial_20261018_v1'
BRIDGE = ROOT/'outputs/sce_atus_sce_matching_20261019_v1'
MENUS = ROOT/'outputs/sce_personal_information_menus_20261019_v1'
PLAN = ROOT/'docs/workstreams/20261018_targeted_mechanisms/news_breadth_trial_plan_20261019.md'
ARMS = ['baseline', 'news_matched', 'news_randomized']
LEVELS = (3, 8, 20)
SEED = 20261019
TAGS = sorted(TERMS)


def exposure_features(messages, catalog):
    """Counts, byte-length proxies and coarse routing tags; never model outcomes."""
    text = messages[0]['content']
    if len(messages) != 1 or messages[0]['role'] != 'user':
        raise ValueError('Expected single user message')
    if text.count(NEWS_START) != 1 or text.count(POLICY_START) != 1:
        raise ValueError('Unique news block boundaries required')
    news = text[text.index(NEWS_START):text.index(POLICY_START)]
    lookup = defaultdict(list)
    for row in catalog.values():
        lookup[row['pub_date'][:10], row['headline']].append(row)
    topics, identities = Counter(), []
    for date, title in re.findall(r'^- Online publication date ([0-9-]+): (.*)$', news, re.M):
        candidates = lookup[date, title]
        if not candidates or len({tuple(r['routing_tags']) for r in candidates}) != 1:
            raise ValueError('Missing or ambiguous source topic tags')
        topics.update(candidates[0]['routing_tags'])
        identities.append((date, title))
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate displayed news header')
    return np.array([len(identities), len(news.encode()), len(json.dumps(messages, ensure_ascii=False).encode()),
                     *[topics[t] for t in TAGS]], float)


def balance_receipt(reference, candidate, weights):
    left, right = weights@reference, weights@candidate
    gaps = np.abs(right[:3]/left[:3]-1)
    topic = np.abs(right[3:]/right[0]-left[3:]/left[0])
    return {'weighted_count_relative_gap': float(gaps[0]),
        'weighted_news_bytes_relative_gap': float(gaps[1]),
        'weighted_prompt_bytes_relative_gap': float(gaps[2]),
        'topic_share_absolute_gaps': dict(zip(TAGS, topic.tolist())),
        'weighted_mean_news_reference': float(left[0]/weights.sum()),
        'weighted_mean_news_candidate': float(right[0]/weights.sum())}


def balanced_shuffle(labels, cube, weights, seed, max_draws=4096):
    """First random permutation meeting prespecified input balance tolerances.

    cube[person, level] contains that person's actual prompt-view measurements.
    Rejection depends on inputs alone, never answers, errors or fitted outcomes.
    """
    labels = np.asarray(labels, int)
    cube, weights = np.asarray(cube, float), np.asarray(weights, float)
    n = len(labels)
    if (cube.shape != (n, 3, 3+len(TAGS)) or weights.shape != (n,)
            or not np.isfinite(cube).all() or not np.isfinite(weights).all()
            or (weights <= 0).any() or not set(labels) <= set(LEVELS)):
        raise ValueError('Invalid allocation/input-feature matrix')
    indices = np.array([LEVELS.index(int(v)) for v in labels])
    reference = cube[np.arange(n), indices]
    rng = np.random.default_rng(seed)
    for attempt in range(1, max_draws+1):
        chosen = rng.permutation(indices)
        if np.array_equal(chosen, indices):
            continue
        receipt = balance_receipt(reference, cube[np.arange(n), chosen], weights)
        if (max(receipt[k] for k in ('weighted_count_relative_gap', 'weighted_news_bytes_relative_gap',
                                    'weighted_prompt_bytes_relative_gap')) <= .01
                and max(receipt['topic_share_absolute_gaps'].values()) <= .02):
            return np.array(LEVELS)[chosen], {**receipt, 'attempts': attempt,
                'same_level_fraction': float(np.mean(chosen == indices))}
    raise ValueError('No balanced shuffle within prespecified candidates; do not silently relax')


def select_views(by_level, labels):
    """Select intact archived prompts, including their matching release labels."""
    if any(set(rows) != set(labels) for rows in by_level.values()):
        raise ValueError('View/roster mismatch')
    result = {}
    for aid, level in labels.items():
        if level not in LEVELS:
            raise ValueError('Unsupported news count')
        row = deepcopy(by_level[level][aid])
        if message_hash(row['messages']) != row['prompt_sha256']:
            raise ValueError('Archived prompt hash mismatch')
        base = by_level[8][aid]['messages'][0]['content']
        text = row['messages'][0]['content']
        if (text[:text.index(NEWS_START)] != base[:base.index(NEWS_START)]
                or text[text.index(PRIOR_START):] != base[base.index(PRIOR_START):]):
            raise ValueError('Persona/statistics or prior/questionnaire changed')
        result[aid] = row
    return result


def prepare(out):
    began = perf_counter(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored trial folder required')
    parent = read_json(PARENT/'manifest.json')
    menu = read_json(MENUS/'summary.json')
    source = {str(PLAN.relative_to(ROOT)):sha(PLAN)}
    def pinned(path, digest):
        if sha(path) != digest:
            raise ValueError('Pinned source changed: '+str(path))
        source[str(path.relative_to(ROOT))] = digest
        return read_json(path)
    def frozen(name):
        return pinned(PARENT/name, parent['prepared_file_sha256'][name])
    for path in (PARENT/'manifest.json', MENUS/'summary.json'):
        source[str(path.relative_to(ROOT))] = sha(path)
    allocations = pinned(BRIDGE/'allocations_private.json',
        menu['source_sha256'][str((BRIDGE/'allocations_private.json').relative_to(ROOT))])[str(SEED)]
    catalog = pinned(MENUS/'article_catalog_public_source_local.json',
        menu['output_sha256']['article_catalog_public_source_local.json'])
    old_protocol, links = frozen('protocol.json'), frozen('evaluation_links_private.json')
    allowed = {'month','agent_id','userid','profile','stratum','survey_weight','inclusion_probability','design_survey_weight'}
    if any(set(row)-allowed for row in links):
        raise ValueError('Unexpected answer fields in input linkage')
    months = old_protocol['months']; n = 96; repeats = [1, 2]
    calls = len(months)*n*len(ARMS)*len(repeats)
    protocol = {'id':'sce-news-breadth-v1','registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'mechanism':'externally_matched_news_breadth','months':months,'n_per_month':n,'arms':ARMS,
        'generation_repeats':repeats,'planned_calls':calls,'research_line':'A_conditional_returner_reconstruction',
        'model':'deepseek-flash','official_advertised_version':'DeepSeek-V4.1-Flash-1017',
        'model_identity_limit':'Mutable alias; record returned model/fingerprint and concurrent controls.',
        'destination':'https://api.deepseek.com','temperature':.5,'max_tokens':1024,'thinking':'disabled','retry_max':0,
        'budget_cap_usd':16.,'price_input_per_mtok':.3,'price_output_per_mtok':1.2,
        'pricing_verified_date':'2026-10-19','pricing_url':'https://api-docs.deepseek.com/quick_start/pricing/',
        'allocation_seed':SEED,'shuffle_seed_rule':'20261019 + target YYYYMM',
        'dispatch_order_seed':20261029,'sampling':'Same frozen age x income stratified 96 returners per wave; design weights unchanged.',
        'allocation':'External six-class economic-news interest probabilities conditional on age, education, income and region; stable person draw and wave ranks; quotas 48x3/28x8/20x20.',
        'input_balance':'Matched/random preserve count multiset; design-weighted count/news bytes/total bytes relative gaps <=1%, coarse topic shares absolute gaps <=.02. First acceptable shuffle out of <=4096. Bytes are a token proxy.',
        'primary_metric':'q9_center_mae_pp','primary_weight':'design_survey_weight',
        'primary_comparator':'news_randomized vs news_matched isolates allocation conditional on approximate input balance.',
        'prespecified_contrasts':[['news_randomized','news_matched'],['baseline','news_randomized'],['baseline','news_matched']],
        'secondary_metrics':['cross_section_w1_pp','delta_w1_pp','across_person_iqr_pp','individual_density_mean_mae_pp','q8_center_mae_pp'],
        'population_groups':['education_group','age_group','household_income_band','region','numeracy'],
        'screen':'Exploratory candidate only: matched improves center MAE and cross-section W1 vs randomized; >=4/6 monthly center contrasts nonpositive; show repeats, leave-one-month-out and false/missed moves. No automatic default upgrade.',
        'coverage_rule':'Complete all36 cells; all-arm/both-repeat common support, retain invalid responses, no automatic retries.',
        'baseline_refs':['copy_previous','history_anchor_half'],
        'limits':['All six months previously explored; this is prospective mechanism execution on development months, not independent validation.',
            'Shared interest P has weak out-of-sample predictive support; counts and quotas are experimental, not observed readership.',
            '2021 external attention data used retrospectively for 2020; not strict B. Own true prior is conditional A input.',
            'Assignment seed fixed once, two generations do not test alternative allocation seeds or create more people.',
            'Macro statistics, P, CE, Fed confidence, prior/history, news relevance rules, policy, questionnaire all retained.',
            'No new shopping role, personal receipts, Q1/Q2, quiz answers, psychology, or Event data are added.',
            'Input balance does not identify equal semantic information value or actual token count. Topic tags are coarse.',
            'Future independent months must be registered after mechanism selection, before new input construction/calls.']}
    # Truth remains an opaque hash pin here; the evaluator alone may open it.
    truth = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
    source[str(truth.relative_to(ROOT))] = sha(truth)
    out.mkdir(parents=True); dump(out/'evaluation_links_private.json',links)
    jobs, audit_rows, inventories = [], [], []
    total_bytes, max_chars, reserve = 0, 0, 0.
    for month in months:
        dest = out/str(month); dest.mkdir()
        population, environment = frozen(f'{month}/population.json'), frozen(f'{month}/environment.json')
        cfg = frozen(f'{month}/simulation.json'); cfg['decision_args'] = {}
        for name,value in [('population',population),('environment',environment),('simulation',cfg)]:
            dump(dest/(name+'.json'),value)
        people = [p['agent_id'] for p in population['personas']]
        wave = {r['agent_id']:r for r in allocations if r['month']==month}
        link = {r['agent_id']:r for r in links if r['month']==month}
        if len(people)!=n or set(people)!=set(wave) or set(people)!=set(link):
            raise ValueError('Expected frozen 96-person allocation scope')
        views = {level:frozen(f'{month}/prompts_'+('baseline' if level==8 else f'news_{level}_complete')+'.json')['rows'] for level in LEVELS}
        cube = np.array([[exposure_features(views[level][aid]['messages'],catalog[str(month)]) for level in LEVELS] for aid in people])
        if not np.array_equal(cube[:,:,0],np.tile(LEVELS,(n,1))):
            raise ValueError('Archived article count mismatch')
        counts = np.array([wave[aid]['news_matched'] for aid in people])
        if Counter(counts)!={3:48,8:28,20:20}:
            raise ValueError('Fixed quota changed')
        w = np.array([link[aid]['design_survey_weight'] for aid in people])
        randomized,balance = balanced_shuffle(counts,cube,w,SEED+month)
        labels = {'baseline':{aid:8 for aid in people},'news_matched':dict(zip(people,counts.tolist())),
            'news_randomized':dict(zip(people,randomized.tolist()))}
        for aid in people:
            audit_rows.append({'month':month,'agent_id':aid,**{arm:m[aid] for arm,m in labels.items()}})
        inventories.append({'month':month,'as_of':environment['provider_args']['targets'][0]['as_of'],
            'n':n,'quota':{'3':48,'8':28,'20':20},'balance':balance,
            'unweighted_mean_news':8.,'weighted_mean_news_uniform':8.})
        for arm in ARMS:
            rows = select_views(views,labels[arm])
            dump(dest/f'prompts_{arm}.json',{'month':month,'arm':arm,'rows':rows})
            sizes = [len(json.dumps(r['messages'],ensure_ascii=False).encode()) for r in rows.values()]
            max_chars = max(max_chars,max(len(json.dumps(r['messages'],ensure_ascii=False)) for r in rows.values()))
            bound = sum(((size+256)*.3+1024*1.2)/1e6 for size in sizes)
            cap = math.ceil(bound*1e6)/1e6
            total_bytes += 2*sum(sizes)
            for repeat in repeats:
                jobs.append({'month':month,'arm':arm,'repeat':repeat,'seed':41+repeat,
                    'run_id':f'{out.name}-{month}-{arm}-r{repeat}','cap_usd':cap})
                reserve += cap
    protocol['max_prompt_chars']=max_chars+100
    if reserve > protocol['budget_cap_usd']:
        raise ValueError('Conservative reservations exceed proposed budget')
    rng = random.Random(protocol['dispatch_order_seed']); blocks=[(m,r) for m in months for r in repeats]; rng.shuffle(blocks)
    ordered=[]
    for month,repeat in blocks:
        block=[j for j in jobs if j['month']==month and j['repeat']==repeat]; rng.shuffle(block); ordered.extend(block)
    dump(out/'protocol.json',protocol); dump(out/'allocation_private.json',audit_rows)
    for p in [*sorted((ROOT/'studies/sce_inflation_expectations').rglob('*.py')),
              ROOT/'scripts/run_sce_frozen_trial.py',ROOT/'scripts/prepare_sce_news_breadth_trial.py']:
        source[str(p.relative_to(ROOT))]=sha(p)
    rough=total_bytes/4*.3/1e6+calls*300*1.2/1e6
    manifest={'jobs':ordered,'planned_calls':calls,'protocol_sha256':sha(out/'protocol.json'),
        'prepared_file_sha256':{str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')},
        'source_sha256':source,'proposed_cap_usd':16.,'conservative_reservation_usd':reserve,
        'estimated_cost_usd':rough,'new_api_calls':0,'status':'frozen_pending_engine_checks_and_authorization'}
    dump(out/'manifest.json',manifest)
    dump(out/'authorization.json',{'approved':False,'protocol_sha256':manifest['protocol_sha256'],
        'cap_usd':16.,'planned_calls':calls,'destination':protocol['destination'],'user_confirmation':None})
    verify(out)
    receipt={'status':'prepared_no_api_calls','months':months,'n_per_month':n,'jobs':len(jobs),'planned_calls':calls,
        'inventories':inventories,'estimated_cost_usd':rough,'conservative_reservation_usd':reserve,
        'proposed_hard_cap_usd':16.,'new_api_calls':0,'new_cost_usd':0.,'target_answers_parsed':False,
        'seconds':perf_counter()-began}
    dump(out/'preparation_receipt.json',receipt)
    return receipt
