"""Materialize the accepted 12-wave reference, with no current target reads.

News tagging must have completed separately under its own authorization. This
module performs only local deterministic assembly; it cannot call any API.
"""
from copy import deepcopy
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
from zipfile import ZipFile

import numpy as np
import pandas as pd
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig

from .expanded_state_inputs import (slice_environment, labels, sha, dump, ENV)
from .reference_population_preparation import MONTHS, N, SEED
from .coverage_preparation import latest_wave, national_confidence, build_news_pool
from .news_selection_trial import RecallRules, RULE_FILE
from .news_exposure_demo import draw_news, exact_deduplicate, news_tags
from .news_exposure import NEWS_KEYS, SCHEMA as NEWS_SCHEMA, interests_for_profile
from .confidence_experiment import SCHEMA as CONF_SCHEMA, validate_bundle, build_messages as baseline_messages
from .price_experience import BasketAssigner, prepare_ce_donors, profile_hash
from .prior_belief_preparation import add_prior, month_offset
from .belief_state_preparation import add_state_block
from .behavior_prompt_blocks import ANCHOR_BLOCK, insert_block
from .information_update_runtime import time_index, transform as dated_transform
from .reference_validation_runtime import REF, PROMPT, transform, build_messages
from .revision_format_runtime import REPLY_MARKER
from .prior_belief_experiment import message_hash
from .model import SCEEnvironmentProvider

ROOT = Path(__file__).resolve().parents[2]
POP = ROOT/'outputs/sce_reference_population_20261017_v1'
NEWS_PREP = ROOT/'outputs/sce_reference_news_prepared_20261017_v1'
NEWS_RUN = ROOT/'outputs/sce_reference_news_run_20261017_v1'
DOC = ROOT/'docs/workstreams/20261017_reference_scaleup'
REFERENCE = ROOT/'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'
OLD = (202206,202306,202410,202509)
NEW = tuple(m for m in MONTHS if m not in OLD)


def registered_protocol(cap):
    return {
        'id':'sce-reference-scaleup-v1', 'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'research_line':'A_conditional_returner_reconstruction', 'months':list(MONTHS),
        'old_months':list(OLD), 'new_months':list(NEW), 'n_per_month':N, 'arms':['reference'],
        'generation_repeats':[1,2], 'planned_calls':4608, 'sampling_seed':SEED,
        'dispatch_order_seed':SEED+10, 'model':'deepseek-flash',
        'official_advertised_version':'DeepSeek-V4.1-Flash',
        'model_identity_limit':'Mutable alias, no independently verified weights or training cutoff.',
        'temperature':.5,'max_tokens':1024,'thinking':'disabled','retry_max':0,
        'price_input_per_mtok':.3,'price_output_per_mtok':1.2,
        'pricing_verified_date':'2026-10-17','pricing_url':'https://api-docs.deepseek.com/quick_start/pricing/',
        'budget_cap_usd':cap, 'primary_metric':'q9_center_mae_pp',
        'primary_weight':'design_survey_weight','primary_month_scope':'new_months',
        'configuration':'Same common reference as the completed four-month validation: demographics, synthetic CE shares/Fed confidence, public price trends/news/policy, own observed prior Q8/Q9 and older state, publication timing, direct current response. No Q1, detailed quiz, frequency cue or new update rule.',
        'month_selection':'Two preselected months per year2020-2025; original4, additional8 and all12 reported separately. No month chosen from the new responses. Existing aggregate data and earlier configurations were explored; not project-level blind.',
        'sampling':'Fresh192 from complete eligible adjacent returners per month; age_group x income_band proportional stratified SRS, bounded largest remainder with minimum1 per observed stratum. No current inflation answer or expected error used. Do not force the old48 favorable sample into the new roster.',
        'eligibility':'Adjacent panel/timeline eligibility, valid strict prior Q9 fit, usable demographics and finite positive survey weight. Strict prior sum tolerance1e-6 is the existing input contract; current truth cleaning is separate, never a reason to resample.',
        'primary_estimand':'Conditional reconstruction of eligible SCE returners. Per month/repeat left-inverse weighted median of fitted individual Q9 means, compared with the same selected real people. Months equally averaged; repeats are not extra people.',
        'weights':'Main=survey_weight/(stratum_n/stratum_N). Model receives weight1 only. Equal-person sensitivity separate. Weights correct this sampling stage, not returner nonresponse or proxy measurement.',
        'full_wave':'Also fit all available current raw-bin SCE responses with positive survey weight using the same scorer; distinguish full wave, eligible returners and selected sample. Signed identity model-sample + sample-eligible + eligible-full = model-full; do not add absolute errors.',
        'secondary_metrics':['individual_density_mean_mae_pp','cross_section_w1_pp','delta_w1_pp','across_person_iqr_pp','individual_iqr_mae_pp','q8_sample_center_mae_pp','full_wave_center_mae_pp'],
        'baseline_refs':['copy_previous','history_anchor_half','full_wave_previous_center'],
        'baseline_status':'Own prior and fixed .5 historical anchor executable offline; full-wave previous center executable. AR1/same-information regression pending and not claimed implemented here.',
        'nested_samples':'Thirty prespecified fixed-seed SRS48 subset SRS96 subset192 per month. Reuse answers; sub-inclusion probability n/192 multiplies parent inclusion. These correlated subsets diagnose sample sensitivity, not30 independent model runs.',
        'intervals':'Year-block bootstrap for monthly centers, two selected months per year; average repeats first. Six year blocks give exploratory intervals. Other person/seed summaries retain their conditional nature.',
        'project_goal':'User goal center MAE<=.3pp is a project benchmark, not a published scientific threshold. Report mean, monthly fraction below.3, worst month and repeat variation. Nationwide claims require the separately reported full-wave comparison.',
        'coverage_rule':'All24 jobs completed, no missing planned prompts. Report model validation and scorer failures separately from human missingness; Q9 common support and Q8 support separately. No current-target replacement.',
        'groups':['age_group','household_income_band','numeracy','education_group','region','housing_tenure','employment_status'],
        'group_reporting':'Descriptive only; at least3 common people per month/repeat/group cell, missing categories explicit. Report cells used; do not imply causal group effects or fill suppressed cells.',
        'truth_isolation':'Preparation reads only profile fields, actual previous response date, and strictly past responses. Current Q8/Q9 stay in hash-pinned evaluation-only reference, opened after24 complete real jobs.',
        'information_boundary':'A conditions use current retrospective demographics and actual own past beliefs; each selected month is one step, not a consecutive autonomous B forecast. Public E retains frozen cutoffs; private true dates only derive earlier/later/same-day labels.',
        'scorer':'Same frozen approximate Q9 raw-bin fitter for model and real; official derived means are not substituted. Current common legal gate .5pp sum tolerance followed by frozen fitter; prior input contract remains stricter.',
        'generations':'Engine seeds42/43; same prompts in both generations. Provider alias does not guarantee a fixed model or provider-enforced seed.',
        'reused_paid_simulation_calls':0,'no_tuning_after_run':True,
        'limits':['Returner-only conditional sample; full-wave diagnostics quantify rather than remove selection.',
            'CE2020Q4 and national Fed confidence are synthetic structural proxies, not measured household traits.',
            'Current NYT archive/gas snapshots do not establish original historical bytes; not automatically strict B inputs.',
            'Selected time coverage cannot prove all-month or future accuracy.'],
    }


def completed_news():
    """Require all disjoint paid tags, not merely a successful process exit."""
    result, sources = labels()
    manifest=json.loads((NEWS_PREP/'manifest.json').read_text())
    for name,digest in manifest['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Frozen news source changed:'+name)
        sources[name]=digest
    sources[str((NEWS_PREP/'manifest.json').relative_to(ROOT))]=sha(NEWS_PREP/'manifest.json')
    expected={r['article_id'] for r in json.loads((NEWS_PREP/'pending_public_articles.json').read_text())}
    seen=set()
    for part in manifest['parts']:
        dest=NEWS_RUN/Path(part['folder']).name
        state_path,label_path=dest/'state.json',dest/'labels.jsonl'
        state=json.loads(state_path.read_text())
        if state.get('status')=='stopped_on_error' and Path(part['folder']).name=='part_11':
            # One exact duplicate label row was recovered from the saved raw
            # response. The original failure is preserved, not overwritten.
            completion=NEWS_RUN/'part_11_completion_v1'
            recovered=json.loads((completion/'state.json').read_text())
            if (recovered.get('prior_state_sha256')!=sha(state_path)
                    or recovered.get('prior_errors_recorded')!=1
                    or recovered.get('validation_adapter_sha256')!=sha(Path(__file__).with_name('reference_news_completion_adapter.py'))):
                raise ValueError('Unverified news completion chain')
            before=[json.loads(s) for s in (dest/'calls.jsonl').read_text().splitlines()]
            after=[json.loads(s) for s in (completion/'calls.jsonl').read_text().splitlines()]
            if ({r['batch_id'] for r in before}!={*range(471,508)}
                    or {r['batch_id'] for r in after}!={*range(508,518)}
                    or len(before)!=37 or len(after)!=10):
                raise ValueError('Completion must only send original unattempted batches508-517')
            for p in (state_path,dest/'calls.jsonl',completion/'calls.jsonl',completion/'recovered_prior_batches.jsonl'):
                sources[str(p.relative_to(ROOT))]=sha(p)
            dest=completion;state_path,label_path=dest/'state.json',dest/'labels.jsonl';state=recovered
        if state.get('status')!='completed' or state.get('articles_valid')!=part['articles'] or state.get('errors')!=0:
            raise ValueError('Incomplete/error news part; preserve and do not auto retry: '+str(dest))
        for p in (state_path,label_path):sources[str(p.relative_to(ROOT))]=sha(p)
        for line in label_path.read_text().splitlines():
            record=json.loads(line);row=record.get('label',record);aid=row['article_id']
            if aid not in expected or aid in seen or aid in result and result[aid]!=row:
                raise ValueError('Unknown/duplicate/conflicting new label')
            result[aid]=row;seen.add(aid)
    if seen!=expected or len(expected)!=4316:raise ValueError('New labels incomplete')
    return result,sources


def prepare(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output required')
    pmanifest=json.loads((POP/'manifest.json').read_text())
    sources=dict(pmanifest['source_sha256'])
    for name,digest in pmanifest['prepared_file_sha256'].items():
        if sha(POP/name)!=digest:raise ValueError('Frozen P/past changed: '+name)
        sources[str((POP/name).relative_to(ROOT))]=digest
    for name,digest in sources.items():
        if sha(ROOT/name)!=digest:raise ValueError('Frozen source changed:'+name)
    newslabels,newshashes=completed_news();sources.update(newshashes)
    policy=json.loads((DOC/'policy_sources.json').read_text())
    # This file is a direct month mapping, matching the archived policy schema.
    waves=json.loads((DOC/'confidence_sources.json').read_text())['waves']
    for w in waves:
        if sha(ROOT/w['local_file'])!=w['sha256']:raise ValueError('Confidence source changed')
        sources[w['local_file']]=w['sha256']
    for p in (POP/'manifest.json',DOC/'policy_sources.json',DOC/'confidence_sources.json',REFERENCE):
        sources[str(p.relative_to(ROOT))]=sha(p)
    source_env=json.loads((ROOT/ENV).read_text())
    rules=RecallRules(json.loads(RULE_FILE.read_text()))
    source_receipt=ROOT/'outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/experience.json'
    ce_source=json.loads(source_receipt.read_text())['source']
    ce=ROOT/'data/raw/ce_experience/20261006/intrvw20.zip'
    with ZipFile(ce) as archive:data=archive.read(ce_source['member'])
    if sha(ce)!=ce_source['data_sha256'] or hashlib.sha256(data).hexdigest()!=ce_source['member_sha256']:
        raise ValueError('CE source changed')
    for p in (source_receipt,ce):sources[str(p.relative_to(ROOT))]=sha(p)
    donors,_=prepare_ce_donors(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    assigner=BasketAssigner(donors,ce_source,seed=42,min_pool=25)
    date_path=ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
    dates=pd.read_parquet(date_path,columns=['date','userid','survey_date']).set_index(['date','userid'])['survey_date']
    out.mkdir(parents=True);jobs=[];coverage={};examples=[];reserve_all=estimate_all=0.
    shutil.copy2(POP/'evaluation_links_private.json',out/'evaluation_links_private.json')
    for month in MONTHS:
        dest=out/str(month);dest.mkdir()
        for name in ('population.json','past_private.json','eligible_ids_private.json','nested_subsamples_private.json','sampling_private.json'):
            shutil.copy2(POP/str(month)/name,dest/name)
        population=json.loads((dest/'population.json').read_text());pop=PopulationBundle.model_validate(population)
        past=json.loads((dest/'past_private.json').read_text())
        ids=json.loads((POP/str(month)/'profile_index_private.json').read_text());idmap={r['agent_id']:r for r in ids}
        env=slice_environment(source_env,month);target=env['provider_args']['targets'][0]
        env['provider_args']['persona_by_id']={p.agent_id:p.attributes for p in pop.personas}
        env_b=EnvironmentBundle.model_validate(env)
        pool_path=NEWS_PREP/f'pool_{month}.json'
        pool=json.loads(pool_path.read_text());sources[str(pool_path.relative_to(ROOT))]=sha(pool_path)
        rebuilt,_,raw_hashes=build_news_pool(ROOT,target['target_month'],target['as_of'],rules)
        if pool!=rebuilt:raise ValueError('News pool differs from hash-verified archive sources')
        sources.update(raw_hashes)
        if any(r['new_hits'] and r['article_id'] not in newslabels for r in pool):raise ValueError('Missing coarse-candidate tag')
        enriched=[]
        for row in pool:
            if datetime.fromisoformat(row['pub_date'].replace('Z','+00:00'))>datetime.fromisoformat(target['as_of']):
                raise ValueError('Future news')
            item={k:row[k] for k in NEWS_KEYS-{'routing_tags','semantic_label'}}
            item.update(routing_tags=news_tags(row),semantic_label=newslabels.get(row['article_id']));enriched.append(item)
        general=exact_deduplicate([r for r in enriched if r['placement']=='a1'])
        personalpool=exact_deduplicate([r for r in enriched if r['placement']!='a1' and r['semantic_label'] and r['semantic_label']['decision']=='keep'])
        common,_=draw_news(general,3,f'104729|{month}|common-a1');common.sort(key=lambda r:(r['pub_date'],r['article_id']))
        wave=latest_wave(waves,target['as_of']);sp=policy[str(month)]
        if sha(ROOT/sp['file'])!=sp['sha256'] or datetime.fromisoformat(sp['published_at'])>datetime.fromisoformat(target['as_of']):
            raise ValueError('Policy source/cutoff changed')
        sources[sp['file']]=sp['sha256']
        rows={};confidences={};baskets={}
        for p in pop.personas:
            aid=p.agent_id;source_id=idmap[aid]['source_id']
            basket=assigner.assign(source_id,p.attributes);baskets[aid]=basket;shares=basket['spending_shares']
            personal,_=draw_news(personalpool,5,f'104729|{month}|{source_id}|personal',interests_for_profile(p.attributes,shares),.5,2.)
            personal.sort(key=lambda r:(r['pub_date'],r['article_id']))
            rows[aid]={'profile_sha256':profile_hash(p.attributes),'spending_shares':shares,'personal_news':personal}
            confidences[aid]=national_confidence(source_id,42,wave)
        base={'schema_version':CONF_SCHEMA,'arm':'national_confidence',
            'news':{'schema_version':NEWS_SCHEMA,'research_line':'A_historical_reconstruction',
                'target_month':target['target_month'],'as_of':target['as_of'],'arm':'matched','mixing_weight':.5,
                'affinity_boost':2.,'common_news':common,'rows':rows,'source_sha256':newshashes,
                'pool_status':'complete_coarse_candidate_labels'},'labels':confidences,
            'policy':{k:sp[k] for k in ('published_at','source_url','source_sha256','facts')},'wave_id':wave['wave_id']}
        validate_bundle(base,pop.personas,target['target_month'],target['as_of'])
        provider=SCEEnvironmentProvider(env_b);provider.audit_dir=None;provider.reset(42);provider.advance_to(1)
        obs=provider.observe_batch([p.agent_id for p in pop.personas],1)
        expanded={'arm':'self_update','month':month,'baseline':base,'rows':{}}
        anchor={'arm':'belief_start','base':expanded,'messages_sha256':{}}
        info={'arm':'dated_information','parent':anchor,'time_index_by_id':{},'messages_sha256':{}}
        bundle={'parent':info,'messages_sha256':{}}
        previews=[];timings=[];reserve=estimate=0.
        for ob in obs:
            aid=ob.agent_id;messages=baseline_messages(ob,base)
            messages,_=add_prior(messages,past[aid]['prior'],month)
            messages,_=add_state_block(messages,past[aid]['state'],month,False)
            expanded['rows'][aid]={**past[aid],'messages_sha256':message_hash(messages)}
            anchored=insert_block(messages,ANCHOR_BLOCK,require_prior=True);anchor['messages_sha256'][aid]=message_hash(anchored)
            previous_day=pd.Timestamp(dates.loc[(month_offset(month,-1),idmap[aid]['userid'])])
            if pd.isna(previous_day) or previous_day.year*100+previous_day.month!=month_offset(month,-1):raise ValueError('Missing adjacent prior response date')
            timing,detail=time_index(env['provider_args']['signals_by_step']['0'],common,rows[aid]['personal_news'],base['policy'],previous_day.date().isoformat(),target['as_of'])
            info['time_index_by_id'][aid]=timing;dated=dated_transform(anchored,'dated_information',timing)
            info['messages_sha256'][aid]=message_hash(dated);final=transform(dated)
            digest=message_hash(final);bundle['messages_sha256'][aid]=digest
            text=final[0]['content']
            if len(text)>40000 or text.count(REPLY_MARKER)!=1 or any(term in text for term in ('"userid"','"weight"','"sex"','QSP5','MIDUS','Q9_mean')):
                raise ValueError('Prompt whitelist/size/boundary failure')
            previews.append({'agent_id':aid,'messages':final,'prompt_sha256':digest});timings.append({'agent_id':aid,**detail})
            size=len(json.dumps(final,ensure_ascii=False).encode())
            reserve+=(size+256)*.3/1e6+1024*1.2/1e6
            estimate+=(size/4*.3+300*1.2)/1e6
        for ob in obs:build_messages(ob,bundle)
        cfg=SimulationConfig(study_id='sce_inflation_expectations',n_steps=1,seed=42,warm_start=None,
            decision_ref=REF,decision_args={'reference_validation_bundle':bundle,'prompt_version':PROMPT,
                'llm_kind':'scripted','seed':42,'retry_max':0,'max_prompt_chars':40000},
            collector_ref='sce_inflation_expectations.collector',collector_args={},interaction_rounds=1,
            engine_args={'memory_window':2},store_ref='duckdb',store_args={})
        dump(dest/'environment.json',env);dump(dest/'simulation_reference.json',cfg.model_dump(mode='json'))
        dump(dest/'preview_reference.json',previews);dump(dest/'publication_timing_audit_private.json',timings)
        dump(dest/'baskets_private.json',baskets)
        for repeat in (1,2):
            jobs.append({'month':month,'arm':'reference','repeat':repeat,'cap_usd':math.ceil((reserve+1e-6)*1e4)/1e4,
                'run_id':f'{out.name}-{month}-reference-r{repeat}'})
            reserve_all+=reserve;estimate_all+=estimate
        coverage[str(month)]={'n':N,'as_of':target['as_of'],'full_eligible_n':len(json.loads((dest/'eligible_ids_private.json').read_text())),
            'common_news_n':len(common),'personal_pool_n':len(personalpool),'confidence_wave':wave['wave_id'],
            'stored_e_signals':len(env['provider_args']['signals_by_step']['0']),'new_api_calls':0}
        examples.append(f'{month} / reference\n'+previews[0]['messages'][0]['content'])
        print('Prepared reference',month,N,'no API',flush=True)
    cap=math.ceil(sum(j['cap_usd'] for j in jobs)*2)/2
    dump(out/'protocol.json',registered_protocol(cap));dump(out/'coverage.json',coverage)
    (out/'prompt_preview.txt').write_text('\n\n'.join(examples)+'\n')
    for name in ('scripts/run_sce_reference_validation_trial.py','scripts/run_sce_household_finance_trial.py','scripts/export_study_runtime.py'):
        sources[name]=sha(ROOT/name)
    for path in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        relative=path.relative_to(ROOT/'studies/sce_inflation_expectations')
        if '__pycache__' not in relative.parts and 'evaluation' not in relative.parts:sources[str(path.relative_to(ROOT))]=sha(path)
    # Fix the analysis before seeing the new trajectories as well as the B
    # provider; evaluation does not get silently revised after a disappointing run.
    for name in ('scripts/analyze_sce_reference_validation.py',
                 'studies/sce_inflation_expectations/evaluation/reference_validation.py',
                 'studies/sce_inflation_expectations/evaluation/cognition.py',
                 'studies/sce_inflation_expectations/evaluation/finance_validation.py',
                 'studies/sce_inflation_expectations/evaluation/behavior_comparison.py',
                 'studies/sce_inflation_expectations/evaluation/metrics.py'):
        sources[name]=sha(ROOT/name)
    jobs=[jobs[i] for i in np.random.default_rng(SEED+10).permutation(len(jobs))]
    manifest={'status':'prepared_requires_authorization_record_and_dry_run','source_sha256':sources,
        'prepared_file_sha256':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()},
        'jobs':jobs,'planned_calls':4608,'protocol_sha256':sha(out/'protocol.json'),
        'sum_job_caps_usd':sum(j['cap_usd'] for j in jobs),'conservative_reservation_usd':reserve_all,
        'estimated_peak_cost_usd':estimate_all,'proposed_cap_usd':cap,'new_api_calls':0,
        'estimate_assumption':'UTF8 bytes/4 input and300 output; reservation bytes+256 and1024 output, peak uncached pricing.'}
    dump(out/'manifest.json',manifest);return manifest
