"""Terminal/background adapter for the approved independent-month B date study.

Consumes frozen messages only. Reuses the completed full-A transport scheduler,
including durable dispatch, bounded cooling, restart protection and one repair.
It never calls the old adjacent-observed-history prompt renderer.
"""
from argparse import ArgumentParser
from copy import deepcopy
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from .frozen_batch import ROOT, OFFICIAL, read_json, dump, sha
from .monthly_main_background import atomic_json
from .state_continuity_execution import authorize, verify, live_sender
from . import frozen_message_queue as queue
from . import full_a_personal_terminal as transport
from .recent_b_sampled_dates import render_B_messages
from ..prior_belief_experiment import message_hash
from ..q9_normalization import response_point, response_view

ENTRY = ROOT / 'scripts/run_sce_recent_b_sampled.py'
MONTHS = ['202511', '202512', *[f'2026{m:02}' for m in range(1, 10)]]
PARAMS = ROOT / 'outputs/sce_recent_b_review_materials_20261026_v2/macro_parameters.json'
REVIEW = ROOT / 'outputs/sce_recent_b_review_materials_20261026_v2/monthly_inputs_review.csv'
CATALOG = ROOT / 'data/evaluation/sce_recent_b_evaluation_20261025_v1/aggregate_inputs.json'


def prepare(assembly, folder, cap=8.):
    assembly, folder = Path(assembly).resolve(), Path(folder).resolve()
    if folder.exists() or not folder.is_relative_to(ROOT / 'outputs') or not 0 < cap <= 8:
        raise ValueError('Fresh outputs directory and combined cap in (0,8] required')
    summary = read_json(assembly / 'summary.json')
    manifest = read_json(assembly / 'manifest.json')
    for root, hashes in ((assembly, manifest['files_sha256']), (ROOT, manifest['source_sha256'])):
        for rel, digest in hashes.items():
            path = (root / rel).resolve()
            if not path.is_relative_to(root) or sha(path) != digest:
                raise ValueError('Assembly binding changed: ' + rel)
    core = summary['official_core']
    if (not summary['complete_B11'] or [r['month'] for r in summary['coverage']] != MONTHS
            or core['official_engine_units'] != 11 or core['decisions'] != 5632
            or summary['sampling_dates']['source_lag_months'] != 12
            or summary['sampling_dates']['global_as_of_changed']):
        raise ValueError('Complete 11-month, 12-month-lag offline acceptance required')
    nodes = read_json(assembly / 'inputs/state_dependencies_private.json')
    if len(nodes) != 5632 or any(n['dependency'] is not None for n in nodes):
        raise ValueError('Only the registered independent-month 5632 scope is supported')
    folder.mkdir(); (folder / 'package').mkdir(); messages = folder / 'frozen_messages'
    messages.mkdir(); slots = []; maxbytes = 0
    for month in MONTHS:
        src = assembly / 'prompts' / month
        previews = read_json(src / 'initial_previews_private.json')
        states = read_json(src / 'initial_states_private.json')
        templates = read_json(src / 'templates_private.json')
        contexts = read_json(src / 'timing_context_private.json')
        if len(previews) != 512 or set(previews) != set(states) or set(states) != set(contexts):
            raise ValueError('Unexpected B roster')
        rows = {}
        for aid, row in previews.items():
            payload = row['messages']
            if render_B_messages(templates[aid], states[aid], month, contexts[aid]) != payload:
                raise ValueError('Frozen preview/template/state mismatch')
            digest = message_hash(payload)
            size = len(json.dumps(payload, ensure_ascii=False).encode())
            maxbytes = max(maxbytes, size)
            key = f'Bdates|{month}|{aid}|1'
            slots.append(dict(key=key, month=month, arm='recent_b', repeat=1,
                              agent_id=aid, prompt_sha256=digest, prompt_bytes=size))
            rows[aid] = dict(messages=payload, prompt_sha256=digest)
        (messages / month).mkdir()
        dump(messages / month / 'prompts.json', dict(month=month, rows=rows))
    params = read_json(PARAMS)
    p = dict(schema='sce_recent_B_sampled_terminal/v1', mechanism='B_independent_sampled_dates_12m',
        research_line=summary['research_line'], months=MONTHS, n_per_month=512, planned_calls=len(slots),
        logical_positions=len(slots), maximum_physical_api_attempts=2*len(slots),
        destination='https://openrouter.ai/api/v1', model='deepseek/deepseek-v3.2',
        route='siliconflow/fp8', expected_provider='SiliconFlow', temperature=.5,
        thinking='disabled', response_format='json_object', max_tokens=1024, timeout_s=120,
        retry_max=0, provider_fallback=False, price_input_per_mtok=.259, price_output_per_mtok=.8,
        provider_metadata=str(transport.METADATA.relative_to(ROOT)),
        request_extra_body={'provider': {'order': ['siliconflow/fp8'], 'allow_fallbacks': False,
            'require_parameters': True, 'max_price': {'prompt': .259, 'completion': .8}},
            'reasoning': {'enabled': False}},
        budget_cap_usd=float(cap), estimated_main_cost_usd=summary['estimated_cost_usd'],
        budget_mode='shared_main_repair_spent_plus_inflight_reservation',
        max_prompt_bytes=maxbytes+1024, max_prompt_chars=summary['runtime_character_cap'],
        technical_gate={'minimum_format_ratio': .95},
        input_package_path=str(messages), input_templates=str((assembly/'prompts').relative_to(ROOT)),
        preparation=str((assembly/'inputs').relative_to(ROOT)),
        population_preflight=summary['population_preflight'], prior_source=summary['prior_source'],
        assembly=str(assembly.relative_to(ROOT)), sampling_dates=summary['sampling_dates'],
        micro_availability_basis=summary['micro_availability_basis'],
        strict_B_eligible=False, q9_postprocessing='proportional_nonnegative_v1',
        frozen_combination_simulation_share=params['blends']['mse']['simulation_weight'],
        parameter_source=str(PARAMS.relative_to(ROOT)), public_macro_review=str(REVIEW.relative_to(ROOT)),
        target_catalog_evaluation_only=str(CATALOG.relative_to(ROOT)),
        truth_opened_during_prepare=False, created_at_utc=queue.now(),
        scope='Same 11x512 proxies; independent public-anchor synthetic priors; sampled-date E; no Normal, entry/exit or recursion',
        repair='Each known transport/non-stop/format failure at most once; preserve successful original fields; unknown intents never replayed')
    for slot in slots: slot['reserved_usd'] = transport.reserve(p, slot.pop('prompt_bytes'))
    # Deterministically spread gate checks over all eleven months, not one month.
    slots.sort(key=lambda r: __import__('hashlib').sha256(r['key'].encode()).digest())
    dump(folder/'slot_index_private.json', slots)
    policy = transport._policy(); policy['batch_slots'] = len(slots)
    dump(folder/'package/protocol.json', p); dump(folder/'package/execution_policy.json', policy)
    source_files = [Path(__file__), ENTRY, Path(transport.__file__), Path(queue.__file__),
        Path(__file__).with_name('recent_b_sampled_evaluation.py'),
        Path(__file__).with_name('state_continuity_execution.py'),
        Path(__file__).with_name('recent_b_evaluation.py'),
        Path(__file__).with_name('recent_b_review_materials.py'),
        Path(__file__).with_name('recent_b_sampled_dates.py'),
        PARAMS, REVIEW, transport.METADATA, assembly/'manifest.json',
        folder/'slot_index_private.json', folder/'package/execution_policy.json',
        *transport.RUNTIME_SOURCE_PATHS, *transport.EVALUATION_SOURCE_PATHS]
    source_files += list(messages.rglob('*.json'))
    # Pin all P/E/prior sources and all complete assembled prompt files.
    hashes = dict(manifest['source_sha256'])
    hashes.update({str((assembly/rel).relative_to(ROOT)): digest for rel,digest in manifest['files_sha256'].items()})
    for path in source_files: hashes[str(path.relative_to(ROOT))] = sha(path)
    # Target answers are deliberately not opened by the preparation/generator.
    dump(folder/'package/manifest.json', dict(protocol_sha256=sha(folder/'package/protocol.json'),
        source_sha256=hashes, target_truth_opened=False, new_api_calls=0))
    for rel, digest in hashes.items():
        if Path(rel).suffix == '.py':
            dest=folder/'package/source_snapshot'/rel; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,dest)
    dump(folder/'config.json',dict(python=sys.executable, protocol_sha256=sha(folder/'package/protocol.json')))
    return dict(status='prepared_not_started', requests=len(slots), estimated_main_cost_usd=p['estimated_main_cost_usd'],
                cap_usd=cap, new_api_calls=0)


def checked(folder, authorized=False):
    folder=Path(folder).resolve(); p,m=verify(folder/'package')
    if p['months']!=MONTHS or p['planned_calls']!=5632 or p['budget_cap_usd']>8:
        raise ValueError('Registered B scope/cap changed')
    if authorized:
        a=read_json(folder/'package/authorization.json')
        if not a.get('approved') or a['protocol_sha256']!=m['protocol_sha256']:
            raise ValueError('Exact batch authorization required')
        for k in ('planned_calls','budget_cap_usd','destination','model','route'):
            if a.get(k)!=p[k]:raise ValueError('Authorization mismatch: '+k)
    return p,m


def merge_state(initial, main, repair, target_fields, month):
    """Independent fields; no scorer, current truth or recursive state is needed."""
    state=deepcopy(initial); accepted={}; normalized=False
    for field in ('q8','q9'):
        row=main; view=queue.fields(row)
        if not view[field] and field in target_fields and repair and queue.fields(repair)[field]:row=repair
        valid=queue.fields(row)[field]
        if field=='q8':
            point=response_point(row.get('raw_response_text','')) if valid else None
            valid=point is not None and abs(point)<=100
            if valid:state['fields'][field]=dict(value=point,source_period=int(month),source_kind='simulated')
        else:
            if valid:
                bins=response_view(row['raw_response_text']);normalized=bins['applied']
                state['fields'][field]=dict(value=bins['bins'],source_period=int(month),source_kind='simulated')
        accepted[field]=valid
    state['transition']=dict(field_updated_from_model=accepted,
        field_retained_as_explicit_fallback={k:not v for k,v in accepted.items()},
        q9_proportional_normalization=normalized)
    return state


def combine(folder,p,main_i,main_r,repair_i,repair_r,targets, *, engineering=False):
    folder=Path(folder); states={m:read_json(ROOT/p['input_templates']/m/'initial_states_private.json') for m in p['months']}
    slots=read_json(folder/'slot_index_private.json'); bykey={r['key']:r for r in main_r}
    repaired={r['key'].removeprefix('repair1|'):r for r in repair_r}
    dest=folder/('engineering_combined' if engineering else 'combined');dest.mkdir()
    remaining={'q8':0,'q9':0}; complete=0
    with (dest/'positions_private.jsonl').open('x') as stream:
        for slot in slots:
            key=slot['key']; row=bykey[key];fix=repaired.get(key)
            if fix and fix['prompt_sha256']!=row['prompt_sha256']:raise ValueError('Repair changed prompt')
            state=merge_state(states[row['month']][row['agent_id']],row,fix,targets.get(key,{}).get('fields',[]),row['month'])
            updated=state['transition']['field_updated_from_model']; complete+=all(updated.values())
            for field in remaining:remaining[field]+=not updated[field]
            merged={**row,'reuse_key':key,'state_after':state,'technical_usable':all(updated.values()),
                'response_error':row.get('error'),'field_overlay_repair_key':fix['key'] if fix else None,
                'raw_responses_in_separate_ledgers':True}
            stream.write(json.dumps(merged,ensure_ascii=False,allow_nan=False)+'\n')
    a,b=queue.account(main_i,main_r),queue.account(repair_i,repair_r)
    receipt=dict(status='generation_and_one_repair_complete',main_logical_positions=len(slots),
        main_api_attempts=a['attempts'],automatic_repair_api_attempts=b['attempts'],physical_api_attempts=a['attempts']+b['attempts'],
        technical_complete=complete,remaining_q8=remaining['q8'],remaining_q9=remaining['q9'],
        reported_cost_usd=a['reported_cost_usd']+b['reported_cost_usd'],
        spent_or_reserved_usd=a['spent_or_reserved_usd']+b['spent_or_reserved_usd'],
        budget_cap_usd=p['budget_cap_usd'],truth_read=False,actual_model_results=not engineering,
        ended_at_utc=queue.now())
    if receipt['spent_or_reserved_usd']>p['budget_cap_usd']+1e-9:raise ValueError('Shared budget exceeded')
    dump(dest/'receipt.json',receipt)
    dump(dest/'manifest.json',dict(files_sha256={f.name:sha(f) for f in dest.iterdir() if f.is_file()}))
    return receipt


def generate(folder, *, fake_sender=None, cool=queue.cooldown):
    folder=Path(folder);engineering=fake_sender is not None;p,_=checked(folder,authorized=not engineering)
    slots=read_json(folder/'slot_index_private.json');policy=read_json(folder/'package/execution_policy.json')
    send=fake_sender if engineering else live_sender(p)
    def publish(stage,live):atomic_json(folder/'progress.json',{**live,'stage':stage,'planned_calls':len(slots)})
    main=transport.run_main_segments(p,slots,folder,send,policy,cool=cool,publish=publish,engineering_only=engineering)
    mi,mr=queue.archive(folder/'main')
    hard=any(r.get('error') and not transport.recoverable(r,policy) for r in mr)
    if main['status']!='completed' or hard:
        result=dict(status='generation_stopped_data_preserved',main=main,truth_read=False)
    else:
        repair,ri,rr,targets=transport.run_repair_segments(p,slots,folder,mi,mr,send,policy,
            cool=cool,publish=publish,engineering_only=engineering)
        if repair['status'] not in ('completed','not_needed'):
            result=dict(status='repair_stopped_data_preserved',main=main,repair=repair,truth_read=False)
        else:
            result=combine(folder,p,mi,mr,ri,rr,targets,engineering=engineering)
    atomic_json(folder/('engineering_receipt.json' if engineering else 'generation_receipt.json'),result)
    return result


def worker(folder):
    folder=Path(folder); p,_=checked(folder,authorized=True); wake=None
    with (folder/'active.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if sys.platform=='darwin':
            wake=subprocess.Popen(['/usr/bin/caffeinate','-is','-w',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            with (folder/'generation.log').open('a') as log:
                child=subprocess.run([sys.executable,str(ENTRY),'_generate','--run-dir',str(folder)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if child.returncode:raise RuntimeError('Generation subprocess failed; see generation.log')
            gen=read_json(folder/'generation_receipt.json')
            if gen['status']!='generation_and_one_repair_complete':
                atomic_json(folder/'worker_receipt.json',dict(status=gen['status'],generation_receipt=gen,at_utc=queue.now()));return
            atomic_json(folder/'progress.json',{**read_json(folder/'progress.json'),'stage':'evaluation'})
            with (folder/'evaluation.log').open('a') as log:
                child=subprocess.run([sys.executable,str(ENTRY),'_evaluate','--run-dir',str(folder)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            result=dict(status='generation_and_evaluation_complete' if child.returncode==0 else 'evaluation_failed_data_preserved',
                exit_code=child.returncode,generation_receipt=gen,at_utc=queue.now())
            atomic_json(folder/'worker_receipt.json',result)
        except Exception as exc:
            atomic_json(folder/'worker_receipt.json',dict(status='worker_failed_data_preserved',error_type=type(exc).__name__,at_utc=queue.now()))
            raise
        finally:
            if wake is not None:wake.terminate();wake.wait()


def launch(folder,confirm=False,resume=False):
    folder=Path(folder).resolve();p,m=checked(folder)
    if not confirm:raise ValueError('Explicit confirmed scope/budget required')
    # Separate launch lock prevents duplicate workers even during initialization.
    with (folder/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        active=folder/'active.lock'
        with active.open('a') as running:
            try:fcntl.flock(running,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Run already active; use watch')
        if (folder/'launch.json').exists() and not resume:raise ValueError('Already launched; explicit resume required')
        if (folder/'combined').exists():raise ValueError('Generation already complete; evaluate without new API')
        if not (folder/'package/authorization.json').exists():
            authorize(folder/'package', 'Human explicitly requested Codex to start the repaired 11-month B task independently in the current chat. '+
                'Same OpenRouter -> SiliconFlow FP8 DeepSeek V3.2 scope and synthetic-date change previously approved; '+
                'one main pass and one technical repair; retain the previously proposed restrictive $8 combined cap. No unlimited spend.')
        checked(folder,authorized=True)
        from ..news_label_trial import dotenv_values
        if not (os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL/'.env').get('OPENROUTER_API_KEY')):
            raise ValueError('OpenRouter credential unavailable')
        with (folder/'terminal_worker.log').open('a') as log:
            child=subprocess.Popen([sys.executable,'-u',str(ENTRY),'_worker','--run-dir',str(folder)],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        record=dict(pid=child.pid,started_at_utc=queue.now(),independent_of_codex=True,
                    protocol_sha256=m['protocol_sha256'],resumed=resume)
        atomic_json(folder/'launch.json',record)
        dump(folder/f'launch_{child.pid}.json',record)
    return record


def watch(folder,once=False):
    folder=Path(folder)
    while True:
        progress=read_json(folder/'progress.json') if (folder/'progress.json').exists() else {'stage':'starting'}
        stage=progress.get('stage','starting');attempts=progress.get('attempts',0)
        main=min(attempts,5632);repair=max(0,attempts-5632)
        print(datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S')+
            f" | {stage} | 主批已发 {main:,}/5,632 | 补跑已发 {repair} | 总回包 {progress.get('completed',0):,}"+
            f" | 原始可用 {progress.get('usable',0):,} | 在途 {progress.get('in_flight',0)}"+
            f" | 已报 ${progress.get('reported_cost_usd',0):.4f} | 已计及预留 ${progress.get('spent_or_reserved_usd',0):.4f}",flush=True)
        if (folder/'worker_receipt.json').exists():
            print(json.dumps(read_json(folder/'worker_receipt.json'),ensure_ascii=False,indent=2));return
        if once:return
        time.sleep(10)


def main(argv=None):
    parser=ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='cmd',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--assembly',type=Path,required=True);prep.add_argument('--run-dir',type=Path,required=True);prep.add_argument('--cap-usd',type=float,default=8.)
    for name in ('review','run','watch','_worker','_generate','_evaluate'):
        arg=sub.add_parser(name);arg.add_argument('--run-dir',type=Path,required=True)
        if name=='run':arg.add_argument('--confirm-scope-and-budget',action='store_true');arg.add_argument('--resume',action='store_true')
        if name=='watch':arg.add_argument('--once',action='store_true')
    args=parser.parse_args(argv)
    if args.cmd=='prepare':print(json.dumps(prepare(args.assembly,args.run_dir,args.cap_usd),ensure_ascii=False,indent=2))
    elif args.cmd=='review':
        p,_=checked(args.run_dir);print(json.dumps(dict(status='offline_verified',protocol=p),ensure_ascii=False,indent=2))
    elif args.cmd=='run':print(json.dumps(launch(args.run_dir,args.confirm_scope_and_budget,args.resume),ensure_ascii=False,indent=2))
    elif args.cmd=='watch':watch(args.run_dir,args.once)
    elif args.cmd=='_worker':worker(args.run_dir)
    elif args.cmd=='_generate':generate(args.run_dir)
    elif args.cmd=='_evaluate':
        from .recent_b_sampled_evaluation import evaluate
        evaluate(args.run_dir)

