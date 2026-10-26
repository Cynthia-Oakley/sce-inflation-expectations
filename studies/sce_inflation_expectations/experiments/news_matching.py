"""Outcome-blind news quantity/theme contrasts over archived V3.2 prompts.

Preparation is offline. No target answers, model replies, or API are read here.
Existing raw calls are indexed only by the separate, authorized ledger adapter.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np
import pandas as pd

from .frozen_batch import ROOT, dump, read_json, sha
from .model_comparison import validate_v32_transport
from .news_breadth import balanced_shuffle, exposure_features, balance_receipt
from .post2025_trial import source_labels
from .information_exposure import NEWS_START, POLICY_START, TIMING_START, PRIOR_START
from ..coverage_preparation import build_news_pool
from ..news_selection_trial import RecallRules, RULE_FILE
from ..news_exposure import NEWS_KEYS, check_news, interests_for_profile
from ..news_exposure_demo import draw_news, exact_deduplicate, news_tags, render_news_input
from ..information_update_runtime import publication_status
from ..prior_belief_preparation import month_offset
from ..prior_belief_experiment import message_hash
from ..evaluation.attention_support import ARCHIVE, FEATURES, fit_probabilities, harmonize
from ..evaluation.heterogeneous_news import stable_uniform

ARMS = ['fixed_8', 'random_quantity', 'demographic_quantity', 'random_quantity_uniform_topics']
OLD = [202009, 202109, 202206, 202503]
NEW = [202504, 202506, 202508, 202510]
MONTHS = sorted(OLD + NEW)
LINK_KEYS = {'month','agent_id','userid','profile','stratum','survey_weight',
             'inclusion_probability','design_survey_weight'}
FRAME = ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'


def allocate_quantity(ids, probabilities, seed):
    """Scale the registered 48/28/20 quotas; random person draws persist by ID."""
    p = np.asarray(probabilities, float)
    ids = list(map(str, ids)); n = len(ids)
    if (n % 96 or not n or len(set(ids)) != n or p.shape != (n,6)
            or not np.isfinite(p).all() or (p < 0).any() or not np.allclose(p.sum(1),1)):
        raise ValueError('Unique 96-multiple roster and six-class probabilities required')
    scores = []
    for uid, row in zip(ids,p):
        category = min(int(np.searchsorted(np.cumsum(row),stable_uniform(seed,uid,'class'),side='right')),5)
        scores.append((category,stable_uniform(seed,uid,'tie'),uid))
    levels = [level for level,count in [(3,48),(8,28),(20,20)] for _ in range(count*(n//96))]
    return {uid:level for (_,_,uid),level in zip(sorted(scores),levels)}


def change_news(messages, common, old_personal, new_personal, previous_day, as_of):
    """Only article text and its own public-availability list may change."""
    if len(messages) != 1 or messages[0]['role'] != 'user':
        raise ValueError('One archived user message required')
    check_news(common,as_of,common=True); check_news(new_personal,as_of)
    original = messages[0]['content']
    for marker in (NEWS_START,POLICY_START,TIMING_START,PRIOR_START):
        if original.count(marker) != 1:
            raise ValueError('Unique archived news/timing/prior boundaries required')
    old = render_news_input(common,old_personal)
    if original.count(old) != 1:
        raise ValueError('Archived news must reproduce exactly')
    pattern = r'^- Other news, in the order listed above: .*\.$'
    old_status = '- Other news, in the order listed above: '+'; '.join(
        publication_status(r['pub_date'],previous_day,as_of) for r in old_personal)+'.'
    if re.findall(pattern,original,re.M) != [old_status]:
        raise ValueError('Recipient-specific old news timing mismatch')
    status = '- Other news, in the order listed above: '+'; '.join(
        publication_status(r['pub_date'],previous_day,as_of) for r in new_personal)+'.'
    updated = original.replace(old,render_news_input(common,new_personal),1).replace(old_status,status,1)
    if (updated[:updated.index(NEWS_START)] != original[:original.index(NEWS_START)]
            or updated[updated.index(PRIOR_START):] != original[original.index(PRIOR_START):]):
        raise ValueError('A non-news persona, price, prior, or questionnaire byte changed')
    # Removing both treatment blocks must recover the same entire message.
    def remove(text):
        return text[:text.index(NEWS_START)]+re.sub(pattern,'<NEWS_TIMING>',text[text.index(POLICY_START):],flags=re.M)
    if remove(updated) != remove(original):
        raise ValueError('Non-news policy/timing information changed')
    result = deepcopy(messages);result[0]['content'] = updated
    return result


def validate_config(c):
    validate_v32_transport(c)
    if (c['mechanism'] != 'v32_news_matching' or c['months'] != MONTHS or c['arms'] != ARMS
            or c['n_by_month'] != {str(m):96 if m in OLD else 192 for m in MONTHS}
            or c['n_per_month'] != 192 or c['generation_repeats'] != [1,2]
            or c['allocation_seed'] != 20261022 or c['temperature'] != .5
            or c['max_tokens'] != 1024 or c['retry_max'] != 0
            or c['q9_postprocessing'] != 'proportional_nonnegative_v1'
            or c['minimum_available_fraction'] != .95):
        raise ValueError('Registered archived cohorts, four arms and unchanged answer format required')


def prepare(out, config):
    validate_config(config);out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored preparation folder required')
    sources = {}
    def pin(path, expected=None, load=True):
        path = Path(path).resolve()
        if not path.is_relative_to(ROOT) or expected is not None and sha(path) != expected:
            raise ValueError('Archived source changed: '+str(path))
        sources[str(path.relative_to(ROOT))] = sha(path)
        return read_json(path) if load else None
    pin(ROOT/config['analysis_plan'],load=False)
    parents = {kind:ROOT/config['source_trials'][kind] for kind in ('old','new')}
    manifests = {k:pin(p/'manifest.json') for k,p in parents.items()}
    def frozen(kind,name):
        return pin(parents[kind]/name,manifests[kind]['prepared_file_sha256'][name])
    protocols = {k:pin(p/'protocol.json',manifests[k]['protocol_sha256']) for k,p in parents.items()}
    for p in protocols.values():
        validate_v32_transport(p)
        if any(p[k] != config[k] for k in ('model','route','temperature','thinking','max_tokens','request_extra_body')):
            raise ValueError('Archived transport cannot differ from current control')
    links = frozen('old','evaluation_links_private.json')+frozen('new','evaluation_links_private.json')
    if any(set(r)-LINK_KEYS for r in links) or len(links) != 1152:
        raise ValueError('Only the frozen outcome-free cohort linkage is permitted')
    features = pd.DataFrame([{k:r['profile'].get(k) if r['profile'].get(k) is not None else 'missing'
                              for k in FEATURES} for r in links])
    pin(ARCHIVE,load=False)
    with ZipFile(ARCHIVE) as z:
        external = pd.read_stata(BytesIO(z.read('out/data/associations.dta')),convert_categoricals=False)
    train = harmonize(external[external.survey.eq('household') & external.follow_news.notna()].copy())
    probabilities = fit_probabilities(train,features,train.follow_news.astype(int).to_numpy()-1,6,FEATURES)
    prob_by_key = {(r['month'],r['agent_id']):p for r,p in zip(links,probabilities)}
    pin(FRAME,load=False)
    dates = pd.read_parquet(FRAME,columns=['date','userid','survey_date'],filters=[
        ('date','in',[month_offset(m,-1) for m in MONTHS])]).set_index(['date','userid'])['survey_date']
    # Current Q8/Q9 truth and scored model replies are not opened during input preparation.
    for kind,p in protocols.items():pin(ROOT/p['evaluation_truth'],load=False)
    pin(ROOT/config['evaluation_truth'],load=False)
    oldcatalog = pin(ROOT/config['old_news_catalog'])
    ref = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
    refmanifest = pin(ref/'manifest.json')
    inventory = pin(ROOT/'outputs/sce_v32_new2025_news_preparation_20261021_v2/summary.json')
    labelpaths = []
    for name,digest in inventory['source_sha256'].items():
        if name.endswith('labels.jsonl'):
            pin(ROOT/name,digest,load=False);labelpaths.append(ROOT/name)
    acceptance = ROOT/'outputs/sce_v32_new2025_news_acceptance_20261021_v1/labels.jsonl'
    pin(acceptance,load=False);labelpaths.append(acceptance)
    labels = source_labels(labelpaths);rules = RecallRules(pin(RULE_FILE))
    out.mkdir(parents=True);dump(out/'evaluation_links_private.json',links)
    jobs=[];coverage=[];allocation=[];maximum=0;reserve=estimate=0.
    for month in MONTHS:
        kind='old' if month in OLD else 'new';dest=out/str(month);dest.mkdir()
        population = frozen(kind,f'{month}/population.json')
        environment = frozen(kind,f'{month}/environment.json')
        simulation = frozen(kind,f'{month}/simulation.json')
        base = frozen(kind,f'{month}/prompts_deepseek_v32.json')['rows']
        ids = [p['agent_id'] for p in population['personas']]
        lookup = {r['agent_id']:r for r in links if r['month']==month}
        if len(ids) != config['n_by_month'][str(month)] or set(ids) != set(base) or set(ids) != set(lookup):
            raise ValueError('Exact frozen monthly people required')
        as_of=environment['provider_args']['targets'][0]['as_of']
        if kind=='old':
            oldsim = pin(ref/f'{month}/simulation_reference.json',refmanifest['prepared_file_sha256'][f'{month}/simulation_reference.json'])
            nb=oldsim['decision_args']['reference_validation_bundle']['parent']['parent']['base']['baseline']['news']
            common=nb['common_news'];pool=list(oldcatalog[str(month)].values())
            shares={aid:nb['rows'][aid]['spending_shares'] for aid in ids}
        else:
            raw,_,hashes=build_news_pool(ROOT,f'{month//100}-{month%100:02}',as_of,rules);sources.update(hashes)
            if any(r['new_hits'] and r['article_id'] not in labels for r in raw):
                raise ValueError('Pending news labels in an archived completed month')
            pool=[]
            for r in raw:
                row={k:r[k] for k in NEWS_KEYS-{'routing_tags','semantic_label'}}
                row.update(routing_tags=news_tags(r),semantic_label=labels.get(r['article_id']));pool.append(row)
            general=exact_deduplicate([r for r in pool if r['placement']=='a1'])
            common,_=draw_news(general,3,f'104729|{month}|common-a1')
            shares={aid:r['spending_shares'] for aid,r in frozen(kind,f'{month}/baskets_private.json').items()}
        common=sorted(common,key=lambda r:(r['pub_date'],r['article_id']))
        check_news(common,as_of,common=True)
        pool=exact_deduplicate([r for r in pool if r['placement']!='a1' and r['semantic_label'] and r['semantic_label']['decision']=='keep'])
        if len(pool)<17:raise ValueError('At least seventeen eligible personal stories required')
        catalog={r['article_id']:r for r in pool+common}
        bylevel={v:{} for v in (3,8,20)};uniform={v:{} for v in (3,8,20)};features_by_person=[];topic_gaps=[]
        for person in population['personas']:
            aid=person['agent_id'];uid=str(lookup[aid]['userid']);old=base[aid]
            if message_hash(old['messages']) != old['prompt_sha256']:raise ValueError('Archived prompt drift')
            interest=interests_for_profile(person['attributes'],shares[aid]);key=f'104729|{month}|sce_u{uid}|personal'
            ranked,_=draw_news(pool,17,key,interest,.5,2.)
            plain,_=draw_news(pool,17,key,interest,0.,2.)
            oldpersonal=sorted(ranked[:5],key=lambda r:(r['pub_date'],r['article_id']))
            day=pd.Timestamp(dates.loc[(month_offset(month,-1),int(uid))]).date().isoformat()
            for level in (3,8,20):
                chosen=sorted(ranked[:level-3],key=lambda r:(r['pub_date'],r['article_id']))
                unchosen=sorted(plain[:level-3],key=lambda r:(r['pub_date'],r['article_id']))
                for destrows,stories in ((bylevel[level],chosen),(uniform[level],unchosen)):
                    messages=change_news(old['messages'],common,oldpersonal,stories,day,as_of)
                    destrows[aid]=dict(messages=messages,prompt_sha256=message_hash(messages))
                if level==8 and bylevel[level][aid] != old:raise ValueError('Fixed-eight control not byte-identical')
            features_by_person.append([exposure_features(bylevel[v][aid]['messages'],catalog) for v in (3,8,20)])
            topic_gaps.append({v:len({r['article_id'] for r in ranked[:v-3]} ^ {r['article_id'] for r in plain[:v-3]})//2 for v in (3,8,20)})
        cube=np.asarray(features_by_person);weights=np.array([lookup[aid]['design_survey_weight'] for aid in ids])
        matched=allocate_quantity([lookup[aid]['userid'] for aid in ids],
            [prob_by_key[month,aid] for aid in ids],config['allocation_seed'])
        levels=np.array([matched[str(lookup[aid]['userid'])] for aid in ids])
        randomlevels,balance=balanced_shuffle(levels,cube,weights,config['allocation_seed']+month)
        armlevels={'fixed_8':np.full(len(ids),8),'random_quantity':randomlevels,
            'demographic_quantity':levels,'random_quantity_uniform_topics':randomlevels}
        for i,aid in enumerate(ids):
            allocation.append(dict(month=month,agent_id=aid,attention_probabilities=prob_by_key[month,aid].tolist(),
                interests=sorted(interests_for_profile(lookup[aid]['profile'],shares[aid])),
                news_counts={arm:int(lev[i]) for arm,lev in armlevels.items()}))
        for name,value in [('population.json',population),('environment.json',environment),('simulation.json',simulation)]:dump(dest/name,value)
        for arm in ARMS:
            menu=uniform if arm.endswith('uniform_topics') else bylevel
            rows={aid:menu[int(armlevels[arm][i])][aid] for i,aid in enumerate(ids)}
            dump(dest/f'prompts_{arm}.json',dict(month=month,arm=arm,rows=rows))
            sizes=[len(json.dumps(r['messages'],ensure_ascii=False).encode()) for r in rows.values()]
            maximum=max(maximum,*[len(json.dumps(r['messages'],ensure_ascii=False)) for r in rows.values()])
            bound=sum(((size+1024)*config['price_input_per_mtok']+1024*config['price_output_per_mtok'])/1e6 for size in sizes)
            rough=sum((size/4*config['price_input_per_mtok']+300*config['price_output_per_mtok'])/1e6 for size in sizes)
            for repeat in (1,2):
                cap=math.ceil(bound*1e6)/1e6;reserve+=cap;estimate+=rough
                jobs.append(dict(month=month,arm=arm,repeat=repeat,seed=41+repeat,
                    run_id=f'{out.name}-{month}-{arm}-r{repeat}',cap_usd=cap))
        changed=[topic_gaps[i][int(v)] for i,v in enumerate(randomlevels)]
        coverage.append(dict(month=month,n=len(ids),as_of=as_of,eligible_personal_news=len(pool),
            quota=dict(Counter(map(int,levels))),balance=balance,control_byte_identity_count=len(ids),
            theme_changed_persons=sum(v>0 for v in changed),theme_mean_articles_changed=float(np.mean(changed)),
            theme_effect_excludes_three_news_group=True,weight_ess=float(weights.sum()**2/(weights@weights))))
        print(f'News-only views {month}: {len(ids)} people, control unchanged',flush=True)
    protocol=dict(config,planned_calls=sum(config['n_by_month'].values())*len(ARMS)*2,max_prompt_chars=maximum+100,
        registered_at_utc=datetime.now(timezone.utc).isoformat(),primary_comparison=['random_quantity','demographic_quantity'],
        additional_comparisons=[['fixed_8','random_quantity'],['random_quantity','random_quantity_uniform_topics']],
        primary_metric='cross_section_w1_pp',research_line='A_conditional_returner_news_mechanism',
        evaluation_rule='Frozen target roster; preregistered prior fallback plus actual common-support results; MAE/RMSE/W1/delta-W1/IQR, per month/repeat.',
        old_control_reuse='Exact person/month/repeat/prompt/transport identity, including old failed attempts; never resend them.',
        allocation_rule='Same per96 quotas48/28/20; external six-class probabilities; first outcome-blind shuffle meeting1% weighted volume/2pp topic balance.',
        topic_rule='Only .5 uniform/.5 relevance versus uniform personal draw; same random uniforms, same per-person count, common A1 and chronological display.',
        limits=['Historical and 2025 months already inspected for model choice; only new news-mechanism execution, not a wholly unseen test.',
            'Older months have96 people, recent months192; paired within month and equal-month aggregate, not equal precision.',
            'News count is a design setting, not a measured reading rate; external demographic predictor has weak holdout gains.',
            'Only one quantity allocation seed; two LLM generations do not measure allocation uncertainty.',
            'Uniform-theme contrast changes actual texts and may alter lengths/topics; no claim of equal semantic information.',
            'Archived controls and future calls are not simultaneous; fixed route/model and input hashes do not prove weights unchanged.',
            'A conditional reconstruction uses real prior beliefs; no strict B or training-contamination exclusion claim.'])
    if reserve>config['budget_cap_usd']:raise ValueError('Conservative full-slot bound exceeds proposed cap')
    dump(out/'protocol.json',protocol);dump(out/'coverage.json',coverage);dump(out/'allocations_private.json',allocation)
    for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        if 'panel' not in p.parts:sources[str(p.relative_to(ROOT))]=sha(p)
    for name in ('run_sce_frozen_trial.py','evaluate_sce_call_ledger.py','prepare_sce_news_matching.py','evaluate_sce_news_matching.py'):
        p=ROOT/'scripts'/name;sources[str(p.relative_to(ROOT))]=sha(p)
    manifest=dict(status='prepared_requires_engine_checks_and_new_authorization',jobs=jobs,planned_calls=protocol['planned_calls'],
        protocol_sha256=sha(out/'protocol.json'),source_sha256=sources,
        prepared_file_sha256={str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')},
        estimated_cost_all_slots_usd=estimate,conservative_reservation_all_slots_usd=reserve,
        current_target_answers_read=False,model_replies_read=False,new_api_calls=0)
    dump(out/'manifest.json',manifest)
    dump(out/'authorization.json',dict(approved=False,protocol_sha256=manifest['protocol_sha256'],cap_usd=config['budget_cap_usd'],
        planned_calls=protocol['planned_calls'],destination=config['destination'],user_confirmation=None))
    return {k:manifest[k] for k in ('status','planned_calls','estimated_cost_all_slots_usd','conservative_reservation_all_slots_usd','new_api_calls')}
