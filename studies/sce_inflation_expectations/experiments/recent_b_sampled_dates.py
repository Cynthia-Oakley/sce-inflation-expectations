"""Past-year sampled B dates and versioned per-person public information.

Date planning and assembly are offline. Archive repairs are explicit overlays;
canonical archives, old B rosters, weights and priors are never overwritten.
"""
import argparse
import calendar
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import date,datetime,timedelta,time
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from .full_a_core_normal import ROOT,read,write,sha,fresh,checked
from .recent_b_news_refresh import _load_labels,_topic_label,_news_pools,_latest_cpi_release_day,SEED
from .fullperiod_materialization import news_pool_for_prompts
from .full_a_personal_inputs import _food_snapshot,_policy_snapshot
from .media_timing_inputs import FOOD,BASKET,STATE,TIMING,transform,food_text,policy_text,parsed,timing_block
from .media_mechanism_v3 import four_tier_levels,draw_personal
from ..state_continuity_runtime import render_messages,render_state,TIMING_TOKEN,STATE_TOKEN
from ..prior_belief_experiment import message_hash
from ..news_exposure import interests_for_profile
from ..coverage_preparation import latest_wave,national_confidence,previous_month
from ..belief_trial_preparation import confidence_block
from ..news_selection_trial import RecallRules,RULE_FILE
from ..news_label_compat import normalize_label
from ..evaluation.response_date_distribution import rebin,shifted,days
from ..submission_tools.reproduce import no_network

BASE=ROOT/'outputs/sce_recent_b_news_refresh_20261025_v3'
DATE_SOURCE=ROOT/'outputs/sce_response_date_distribution_20261026_v2'
NY=ZoneInfo('America/New_York')
DATE_SEED=20261026


def safe_file(name,expected=None):
    path=(ROOT/name).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():raise ValueError('Project-local existing file required')
    if expected and sha(path)!=expected:raise ValueError('Pinned file changed: '+name)
    return path


def load_repair(path,sources):
    if path is None:return {},{}
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT):raise ValueError('Project-local repair manifest required')
    config=read(path)
    if config.get('schema')!='sce_B_news_repair_overlay/v1':raise ValueError('Registered project repair manifest required')
    sources[str(path.relative_to(ROOT))]=sha(path);overrides={};labels={}
    for month,row in config.get('archive_overrides',{}).items():
        if len(month)!=7 or month[4]!='-':raise ValueError('Archive override usesYYYY-MM')
        actual=safe_file(row['path'],row['sha256']);overrides[month]=actual
        sources[str(actual.relative_to(ROOT))]=row['sha256']
        if row.get('meta_path'):
            meta=safe_file(row['meta_path'],row.get('meta_sha256'));sources[str(meta.relative_to(ROOT))]=sha(meta)
    for row in config.get('base_label_overlays',[]):
        actual=safe_file(row['path'],row['sha256']);sources[str(actual.relative_to(ROOT))]=row['sha256']
        for line in actual.read_text().splitlines():
            if not line.strip():continue
            value=json.loads(line);label=_topic_label(value.get('label',value));aid=label['article_id']
            if aid in labels and labels[aid]!=label:raise ValueError('Conflicting repair labels')
            labels[aid]=label
    return overrides,labels


def archive_path(month,overrides):
    return overrides.get(month,ROOT/'data/raw/nyt_archive'/f'{month}.json')


def archive_screen(month,required_last_day,overrides,sources):
    path=archive_path(month,overrides);payload=read(path)
    docs=payload.get('response',{}).get('docs')
    if not isinstance(docs,list):raise ValueError('NYT archive response.docs list required')
    observed=sorted({int(r['pub_date'][8:10]) for r in docs if r.get('pub_date','')[:7]==month})
    missing=[d for d in range(1,required_last_day+1) if d not in observed]
    sources[str(path.relative_to(ROOT))]=sha(path)
    return dict(month=month,path=str(path.relative_to(ROOT)),sha256=sha(path),n_docs=len(docs),
        required_last_day=required_last_day,observed_day_count=len(observed),last_observed_day=max(observed) if observed else None,
        unobserved_required_days=missing,screen_passed=not missing,
        meaning='Daily coverage screen, not proof of complete article universe or historical text vintage')


def source_probability(distributions,month,source_wave,lag_months):
    if lag_months not in (12,24):raise ValueError('Calendar-year lag must be12 or24')
    source=str(shifted(month,-lag_months))
    if int(source)>int(source_wave) or source not in distributions:raise ValueError('Date source not available under declared B source-wave rule')
    p=rebin(distributions[source],days(month))
    return source,p


def assign_date(month,aid,p,global_cutoff,seed=DATE_SEED):
    if len(p)!=days(month) or not np.isclose(sum(p),1):raise ValueError('Target-month probability vector required')
    uniform=int.from_bytes(hashlib.sha256(f'{seed}|B-completion-date|{month}|{aid}'.encode()).digest()[:8],'big')/2**64
    day=min(int(np.searchsorted(np.cumsum(p),uniform,side='right'))+1,len(p))
    completion=date(int(month)//100,int(month)%100,day)
    candidate=datetime.combine(completion-timedelta(days=1),time(23,59,59),NY)
    global_dt=parsed(global_cutoff);cutoff=min(candidate,global_dt)
    return dict(synthetic_completion_day=completion.isoformat(),uncapped_information_cutoff=candidate.isoformat(),
        information_cutoff=cutoff.isoformat(),forecast_as_of=global_cutoff,capped_by_global_as_of=candidate>global_dt)


def prepare_dates(out,lag_months=12):
    out=fresh(out);manifest=read(BASE/'manifest.json')
    checked(BASE,manifest['files_sha256']);checked(ROOT,manifest['source_sha256'])
    checked(DATE_SOURCE,read(DATE_SOURCE/'manifest.json')['files_sha256'])
    summary=read(BASE/'summary.json');pre=ROOT/summary['population_preflight'];plans=read(pre/'monthly_input_plan.json')
    distributions=read(DATE_SOURCE/'summary.json')['monthly_probabilities']['counts']
    sources={str(p.relative_to(ROOT)):sha(p) for p in (BASE/'manifest.json',BASE/'summary.json',DATE_SOURCE/'manifest.json',DATE_SOURCE/'summary.json',pre/'monthly_input_plan.json',Path(__file__))}
    mapping={};coverage=[];required=defaultdict(int)
    for plan in plans:
        month=plan['month'];states=read(BASE/'prompts'/month/'initial_states_private.json');ids=sorted(states)
        src,p=source_probability(distributions,int(month),plan['old_population_reference_period'],lag_months)
        rows={aid:dict(date_source_reference=src,source_lag_months=lag_months,
            **assign_date(month,aid,p,plan['as_of'])) for aid in ids}
        if len(rows)!=512:raise ValueError('Exact existing512-person B roster required')
        for aid,row in rows.items():
            if states[aid]['comparison_reference_day']>row['information_cutoff'][:10]:raise ValueError('Synthetic prior reference is after personal cutoff')
        mapping[month]=rows;cutoffs=Counter(r['information_cutoff'] for r in rows.values())
        end=max(cutoffs,key=parsed);target=month[:4]+'-'+month[4:]
        prev=previous_month(target);required[prev]=max(required[prev],calendar.monthrange(int(prev[:4]),int(prev[5:]))[1])
        if end[:7]==target:required[target]=max(required[target],int(end[8:10]))
        coverage.append(dict(month=month,n=512,forecast_as_of=plan['as_of'],date_source_reference=src,
           probability_by_day=p.tolist(),synthetic_completion_day_counts=dict(Counter(r['synthetic_completion_day'] for r in rows.values())),
           information_cutoff_counts=dict(cutoffs),capped_persons=sum(r['capped_by_global_as_of'] for r in rows.values())))
    for name in ('evaluation/response_date_distribution.py','experiments/recent_b_rolling_preflight.py'):
        path=ROOT/'studies/sce_inflation_expectations'/name;sources[str(path.relative_to(ROOT))]=sha(path)
    screens=[archive_screen(m,n,{},sources) for m,n in sorted(required.items())]
    write(out/'date_assignments_private.json',mapping);write(out/'required_news_archives.json',screens)
    write(out/'summary.json',dict(status='date_assignments_ready_environment_assembly_pending',positions=sum(len(v) for v in mapping.values()),
       source_lag_months=lag_months,date_seed=DATE_SEED,probability_weighting='unweighted historical completion frequency; P weights unchanged',
       global_as_of_changed=False,cutoff_rule='min(synthetic completion date minus one day at NY end-of-day,registered global as_of)',
       coverage=coverage,news_archive_blockers=[r for r in screens if not r['screen_passed']],
       prior_and_population_policy='Analyst P/prior remain based on global D; per-agent visible E uses its personal cutoff; prior synthetic reference must precede cutoff',
       new_api_calls=0,paid_authorization_written=False,live_ready=False))
    write(out/'manifest.json',dict(source_sha256=sources,files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('Prepared5632 sampled date assignments;lag',lag_months,';unresolved archive months',[r['month'] for r in screens if not r['screen_passed']])


def template_from_rendered(messages,state,month,context):
    text=messages[0]['content'];state_text=render_state(state,month)
    rendered=render_B_messages([dict(role='user',content=TIMING_TOKEN+STATE_TOKEN)],state,month,context)[0]['content']
    timing=rendered[:-len(state_text)]
    start=text.index(TIMING);end=text.index(STATE)
    gap=text[start:end]
    if not gap.startswith(timing) or gap[len(timing):].strip() or not text[end:].startswith(state_text):
        raise ValueError('B state/timing blocks do not match canonical renderer')
    template=[dict(role='user',content=text[:start]+TIMING_TOKEN+gap[len(timing):]+STATE_TOKEN+text[end+len(state_text):])]
    if render_B_messages(template,state,month,context)!=messages:raise ValueError('Re-rendered B date prompt differs')
    return template


def render_B_messages(template,state,month,context):
    """Allow a synthetic month-end reference to equal the conservative cutoff.

    A first-day synthetic interview has a previous-day cutoff on month end.
    Keep numeric prior and reference unchanged; same-day releases remain
    uncertain. Do not relax the old renderer for actual observed interviews.
    """
    reference=date.fromisoformat(state['comparison_reference_day'])
    cutoff=parsed(context['as_of']).astimezone(NY).date()
    if reference>cutoff:raise ValueError('Prior reference is later than personal cutoff')
    if reference<cutoff:return render_messages(template,state,month,context)
    if state['comparison_day_source']!='synthetic_prior_reference_month_end' or any(
        v['source_kind']!='synthetic_donor' for v in state['fields'].values()):
        raise ValueError('Equal-date exception only for declared synthetic month-end priors')
    if len(template)!=1 or template[0]['content'].count(TIMING_TOKEN)!=1 or template[0]['content'].count(STATE_TOKEN)!=1:
        raise ValueError('Unique B rendering tokens required')
    result=deepcopy(template)
    result[0]['content']=template[0]['content'].replace(TIMING_TOKEN,timing_block(context,state),1).replace(STATE_TOKEN,render_state(state,month),1)
    return result


def check_frozen_core(prompts,out):
    """Existing official Core worker consumes frozen messages, no date redraw."""
    from .frozen_batch import worker
    prompts,out=Path(prompts),Path(out);out.mkdir()
    summary=read(prompts/'summary.json');receipts=[];total=0
    sample_config=ROOT/'outputs/sce_v32_new2025_trial_20261022_v4/202506/simulation.json'
    files=[Path(__file__),Path(__file__).with_name('frozen_batch.py'),
       ROOT/'studies/sce_inflation_expectations/frozen_prompt_runtime.py',
       ROOT/'studies/sce_inflation_expectations/model.py',sample_config]
    source_hashes={str(p.relative_to(ROOT)):sha(p) for p in files}
    for cov in summary['coverage']:
        month=cov['month'];rows=read(prompts/month/'initial_previews_private.json')
        cell=out/f'{month}-recent_b-r1';dest=cell/month;dest.mkdir(parents=True)
        for name in ('population','environment'):(dest/f'{name}.json').write_bytes((prompts/month/f'{name}.json').read_bytes())
        write(dest/'simulation.json',read(sample_config));write(dest/'prompts_recent_b.json',dict(month=int(month),arm='recent_b',rows=rows))
        protocol=dict(execution_mode='engineering_only',destination=None,model='NOT_CONFIGURED_ENGINEERING_ONLY',
             mechanism='B_sampled_date_frozen_prompt_check',months=[int(month)],arms=['recent_b'],generation_repeats=[1],
             n_per_month=len(rows),engineering_decision_count=len(rows),planned_calls=0,budget_cap_usd=0,
             temperature=.5,max_tokens=1024,retry_max=0,thinking='disabled',
             max_prompt_chars=summary['runtime_character_cap'],price_input_per_mtok=0,price_output_per_mtok=0)
        write(cell/'protocol.json',protocol)
        job=dict(month=int(month),arm='recent_b',repeat=1,seed=42,run_id=f'{out.parent.name}-{month}-date-core',cap_usd=0)
        write(cell/'manifest.json',dict(planned_calls=0,jobs=[job],protocol_sha256=sha(cell/'protocol.json'),
            source_sha256=source_hashes,prepared_file_sha256={str(p.relative_to(cell)):sha(p) for p in cell.rglob('*.json')}))
        worker(cell,0,True);receipts.append(job['run_id']);total+=len(rows)
    result=dict(status='completed_official_core_frozen_message_checks',official_engine_units=len(receipts),
         decisions=total,new_api_calls=0,run_ids=receipts,
         limits='Scripted frozen-message Core check,not actual model or paid-run acceptance')
    write(out/'summary.json',result);return result


def archive_view(out,required_months,overrides):
    folder=out/'archive_view';dest=folder/'data/raw/nyt_archive';dest.mkdir(parents=True)
    mapping={}
    for month in sorted(required_months):
        source=archive_path(month,overrides);target=dest/f'{month}.json'
        target.symlink_to(os.path.relpath(source,target.parent));mapping[month]=str(source.relative_to(ROOT))
    write(out/'archive_aliases.json',mapping)
    return folder,mapping


def merge_labels(base,extra):
    result=dict(base)
    for aid,label in extra.items():
        if aid in result and result[aid]!=label:raise ValueError('Overlay cannot silently relabel an already classified article')
        result[aid]=label
    return result


def assemble(date_plan,out,repair_manifest=None,months=None):
    date_plan=Path(date_plan).resolve();out=fresh(out)
    dm=read(date_plan/'manifest.json');checked(date_plan,dm['files_sha256']);checked(ROOT,dm['source_sha256'])
    oldmanifest=read(BASE/'manifest.json');checked(BASE,oldmanifest['files_sha256']);checked(ROOT,oldmanifest['source_sha256'])
    ds=read(date_plan/'summary.json');assignments=read(date_plan/'date_assignments_private.json')
    selected=sorted(assignments) if months is None else sorted(months)
    if not selected or not set(selected)<=set(assignments):raise ValueError('Unknown B engineering month')
    sources={str(p.relative_to(ROOT)):sha(p) for p in (date_plan/'manifest.json',date_plan/'date_assignments_private.json',BASE/'manifest.json',BASE/'summary.json',Path(__file__))}
    overrides,extra_labels=load_repair(repair_manifest,sources)
    required=defaultdict(int)
    for month in selected:
        target=month[:4]+'-'+month[4:];prev=previous_month(target)
        required[prev]=calendar.monthrange(int(prev[:4]),int(prev[5:]))[1]
        end=max((r['information_cutoff'] for r in assignments[month].values()),key=parsed)
        if end[:7]==target:required[target]=max(required[target],int(end[8:10]))
    screens=[archive_screen(m,n,overrides,sources) for m,n in sorted(required.items())]
    write(out/'archive_screen.json',screens)
    blockers=[r for r in screens if not r['screen_passed']]
    if blockers:
        write(out/'summary.json',dict(status='blocked_news_archive_coverage_before_prompt_assembly',months=selected,
             blockers=blockers,new_api_calls=0,live_ready=False,old_inputs_changed=False))
        write(out/'manifest.json',dict(source_sha256=sources,files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
        print('BLOCKED:repair archive coverage first:',[r['month'] for r in blockers]);return
    oldsummary=read(BASE/'summary.json');labels=merge_labels(_load_labels(oldsummary,sources),extra_labels)
    global_plans={r['month']:r for r in oldsummary['coverage']}
    rules=RecallRules(read(RULE_FILE));sources[str(RULE_FILE.relative_to(ROOT))]=sha(RULE_FILE)
    view,aliases=archive_view(out,required,overrides)
    food_path=ROOT/'outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json'
    policy_path=ROOT/'data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json'
    conf_paths=[ROOT/'docs/workstreams/20261017_reference_scaleup/confidence_sources.json',ROOT/'data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json']
    foods=read(food_path);policies=read(policy_path);waves=sum([read(p)['waves'] for p in conf_paths],[])
    for path in [food_path,policy_path,*conf_paths]:sources[str(path.relative_to(ROOT))]=sha(path)
    roles={(r['month'],r['agent_id']):r['role'] for r in read(BASE/'prompts/role_assignments_private.json')}
    prompts=out/'prompts';prompts.mkdir();prep=out/'inputs';prep.mkdir();nodes=[];coverage=[];sizes=[]
    for month in selected:
        base=BASE/'prompts'/month
        prior=read(base/'initial_states_private.json');oldcontexts=read(base/'timing_context_private.json')
        previews=read(base/'initial_previews_private.json');baskets=read(base/'baskets_private.json');env=read(base/'environment.json')
        population=read(base/'population.json');people={p['agent_id']:p['attributes'] for p in population['personas']}
        ids=sorted(prior);tiers=four_tier_levels(ids,int(month),SEED);target=month[:4]+'-'+month[4:]
        maxcut=max((r['information_cutoff'] for r in assignments[month].values()),key=parsed)
        raw,_,hashes=news_pool_for_prompts(view,target,maxcut,rules)
        for name,digest in hashes.items():
            m=Path(name).stem;actual=safe_file(aliases[m],digest);sources[str(actual.relative_to(ROOT))]=digest
        cache={}
        for cutoff in sorted({r['information_cutoff'] for r in assignments[month].values()},key=parsed):
            eligible=[r for r in raw if parsed(r['pub_date'])<=parsed(cutoff)]
            release=_latest_cpi_release_day(env,cutoff);common,pool,audit=_news_pools(eligible,labels,cutoff,release)
            food_key,facts=_food_snapshot(foods,cutoff);policy=_policy_snapshot(policies,cutoff);wave=latest_wave(waves,cutoff)
            for fact in facts.values():sources[fact['source_file']]=sha(safe_file(fact['source_file'],fact['source_sha256']))
            sources[policy['file']]=sha(safe_file(policy['file'],policy['sha256']))
            sources[wave['local_file']]=sha(safe_file(wave['local_file']))
            cache[cutoff]=dict(common=common,pool=pool,audit=audit,food_key=food_key,facts=facts,policy=policy,wave=wave)
        contexts={};templates={};newpreviews={}
        for aid in ids:
            row=assignments[month][aid];cutoff=row['information_cutoff'];c=cache[cutoff];state=prior[aid];old=oldcontexts[aid]
            personal=draw_personal(c['pool'],[],tiers[aid]-3,f'{SEED}|{month}|{aid}',
                 interests_for_profile(people[aid],baskets[aid]['spending_shares']),alarming_boost=1.,cpi_boost=1.5,fox_share=0.)
            context={**old,**row,'as_of':cutoff,'common_news':c['common'],'personal_news':personal,
               'food_published_at':c['facts']['food_at_home']['published_at'],'policy_published_at':c['policy']['published_at'],
               'food_catalog_period':c['food_key'],'confidence_wave_id':c['wave']['wave_id'],
               'cutoff_rule':'min(synthetic completion date minus one day at NY end-of-day,global forecast as_of)'}
            oldtext=previews[aid]['messages'][0]['content'];oldfood=oldtext[oldtext.index(FOOD):oldtext.index(BASKET)]
            oldpolicy=_policy_snapshot(policies,old['as_of']);oldwave=latest_wave(waves,old['as_of'])
            newmessages=transform(previews[aid]['messages'],old,context,state,oldfood,
                food_text(roles[month,aid],aid,c['facts']),oldpolicy,c['policy'],
                confidence_block(national_confidence(aid,42,oldwave)),confidence_block(national_confidence(aid,42,c['wave'])))
            annotation=('Synthetic questionnaire completion date: '+row['synthetic_completion_day']+'. '
                'This is a constructed date, not an observed interview. It does not permit use of information after the public cutoff stated above.\n\n')
            text=newmessages[0]['content'];pos=text.index(FOOD);newmessages[0]['content']=text[:pos]+annotation+text[pos:]
            if aid in newmessages[0]['content']:raise ValueError('Proxy ID leaked into prompt')
            templates[aid]=template_from_rendered(newmessages,state,month,context)
            contexts[aid]=context;newpreviews[aid]=dict(messages=newmessages,prompt_sha256=message_hash(newmessages))
            sizes.append(len(json.dumps(newmessages,ensure_ascii=False)))
            nodes.append(dict(month=month,agent_id=aid,repeat=1,arm='recent_b',dependency=None,
                 source_kind='synthetic_public_prior',logical_reuse_key=f'{month}|{aid}|1|recent_b'))
        dest=prompts/month;dest.mkdir()
        for name in ('population','environment','initial_states_private','baskets_private'):(dest/f'{name}.json').write_bytes((base/f'{name}.json').read_bytes())
        for name,value in [('templates_private',templates),('timing_context_private',contexts),('initial_previews_private',newpreviews)]:write(dest/f'{name}.json',value)
        coverage.append(dict(month=month,n=512,as_of=global_plans[month]['as_of'],
           source_lag_months=ds['source_lag_months'],date_source_reference=assignments[month][ids[0]]['date_source_reference'],
           news_quantity=dict(Counter(tiers.values())),cutoff_count=len(cache),
           global_environment_envelope='Forecaster D metadata; individual LLM information comes only from frozen per-agent prompts'))
        print(month,':512 person-date prompts;unique cutoff views',len(cache),flush=True)
    write(prep/'state_dependencies_private.json',nodes)
    (prompts/'role_assignments_private.json').write_bytes((BASE/'prompts/role_assignments_private.json').read_bytes())
    summary=dict(status='assembled_sampled_date_B_offline_not_authorized',coverage=coverage,
       research_line=oldsummary['research_line'],population_preflight=oldsummary['population_preflight'],prior_source=oldsummary['prior_source'],
       micro_availability_basis=oldsummary['micro_availability_basis'],planned_unique_requests=len(nodes),logical_positions=len(nodes),
       runtime_character_cap=max(sizes)+512,runtime_utf8_byte_cap=max(len(json.dumps(v['messages'],ensure_ascii=False).encode()) for month in selected for v in read(prompts/month/'initial_previews_private.json').values())+1024,
       estimated_cost_usd=(sum(sizes)/4*.259+len(nodes)*300*.8)/1e6,
       sampling_dates=dict(source_lag_months=ds['source_lag_months'],date_seed=DATE_SEED,global_as_of_changed=False),
       complete_B11=len(selected)==11,source_sha256=sources,new_api_calls=0,live_ready=False,
       note='Official Core check is a deterministic fixture, not model accuracy or paid-dispatch authorization')
    for name in ('experiments/media_timing_inputs.py','experiments/full_a_personal_inputs.py','experiments/recent_b_news_refresh.py',
                 'experiments/fullperiod_materialization.py','experiments/media_mechanism_v3.py','experiments/state_continuity_core.py',
                 'state_continuity_runtime.py','coverage_preparation.py','news_exposure.py'):
        path=ROOT/'studies/sce_inflation_expectations'/name;sources[str(path.relative_to(ROOT))]=sha(path)
    summary['rendering_contract']='Per-person B frozen messages with synthetic-reference same-date support; use frozen-message queue,not the old strict adjacent-history renderer'
    write(prompts/'summary.json',summary);core=check_frozen_core(prompts,out/'core_engineering');summary['official_core']=core
    write(out/'summary.json',summary)
    generated={str(p.relative_to(out)):sha(p) for p in out.rglob('*.json') if 'archive_view' not in p.relative_to(out).parts}
    write(out/'manifest.json',dict(source_sha256=sources,files_sha256=generated,new_api_calls=0,authorization_written=False))
    print('Offline B date assembly complete;',len(nodes),'prompts;newAPI0')


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('dates');d.add_argument('--out',required=True,type=Path);d.add_argument('--lag-months',choices=(12,24),default=12,type=int)
    a=sub.add_parser('assemble');a.add_argument('--date-plan',required=True,type=Path);a.add_argument('--out',required=True,type=Path)
    a.add_argument('--repair-manifest',type=Path);a.add_argument('--months',help='Optional comma-separated engineering subset, not a full B run')
    args=p.parse_args()
    with no_network():
        if args.command=='dates':prepare_dates(args.out,args.lag_months)
        else:assemble(args.date_plan,args.out,args.repair_manifest,args.months.split(',') if args.months else None)


if __name__=='__main__':main()
