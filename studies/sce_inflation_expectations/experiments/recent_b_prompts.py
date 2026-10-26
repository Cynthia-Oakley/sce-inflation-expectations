"""Prepare recent-B messages with existing P/E formatters; never send an API.

Only the source-qualified old snapshot supplies P/family information. Published
dates are checked; unverified historical text versions remain explicit limits.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,date
import calendar,csv,hashlib,json,re
from io import StringIO
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from socioverse.schemas import PopulationBundle,EnvironmentBundle

from .frozen_batch import ROOT,read_json,dump,sha
from .recent_b_preflight import identity
from .fullperiod_materialization import news_pool_for_prompts
from .post2025_trial import unique_public_signals
from .state_continuity_core import check as check_core
from .state_continuity_dry_run import dry_run
from .news_matching import change_news
from .. import personal_information_preparation as family
from ..model import SCEEnvironmentProvider
from ..news_selection_trial import RecallRules,RULE_FILE
from ..news_label_compat import normalize_label
from ..news_exposure import NEWS_KEYS,SCHEMA as NEWS_SCHEMA,interests_for_profile,check_news
from ..news_exposure_demo import draw_news,exact_deduplicate,news_tags
from ..confidence_experiment import SCHEMA as CONF_SCHEMA,build_messages
from ..coverage_preparation import latest_wave,national_confidence
from ..price_experience import BasketAssigner,prepare_ce_donors,profile_hash
from ..news_quantity import random_quantities
from ..prior_belief_preparation import add_prior,MARKER
from ..behavior_prompt_blocks import insert_block,ANCHOR_BLOCK
from ..information_update_runtime import time_index,transform as dated_transform
from ..reference_validation_runtime import transform as direct_transform
from ..procurement_price_views import choose_categories,render_view,transform_prompt,validate_cutoff
from ..output_format_example import append_format_example
from ..prior_belief_experiment import message_hash
from ..state_continuity_runtime import STATE_TOKEN,TIMING_TOKEN,render_messages

LINE='B_retrospective_asof_public_P_synthetic_priors_text_vintage_unverified'
LEAK=re.compile(r'\bsurvey of consumer expectations\b|\bconsumer expectations survey\b|\bSCE\b|new york fed(?:eral)? (?:bank|reserve)',re.I)


def prepare(pop_source,prior_source,out):
    pop_source,prior_source,out=map(lambda p:Path(p).resolve(),(pop_source,prior_source,out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored B assembly required')
    ps=read_json(pop_source/'summary.json');pr=read_json(prior_source/'summary.json')
    if pr.get('finite_assignment_statuses')!={'finite_assignment_band_met':11}:raise ValueError('Complete B prior constraints required')
    selected=read_json(pop_source/'selected_proxy_population_private.json');plans=read_json(pop_source/'monthly_input_plan.json')
    sources={}
    def pin(path):
        path=Path(path).resolve();sources[str(path.relative_to(ROOT))]=sha(path);return read_json(path)
    for s in (ps,pr):
        for path,digest in s['source_sha256'].items():
            if sha(ROOT/path)!=digest:raise ValueError('B preparation source changed: '+path)
            sources[path]=digest
    line=(LINE if not ps.get('availability_basis') else
          'B_retrospective_assumed_micro_release_lag_synthetic_priors_text_vintage_unverified')
    # Recover source IDs locally only; source-wave filtering occurs before P selection.
    frame=pd.read_parquet(pop_source/'public_snapshot_frame_private.parquet',columns=['userid'])
    reverse={identity(u):int(u) for u in frame.userid.unique()}
    ids={reverse[r['persona']['agent_id']] for people in selected.values() for r in people}
    histories=defaultdict(list);prepared_families=None
    if ps.get('family_states_file'):
        prepared_families=pin(ROOT/ps['family_states_file'])
    else:
        snapshot=next(ROOT/p for p in ps['source_sha256'] if p.endswith('micro_snapshot_20250702.xlsx'))
        print('Projecting household structure only from the qualified public snapshot.',flush=True)
        for r in family.read_profile_rows(snapshot,ids):
            histories[int(float(r['userid']))].append((int(float(r['date'])),r))
    role_rows=[];features=[]
    for month,people in selected.items():
        for r in people:
            p=r['persona']
            f=(prepared_families[month][p['agent_id']] if prepared_families is not None else
               family.past_state(histories[reverse[p['agent_id']]],202409))
            size=f.get('whole_residence_size')
            v={'age_group':{'Under 40':'under_40','40 to 60':'40_to_60','Over 60':'over_60'}.get(p['attributes'].get('age_group'),'missing'),
               'household_size_group':'missing' if size is None else 'one' if size==1 else 'two' if size==2 else 'three_plus',
               'children_group':f.get('children_group','missing')}
            role_rows.append({'month':month,'agent_id':p['agent_id'],'family':f,'features':v});features.append(v)
    role_path=family.DONORS/'role_donors_2022_private.parquet';sources[str(role_path.relative_to(ROOT))]=sha(role_path)
    probabilities,supports=family.conditional_roles(pd.read_parquet(role_path),pd.DataFrame(features),'EUGROSHP2',5)
    roles={}
    for i,r in enumerate(role_rows):
        r.update(role=family.draw_role(probabilities[i],r['agent_id'],20261019),matching_support=supports[i])
        roles[r['month'],r['agent_id']]=r['role']
    receipt=pin(ROOT/'outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/experience.json')['source']
    archive=ROOT/'data/raw/ce_experience/20261006/intrvw20.zip';sources[str(archive.relative_to(ROOT))]=sha(archive)
    if sha(archive)!=receipt['data_sha256']:raise ValueError('CE archive changed')
    with ZipFile(archive) as z:payload=z.read(receipt['member'])
    if hashlib.sha256(payload).hexdigest()!=receipt['member_sha256']:raise ValueError('CE member changed')
    donors,_=prepare_ce_donors(csv.DictReader(StringIO(payload.decode('utf-8-sig'))));assigner=BasketAssigner(donors,receipt,seed=42,min_pool=25)
    waves=pin(ROOT/'docs/workstreams/20261017_reference_scaleup/confidence_sources.json')['waves']
    waves+=pin(ROOT/'data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json')['waves']
    policies=pin(ROOT/'data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json')
    food=pin(ROOT/'outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json')
    rules=RecallRules(pin(RULE_FILE))
    # Use the same complete label union as the full-period materializer.
    from .fullperiod_materialization import helpers
    S,_=helpers();labels={k:normalize_label(v) for k,v in S.load_labels().items()}
    for glob in S.LABEL_GLOBS:
        for file in sorted(ROOT.glob(glob)):sources[str(file.relative_to(ROOT))]=sha(file)
    out.mkdir(parents=True);prompts=out/'prompts';prompts.mkdir();prep=out/'inputs';prep.mkdir()
    nodes=[];all_inputs={};coverage=[];sizes=[]
    pop_meta=pin(ROOT/'outputs/sce_fullperiod_materialized_20261022_v2/202408/population.json')
    for plan in plans:
        month=plan['month'];cutoff=plan['as_of'];target=f'{month[:4]}-{month[4:]}'
        env=pin(ROOT/plan['environment_source']);env['provider_args']['signals_by_step']['0'],_=unique_public_signals(env['provider_args']['signals_by_step']['0'])
        if env['provider_args']['targets'][0]['as_of']!=cutoff:raise ValueError('Wrong B cutoff')
        # No external archive broadcasting or old population P enters the prompt.
        env['provider_args']['events_by_step']={'0':[]};env['information_program']['broadcasts']=[]
        people=[deepcopy(r['persona']) for r in selected[month]]
        for p in people:
            for key in ('source_reference_period','public_known_by_utc','synthetic_proxy','availability_basis'):p.pop(key,None)
            p['init_state']={'target_month':'','q9_valid':False,'synthetic':True};p['weight']=1.
        population={k:deepcopy(v) for k,v in pop_meta.items() if k not in {'personas','provider_args','materialized_count'}}
        source_wave=int(plan['old_population_reference_period'])
        population.update(personas=people,materialized_count=len(people),provider_args={'source':'proxy_source_wave','source_reference_period':str(source_wave),
            'target_month':target,'as_of':cutoff,'public_known_by_utc':ps['source_public_known_by_utc'],
            'micro_availability_basis':ps.get('availability_basis','archived_public_snapshot'),'evidence_class':line,'strict_B_eligible':False})
        pop=PopulationBundle.model_validate(population)
        env['provider_args']['persona_by_id']={p.agent_id:p.attributes for p in pop.personas}
        provider=SCEEnvironmentProvider(EnvironmentBundle.model_validate(env));provider.audit_dir=None;provider.reset(42);provider.advance_to(1)
        raw,_,hashes=news_pool_for_prompts(ROOT,target,cutoff,rules);sources.update(hashes)
        pool=[];leaks=0
        for r in raw:
            if LEAK.search(' '.join(str(r.get(k,'')) for k in ('headline','abstract','snippet'))):leaks+=1;continue
            if r['new_hits'] and r['article_id'] not in labels:raise ValueError('Unlabeled recent news: '+month)
            v={k:r[k] for k in NEWS_KEYS-{'routing_tags','semantic_label'}}
            v.update(routing_tags=news_tags(r),semantic_label=labels.get(r['article_id']));pool.append(v)
        general=exact_deduplicate([r for r in pool if r['placement']=='a1'])
        personal_pool=exact_deduplicate([r for r in pool if r['placement']!='a1' and r['semantic_label'] and r['semantic_label']['decision']=='keep'])
        if len(general)<3 or len(personal_pool)<17:raise ValueError('Insufficient dated news: '+month)
        common,_=draw_news(general,3,f'104729|{month}|common-a1');common.sort(key=lambda r:(r['pub_date'],r['article_id']));check_news(common,cutoff,common=True)
        # The quantity frame is the complete latest-source wave, not only selected Core IDs.
        full=pd.read_parquet(pop_source/'public_snapshot_frame_private.parquet',columns=['date','userid']);fullids=[identity(u) for u in full.loc[full.date.eq(source_wave),'userid']]
        levels=random_quantities(fullids,20261022)
        sp=max((v for v in policies.values() if datetime.fromisoformat(v['published_at'])<=datetime.fromisoformat(cutoff)),key=lambda v:v['published_at'])
        if sha(ROOT/sp['file'])!=sp['sha256']:raise ValueError('Policy bytes changed')
        sources[sp['file']]=sp['sha256'];wave=latest_wave(waves,cutoff);sources[wave['local_file']]=sha(ROOT/wave['local_file'])
        validate_cutoff(list(food[month].values()),cutoff)
        for fact in food[month].values():
            if sha(ROOT/fact['source_file'])!=fact['source_sha256']:raise ValueError('Food archive changed')
            sources[fact['source_file']]=fact['source_sha256']
        prior=pin(prior_source/f'{month}_initial_states_private.json')
        rows={};baskets={};confidence={};selected_news={}
        for p in pop.personas:
            aid=p.agent_id;basket=assigner.assign(aid,p.attributes);baskets[aid]=basket
            personal,_=draw_news(personal_pool,17,f'104729|{month}|{aid}|personal',interests_for_profile(p.attributes,basket['spending_shares']),.5,2.)
            selected_news[aid]=sorted(personal[:levels[aid]-3],key=lambda r:(r['pub_date'],r['article_id']))
            rows[aid]={'profile_sha256':profile_hash(p.attributes),'spending_shares':basket['spending_shares'],'personal_news':sorted(personal[:5],key=lambda r:(r['pub_date'],r['article_id']))}
            check_news(rows[aid]['personal_news'],cutoff);check_news(selected_news[aid],cutoff)
            confidence[aid]=national_confidence(aid,42,wave)
        bundle={'schema_version':CONF_SCHEMA,'arm':'national_confidence','wave_id':wave['wave_id'],'labels':confidence,
                'policy':{k:sp[k] for k in ('published_at','source_url','source_sha256','facts')},
                'news':{'schema_version':NEWS_SCHEMA,'research_line':line,'target_month':target,'as_of':cutoff,'arm':'matched','mixing_weight':.5,'affinity_boost':2.,
                        'common_news':common,'rows':rows,'source_sha256':{},'pool_status':'complete_coarse_candidate_labels'}}
        folder=prompts/month;folder.mkdir();templates={};states={};contexts={};previews={}
        for ob in provider.observe_batch([p.agent_id for p in pop.personas],1):
            aid=ob.agent_id;r=prior[aid];ref=int(r['synthetic_reference_period'].replace('-',''));yr,mo=divmod(ref,100)
            day=date(yr,mo,calendar.monthrange(yr,mo)[1]).isoformat()
            state={'fields':{'q8':{'value':r['q8_point_pct'],'source_period':ref,'source_kind':'synthetic_donor'},
                             'q9':{'value':r['q9_bins'],'source_period':ref,'source_kind':'synthetic_donor'}},
                   'history_centers':[],'comparison_reference_day':day,'comparison_day_source':'synthetic_prior_reference_month_end',
                   'transition':'initialization_not_a_new_model_answer'}
            messages=build_messages(ob,bundle)
            bridge={'source_month':ref,'point_pct':r['q8_point_pct'],'q9':{f'bin{i}':v for i,v in enumerate(r['q9_bins'],1)}}
            messages,_=add_prior(messages,bridge,int(month));messages=insert_block(messages,ANCHOR_BLOCK,require_prior=True)
            timing,_=time_index(env['provider_args']['signals_by_step']['0'],common,rows[aid]['personal_news'],bundle['policy'],day,cutoff)
            messages=direct_transform(dated_transform(messages,'dated_information',timing))
            role=roles[month,aid];view=render_view(role,choose_categories(role,aid,20261019),food[month],'see the synthetic reference comparison below')
            view=view.replace('availability relative to your previous survey:','availability relative to the synthetic reference:')
            messages=append_format_example(transform_prompt(messages,view))
            messages=change_news(messages,common,rows[aid]['personal_news'],selected_news[aid],day,cutoff)
            text=messages[0]['content'];start=text.index('Publication timing for the same information above:\n');end=text.index(MARKER)
            source_label=f'{source_wave//100}-{source_wave%100:02}'
            source_description=(f'a {source_label} population frame treated as available under the declared nine-month microdata release-lag assumption; its exact historical file version is unverified' if ps.get('availability_basis') else f'a publicly available {source_label} population frame')
            provenance=(f'Simulation population and prior provenance: this is a synthetic proxy household, based on {source_description}. '
                f'The assigned earlier belief is a synthetic state referenced to {r["synthetic_reference_period"]}; its observed donor answer was recorded in {r["observed_donor_reference_period"]}. '
                'It is not your actual previous-month interview. Timing labels compare with the synthetic reference month end; they do not establish personal exposure dates. No personal response history is claimed.\n\n')
            template=[{'role':'user','content':text[:start]+provenance+TIMING_TOKEN+'\n\n'+STATE_TOKEN+'\n\n'+text[end:]}]
            context={'as_of':cutoff,'common_news':common,'personal_news':selected_news[aid],'policy_published_at':sp['published_at'],'food_published_at':food[month]['food_at_home']['published_at']}
            preview=render_messages(template,state,month,context)
            if any(t in preview[0]['content'] for t in (aid,'"userid"','Q9_mean','"weight"','your own earlier survey answer')):raise ValueError('B identity/history leak')
            templates[aid]=template;states[aid]=state;contexts[aid]=context;previews[aid]={'messages':preview,'prompt_sha256':message_hash(preview)}
            all_inputs[month,aid]=(template,state,context);sizes.append(len(json.dumps(preview,ensure_ascii=False).encode()))
            nodes.append({'month':month,'agent_id':aid,'repeat':1,'arm':'recent_b','dependency':None,'source_kind':'synthetic_public_prior',
                          'logical_reuse_key':f'{month}|{aid}|1|recent_b'})
        for name,value in [('population.json',population),('environment.json',env),('templates_private.json',templates),('initial_states_private.json',states),
                           ('timing_context_private.json',contexts),('initial_previews_private.json',previews),('baskets_private.json',baskets)]:dump(folder/name,value)
        coverage.append({'month':month,'n':len(states),'as_of':cutoff,'population_source_wave':str(source_wave),
                         'micro_availability_basis':ps.get('availability_basis','archived_public_snapshot'),
                         'news_quantity':dict(Counter(levels[a] for a in states)),
                         'common_pool':len(general),'personal_pool':len(personal_pool),'sce_news_excluded':leaks,'policy_published_at':sp['published_at'],
                         'confidence_wave':wave['wave_id'],'text_vintage_verified':False})
        print(f'{month}: {len(states)} B prompts, policy {sp["published_at"][:10]}, news pool {len(personal_pool)}',flush=True)
    dump(prep/'state_dependencies_private.json',nodes)
    dump(prompts/'role_assignments_private.json',role_rows)
    replay=dry_run(nodes,all_inputs);dump(prompts/'dry_run_summary.json',{k:v for k,v in replay.items() if k!='preview_rows_private'})
    dump(prompts/'preview_sample.json',next(iter(replay['preview_rows_private'].values())))
    summary={'coverage':coverage,'runtime_character_cap':replay['max_rendered_characters']+512,'runtime_utf8_byte_cap':replay['max_rendered_utf8_bytes']+1024,
             'source_sha256':sources,'planned_unique_requests':len(nodes),'logical_positions':len(nodes),'research_line':line,'strict_B_eligible':False,
             'population_preflight':str(pop_source.relative_to(ROOT)),'prior_source':str(prior_source.relative_to(ROOT)),
             'micro_availability_basis':ps.get('availability_basis','archived_public_snapshot'),
             'estimated_cost_usd':(sum(sizes)/4*.259+len(nodes)*180*.8)/1e6,'new_api_calls':0,'old_family_structure_available':sum(r['family']['available'] for r in role_rows),
             'input_timing_rule':'Synthetic month-end reference, not individual observed interview dates','sources_certified_as_original_text':False}
    dump(prompts/'summary.json',summary)
    core=check_core(prep,prompts,out/'core_engineering')
    dump(out/'summary.json',dict(status='recent_B_offline_assembled_not_authorized',**summary,official_core=core))
    return summary
