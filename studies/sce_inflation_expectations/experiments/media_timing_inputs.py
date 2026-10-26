"""Offline A-line personal-date views, preserving the registered Q3 framework.

No target outcomes, API clients or scoring. Supplemental labels are a separate
public-news operation; an unfinished label inventory never becomes a live arm.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, time
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import pandas as pd

from .frozen_batch import ROOT, dump, read_json, sha, verify
from .fullperiod_materialization import news_pool_for_prompts
from .media_mechanism_trial import ASSEMBLY, MATERIALIZED, select_salient_common, is_sce_report
from .media_mechanism_v3 import MONTHS, draw_personal, four_tier_levels
from .media_mechanism_v3_preparation import load_supplemental_run, apply_label_overrides
from ..coverage_preparation import latest_wave, national_confidence
from ..news_selection_trial import RecallRules, RULE_FILE
from ..news_label_compat import normalize_label
from ..news_exposure import NEWS_KEYS, interests_for_profile
from ..news_exposure_demo import news_tags, exact_deduplicate, render_news_input
from ..news_mechanism_labels import PUBLIC_FIELDS
from ..news_mechanism_label_preparation import prepare_public_articles
from ..procurement_price_views import choose_categories, render_view, validate_cutoff
from ..belief_trial_preparation import confidence_block
from ..prior_belief_experiment import message_hash

NY=ZoneInfo('America/New_York')
PARENT=ROOT/'outputs/sce_media_mechanism_v3_20261025_v1'
FRAME=ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
DELIVERY=ROOT/MATERIALIZED
BASE=ROOT/ASSEMBLY
TIMING='Publication timing for the same information above:\n'
STATE='Earlier belief state (expectations, not measured inflation):'
FOOD='Household grocery context for this simulation:'
BASKET='Synthetic household spending context (not your observed receipts):'
NEWS='General news you encountered:\n'
POLICY='Public policy news brief ('
POLICY_END='This records the policy statement at that time, not a known future outcome.\n\n'


def parsed(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('Aware publication/cutoff required')
    return d


def cutoff_for_response(day, month):
    d=pd.Timestamp(day)
    if pd.isna(d) or d.strftime('%Y%m')!=str(month):
        raise ValueError('Missing or cross-month completion date is not remapped')
    previous=d.date()-timedelta(days=1)
    return datetime.combine(previous,time(23,59,59),NY).isoformat()


def status(published, previous_day, as_of):
    when,cutoff=parsed(published),parsed(as_of)
    prev=datetime.fromisoformat(previous_day).date()
    if when>cutoff or prev>cutoff.astimezone(NY).date():raise ValueError('Future input/reference')
    local=when.astimezone(NY).date()
    return 'earlier' if local<prev else 'later' if local>prev else 'same-day uncertain'


def timing_block(context, state):
    prev=state['comparison_reference_day'];cutoff=context['as_of']
    def s(d):return status(d,prev,cutoff)
    rows=[TIMING.rstrip(),
        'earlier/later/same-day uncertain compare public release dates with the reference day '
        'of the earlier belief state; they do not establish what you actually noticed.',
        '- General news, in the order listed above: '+'; '.join(s(r['pub_date']) for r in context['common_news'])+'.',
        '- Other news, in the order listed above: '+'; '.join(s(r['pub_date']) for r in context['personal_news'])+'.',
        '- Policy brief: '+s(context['policy_published_at'])+'.',
        '- Grocery figures: '+s(context['food_published_at'])+'.']
    if state['comparison_day_source']!='own_observed_survey_day':
        rows.append('The comparison day is an initialization or simulation reference, not a claimed real interview date.')
    return '\n'.join(rows)+'\n\n'


def policy_text(record):
    if len(record['facts'])!=3:raise ValueError('Three dated policy facts required')
    return ('Public policy news brief ('+record['published_at'][:10]+'):\n'+
            '\n'.join('- '+x for x in record['facts'])+'\n'+POLICY_END)


def food_text(role, aid, facts):
    text=render_view(role,choose_categories(role,aid,20261019),facts,'see timing comparison below')
    return text.replace(f"BLS release {facts['food_at_home']['published_at']}; availability relative to your previous survey: see timing comparison below.",
                        f"BLS release {facts['food_at_home']['published_at']}; see the timing comparison below.")


def replace_region(text,start,end,value):
    if text.count(start)!=1 or text.count(end)!=1:raise ValueError('Unique prompt region required')
    a,b=text.index(start),text.index(end)
    if a>=b:raise ValueError('Reversed region')
    return text[:a]+value+text[b:]


def transform(messages, old_context, new_context, state, old_food, new_food,
              old_policy, new_policy, old_confidence, new_confidence):
    if len(messages)!=1 or messages[0]['role']!='user':raise ValueError('Single user message required')
    text=messages[0]['content'];unchanged_state=text[text.index(STATE):]
    old_basket=text[text.index(BASKET):text.index(NEWS)]
    if text[text.index(FOOD):text.index(BASKET)]!=old_food:
        raise ValueError('Original food view does not reproduce')
    old_news=text[text.index(NEWS):text.index(POLICY)]
    expected_news=render_news_input(old_context['common_news'],old_context['personal_news'])
    if not old_news.startswith(expected_news) or old_news[len(expected_news):].strip():
        raise ValueError('Original Q3 news does not reproduce')
    separator=old_news[len(expected_news):]
    if text.count(policy_text(old_policy))!=1:raise ValueError('Original policy does not reproduce')
    if old_confidence and text.count(old_confidence)!=1:raise ValueError('Original confidence does not reproduce')
    # Only the public cutoff phrase, food/news/policy/confidence and timing move.
    d=parsed(new_context['as_of']);date_label=f'{d.strftime("%B")} {d.day}, {d.year}'
    text,n=re.subn(r'You only know information that was publicly available by [^.]+\.',
                  'You only know information that was publicly available by '+date_label+'.',text)
    if n!=1:raise ValueError('Unique public cutoff sentence required')
    text=replace_region(text,FOOD,BASKET,new_food)
    text=replace_region(text,NEWS,POLICY,render_news_input(new_context['common_news'],new_context['personal_news'])+separator)
    text=text.replace(policy_text(old_policy),policy_text(new_policy),1)
    if old_confidence:text=text.replace(old_confidence,new_confidence,1)
    elif new_confidence:text=text.replace(TIMING,new_confidence+TIMING,1)
    old_timing=text[text.index(TIMING):text.index(STATE)]
    trailing=old_timing[len(old_timing.rstrip('\n')):]
    text=replace_region(text,TIMING,STATE,timing_block(new_context,state).rstrip('\n')+trailing)
    if text[text.index(STATE):]!=unchanged_state or text[text.index(BASKET):text.index(NEWS)]!=old_basket:
        raise ValueError('Prior/questions/output instructions or basket changed')
    if text[:text.index('You are answering a monthly survey')]!=messages[0]['content'][:messages[0]['content'].index('You are answering a monthly survey')]:
        raise ValueError('Persona changed')
    result=deepcopy(messages);result[0]['content']=text
    return result


def load_date_map():
    df=pd.read_parquet(FRAME,columns=['userid','date','survey_date'])
    salt=read_json(DELIVERY/'201905/population_state_private.json')['anon_salt']
    ids={u:'sce_'+hashlib.sha256(f'{int(u)}|{salt}'.encode()).hexdigest()[:16] for u in df.userid.unique()}
    return {(int(r.date),ids[r.userid]):r.survey_date for r in df.itertuples(index=False)}


def prepare(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh output required')
    manifest,p=verify(PARENT)
    dates=load_date_map();sources={str(x.relative_to(ROOT)):sha(x) for x in [FRAME,PARENT/'manifest.json',PARENT/'protocol.json',RULE_FILE]}
    def pin(path):
        path=Path(path);sources[str(path.relative_to(ROOT))]=sha(path);return read_json(path)
    old_supp_dir=ROOT/'outputs/sce_news_mechanism_labels_20261025_v1'
    supp=apply_label_overrides(load_supplemental_run(old_supp_dir),pin(ROOT/'outputs/sce_news_mechanism_label_audit_20261025_v1/review.json')['overrides'])
    for f in ('state.json','labels.jsonl'):sources[str((old_supp_dir/f).relative_to(ROOT))]=sha(old_supp_dir/f)
    foods=pin(DELIVERY/'food_catalog.json')
    policies=pin(ROOT/'docs/workstreams/20261021_fullperiod/new2025_policy_sources.json')
    policies.update(pin(ROOT/'data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json'))
    waves=pin(ROOT/'docs/workstreams/20261017_reference_scaleup/confidence_sources.json')['waves']
    waves+=pin(ROOT/'data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json')['waves']
    roles={(r['month'],r['agent_id']):r['role'] for r in pin(BASE/'role_assignments_private.json')}
    rules=RecallRules(read_json(RULE_FILE));missing={};summary=[];exclusions=[];logical=0;all_rows=[]
    out.mkdir(parents=True)
    for month in MONTHS:
        old=pin(PARENT/str(month)/'prompts_Q3.json')['rows'];oldctx=pin(BASE/str(month)/'timing_context_private.json')
        states=pin(BASE/str(month)/'initial_states_private.json');env=pin(BASE/str(month)/'environment.json')
        coverage=next(r for r in pin(PARENT/'coverage.json') if r['month']==month)
        cutoff=env['provider_args']['targets'][0]['as_of'];ids=sorted(old);kept=[];cutoffs={}
        for aid in ids:
            try:cutoffs[aid]=cutoff_for_response(dates[month,aid],month)
            except ValueError:
                exclusions.append({'month':month,'agent_id':aid,'reason':'completion_date_outside_target_month_or_missing'});continue
            if datetime.fromisoformat(states[aid]['comparison_reference_day']).date()>parsed(cutoffs[aid]).date():
                exclusions.append({'month':month,'agent_id':aid,'reason':'prior_reference_after_personal_cutoff'});continue
            kept.append(aid)
        # Reuse existing topic labels from target and following-month inventory.
        # The following inventory supplies article labels, never outcomes/events.
        y,mo=divmod(month,100);next_month=(y+(mo==12))*100+(1 if mo==12 else mo+1)
        labels={}
        for label_month in (month,next_month):
            for row in pin(DELIVERY/str(label_month)/'news_label_index.json')['pool']:
                if row['label']:labels.setdefault(row['article_id'],normalize_label(row['label']))
        maxcut=max(cutoffs[a] for a in kept);raw,_,hashes=news_pool_for_prompts(ROOT,f'{y}-{mo:02}',maxcut,rules);sources.update(hashes)
        pool=[];unlabeled_topic=[];leaks=0;public_by_id={}
        for row in raw:
            if is_sce_report(row):leaks+=1;continue
            label=labels.get(row['article_id'])
            if not label:
                if row['new_hits']:unlabeled_topic.append(row['article_id'])
                continue
            if label['decision']!='keep':continue
            public_by_id[row['article_id']]={k:row.get(k) or '' for k in PUBLIC_FIELDS}
            r={k:row[k] for k in NEWS_KEYS-{'routing_tags','semantic_label'}}
            r.update(routing_tags=news_tags(row),semantic_label=dict(label,**supp.get(row['article_id'],{})))
            pool.append(r)
        if unlabeled_topic:raise ValueError('Missing base topic labels; prepare classification before selection')
        pool=exact_deduplicate(pool)
        for r in pool:
            if r['article_id'] not in supp:
                public=dict(public_by_id[r['article_id']]);public['source']='NYT Archive API'
                missing.setdefault(r['article_id'],public)
        baskets=pin(BASE/str(month)/'baskets_private.json');people=pin(BASE/str(month)/'population.json')
        qcontexts=pin(PARENT/str(month)/'contexts_private.json')['Q3'];byid={r['article_id']:r for r in pool}
        profiles={v['agent_id']:v['attributes'] for v in people['personas']};tiers=four_tier_levels(ids,month)
        oldpolicy=max((v for v in policies.values() if parsed(v['published_at'])<=parsed(cutoff)),key=lambda r:parsed(r['published_at']))
        oldwave=latest_wave(waves,cutoff);oldfacts=foods[str(month)]
        corrected={};oldalarm={};newq3={};contexts={};mismatch=0;date_rows=[]
        oldavailable=[r for r in pool if parsed(r['pub_date'])<=parsed(cutoff)]
        for aid in kept:
            oldcontext={**oldctx[aid],'common_news':coverage['common_news']}
            # Recover complete shared/news rows from actual frozen Q3 selection.
            # Common rows in coverage contain only id/title/date; render needs text.
            orig_common_ids=[r['article_id'] for r in coverage['common_news']]
            qc=qcontexts[aid]
            oldcontext.update(common_news=[byid[k] for k in orig_common_ids],personal_news=[byid[k] for k in qc['article_ids']])
            role=roles[str(month),aid];oldconf=confidence_block(national_confidence(aid,42,oldwave));oldfood=food_text(role,aid,oldfacts)
            repaired=transform(old[aid]['messages'],oldcontext,oldcontext,states[aid],oldfood,oldfood,oldpolicy,oldpolicy,oldconf,oldconf)
            pattern=r'^- General news, in the order listed above: .*\.$'
            if re.sub(pattern,'<GENERAL_TIMING>',repaired[0]['content'],flags=re.M)!=re.sub(pattern,'<GENERAL_TIMING>',old[aid]['messages'][0]['content'],flags=re.M):
                raise ValueError('Corrected control changed more than the General-news timing labels')
            mismatch+=repaired!=old[aid]['messages'];corrected[aid]={'messages':repaired,'prompt_sha256':message_hash(repaired)}
            interest=interests_for_profile(profiles[aid],baskets[aid]['spending_shares'])
            oldcommon_ids=set(orig_common_ids)
            alarm_news=draw_personal([r for r in oldavailable if r['article_id'] not in oldcommon_ids],[],tiers[aid]-3,
                f'20261025|{month}|{aid}',interest,alarming_boost=2.,cpi_boost=1.5,fox_share=0.)
            alarmctx={**oldcontext,'personal_news':alarm_news}
            alarm_msg=transform(old[aid]['messages'],oldcontext,alarmctx,states[aid],oldfood,oldfood,oldpolicy,oldpolicy,oldconf,oldconf)
            oldalarm[aid]={'messages':alarm_msg,'prompt_sha256':message_hash(alarm_msg)}
            personal_cutoff=cutoffs[aid];available=[r for r in pool if parsed(r['pub_date'])<=parsed(personal_cutoff)]
            facts=max((v for v in foods.values() if parsed(v['food_at_home']['published_at'])<=parsed(personal_cutoff)),key=lambda v:parsed(v['food_at_home']['published_at']))
            validate_cutoff(facts.values(),personal_cutoff)
            policy=max((v for v in policies.values() if parsed(v['published_at'])<=parsed(personal_cutoff)),key=lambda r:parsed(r['published_at']))
            wave=latest_wave(waves,personal_cutoff)
            for fact in facts.values():
                if fact['source_file'] not in sources and sha(ROOT/fact['source_file'])!=fact['source_sha256']:raise ValueError('Price archive changed')
                sources[fact['source_file']]=fact['source_sha256']
            for path,digest in [(policy['file'],policy['sha256']),(wave['local_file'],wave['sha256'])]:
                if path not in sources and sha(ROOT/path)!=digest:raise ValueError('Policy/confidence source changed')
                sources[path]=digest
            common=select_salient_common(available,facts['food_at_home']['published_at'][:10]);common_ids={r['article_id'] for r in common}
            personal=draw_personal([r for r in available if r['article_id'] not in common_ids],[],tiers[aid]-3,
                f'20261025|{month}|{aid}',interest,alarming_boost=1.,cpi_boost=1.5,fox_share=0.)
            ctx={'as_of':personal_cutoff,'common_news':common,'personal_news':personal,
                 'policy_published_at':policy['published_at'],'food_published_at':facts['food_at_home']['published_at']}
            msg=transform(old[aid]['messages'],oldcontext,ctx,states[aid],oldfood,food_text(role,aid,facts),oldpolicy,policy,
                          oldconf,confidence_block(national_confidence(aid,42,wave)))
            newq3[aid]={'messages':msg,'prompt_sha256':message_hash(msg)};contexts[aid]=ctx
            date_rows.append({'agent_id':aid,'information_cutoff':personal_cutoff,'news_count':tiers[aid],
                 'food_reference_period':facts['food_at_home']['reference_period'],'food_published_at':facts['food_at_home']['published_at'],
                 'policy_published_at':policy['published_at'],'confidence_wave_id':wave['wave_id']})
            all_rows.append({'month':month,'agent_id':aid,'information_cutoff':personal_cutoff})
        folder=out/str(month);folder.mkdir()
        dump(folder/'prompts_C0.json',{'arm':'C0','month':month,'rows':corrected})
        dump(folder/'prompts_C1.json',{'arm':'C1','month':month,'rows':oldalarm})
        dump(folder/'prompts_T0.json',{'arm':'T0','month':month,'rows':newq3})
        dump(folder/'contexts_T0_private.json',contexts);dump(folder/'date_views_private.json',date_rows)
        dump(folder/'full_news_pool_private.json',pool)
        logical+=len(kept)*2
        summary.append({'month':month,'n_original':len(ids),'n_timing_eligible':len(kept),'shared_cutoff':cutoff,
                        'personal_cutoff_min':min(cutoffs[a] for a in kept),'personal_cutoff_max':maxcut,
                        'general_timing_label_repairs':mismatch,'full_dated_keep_pool':len(pool),
                        'pool_missing_supplemental_labels':sum(r['article_id'] not in supp for r in pool),
                        'SCE_report_exclusions':leaks,'base_topic_label_gaps':len(unlabeled_topic)})
        print(month,summary[-1],flush=True)
    dump(out/'summary.json',{'status':'personal_date_Q3_input_draft_labels_pending','new_api_calls':0,'target_answer_columns_read':False,
        'months':summary,'new_Q3_logical_positions':logical,'repeats':2,'exclusions':exclusions,
        'arms':{'O0':'original Q3 archived reference','C0':'same cutoff/content, General timing labels corrected',
                'C1':'C0 plus alarming2','T0':'personal-date Q3','T1':'T0 plus alarming2, pending supplemental labels'},
        'pending_supplemental_articles':len(missing),'source_sha256':sources,
        'limits':['No live simulation or Core acceptance yet.','Missing tone tags are not fabricated as neutral.',
                  'T0 weights do not depend on tone; T1 cannot be assembled until labels complete.',
                  'Date-only completion metadata uses previous-day-end NY convention, not certified response-hour matching.']})
    dump(out/'source_inventory.json',{'source_sha256':sources})
    label_inputs=out/'supplemental_label_inputs'
    label_summary=prepare_public_articles([missing[k] for k in sorted(missing)],label_inputs,ROOT,
        [out/'source_inventory.json',Path(__file__)],
        'Only public NYT headline/abstract/snippet/source/section/desk and article identifiers, for extra date-eligible news in seven A-line windows; no population, survey date or SCE answers.')
    dump(out/'manifest.json',{'new_api_calls':0,'source_code_sha256':sha(__file__),
        'files_sha256':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}})
    return {'status':'prepared_offline_labels_needed','new_api_calls':0,'months':summary,
            'simulation_draft_logical_positions_per_new_arm':logical,'supplemental_label_plan':label_summary}
