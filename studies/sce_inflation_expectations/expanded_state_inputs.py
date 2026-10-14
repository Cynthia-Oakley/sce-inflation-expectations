"""Frozen eight-month returner inputs. Current outcomes never select people or enter B."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from .monthly_population import PROFILE_COLUMNS, build_monthly_population
from .age_reporting_audit import SOURCES
from .coverage_preparation import build_news_pool, latest_wave, national_confidence
from .news_selection_trial import RecallRules, RULE_FILE
from .news_exposure_demo import draw_news, exact_deduplicate, news_tags
from .news_exposure import NEWS_KEYS, SCHEMA as NEWS_SCHEMA, interests_for_profile
from .confidence_experiment import SCHEMA as CONF_SCHEMA, validate_bundle, build_messages as baseline_messages
from .price_experience import BasketAssigner, prepare_ce_donors, profile_hash
from .prior_belief_preparation import eligible_previous, month_offset, prior_record, add_prior
from .belief_state_preparation import compute_person_state, add_state_block
from .prior_belief_experiment import message_hash
from .model import SCEEnvironmentProvider
from .expanded_state_runtime import REF, PROMPT

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = 'docs/workstreams/20261013_behavior/codex_expanded_protocol_20261014.json'
PRIOR = 'outputs/sce_prior_preparation_20261013_v4'
ENV = 'outputs/sce_e_extension_2020_2025_verified_20261007/environment_candidate.json'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def slice_environment(bundle, month):
    out = deepcopy(bundle)
    args = out['provider_args']
    label = f'{month//100:04d}-{month%100:02d}'
    index, = [i for i,t in enumerate(args['targets']) if t['target_month'] == label]
    args['targets'] = [args['targets'][index]]
    args['signals_by_step'] = {'0': args['signals_by_step'][str(index)]}
    args['events_by_step'] = {}
    for key in ('persona_by_id','audit_dir','run_id'):
        args.pop(key, None)
    out['information_program']['broadcasts'] = []
    out['scheduled_events'] = []
    cutoff = datetime.fromisoformat(args['targets'][0]['as_of'])
    if any(datetime.fromisoformat(s['published_at']) > cutoff for s in args['signals_by_step']['0']):
        raise ValueError('Future E signal')
    EnvironmentBundle.model_validate(out)
    return out

def reference():
    path = ROOT / PRIOR / 'labeled_reference_private.parquet'
    receipt = json.loads((ROOT / PRIOR / 'summary.json').read_text())
    if sha(path) != receipt['output_file_sha256'][path.name]:
        raise ValueError('Reference hash mismatch')
    return pd.read_parquet(path)

def profiles():
    frames, hashes = [], {}
    columns = PROFILE_COLUMNS + ['weight','survey_date']
    for name,start,end in SOURCES:
        path = ROOT / name
        digest = sha(path)
        cachekey = hashlib.sha256((digest + json.dumps(columns)).encode()).hexdigest()[:20]
        cache = ROOT / 'data/cache' / f'monthly_profiles_{cachekey}.parquet'
        if not cache.exists():
            raise ValueError('Verified monthly profile cache missing: ' + str(cache))
        data = pd.read_parquet(cache)
        frames.append(data[data.date.between(start,end)])
        hashes[name] = digest
        hashes[str(cache.relative_to(ROOT))] = sha(cache)
    frame = pd.concat(frames,ignore_index=True)
    if frame.duplicated(['date','userid']).any():
        raise ValueError('Duplicate profiles')
    return frame, hashes

def labels():
    analysis = json.loads((ROOT / 'outputs/sce_multiperiod_news_label_analysis_20261011_v1/summary.json').read_text())
    paths = {ROOT/p for p in analysis['source_sha256'] if p.endswith('labels.jsonl')}
    paths.update((ROOT/'outputs/sce_expanded_news_run_20261014_v1').glob('part_*/labels.jsonl'))
    result, hashes = {}, {}
    for path in sorted(paths):
        if str(path.relative_to(ROOT)) in analysis['source_sha256'] and sha(path) != analysis['source_sha256'][str(path.relative_to(ROOT))]:
            raise ValueError('Old labels changed')
        hashes[str(path.relative_to(ROOT))] = sha(path)
        for line in path.read_text().splitlines():
            record = json.loads(line)
            row = record.get('label',record)
            aid = row['article_id']
            if aid in result and result[aid] != row:
                raise ValueError('Conflicting article label')
            result[aid] = row
    return result, hashes

def confidence_waves():
    original = ROOT / 'docs/literature/sce/belief_proxies/gallup_waves_20261011.json'
    waves = json.loads(original.read_text())['waves']
    # A retrospective P proxy: 2019 row observed in the official 2024 historical
    # topline; original 2019 publication availability is unverified, never B PIT.
    historical = ROOT/'data/raw/belief_proxies/20261010/gallup_fed_confidence_20240506.pdf'
    waves += [dict(wave_id='gallup_2024_april',field_dates=['2024-04-01','2024-04-22'],
                   published_date='2024-05-06',national_source_percent=[8,31,23,22,16],
                   local_file=str(historical.relative_to(ROOT)),sha256=sha(historical))]
    latest = ROOT/'data/raw/expanded_policy_20261014/gallup_2025.pdf'
    if latest.exists():
        waves.append(dict(wave_id='gallup_2025_april',field_dates=['2025-04-01','2025-04-14'],
                          published_date='2025-04-17',national_source_percent=[11,26,28,22,14],
                          local_file=str(latest.relative_to(ROOT)),sha256=sha(latest)))
    for w in waves:
        if sha(ROOT/w['local_file']) != w['sha256']:
            raise ValueError('Confidence source drift')
    return waves

def prepare(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    protocol = json.loads((ROOT/PROTOCOL).read_text())
    frame = reference()
    # Physically omit current question outcomes from population selection.
    eligibility = frame[['date','userid','panel_status','tenure_valid','timeline_consistent',
                         'raw_prior_valid','survey_date']].copy()
    prof, hashes = profiles()
    news_labels, label_hashes = labels()
    hashes.update(label_hashes)
    hashes[PROTOCOL] = sha(ROOT/PROTOCOL)
    hashes[ENV] = sha(ROOT/ENV)
    for name in ('scripts/run_sce_expanded_trial.py','docs/workstreams/20261013_behavior/codex_expanded_policy_sources_20261014.json'):
        hashes[name] = sha(ROOT/name)
    hashes[f'{PRIOR}/labeled_reference_private.parquet'] = sha(ROOT/PRIOR/'labeled_reference_private.parquet')
    source_env = json.loads((ROOT/ENV).read_text())
    policy = json.loads((ROOT/'docs/workstreams/20261013_behavior/codex_expanded_policy_sources_20261014.json').read_text())
    waves = confidence_waves()
    rules = RecallRules(json.loads(RULE_FILE.read_text()))
    basket_path = ROOT/'outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/experience.json'
    ce_source = json.loads(basket_path.read_text())['source']
    ce = ROOT/'data/raw/ce_experience/20261006/intrvw20.zip'
    with ZipFile(ce) as archive: data = archive.read(ce_source['member'])
    if sha(ce) != ce_source['data_sha256'] or hashlib.sha256(data).hexdigest() != ce_source['member_sha256']:
        raise ValueError('CE source drift')
    donors,_ = prepare_ce_donors(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    assigner = BasketAssigner(donors,ce_source,seed=42,min_pool=25)
    out.mkdir(parents=True)
    links, jobs, metadata = [], [], []
    for month in protocol['development_months']+protocol['evaluation_months']:
        dest = out/str(month);dest.mkdir()
        env = slice_environment(source_env,month)
        target = env['provider_args']['targets'][0]
        current = eligibility[eligibility.date.eq(month)]
        previous = eligibility[eligibility.date.eq(month_offset(month,-1))].set_index('userid',drop=False)
        cutoff = datetime.fromisoformat(target['as_of']).date()
        candidates = [int(r['userid']) for r in current.to_dict('records')
                      if int(r['userid']) in previous.index and
                      eligible_previous(r,previous.loc[int(r['userid'])],month,cutoff)]
        # A valid prior score is needed to construct the registered state. No
        # current answer validity, weight, center, or error is inspected here.
        from .evaluation.behavior_comparison import score
        prior_lookup = frame[frame.date.eq(month_offset(month,-1))].set_index('userid')
        candidates = sorted(uid for uid in candidates if score(tuple(float(prior_lookup.loc[uid,f'Q9_bin{i}']) for i in range(1,11)))['status']=='ok')
        eligible_profiles = prof[prof.userid.isin(candidates)]
        population, meta = build_monthly_population(eligible_profiles,month,n=96,seed=42)
        selected_ids = [int(p['agent_id'][5:]) for p in population['personas']]
        states = {uid:compute_person_state(frame[frame.userid.eq(uid)],uid,month) for uid in selected_ids}
        if any(s is None for s in states.values()):
            raise ValueError('Selected prior state unscorable; retain selection, do not resample')
        lookup = frame[frame.date.eq(month_offset(month,-1))].set_index('userid')
        public_pool, newsstats, newshashes = build_news_pool(ROOT,target['target_month'],target['as_of'],rules)
        missing = [r['article_id'] for r in public_pool if r['new_hits'] and r['article_id'] not in news_labels]
        if missing:
            raise ValueError(f'{month}: {len(missing)} unlabelled coarse candidates; cannot simulate')
        hashes.update(newshashes)
        enriched = []
        for r in public_pool:
            item = {k:r[k] for k in NEWS_KEYS-{'routing_tags','semantic_label'}}
            item.update(routing_tags=news_tags(r),semantic_label=news_labels.get(r['article_id']))
            enriched.append(item)
        common_pool = exact_deduplicate([r for r in enriched if r['placement']=='a1'])
        personal_pool = exact_deduplicate([r for r in enriched if r['placement']!='a1' and r['semantic_label'] and r['semantic_label']['decision']=='keep'])
        common,_ = draw_news(common_pool,3,f'104729|{month}|common-a1')
        common.sort(key=lambda r:(r['pub_date'],r['article_id']))
        if month == 202004:
            historical = ROOT/'data/raw/belief_proxies/20261010/gallup_fed_confidence_20240506.pdf'
            wave = dict(wave_id='gallup_2019_retrospective_proxy',field_dates=['2019-04-01','2019-04-09'],
                        national_source_percent=[9,41,18,14,19],local_file=str(historical.relative_to(ROOT)),
                        sha256=sha(historical),availability_status='A retrospective P; original publication date unknown, not B PIT')
        else:
            wave = latest_wave(waves,target['as_of'])
        hashes[wave['local_file']] = wave['sha256']
        source_policy = policy[str(month)]
        if sha(ROOT/source_policy['file']) != source_policy['sha256']:
            raise ValueError('Policy source drift')
        hashes[source_policy['file']] = source_policy['sha256']
        rows, confidences, past, baskets = {},{},{},{}
        for i,p in enumerate(population['personas'],1):
            source_id = p['agent_id'];uid=int(source_id[5:]);aid=f'exp_{month}_{i:03d}'
            basket = assigner.assign(source_id,p['attributes']);baskets[aid]=basket
            shares = basket['spending_shares']
            interests = interests_for_profile(p['attributes'],shares)
            personal,_ = draw_news(personal_pool,5,f'104729|{month}|{source_id}|personal',interests,.5,2.)
            personal.sort(key=lambda r:(r['pub_date'],r['article_id']))
            p.update(agent_id=aid,weight=1.,group_key=None,init_state={})
            rows[aid] = dict(profile_sha256=profile_hash(p['attributes']),spending_shares=shares,personal_news=personal)
            confidences[aid] = national_confidence(source_id,42,wave)
            past[aid] = dict(prior=prior_record(lookup.loc[uid]),state=states[uid])
            links.append(dict(month=month,agent_id=aid,userid=uid,profile=p['attributes'],
                              survey_weight=float(prof.loc[prof.date.eq(month)&prof.userid.eq(uid),'weight'].iloc[0])))
        pop = PopulationBundle.model_validate(population)
        env['provider_args']['persona_by_id'] = {p.agent_id:p.attributes for p in pop.personas}
        env_b = EnvironmentBundle.model_validate(env)
        baseline = dict(schema_version=CONF_SCHEMA,arm='national_confidence',
                        news=dict(schema_version=NEWS_SCHEMA,research_line='A_historical_reconstruction',
                                  target_month=target['target_month'],as_of=target['as_of'],arm='matched',
                                  mixing_weight=.5,affinity_boost=2.,common_news=common,rows=rows,
                                  source_sha256=newshashes,pool_status='complete_coarse_candidate_labels'),
                        labels=confidences,policy={k:source_policy[k] for k in ('published_at','source_url','source_sha256','facts')},wave_id=wave['wave_id'])
        validate_bundle(baseline,pop.personas,target['target_month'],target['as_of'])
        provider = SCEEnvironmentProvider(env_b);provider.audit_dir=None;provider.reset(42);provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas],1)
        dump(dest/'population.json',population);dump(dest/'environment.json',env)
        dump(dest/'baskets_private.json',baskets)
        for arm in ('self_update','new_signal'):
            bundle = dict(arm=arm,month=month,baseline=baseline,rows={})
            previews=[]
            for ob in observations:
                messages=baseline_messages(ob,baseline)
                if arm=='self_update':
                    messages,_=add_prior(messages,past[ob.agent_id]['prior'],month)
                    messages,_=add_state_block(messages,past[ob.agent_id]['state'],month,False)
                text=json.dumps(messages,ensure_ascii=False)
                if len(text)>18000 or any(term in text for term in ('"userid"','"weight"','Q9_mean')):
                    raise ValueError('Message whitelist/length failure')
                row=dict(messages_sha256=message_hash(messages))
                if arm=='self_update':row.update(past[ob.agent_id])
                bundle['rows'][ob.agent_id]=row
                previews.append(dict(agent_id=ob.agent_id,messages=messages,prompt_sha256=row['messages_sha256']))
            dump(dest/f'preview_{arm}.json',previews)
            cfg=dict(study_id='sce_inflation_expectations',n_steps=1,seed=42,warm_start=None,
                     decision_ref=REF,decision_args=dict(expanded_bundle=bundle,prompt_version=PROMPT,
                     seed=42,llm_kind='scripted',max_prompt_chars=18000),collector_ref='sce_inflation_expectations.collector',
                     collector_args={},interaction_rounds=1,engine_args={'memory_window':2},store_ref='duckdb',store_args={})
            SimulationConfig.model_validate(cfg);dump(dest/f'simulation_{arm}.json',cfg)
            reserve=sum((len(json.dumps(p['messages'],ensure_ascii=False).encode())+256)*.3/1e6+1024*1.2/1e6 for p in previews)
            for repeat in (1,2):
                jobs.append(dict(month=month,arm=arm,repeat=repeat,
                                 phase='development' if month in protocol['development_months'] else 'evaluation',
                                 run_id=f'{out.name}-{month}-{arm}-r{repeat}',reservation_usd=reserve,
                                 cap_usd=float(np.ceil(reserve*10000)/10000)))
        metadata.append(dict(month=month,as_of=target['as_of'],eligible_n=len(candidates),selected_n=96,
                             population_counts=meta['attribute_counts'],news=newsstats,
                             personal_pool_n=len(personal_pool),common_pool_n=len(common_pool),wave_id=wave['wave_id'],
                             confidence_age_days=(cutoff-datetime.fromisoformat(wave['field_dates'][1]).date()).days,
                             ce_proxy='2020Q4 retrospective structural proxy; for 2020-04 not PIT P',
                             unknown_confidence_availability=wave.get('availability_status')))
        dump(dest/'past_private.json',past)
        print('Prepared',month,96,'returners',flush=True)
    if sum(j['cap_usd'] for j in jobs)>12:
        raise ValueError('Frozen byte reservation exceeds approved $12 cap; do not call')
    dump(out/'evaluation_links_private.json',links)
    hashes.update({str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py') if '__pycache__' not in p.parts})
    dump(out/'protocol.json',protocol)
    prepared = {str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')}
    manifest=dict(status='prepared_no_calls',protocol_ref=PROTOCOL,source_sha256=hashes,
                  prepared_file_sha256=prepared,jobs=jobs,months=metadata,planned_calls=3072,
                  total_job_caps_usd=sum(j['cap_usd'] for j in jobs),simulation_budget_cap_usd=12.,
                  prepared_at=datetime.now(timezone.utc).isoformat())
    dump(out/'manifest.json',manifest)
    return manifest
