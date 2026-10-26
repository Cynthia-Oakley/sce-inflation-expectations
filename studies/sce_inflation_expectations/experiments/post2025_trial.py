"""Assemble later-2025 validation with the existing food-view mechanism.

Local preparation only. Uses existing persona, news, state, price-view and
execution components; current target responses are hash-pinned, never loaded.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
import csv
import hashlib
import io
import json
import math

import pandas as pd
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig

from .frozen_batch import ROOT, dump, read_json, sha
from .model_comparison import validate_v32_transport
from .post2025_validation import MONTHS, N, SEED, FRAME
from ..coverage_preparation import latest_wave, national_confidence, build_news_pool
from ..news_selection_trial import RecallRules, RULE_FILE
from ..news_exposure_demo import draw_news, exact_deduplicate, news_tags
from ..news_exposure import NEWS_KEYS, SCHEMA as NEWS_SCHEMA, interests_for_profile
from ..confidence_experiment import SCHEMA as CONF_SCHEMA, validate_bundle, build_messages
from ..price_experience import BasketAssigner, prepare_ce_donors, profile_hash
from ..prior_belief_preparation import add_prior, month_offset
from ..belief_state_preparation import add_state_block
from ..behavior_prompt_blocks import ANCHOR_BLOCK, insert_block
from ..information_update_runtime import time_index, transform as dated_transform
from ..reference_validation_runtime import transform as direct_transform
from ..reference_validation_preparation import prior_response_day
from ..model import SCEEnvironmentProvider
from ..expanded_state_inputs import slice_environment
from ..personal_information_preparation import past_state, conditional_roles, draw_role, DONORS
from ..procurement_price_views import choose_categories, render_view, transform_prompt, validate_cutoff
from ..output_format_example import append_format_example, FORMAT_VERSION
from ..prior_belief_experiment import message_hash
from ..q9_normalization import POLICY

ARM = 'deepseek_v32'
CONFIG_DIR = ROOT/'docs/workstreams/20261021_fullperiod'


def validate_config(c):
    validate_v32_transport(c)
    if (c['mechanism'] != 'v32_new2025_validation' or c['months'] != list(MONTHS)
            or c['n_per_month'] != N or c['arms'] != [ARM]
            or c['generation_repeats'] != [1, 2] or c['temperature'] != .5
            or c['max_tokens'] != 1024 or c['retry_max'] != 0
            or c['q9_postprocessing'] != POLICY or c['allocation_seed'] != 20261019
            or c['max_workers'] != 16 or c['technical_max_workers'] != 8
            or c['queue_technical_gate'] != dict(planned_calls=16, per_month=4, minimum_usable_fraction=.99)):
        raise ValueError('Fixed later-2025 population, mechanism and execution settings required')


def source_labels(paths):
    """Permit quote/rationale metadata differences, never conflicting decisions."""
    result = {}
    for path in sorted(paths):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line); row = row.get('label', row); aid = row['article_id']
            if aid in result and any(result[aid][k] != row[k] for k in ('decision', 'topics', 'scope', 'claim_type')):
                raise ValueError('Conflicting previously assigned news classification: '+aid)
            result[aid] = row
    return result


def unique_public_signals(signals):
    """Keep a delayed latest observation once when also present in history."""
    result = {}; removed = []
    for row in signals:
        key = row['signal_id']
        if key in result:
            previous = result[key]
            if {k:v for k,v in previous.items() if k != 'role'} != {k:v for k,v in row.items() if k != 'role'}:
                raise ValueError('Conflicting repeated public signal: '+key)
            removed.append(dict(signal_id=key,removed_role=row.get('role')))
        else:
            result[key] = row
    return list(result.values()), removed


def prepare(out, config):
    validate_config(config)
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored trial folder required')
    sources = {}

    def pin(path, expected=None, load=True):
        path = Path(path).resolve()
        if not path.is_relative_to(ROOT) or expected is not None and sha(path) != expected:
            raise ValueError('Frozen source changed: '+str(path))
        sources[str(path.relative_to(ROOT))] = sha(path)
        return read_json(path) if load else None

    pop_dir = ROOT/config['source_population']
    env_dir = ROOT/config['source_environments']
    family_dir = ROOT/config['source_household_profiles']
    pm = pin(pop_dir/'manifest.json')
    if pm['months'] != list(MONTHS) or pm['n_per_month'] != N or pm['current_target_answers_read']:
        raise ValueError('Outcome-blind frozen population required')
    # Candidate's source hash predates a news-only helper edit. Verify data files
    # and underlying reference; newly pin current preparation code separately.
    for name, digest in pm['prepared_file_sha256'].items():
        pin(pop_dir/name, digest, load=False)
    pin(FRAME, pm['source_sha256'][str(FRAME.relative_to(ROOT))], load=False)
    links = pin(pop_dir/'evaluation_links_private.json')
    if len(links) != 4*N or any(set(r)-{'month','agent_id','userid','profile','stratum','survey_weight',
            'inclusion_probability','design_survey_weight'} for r in links):
        raise ValueError('Only declared selection/profile fields may be loaded')
    fm = pin(family_dir/'manifest.json')
    for name, digest in fm['source_sha256'].items():
        pin(ROOT/name, digest, load=False)
    projected = pin(family_dir/'profiles_private.json', fm['data_sha256'])
    history = defaultdict(dict)
    for row in projected:
        uid, month = int(row['userid']), int(row['date'])
        if month in history[uid] and history[uid][month] != row:
            raise ValueError('Conflicting household profile record')
        history[uid][month] = row
    role_rows = []
    for r in links:
        state = past_state(list(history[r['userid']].items()), r['month'])
        size = state.get('whole_residence_size')
        features = dict(age_group={'Under 40':'under_40','40 to 60':'40_to_60','Over 60':'over_60'}.get(r['profile'].get('age_group'),'missing'),
            household_size_group='missing' if size is None else 'one' if size == 1 else 'two' if size == 2 else 'three_plus',
            children_group=state.get('children_group','missing'))
        role_rows.append(dict(month=r['month'], agent_id=r['agent_id'], userid=r['userid'], state=state, features=features))
    donor_path = DONORS/'role_donors_2022_private.parquet'
    pin(donor_path, load=False)
    probabilities, supports = conditional_roles(pd.read_parquet(donor_path),
        pd.DataFrame([r['features'] for r in role_rows]), 'EUGROSHP2', 5)
    roles = {}
    for i, r in enumerate(role_rows):
        role = draw_role(probabilities[i], str(r['userid']), config['allocation_seed'])
        roles[r['month'], r['agent_id']] = role
        r.update(role=role, probabilities=probabilities[i].tolist(), support=supports[i])
    # Freeze the exact 44 files used to identify the supplement. A filesystem
    # glob can pick up another agent's new work or raw recovery intermediates.
    inventory=pin(ROOT/'outputs/sce_v32_new2025_news_preparation_20261021_v2/summary.json')
    label_paths=[]
    for name,digest in inventory['source_sha256'].items():
        if name.endswith('labels.jsonl'):
            p=ROOT/name;pin(p,digest,load=False);label_paths.append(p)
    canonical=ROOT/config['news_acceptance']/'labels.jsonl'
    pin(canonical,load=False);label_paths.append(canonical)
    newslabels = source_labels(label_paths)
    acceptance = pin(ROOT/config['news_acceptance']/'summary.json')
    if acceptance['status'] != 'accepted_complete' or acceptance['accepted_articles'] != 2310:
        raise ValueError('Completed declared news supplement required')
    prices = pin(ROOT/config['source_price_catalog'])
    waves = pin(ROOT/'docs/workstreams/20261017_reference_scaleup/confidence_sources.json')['waves']
    policy = pin(ROOT/config['source_policy'])
    rules = RecallRules(pin(RULE_FILE))
    receipt = pin(ROOT/'outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/experience.json')['source']
    ce = ROOT/'data/raw/ce_experience/20261006/intrvw20.zip'
    pin(ce, receipt['data_sha256'], load=False)
    with ZipFile(ce) as archive:
        data = archive.read(receipt['member'])
    if hashlib.sha256(data).hexdigest() != receipt['member_sha256']:
        raise ValueError('Original CE donor member changed')
    donors, _ = prepare_ce_donors(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    assigner = BasketAssigner(donors, receipt, seed=42, min_pool=25)
    # Read prior response dates only; do not load target answers.
    dates = pd.read_parquet(FRAME, columns=['date','userid','survey_date'],
        filters=[('date','in',[month_offset(m,-1) for m in MONTHS])]).set_index(['date','userid'])['survey_date']
    truth = ROOT/config['evaluation_truth']; pin(truth, load=False)
    for name in ('cases_private.json','summary.json'):
        pin(truth.parent/name,load=False)
    template = pin(ROOT/'outputs/sce_price_background_trial_20261021_v4/202503/simulation.json')
    out.mkdir(parents=True); jobs=[]; coverage=[]; reserve=estimate=0.; maximum=0; examples=[]
    dump(out/'evaluation_links_private.json', links)
    dump(out/'grocery_role_allocations_private.json', role_rows)
    for month in MONTHS:
        dest=out/str(month); dest.mkdir()
        population=read_json(pop_dir/str(month)/'population.json')
        pop=PopulationBundle.model_validate(population)
        past=read_json(pop_dir/str(month)/'past_private.json')
        env=slice_environment(pin(env_dir/str(month)/'environment.json'),month)
        signals, removed_signals = unique_public_signals(env['provider_args']['signals_by_step']['0'])
        env['provider_args']['signals_by_step']['0'] = signals
        target=env['provider_args']['targets'][0]; as_of=target['as_of']
        env['provider_args']['persona_by_id']={p.agent_id:p.attributes for p in pop.personas}
        if any(datetime.fromisoformat(s['published_at'])>datetime.fromisoformat(as_of)
                for s in env['provider_args']['signals_by_step']['0']):
            raise ValueError('Future environment signal')
        eb=EnvironmentBundle.model_validate(env)
        facts=prices[str(month)]; validate_cutoff(list(facts.values()),as_of)
        for fact in facts.values():
            pin(ROOT/fact['source_file'],fact['source_sha256'],load=False)
        pool, _, hashes=build_news_pool(ROOT,target['target_month'],as_of,rules); sources.update(hashes)
        if any(r['new_hits'] and r['article_id'] not in newslabels for r in pool):
            raise ValueError('Incomplete coarse-candidate news labels')
        enriched=[]
        for row in pool:
            item={k:row[k] for k in NEWS_KEYS-{'routing_tags','semantic_label'}}
            item.update(routing_tags=news_tags(row),semantic_label=newslabels.get(row['article_id'])); enriched.append(item)
        general=exact_deduplicate([r for r in enriched if r['placement']=='a1'])
        personalpool=exact_deduplicate([r for r in enriched if r['placement']!='a1' and r['semantic_label'] and r['semantic_label']['decision']=='keep'])
        common,_=draw_news(general,3,f'104729|{month}|common-a1'); common.sort(key=lambda r:(r['pub_date'],r['article_id']))
        sp=policy[str(month)]; pin(ROOT/sp['file'],sp['sha256'],load=False)
        wave=latest_wave(waves,as_of); pin(ROOT/wave['local_file'],wave['sha256'],load=False)
        newsrows={}; confidences={}; baskets={}; idmap={r['agent_id']:r for r in links if r['month']==month}
        for p in pop.personas:
            aid=p.agent_id; source_id='sce_u'+str(idmap[aid]['userid'])
            basket=assigner.assign(source_id,p.attributes); baskets[aid]=basket; shares=basket['spending_shares']
            personal,_=draw_news(personalpool,5,f'104729|{month}|{source_id}|personal',interests_for_profile(p.attributes,shares),.5,2.)
            personal.sort(key=lambda r:(r['pub_date'],r['article_id']))
            newsrows[aid]=dict(profile_sha256=profile_hash(p.attributes),spending_shares=shares,personal_news=personal)
            confidences[aid]=national_confidence(source_id,42,wave)
        base=dict(schema_version=CONF_SCHEMA,arm='national_confidence',wave_id=wave['wave_id'],labels=confidences,
            policy={k:sp[k] for k in ('published_at','source_url','source_sha256','facts')},
            news=dict(schema_version=NEWS_SCHEMA,research_line='A_historical_reconstruction',target_month=target['target_month'],
                as_of=as_of,arm='matched',mixing_weight=.5,affinity_boost=2.,common_news=common,rows=newsrows,
                source_sha256={str(p.relative_to(ROOT)):sha(p) for p in label_paths},pool_status='complete_coarse_candidate_labels'))
        validate_bundle(base,pop.personas,target['target_month'],as_of)
        provider=SCEEnvironmentProvider(eb); provider.audit_dir=None; provider.reset(42); provider.advance_to(1)
        rows={}; timing_rows=[]; month_bound=0.; role_counts=Counter()
        for ob in provider.observe_batch([p.agent_id for p in pop.personas],1):
            aid=ob.agent_id; uid=idmap[aid]['userid']; messages=build_messages(ob,base)
            messages,_=add_prior(messages,past[aid]['prior'],month)
            messages,_=add_state_block(messages,past[aid]['state'],month,False)
            messages=insert_block(messages,ANCHOR_BLOCK,require_prior=True)
            previous_day=prior_response_day(dates.loc[(month_offset(month,-1),uid)],as_of)
            timing,detail=time_index(env['provider_args']['signals_by_step']['0'],common,newsrows[aid]['personal_news'],base['policy'],previous_day,as_of)
            messages=direct_transform(dated_transform(messages,'dated_information',timing))
            status='earlier' if facts['food_at_home']['published_at'][:10]<previous_day else 'later' if facts['food_at_home']['published_at'][:10]>previous_day else 'same-day uncertain'
            role=roles[month,aid]; categories=choose_categories(role,str(uid),config['allocation_seed'])
            messages=append_format_example(transform_prompt(messages,render_view(role,categories,facts,status)))
            text=messages[0]['content']
            if any(term in text for term in ('"userid"','"weight"','"sex"','QSP5','MIDUS','Q9_mean')):
                raise ValueError('Private target/identifier field in outgoing message')
            rows[aid]=dict(messages=messages,prompt_sha256=message_hash(messages))
            timing_rows.append(dict(agent_id=aid,**detail));role_counts[role]+=1
            size=len(json.dumps(messages,ensure_ascii=False).encode());maximum=max(maximum,len(json.dumps(messages,ensure_ascii=False)))
            month_bound+=((size+1024)*config['price_input_per_mtok']+1024*config['price_output_per_mtok'])/1e6
            estimate+=(size/4*config['price_input_per_mtok']+300*config['price_output_per_mtok'])/1e6*2
        cfg=deepcopy(template);cfg['decision_args']={};SimulationConfig.model_validate(cfg)
        for name,value in [('population.json',population),('environment.json',env),('simulation.json',cfg),
                (f'prompts_{ARM}.json',dict(month=month,arm=ARM,rows=rows)),('baskets_private.json',baskets),
                ('publication_timing_private.json',timing_rows)]:
            dump(dest/name,value)
        cap=math.ceil(month_bound*1e6)/1e6
        for repeat in (1,2):
            jobs.append(dict(month=month,arm=ARM,repeat=repeat,seed=41+repeat,
                run_id=f'{out.name}-{month}-{ARM}-r{repeat}',cap_usd=cap));reserve+=cap
        coverage.append(dict(month=month,n=N,as_of=as_of,common_news=3,personal_news=5,
            confidence_wave=wave['wave_id'],policy_date=sp['published_at'],grocery_roles=dict(role_counts),
            duplicate_signal_roles_removed=removed_signals))
        examples.append(str(month)+'\n'+next(iter(rows.values()))['messages'][0]['content'])
        print(f'Prepared {month}: {N} complete food-view prompts, zero API calls',flush=True)
    if reserve>config['budget_cap_usd']:
        raise ValueError('Full no-retry reservation exceeds proposed cap')
    protocol=dict(config,planned_calls=1536,max_prompt_chars=maximum+100,
        registered_at_utc=datetime.now(timezone.utc).isoformat(),output_format_version=FORMAT_VERSION,
        primary_metric='cross_section_w1_pp',primary_comparison=[ARM],additional_comparisons=[],
        research_line='A_conditional_returner_later2025_validation',
        evaluation_rule='Same-person design-weighted Q9 center MAE/RMSE, W1, delta W1, IQR and Q8; compare copy-prior/history baselines on the identical final support. National/full-wave centers separate.',
        cutoff_rule='Latest initial CPI release day end in New York; only publicly available E, not individual interview-day reconstruction.',
        no_tuning_after_run=True,scorer='Existing frozen Q9 approximate fitter; individual density mean then weighted empirical-CDF median across people.',
        limits=['Four later-2025 months are not proof of absence of pretraining contamination; aggregates were public before model release.',
            'Model cutoff evidence incomplete; no strict-B claim. True own prior and current demographic profiles are declared A-line inputs.',
            'National food-category proxies and synthetic ATUS2022 role/CE2020Q4/Fed-confidence remain measurement approximations.',
            'National/cohort baseline results inspected before this batch, but no model responses or outcomes used for roster selection; no global blind-test claim.',
            'Repeated generations are within-person randomness, not extra independent people. No automatic default upgrade.'])
    dump(out/'protocol.json',protocol);dump(out/'coverage.json',coverage)
    (out/'prompt_preview_private.txt').write_text('\n\n'.join(examples)+'\n')
    for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        if 'panel' not in p.parts:sources[str(p.relative_to(ROOT))]=sha(p)
    for name in ('run_sce_frozen_trial.py','evaluate_sce_call_ledger.py','run_sce_automatic_pipeline.py',
                 'evaluate_sce_post2025_validation.py'):
        p=ROOT/'scripts'/name;sources[str(p.relative_to(ROOT))]=sha(p)
    manifest=dict(status='prepared_requires_dry_run_and_new_authorization',jobs=jobs,planned_calls=1536,new_api_calls=0,
        protocol_sha256=sha(out/'protocol.json'),source_sha256=sources,
        prepared_file_sha256={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()},
        current_target_answers_read=False,conservative_reservation_usd=reserve,estimated_cost_usd=estimate,
        estimate_basis='UTF8 bytes/4 input and300 output per answer; reservation bytes+1024 input and1024 output.')
    dump(out/'manifest.json',manifest)
    dump(out/'authorization.json',dict(approved=False,protocol_sha256=manifest['protocol_sha256'],cap_usd=config['budget_cap_usd'],
        planned_calls=1536,destination=config['destination'],user_confirmation=None))
    return {k:manifest[k] for k in ('status','planned_calls','estimated_cost_usd','conservative_reservation_usd')}
