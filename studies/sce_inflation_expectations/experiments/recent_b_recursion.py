"""Fixed-household B belief recursion, with a month barrier before every step.

The sole initializer and the actual first-month answers come from the sealed B
run. Later templates contain state tokens, not independent monthly priors. The
existing frozen-message transport handles each monthly wave and its one repair.
No target answers or fitted combination parameters enter the generator.
"""
from argparse import ArgumentParser
from collections import Counter
from copy import deepcopy
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from .frozen_batch import ROOT, OFFICIAL, read_json as read, dump, sha
from .monthly_main_background import atomic_json
from . import frozen_message_queue as queue
from . import full_a_personal_terminal as transport
from . import recent_b_sampled_terminal as prior_run
from .recent_b_sampled_dates import (
    BASE, DATE_SOURCE, NY, assign_date, source_probability, load_repair,
    merge_labels, archive_view, archive_screen, check_frozen_core,
    template_from_rendered, render_B_messages,
)
from .recent_b_news_refresh import _load_labels, _news_pools, _latest_cpi_release_day, SEED
from .fullperiod_materialization import news_pool_for_prompts
from .full_a_personal_inputs import _food_snapshot, _policy_snapshot
from .media_timing_inputs import FOOD, BASKET, transform, food_text, parsed
from .media_mechanism_v3 import draw_personal
from .recent_b_continuity_pe import dependency_plan, validate_dependencies
from .state_continuity_execution import verify, authorize, live_sender
from ..belief_trial_preparation import confidence_block
from ..coverage_preparation import latest_wave, national_confidence
from ..news_exposure import interests_for_profile
from ..news_selection_trial import RecallRules, RULE_FILE
from ..prior_belief_experiment import message_hash
from ..q9_normalization import response_point, response_view
from ..state_continuity_runtime import advance_state, render_state
from ..submission_tools.reproduce import no_network

MONTHS = list(prior_run.MONTHS)
SOURCE = ROOT / 'outputs/sce_recent_b_sampled_terminal_20261026_v1'
REPAIR = ROOT / 'outputs/sce_recent_b_news_repair_20261026_v1/repair_manifest.json'
WEIGHTS = ROOT / 'outputs/sce_recent_b_continuity_pe_20261026_v2/fixed_weights_private.json'
ENTRY = ROOT / 'scripts/run_sce_recent_b_recursion.py'


def binding(path, sources):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('Existing local source required')
    sources[str(path.relative_to(ROOT))] = sha(path)
    return read(path)


def checked_files(base, hashes):
    for rel, digest in hashes.items():
        path = (base / rel).resolve()
        if not path.is_relative_to(base.resolve()) or not path.is_file() or sha(path) != digest:
            raise ValueError('Bound source changed: ' + rel)


def transition(previous, main, repair, fields, month, cutoff):
    """Keep successful original fields; update history once from the final view."""
    payload = {}
    for field in ('q8', 'q9'):
        row = main
        if not queue.fields(row)[field] and field in fields and repair and queue.fields(repair)[field]:
            row = repair
        if not queue.fields(row)[field]:
            continue
        if field == 'q8':
            point = response_point(row['raw_response_text'])
            if abs(point) <= 100:
                payload['point_pct'] = point
        else:
            response_view(row['raw_response_text'])
            # Pass the original bins to the shared transition to retain its
            # proportional-normalization flag, not a second normalized view.
            original = json.loads(row['raw_response_text'])['q9']
            payload['q9'] = original
    return advance_state(previous, json.dumps(payload), month, cutoff)


def prepare(folder, cap=10.):
    folder = Path(folder).resolve()
    if folder.exists() or not folder.is_relative_to(ROOT / 'outputs') or not 0 < cap <= 10:
        raise ValueError('Fresh outputs directory and cap in (0,10] required')
    oldp, oldm = prior_run.checked(SOURCE)
    receipt = read(SOURCE / 'combined/receipt.json')
    if receipt['technical_complete'] != 5632 or receipt['remaining_q8'] or receipt['remaining_q9']:
        raise ValueError('Complete actual B roots required')
    checked_files(SOURCE / 'combined', read(SOURCE / 'combined/manifest.json')['files_sha256'])
    assembly = ROOT / oldp['assembly']; base = assembly / 'prompts'; first = MONTHS[0]
    sources = dict(oldm['source_sha256'])
    binding(SOURCE / 'package/manifest.json', sources)
    binding(SOURCE / 'package/protocol.json', sources)
    binding(SOURCE / 'combined/manifest.json', sources)
    sources[str((SOURCE / 'combined/positions_private.jsonl').relative_to(ROOT))] = sha(SOURCE / 'combined/positions_private.jsonl')
    initial = binding(base / first / 'initial_states_private.json', sources)
    population = binding(base / first / 'population.json', sources)
    people = {r['agent_id']: r['attributes'] for r in population['personas']}; ids = sorted(people)
    if len(ids) != 512 or set(initial) != set(ids):
        raise ValueError('Original complete 512 roots required')
    weights = binding(WEIGHTS, sources)
    if set(weights) != set(ids):
        raise ValueError('Fixed source weights differ from roots')
    # Match root weights to the actual first-B source, not an unrelated PE file.
    selected = binding(ROOT / oldp['population_preflight'] / 'selected_proxy_population_private.json', sources)
    original_weights = {r['persona']['agent_id']: r for r in selected[first]}
    if any(weights[a]['analysis_weight'] != original_weights[a]['analysis_weight'] for a in ids):
        raise ValueError('Root analysis weights differ')
    baskets = binding(base / first / 'baskets_private.json', sources)
    allroles = binding(BASE / 'prompts/role_assignments_private.json', sources)
    roles = {r['agent_id']: r['role'] for r in allroles if r['month'] == first}
    previews = binding(base / first / 'initial_previews_private.json', sources)
    rootctx = binding(base / first / 'timing_context_private.json', sources)
    tiers = {a: len(rootctx[a]['common_news']) + len(rootctx[a]['personal_news']) for a in ids}
    if Counter(tiers.values()) != {4:128, 8:128, 16:128, 32:128}:
        raise ValueError('Root attention allocation changed')
    # Validate the actual root fields against original main/repair ledgers.
    mi, mr = queue.archive(SOURCE / 'main'); ri, rr = queue.archive(SOURCE / 'repair')
    slots = {r['key']: r for r in binding(SOURCE / 'slot_index_private.json', sources)}
    policy = read(SOURCE / 'package/execution_policy.json')
    targets = transport._repair_targets(mr, slots, policy)
    transport._validate_main_archive(mi, mr, list(slots.values()))
    transport._validate_repair(ri, rr, targets, slots)
    main = {r['key']:r for r in mr}; repair = {r['key'].removeprefix('repair1|'):r for r in rr}
    for name in ('main', 'repair'):
        for path in (SOURCE / name).rglob('*'):
            if path.is_file():
                sources[str(path.relative_to(ROOT))] = sha(path)
    roots = {}; rootstates = {}
    for line in (SOURCE / 'combined/positions_private.jsonl').open():
        row = json.loads(line)
        if row['month'] != first:
            continue
        aid = row['agent_id']; key = row['key']
        if aid not in people or aid in roots or not row['actual_model_results']:
            raise ValueError('Unexpected actual root')
        digest = message_hash(previews[aid]['messages'])
        if row['prompt_sha256'] != digest or slots[key]['prompt_sha256'] != digest:
            raise ValueError('Root prompt is not an exact reuse')
        expected = prior_run.merge_state(initial[aid], main[key], repair.get(key), targets.get(key,{}).get('fields',[]), first)
        if expected != row['state_after'] or not all(expected['transition']['field_updated_from_model'].values()):
            raise ValueError('Root effective fields do not match the original ledgers')
        state = transition(initial[aid], main[key], repair.get(key), targets.get(key,{}).get('fields',[]), first, rootctx[aid]['as_of'])
        rootstates[aid] = state
        roots[aid] = dict(agent_id=aid, month=first, prompt_sha256=digest, state_after=state,
                         execution_kind='exact_historical_root_reuse', source_key=key)
    if set(roots) != set(ids):
        raise ValueError('Incomplete root answer reuse')

    date_summary = binding(DATE_SOURCE / 'summary.json', sources)
    binding(DATE_SOURCE / 'manifest.json', sources)
    checked_files(DATE_SOURCE, read(DATE_SOURCE / 'manifest.json')['files_sha256'])
    probs = date_summary['monthly_probabilities']['counts']
    plans = {r['month']:r for r in binding(ROOT / oldp['population_preflight'] / 'monthly_input_plan.json', sources)}
    oldsummary = binding(BASE / 'summary.json', sources)
    overrides, extra = load_repair(REPAIR, sources)
    labels = merge_labels(_load_labels(oldsummary, sources), extra)
    foods = binding(ROOT / 'outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json', sources)
    policies = binding(ROOT / 'data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json', sources)
    waves = binding(ROOT / 'docs/workstreams/20261017_reference_scaleup/confidence_sources.json', sources)['waves']
    waves += binding(ROOT / 'data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json', sources)['waves']
    rules = RecallRules(binding(RULE_FILE, sources))
    folder.mkdir(); pe = folder / 'PE'; pe.mkdir(); coverage = []; sizes = []; bytesizes = []
    required = set()
    for m in MONTHS:
        y, mo = int(m[:4]), int(m[4:]); required.add(f'{y:04}-{mo:02}')
        required.add(f'{y-(mo==1):04}-{12 if mo==1 else mo-1:02}')
    view, aliases = archive_view(pe, required, overrides)
    for month in MONTHS:
        dest = pe / month; dest.mkdir(); plan = plans[month]; env = binding(base / month / 'environment.json', sources)
        # All supplied profiles, weights, shopping roles and tiers stay at root.
        env['provider_args']['persona_by_id'] = deepcopy(people)
        pop = deepcopy(population)
        src, prob = source_probability(probs, int(month), plan['old_population_reference_period'], 12)
        dates = {a:dict(date_source_reference=src, source_lag_months=12,
                       **assign_date(month,a,prob,plan['as_of'])) for a in ids}
        if month == first and any(dates[a]['information_cutoff'] != rootctx[a]['as_of'] or
                                  dates[a]['synthetic_completion_day'] != rootctx[a]['synthetic_completion_day'] for a in ids):
            raise ValueError('Root dates changed; reuse would be invalid')
        maxcut = max((r['information_cutoff'] for r in dates.values()), key=parsed)
        target = month[:4]+'-'+month[4:]
        raw, _, hashes = news_pool_for_prompts(view, target, maxcut, rules)
        for rel,digest in hashes.items():
            actual = ROOT / aliases[Path(rel).stem]
            if sha(actual) != digest:
                raise ValueError('News archive alias changed')
            sources[str(actual.relative_to(ROOT))] = digest
        cache = {}
        for cutoff in sorted({r['information_cutoff'] for r in dates.values()}):
            eligible = [r for r in raw if parsed(r['pub_date']) <= parsed(cutoff)]
            common, pool, audit = _news_pools(eligible, labels, cutoff, _latest_cpi_release_day(env, cutoff))
            foodkey, facts = _food_snapshot(foods, cutoff); policy = _policy_snapshot(policies, cutoff); wave = latest_wave(waves, cutoff)
            for fact in facts.values():
                if sha(ROOT / fact['source_file']) != fact['source_sha256']:
                    raise ValueError('Price archive changed')
                sources[fact['source_file']] = fact['source_sha256']
            sources[policy['file']] = policy['sha256']; sources[wave['local_file']] = sha(ROOT/wave['local_file'])
            cache[cutoff] = dict(common=common,pool=pool,facts=facts,policy=policy,wave=wave,foodkey=foodkey)
        templates = {}; contexts = {}; drypreviews = {}
        for aid in ids:
            if month == first:
                context = rootctx[aid]; msg = previews[aid]['messages']
            else:
                date_row = dates[aid]; cutoff = date_row['information_cutoff']; c = cache[cutoff]
                personal = draw_personal(c['pool'], [], tiers[aid]-3, f'{SEED}|{month}|{aid}',
                    interests_for_profile(people[aid], baskets[aid]['spending_shares']),
                    alarming_boost=1., cpi_boost=1.5, fox_share=0.)
                context = dict(**date_row, as_of=cutoff, common_news=c['common'],personal_news=personal,
                    food_published_at=c['facts']['food_at_home']['published_at'],policy_published_at=c['policy']['published_at'],
                    food_catalog_period=c['foodkey'],confidence_wave_id=c['wave']['wave_id'])
                oldmsg = previews[aid]['messages']; oldtext = oldmsg[0]['content']; old = rootctx[aid]
                oldpolicy = _policy_snapshot(policies, old['as_of']); oldwave = latest_wave(waves, old['as_of'])
                msg = transform(oldmsg, old, context, initial[aid], oldtext[oldtext.index(FOOD):oldtext.index(BASKET)],
                    food_text(roles[aid],aid,c['facts']),oldpolicy,c['policy'],
                    confidence_block(national_confidence(aid,42,oldwave)),confidence_block(national_confidence(aid,42,c['wave'])))
                date_label = datetime.strptime(month,'%Y%m').strftime('%B %Y')
                msg[0]['content'], n = re.subn(r'You are answering a monthly survey in [^.]+\.',
                    f'You are answering a monthly survey in {date_label}.',msg[0]['content'])
                if n != 1:
                    raise ValueError('Monthly survey sentence missing')
                msg[0]['content'], n = re.subn(r'Synthetic questionnaire completion date: \d{4}-\d{2}-\d{2}\.',
                    'Synthetic questionnaire completion date: '+date_row['synthetic_completion_day']+'.',msg[0]['content'])
                if n != 1:
                    raise ValueError('Synthetic date annotation missing')
            template = template_from_rendered(msg,initial[aid],month,context)
            # Engineering fixtures carry the SAME household's earlier model
            # answer forward. They are not live future inputs or target data.
            fixture = initial[aid] if month == first else rootstates[aid]
            rendered = render_B_messages(template, fixture, month, context)
            if aid in rendered[0]['content']:
                raise ValueError('Proxy ID leaked into model message')
            templates[aid] = template; contexts[aid] = context
            drypreviews[aid] = dict(messages=rendered,prompt_sha256=message_hash(rendered))
            sizes.append(len(json.dumps(rendered,ensure_ascii=False))); bytesizes.append(len(json.dumps(rendered,ensure_ascii=False).encode()))
        for name,obj in [('population',pop),('environment',env),('templates_private',templates),
                         ('timing_context_private',contexts),('initial_previews_private',drypreviews)]:
            dump(dest/(name+'.json'),obj)
        coverage.append(dict(month=month,n=512,as_of=plan['as_of'],date_source_reference=src,
            cutoff_count=len(cache),attention_counts=dict(Counter(tiers.values())),fixed_root_population=True))
        print(month+': fixed 512 identities, repaired dated E, tokenized prior',flush=True)
    for name,obj in [('population_private',population),('weights_private',weights),('baskets_private',baskets),
                     ('roles_private',roles),('tiers_private',tiers),('initial_states_private',initial),
                     ('root_answers_private',roots)]:
        dump(pe/(name+'.json'),obj)
    nodes = dependency_plan(ids,MONTHS); validate_dependencies(nodes,ids,MONTHS)
    dump(pe/'dependencies_private.json',nodes)
    # Leave room for at most 11 finite, full-precision history entries. Live
    # rendering checks these bounds before any dispatch.
    maxchars = max(sizes)+10000; maxbytes = max(bytesizes)+20000
    dump(pe/'summary.json',dict(coverage=coverage,runtime_character_cap=maxchars,new_api_calls=0,
        fixtures_are_engineering_only=True,only_one_initial_belief_file=True))
    core = check_frozen_core(pe,folder/'core_engineering')
    p = dict(schema='sce_monthly_fixed_B_recursion/v1',months=MONTHS,n_per_month=512,
        planned_calls=5120,logical_positions=5632,reused_root_calls=512,maximum_physical_api_attempts=10240,
        model=oldp['model'],destination=oldp['destination'],route=oldp['route'],expected_provider=oldp['expected_provider'],
        temperature=.5,thinking='disabled',response_format='json_object',max_tokens=1024,timeout_s=120,
        retry_max=0,provider_fallback=False,request_extra_body=oldp['request_extra_body'],
        provider_metadata=oldp['provider_metadata'],price_input_per_mtok=.259,price_output_per_mtok=.8,
        budget_cap_usd=float(cap),max_prompt_bytes=maxbytes,max_prompt_chars=maxchars,
        technical_gate={'minimum_format_ratio':.95},PE=str(pe.relative_to(ROOT)),
        root_source=str(SOURCE.relative_to(ROOT)),fixed_cohort=True,entry_exit=False,Normal=False,
        public_national_anchor_policy='Root synthetic seed only; no later public national headline broadcast or state reset',
        state_policy='Same-ID immediately previous checkpoint; one technical repair before next month; failed fields retain own prior',
        history_summary='Shared frozen Q9 density mean for own earlier simulated answers; no real future answer',
        parameter_source=str(prior_run.PARAMS.relative_to(ROOT)),
        target_catalog_evaluation_only=str(prior_run.CATALOG.relative_to(ROOT)),
        evaluation='National monthly MAE/RMSE/bias, root-retention and public persistence baselines; simulated dispersion/update/drift only',
        strict_B_eligible=False,target_truth_opened=False,new_api_calls=0,official_Core=core,
        limits=['Fixed root population weights are not later real survey composition.',
                'All outcomes already public: retrospective as-of diagnostic, with unresolved model/text-vintage limitations.',
                'Existing independently initialized B uses changing monthly rosters; descriptive comparison only, not same-input causal control.',
                'No monthly national-anchor refresh: pure autonomous belief-state chain, not a claim that people never see official statistics.',
                'No recent micro truth: dispersion and conditional differences are descriptive only.'],created_at_utc=queue.now())
    # Empirical token expectation from current prompt lengths; not a guarantee.
    p['estimated_main_cost_usd'] = (sum(sizes[512:])/4*.259+5120*300*.8)/1e6
    (folder/'package').mkdir(); dump(folder/'package/protocol.json',p)
    pol=transport._policy(); pol['batch_slots']=512; dump(folder/'package/execution_policy.json',pol)
    sourcecode=[Path(__file__),ENTRY,Path(transport.__file__),Path(queue.__file__),
        Path(__file__).with_name('recent_b_recursive_evaluation.py'),
        Path(__file__).with_name('recent_b_sampled_dates.py'),Path(__file__).with_name('recent_b_continuity_pe.py'),
        ROOT/'studies/sce_inflation_expectations/state_continuity_runtime.py',
        ROOT/'studies/sce_inflation_expectations/scoring/sce_q9_frozen.py',
        Path(__file__).with_name('state_continuity_inputs.py'),
        Path(__file__).with_name('state_continuity_execution.py'),
        Path(__file__).with_name('recent_b_sampled_terminal.py'),*transport.RUNTIME_SOURCE_PATHS]
    for path in sourcecode:
        sources[str(path.relative_to(ROOT))]=sha(path)
    for path in [*pe.rglob('*.json'),folder/'core_engineering/summary.json',folder/'package/execution_policy.json',transport.METADATA]:
        if 'archive_view' not in path.parts:
            sources[str(path.relative_to(ROOT))]=sha(path)
    # Hashing evaluation-only targets does not read their values into a prompt.
    for path in (prior_run.PARAMS,prior_run.CATALOG):
        sources[str(path.relative_to(ROOT))]=sha(path)
    dump(folder/'package/manifest.json',dict(protocol_sha256=sha(folder/'package/protocol.json'),
        source_sha256=sources,new_api_calls=0,target_truth_opened=False))
    for rel in sources:
        if Path(rel).suffix=='.py':
            dest=folder/'package/source_snapshot'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dest)
    result=dict(status='prepared_not_authorized',fixed_households=512,months=11,reused_actual_roots=512,
        new_main_calls=5120,maximum_new_attempts=10240,estimated_main_cost_usd=p['estimated_main_cost_usd'],
        cap_usd=cap,official_core_units=core['official_engine_units'],new_api_calls=0)
    dump(folder/'preparation_receipt.json',result)
    return result


def checked(folder, authorized=False):
    p,m=verify(Path(folder)/'package')
    if p['planned_calls']!=5120 or p['months']!=MONTHS or p['n_per_month']!=512 or p['budget_cap_usd']>10:
        raise ValueError('Frozen recursive scope changed')
    if authorized:
        a=read(Path(folder)/'package/authorization.json')
        if not a.get('approved') or a['protocol_sha256']!=m['protocol_sha256']:
            raise ValueError('Explicit exact recursive batch authorization required')
        for k in ('planned_calls','budget_cap_usd','destination','model','route'):
            if a[k]!=p[k]:raise ValueError('Authorization differs: '+k)
    return p,m


def checkpoint(path):
    manifest=read(path/'manifest.json');checked_files(path,manifest['files_sha256'])
    wave=path.parent.parent/'waves'/path.name
    if sha(wave/'wave_plan.json')!=manifest['wave_plan_sha256']:
        raise ValueError('Sealed monthly prompt plan changed')
    checked_files(wave,manifest['ledger_manifest_sha256'])
    queue.archive(wave/'main');queue.archive(wave/'repair')
    return read(path/'states_private.json'),read(path/'receipt.json')


def prepare_wave(folder,p,month,previous):
    pe=ROOT/p['PE'];wave=folder/'waves'/month;keys=sorted(previous)
    state_digest=hashlib.sha256(json.dumps(previous,sort_keys=True,allow_nan=False).encode()).hexdigest()
    if (wave/'wave_plan.json').exists():
        plan=read(wave/'wave_plan.json')
        if plan['state_before_sha256']!=state_digest:
            raise ValueError('The predecessor checkpoint changed')
        checked_files(wave,plan['files_sha256'])
        return wave,read(wave/'slot_index_private.json')
    wave.mkdir(parents=True,exist_ok=True);templates=read(pe/month/'templates_private.json');contexts=read(pe/month/'timing_context_private.json')
    if set(previous)!=set(templates) or any(r['agent_id']!=a or r['month']!=MONTHS[MONTHS.index(month)-1] for a,r in previous.items()):
        raise ValueError('Missing, cross-person or skipped-month predecessor')
    rows={};slots=[]
    for aid in keys:
        state=previous[aid]['state_after'];messages=render_B_messages(templates[aid],state,month,contexts[aid])
        text=json.dumps(messages,ensure_ascii=False);size=len(text.encode())
        if size>p['max_prompt_bytes'] or len(text)>p['max_prompt_chars']:
            raise ValueError('Dynamic history exceeds frozen prompt-size allowance')
        digest=message_hash(messages);key=f'recursiveB|{month}|{aid}'
        rows[aid]=dict(messages=messages,prompt_sha256=digest)
        slots.append(dict(key=key,month=month,agent_id=aid,arm='recursive_B',repeat=1,
                          prompt_sha256=digest,reserved_usd=transport.reserve(p,size)))
    slots.sort(key=lambda r:hashlib.sha256(r['key'].encode()).digest())
    (wave/'frozen_messages'/month).mkdir(parents=True)
    dump(wave/'frozen_messages'/month/'prompts.json',dict(month=month,rows=rows))
    dump(wave/'slot_index_private.json',slots);dump(wave/'states_before_private.json',previous)
    names=['slot_index_private.json','states_before_private.json',f'frozen_messages/{month}/prompts.json']
    dump(wave/'wave_plan.json',dict(month=month,state_before_sha256=state_digest,
        files_sha256={n:sha(wave/n) for n in names},created_at_utc=queue.now()))
    return wave,slots


def generate(folder, fake_sender=None, cool=queue.cooldown):
    folder=Path(folder);engineering=fake_sender is not None;p,_=checked(folder,authorized=not engineering)
    pe=ROOT/p['PE'];previous=read(pe/'root_answers_private.json');policy=read(folder/'package/execution_policy.json')
    send=fake_sender if engineering else live_sender(p);spent=reported=0.;attempts=0;completed=0;monthly=[]
    for month in p['months'][1:]:
        sealed=folder/'checkpoints'/month
        if sealed.exists():
            previous,r=checkpoint(sealed)
        else:
            wave,slots=prepare_wave(folder,p,month,previous)
            wp={**p,'input_package_path':str(wave/'frozen_messages'),'planned_calls':512,
                'budget_cap_usd':max(0.,p['budget_cap_usd']-spent)}
            def publish(stage,live):
                atomic_json(folder/'progress.json',dict(stage=stage,month=month,completed_months=1+len(monthly),
                    attempts=attempts+live.get('attempts',0),completed=completed+live.get('completed',0),
                    planned_calls=p['planned_calls'],in_flight=live.get('in_flight',0),
                    reported_cost_usd=reported+live.get('reported_cost_usd',0),
                    spent_or_reserved_usd=spent+live.get('spent_or_reserved_usd',0),at_utc=queue.now()))
            main=transport.run_main_segments(wp,slots,wave,send,policy,cool=cool,publish=publish,engineering_only=engineering)
            mi,mr=queue.archive(wave/'main')
            hard=any(r.get('error') and not transport.recoverable(r,policy) for r in mr)
            if main['status']!='completed' or hard:
                result=dict(status='stopped_data_preserved',stopped_month=month,completed_months=1+len(monthly),
                    main=main,new_api_calls=attempts+len(mi),truth_read=False)
                atomic_json(folder/'generation_receipt.json',result);return result
            fix,ri,rr,targets=transport.run_repair_segments(wp,slots,wave,mi,mr,send,policy,cool=cool,
                publish=publish,engineering_only=engineering)
            if fix['status'] not in ('completed','not_needed'):
                result=dict(status='repair_stopped_data_preserved',stopped_month=month,repair=fix,truth_read=False)
                atomic_json(folder/'generation_receipt.json',result);return result
            mains={r['key']:r for r in mr};fixes={r['key'].removeprefix('repair1|'):r for r in rr}
            contexts=read(pe/month/'timing_context_private.json');states={};missing={'q8':0,'q9':0}
            for slot in slots:
                aid=slot['agent_id'];key=slot['key']
                state=transition(previous[aid]['state_after'],mains[key],fixes.get(key),
                    targets.get(key,{}).get('fields',[]),month,contexts[aid]['as_of'])
                for field,valid in state['transition']['field_updated_from_model'].items():missing[field]+=not valid
                states[aid]=dict(agent_id=aid,month=month,state_after=state,previous_month=previous[aid]['month'],
                    prompt_sha256=slot['prompt_sha256'],execution_kind='actual_model' if not engineering else 'engineering_fixture')
            a,b=queue.account(mi,mr),queue.account(ri,rr)
            r=dict(month=month,main_attempts=a['attempts'],repair_attempts=b['attempts'],
                physical_attempts=a['attempts']+b['attempts'],remaining_fields=missing,
                reported_cost_usd=a['reported_cost_usd']+b['reported_cost_usd'],
                spent_or_reserved_usd=a['spent_or_reserved_usd']+b['spent_or_reserved_usd'],actual_model_results=not engineering)
            # The final checkpoint is an atomic directory publication: a crash
            # while sealing leaves a recoverable staging directory, never a
            # partially written checkpoint mistaken for an advanced chain.
            stage=folder/'checkpoints'/(month+'.staging');stage.mkdir(parents=True,exist_ok=True)
            dump(stage/'states_private.json',states);dump(stage/'receipt.json',r)
            files={n:sha(stage/n) for n in ('states_private.json','receipt.json')}
            dump(stage/'manifest.json',dict(files_sha256=files,wave_plan_sha256=sha(wave/'wave_plan.json'),
                ledger_manifest_sha256={str(f.relative_to(wave)):sha(f) for f in wave.rglob('manifest.json')}))
            stage.rename(sealed);previous=states
        spent+=r['spent_or_reserved_usd'];reported+=r['reported_cost_usd'];attempts+=r['physical_attempts'];completed+=r['physical_attempts'];monthly.append(r)
        if spent>p['budget_cap_usd']+1e-9:raise ValueError('Global budget guard')
        print(month+f': checkpoint sealed; total new attempts {attempts}, reported ${reported:.4f}',flush=True)
    result=dict(status='monthly_recursion_generation_complete',months=11,fixed_households=512,
        logical_positions=5632,reused_actual_root_answers=512,new_main_calls=sum(r['main_attempts'] for r in monthly),
        automatic_one_repair_calls=sum(r['repair_attempts'] for r in monthly),physical_new_attempts=attempts,
        reported_cost_usd=reported,spent_or_reserved_usd=spent,unknown_fee_reservation_usd=spent-reported,
        budget_cap_usd=p['budget_cap_usd'],monthly=monthly,truth_read=False,actual_model_results=not engineering,
        Normal=False,entry_exit=False,ended_at_utc=queue.now())
    atomic_json(folder/'generation_receipt.json',result)
    atomic_json(folder/'progress.json',dict(stage='generation_complete',completed_months=11,attempts=attempts,
        completed=completed,in_flight=0,reported_cost_usd=reported,spent_or_reserved_usd=spent,at_utc=queue.now()))
    return result


def worker(folder):
    folder=Path(folder);checked(folder,authorized=True);wake=None
    with (folder/'active.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if sys.platform=='darwin':
            wake=subprocess.Popen(['/usr/bin/caffeinate','-is','-w',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            with (folder/'generation.log').open('a') as log:
                child=subprocess.run([sys.executable,str(ENTRY),'_generate','--run-dir',str(folder)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if child.returncode:raise RuntimeError('Generator failed; original data retained')
            gen=read(folder/'generation_receipt.json')
            if gen['status']!='monthly_recursion_generation_complete':
                atomic_json(folder/'worker_receipt.json',dict(status=gen['status'],generation_receipt=gen,at_utc=queue.now()));return
            with (folder/'evaluation.log').open('a') as log:
                child=subprocess.run([sys.executable,str(ENTRY),'_evaluate','--run-dir',str(folder)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            atomic_json(folder/'worker_receipt.json',dict(status='generation_and_evaluation_complete' if child.returncode==0 else
                'evaluation_failed_data_preserved',exit_code=child.returncode,generation_receipt=gen,at_utc=queue.now()))
        except Exception as exc:
            atomic_json(folder/'worker_receipt.json',dict(status='worker_failed_data_preserved',error_type=type(exc).__name__,at_utc=queue.now()))
            raise
        finally:
            if wake is not None:wake.terminate();wake.wait()


def launch(folder,confirm=False,resume=False):
    folder=Path(folder).resolve();p,m=checked(folder,authorized=True)
    if not confirm:raise ValueError('Confirmed exact scope and budget required')
    with (folder/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with (folder/'active.lock').open('a') as running:
            try:fcntl.flock(running,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Already running; use watch')
        if (folder/'launch.json').exists() and not resume:raise ValueError('Explicit --resume required')
        if (folder/'generation_receipt.json').exists() and read(folder/'generation_receipt.json')['status']=='monthly_recursion_generation_complete':
            raise ValueError('Generation complete; evaluation does not require another launch')
        from ..news_label_trial import dotenv_values
        if not(os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL/'.env').get('OPENROUTER_API_KEY')):
            raise ValueError('OpenRouter key missing')
        # Archive an earlier stopped worker status so watch cannot stop early.
        if (folder/'worker_receipt.json').exists():
            (folder/'worker_receipt.json').rename(folder/f'worker_receipt_before_resume_{time.time_ns()}.json')
        with (folder/'terminal_worker.log').open('a') as log:
            child=subprocess.Popen([sys.executable,'-u',str(ENTRY),'_worker','--run-dir',str(folder)],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        record=dict(pid=child.pid,started_at_utc=queue.now(),independent_of_codex=True,
                    protocol_sha256=m['protocol_sha256'],resumed=resume)
        atomic_json(folder/'launch.json',record);dump(folder/f'launch_{child.pid}.json',record)
        return record


def watch(folder,once=False):
    folder=Path(folder)
    while True:
        r=read(folder/'progress.json') if (folder/'progress.json').exists() else {'stage':'starting'}
        print(datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S')+
            f" | {r.get('stage')} | {r.get('month','')} | 已封存月份 {r.get('completed_months',1)}/11"+
            f" | 新请求 {r.get('attempts',0):,} | 在途 {r.get('in_flight',0)}"+
            f" | 已报 ${r.get('reported_cost_usd',0):.4f} | 计及预留 ${r.get('spent_or_reserved_usd',0):.4f}",flush=True)
        if (folder/'worker_receipt.json').exists():print(json.dumps(read(folder/'worker_receipt.json'),ensure_ascii=False,indent=2));return
        if once:return
        time.sleep(10)


def replay(folder,out):
    """Full-scope queue replay with synthetic answers, never a model result."""
    folder=Path(folder);out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh replay directory required')
    out.mkdir();shutil.copytree(folder/'package',out/'package')
    seen=Counter()
    def send(messages):
        digest=message_hash(messages);seen[digest]+=1
        if len(seen)==55 and seen[digest]==1:
            return dict(error='APIConnectionError',error_http_status=None,finish_reason=None,raw_response_text='',
                api_reported_cost_usd=None,returned_model='deepseek/deepseek-v3.2',returned_provider='SiliconFlow')
        return dict(error=None,returned_model='deepseek/deepseek-v3.2',returned_provider='SiliconFlow',finish_reason='stop',
            api_reported_cost_usd=.00001,raw_response_text=json.dumps(dict(point_pct=3.,q9={f'bin{i}':10. for i in range(1,11)})))
    result=generate(out,fake_sender=send,cool=lambda *_:None)
    if (result.get('status')!='monthly_recursion_generation_complete' or result.get('physical_new_attempts')!=5121
            or result.get('automatic_one_repair_calls')!=1 or sum(seen.values())!=5121):
        raise ValueError('Deterministic replay did not cover exactly one technical repair')
    before=sum(seen.values())
    resumed=generate(out,fake_sender=send,cool=lambda *_:None)
    if sum(seen.values())!=before or resumed['physical_new_attempts']!=before:
        raise ValueError('A completed checkpoint replay must not send again')
    result.update(status='passed_full_11month_recursion_replay',new_real_api_calls=0,
        exact_root_reuse=512,first_failure_repaired_before_next_month=True,completed_resume_sends_zero=True,
        fixture_results_not_accuracy=True)
    dump(out/'offline_acceptance.json',result);return result


def main(argv=None):
    parser=ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='cmd',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--run-dir',type=Path,required=True);prep.add_argument('--cap-usd',type=float,default=10.)
    for name in ('review','authorize','run','watch','replay','_worker','_generate','_evaluate'):
        cmd=sub.add_parser(name);cmd.add_argument('--run-dir',type=Path,required=True)
        if name=='authorize':cmd.add_argument('--human-confirmation',required=True)
        if name=='run':cmd.add_argument('--confirm-scope-and-budget',action='store_true');cmd.add_argument('--resume',action='store_true')
        if name=='watch':cmd.add_argument('--once',action='store_true')
        if name=='replay':cmd.add_argument('--out',required=True,type=Path)
    args=parser.parse_args(argv)
    if args.cmd in ('prepare','replay'):
        with no_network():
            result=prepare(args.run_dir,args.cap_usd) if args.cmd=='prepare' else replay(args.run_dir,args.out)
    elif args.cmd=='review':result=dict(status='verified_not_started',protocol=checked(args.run_dir)[0])
    elif args.cmd=='authorize':result=authorize(args.run_dir/'package',args.human_confirmation)
    elif args.cmd=='run':result=launch(args.run_dir,args.confirm_scope_and_budget,args.resume)
    elif args.cmd=='watch':watch(args.run_dir,args.once);return
    elif args.cmd=='_worker':worker(args.run_dir);return
    elif args.cmd=='_generate':result=generate(args.run_dir)
    else:
        from .recent_b_recursive_evaluation import evaluate
        result=evaluate(args.run_dir)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
