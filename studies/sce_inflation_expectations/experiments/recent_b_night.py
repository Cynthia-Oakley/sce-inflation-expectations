"""One local overnight run: bounded cooling, one technical repair, separate evaluation.

Reuses the frozen one-attempt queue, robust segment scheduler and field overlay.
Only an explicit user launch can record authorization and instantiate a sender.
"""
from copy import deepcopy
from datetime import datetime,timezone
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from zoneinfo import ZoneInfo

from .frozen_batch import ROOT,OFFICIAL,read_json,dump,sha
from .state_continuity_execution import verify,authorize,load_inputs,live_sender,reserve
from . import monthly_main_resilient as robust
from .monthly_main_repair import overlay
from .monthly_main_background import atomic_json,Progress

ENTRY=ROOT/'scripts/run_sce_recent_b.py'
LEDGERS=robust.base.LEDGERS
NOW=lambda:datetime.now(timezone.utc).isoformat()


def lines(path):
    return robust.base.lines(path)


def technical_fields(row):
    if row.get('error'):
        if not robust.recoverable(row,robust.POLICY):raise ValueError('Hard failures cannot be automatically retried')
        return ['q8','q9']
    if row.get('finish_reason')!='stop':return ['q8','q9']
    return [k for k,v in row['state_after']['transition']['field_updated_from_model'].items() if not v]


def gate_result(rows):
    returned=[r for r in rows if r.get('error') is None and r.get('finish_reason')=='stop']
    usable=sum(r['technical_usable'] for r in returned)
    return {'attempted':len(rows),'normal_returns':len(returned),'format_usable':usable,
            'passed':bool(rows) and len(returned)>=min(16,len(rows)) and usable/len(returned)>=.95}


def preparation_sources(summary):
    result={k:summary.get(k,default) for k,default in (
        ('population_preflight','outputs/sce_recent_b_preflight_20261024_v1'),
        ('prior_source','outputs/sce_recent_b_priors_20261024_v2'))}
    for value in result.values():
        path=(ROOT/value).resolve()
        if not path.is_relative_to(ROOT/'outputs'):
            raise ValueError('Preparation must reference an ignored project output directory')
    prior=read_json(ROOT/result['prior_source']/'summary.json')
    if prior.get('population_preflight',result['population_preflight'])!=result['population_preflight']:
        raise ValueError('Prior and population preparation sources differ')
    return result


def freeze(assembly,out,cap_usd):
    assembly,out=Path(assembly).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs') or not 0<cap_usd<=20:raise ValueError('Fresh ignored run directory and proposed cap in (0,20] required')
    s=read_json(assembly/'summary.json');c=read_json(assembly/'core_engineering/summary.json')
    preparations=preparation_sources(s)
    nodes=read_json(assembly/'inputs/state_dependencies_private.json')
    if c['official_engine_units']!=11 or c['decisions']!=len(nodes) or len(nodes)!=5632:raise ValueError('Full official B Core checks required')
    if any(n['dependency'] is not None for n in nodes):raise ValueError('Only independent-month B supported')
    out.mkdir();package=out/'package';package.mkdir()
    p={'mechanism':('recent_B_independent_assumed_release_lag_synthetic_prior_v2' if s.get('micro_availability_basis','archived_public_snapshot')!='archived_public_snapshot' else 'recent_B_independent_public_snapshot_synthetic_prior_v1'),
       'research_line':s['research_line'],'strict_B_eligible':False,
       'months':[r['month'] for r in s['coverage']],'arms':['recent_b'],'generation_repeats':[1],'n_per_month':512,
       'planned_calls':len(nodes),'logical_positions':len(nodes),'maximum_automatic_repair_calls':len(nodes),'maximum_physical_api_attempts':2*len(nodes),
       'destination':'https://openrouter.ai/api/v1','model':'deepseek/deepseek-v3.2','route':'siliconflow/fp8','expected_provider':'SiliconFlow',
       'temperature':.5,'thinking':'disabled','response_format':'json_object','max_tokens':1024,'timeout_s':120,'retry_max':0,'provider_fallback':False,
       'price_input_per_mtok':.259,'price_output_per_mtok':.8,'budget_cap_usd':float(cap_usd),'budget_mode':'spent_plus_inflight_reservation',
       'max_prompt_chars':s['runtime_character_cap'],'max_prompt_bytes':s['runtime_utf8_byte_cap'],
       'technical_gate':{'calls':32,'minimum_usable':0},
       'external_technical_gate':'First 32: >=16 normal responses and >=95% field-format usability among normal stop responses; transport failures excluded from format denominator.',
       'concurrency_stages':[{'after_completed':0,'workers':32},{'after_completed':256,'workers':64}],
       'request_extra_body':{'provider':{'order':['siliconflow/fp8'],'allow_fallbacks':False,'require_parameters':True,'max_price':{'prompt':.259,'completion':.8}},'reasoning':{'enabled':False}},
       'provider_metadata':'data/raw/mcp_checks/2026-10-21_v32_fullperiod_free_v1/deepseek_v32_endpoints.json',
       'input_templates':str((assembly/'prompts').relative_to(ROOT)),'preparation':str((assembly/'inputs').relative_to(ROOT)),
       **preparations,
       'micro_availability_basis':s.get('micro_availability_basis','archived_public_snapshot'),
       'population_source_waves':{r['month']:r.get('population_source_wave','202408') for r in s['coverage']},
       'q9_postprocessing':'proportional_nonnegative_v1','field_fallback':'Retain the declared synthetic prior independently for a failed Q8/Q9 field; never substitute a person.',
       'repair_selection':'Transport/format/non-stop failures only; no truth, error magnitude or density-fit-based re-query.',
       'repair_merge':'Keep successful original fields; accept valid repaired fields only. Original raw responses remain separate.',
       'model_knowledge_cutoff_verified':False,'text_original_vintages_verified':False,'new_api_calls':0,
       'frozen_combination_simulation_share':0.,'combination_training_period':['2019-01','2022-12'],
       'created_at_utc':NOW(),'estimated_main_cost_usd':s['estimated_cost_usd']}
    p['full_main_byte_reservation_usd']=len(nodes)*reserve(p,p['max_prompt_bytes'])
    policy=deepcopy(robust.POLICY)
    dump(package/'execution_policy.json',policy);dump(package/'protocol.json',p)
    source_files=[Path(__file__),ENTRY,Path(robust.__file__),Path(__file__).with_name('state_continuity_execution.py'),
                  ROOT/'studies/sce_inflation_expectations/state_continuity_runtime.py',
                  ROOT/'studies/sce_inflation_expectations/model.py',ROOT/'studies/sce_inflation_expectations/model_counterfactual.py',
                  ROOT/'studies/sce_inflation_expectations/q9_normalization.py',
                  ROOT/'studies/sce_inflation_expectations/scoring/sce_q9.py',ROOT/'studies/sce_inflation_expectations/scoring/sce_q9_frozen.py',
                  ROOT/'studies/sce_inflation_expectations/scoring/beta_fit_kernel.py',Path(__file__).with_name('monthly_main_repair.py'),
                  Path(__file__).with_name('recent_b_evaluation.py'),ROOT/p['provider_metadata'],package/'execution_policy.json',
                  assembly/'inputs/state_dependencies_private.json',assembly/'core_engineering/summary.json']
    source_files+=list((assembly/'prompts').rglob('*.json'))
    pop_folder=ROOT/p['population_preflight'];prior_folder=ROOT/p['prior_source']
    for name in ('summary.json','monthly_input_plan.json','selected_proxy_population_private.json'):
        source_files.append(pop_folder/name)
    source_files.append(prior_folder/'summary.json')
    for name in ('recent_b_rolling_preflight.py','recent_b_preflight.py','recent_b_priors.py'):
        source_files.append(Path(__file__).with_name(name))
    for name in ('frozen_batch.py','monthly_main_background.py','monthly_main_continuation.py','state_continuity_inputs.py','recent_b_prompts.py'):
        source_files.append(Path(__file__).with_name(name))
    for name in ('information_update_runtime.py','prior_belief_preparation.py','prior_belief_experiment.py','evaluation/metrics.py','evaluation/cognition.py'):
        source_files.append(ROOT/'studies/sce_inflation_expectations'/name)
    hashes={str(f.relative_to(ROOT)):sha(f) for f in source_files}
    dump(package/'manifest.json',{'protocol_sha256':sha(package/'protocol.json'),'source_sha256':hashes,'new_api_calls':0,'truth_in_execution_inputs':False})
    for f in source_files:
        if f.suffix=='.py':
            dest=package/'source_snapshot'/f.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
    dump(out/'config.json',{'python':sys.executable,'package':str(package),'run_dir':str(out),'new_api_calls':0,
                          'protocol_sha256':sha(package/'protocol.json'),'controller_sha256':sha(Path(__file__)),'entry_sha256':sha(ENTRY)})
    return p


def checked(folder,*,authorized=False):
    folder=Path(folder).resolve();config=read_json(folder/'config.json');p,m=verify(config['package'])
    if sha(Path(__file__))!=config['controller_sha256'] or sha(ENTRY)!=config['entry_sha256']:raise ValueError('Prepared controller changed')
    if authorized:
        a=read_json(Path(config['package'])/'authorization.json')
        if not a.get('approved') or a['protocol_sha256']!=m['protocol_sha256']:raise ValueError('This exact batch requires authorization')
        for k in ('planned_calls','budget_cap_usd','destination','model','route'):
            if a.get(k)!=p[k]:raise ValueError('Authorization scope differs')
    return config,p,m


def phase(folder,name,**extra):
    atomic_json(Path(folder)/'phase.json',{'phase':name,'at_utc':NOW(),**extra})


def combine_ledgers(folders,out):
    out=Path(out);out.mkdir()
    for name in LEDGERS:
        with (out/name).open('xb') as dst:
            for f in folders:
                with (Path(f)/name).open('rb') as src:shutil.copyfileobj(src,dst)


def execute_main(p,nodes,inputs,out,send,policy,*,engineering_only=False,cool=robust.cooldown):
    """Small true format check, followed by the existing recoverable queue."""
    out=Path(out);out.mkdir()
    first_month=p['months'][0]
    boot=sorted([n for n in nodes if n['month']==first_month],key=lambda n:hashlib.sha256(n['logical_reuse_key'].encode()).digest())[:min(32,len(nodes))]
    bp=deepcopy(p);bp.update(months=[first_month],planned_calls=len(boot),technical_gate={'calls':len(boot),'minimum_usable':0})
    boot_policy={**policy,'initial_workers':8,'max_workers':8,'min_workers':2}
    r=robust.execute_segments(bp,boot,inputs,[],out/'gate',send,boot_policy,engineering_only=engineering_only,cool=cool)
    rows=lines(out/'gate/calls_private.jsonl')
    quality=gate_result(rows);dump(out/'technical_gate.json',quality)
    if r['status']!='completed' or not quality['passed']:
        return {'status':'stopped_before_main','receipt':r,'technical_gate':quality},rows
    if len(nodes)==len(boot):
        combine_ledgers([out/'gate'],out/'complete');dump(out/'complete/receipt.json',r)
        return {'status':'completed','receipt':r,'combined':str(out/'complete')},rows
    rr=robust.execute_segments(p,nodes,inputs,rows,out/'rest',send,policy,engineering_only=engineering_only,cool=cool)
    rest=lines(out/'rest/calls_private.jsonl');all_rows=rows+rest
    combine_ledgers([out/'gate',out/'rest'],out/'complete')
    dump(out/'complete/receipt.json',rr)
    return {'status':rr['status'],'receipt':rr,'combined':str(out/'complete')},all_rows


def execute_repair(p,nodes,inputs,main_rows,out,send,policy,main_receipt,*,engineering_only=False,cool=robust.cooldown):
    """At most one further exact-input request for each technically failed slot."""
    targets={r['reuse_key']:{'reuse_key':r['reuse_key'],'fields':technical_fields(r)} for r in main_rows if technical_fields(r)}
    remaining=p['budget_cap_usd']-main_receipt['spent_or_reserved_usd']
    if not targets or remaining<=0:
        return {'status':'not_needed' if not targets else 'skipped_budget','attempts':0,'reported_cost_usd':0.,'spent_or_reserved_usd':0.},[],targets
    rp=deepcopy(p);rp.update(planned_calls=len(targets),budget_cap_usd=remaining,technical_gate={'calls':1,'minimum_usable':0})
    subset=[n for n in nodes if n['logical_reuse_key'] in targets]
    repair_policy={**policy,'initial_workers':16,'max_workers':32,'min_workers':4,'scale_up_after_completed':32,
                   'max_total_recoveries':10,'max_total_cooldown_seconds':600,'max_unhealthy_recoveries':3}
    receipt=robust.execute_segments(rp,subset,inputs,[],out,send,repair_policy,engineering_only=engineering_only,cool=cool)
    return receipt,lines(Path(out)/'calls_private.jsonl'),targets


def merge_fields(main_rows,repair_rows,targets):
    repairs={r['reuse_key']:r for r in repair_rows}
    if len(repairs)!=len(repair_rows) or not set(repairs)<=set(targets):raise ValueError('Repair duplicates or scope mismatch')
    result=[]
    for row in main_rows:
        r=deepcopy(row);key=row['reuse_key']
        r['response_error']=row.get('error')
        if key in repairs:
            if repairs[key]['prompt_sha256']!=row['prompt_sha256']:raise ValueError('Repair prompt changed')
            r=overlay(r,repairs[key],targets[key])
        r['technical_usable']=all(r['state_after']['transition']['field_updated_from_model'].values())
        r['view_type']='explicit_field_overlay_raw_responses_in_separate_ledgers'
        result.append(r)
    return result


def generate(folder):
    folder=Path(folder);config,p,m=checked(folder,authorized=True)
    with (folder/'generation_lock.json').open('x') as f:json.dump({'started_at_utc':NOW()},f)
    nodes=read_json(ROOT/p['preparation']/'state_dependencies_private.json');inputs=load_inputs(ROOT/p['input_templates'],p['months'])
    policy=read_json(Path(config['package'])/'execution_policy.json');send=live_sender(p)
    phase(folder,'main');result,rows=execute_main(p,nodes,inputs,folder/'main_stages',send,policy)
    if result['status']!='completed' or len(rows)!=p['planned_calls']:
        dump(folder/'generation_receipt.json',{'status':'main_stopped_no_repair_or_evaluation','main':result,'new_api_calls':len(rows)})
        return
    phase(folder,'automatic_repair');repair,replies,targets=execute_repair(p,nodes,inputs,rows,folder/'repair_stages',send,policy,result['receipt'])
    view=merge_fields(rows,replies,targets);dest=folder/'combined';dest.mkdir()
    with (dest/'positions_private.jsonl').open('x') as f:
        for row in view:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
    spent=result['receipt']['spent_or_reserved_usd']+repair['spent_or_reserved_usd']
    if spent>p['budget_cap_usd']+1e-9:raise ValueError('Cumulative main/repair cap exceeded')
    receipt={'status':'generation_and_one_repair_complete','main_logical_positions':len(rows),
             'main_api_attempts':len(rows),'automatic_repair_api_attempts':len(replies),'physical_api_attempts':len(rows)+len(replies),
             'maximum_extra_attempts_per_failed_position':1,'repair_status':repair['status'],
             'technical_complete':sum(r['technical_usable'] for r in view),
             'remaining_q8':sum(not r['state_after']['transition']['field_updated_from_model']['q8'] for r in view),
             'remaining_q9':sum(not r['state_after']['transition']['field_updated_from_model']['q9'] for r in view),
             'reported_cost_usd':result['receipt']['reported_cost_usd']+repair['reported_cost_usd'],
             'spent_or_reserved_usd':spent,'budget_cap_usd':p['budget_cap_usd'],'provider_fallbacks':0,'sdk_automatic_retries':0,
             'protocol_sha256':m['protocol_sha256'],'truth_read':False,'ended_at_utc':NOW()}
    dump(dest/'receipt.json',receipt);dump(dest/'manifest.json',{'files_sha256':{f.name:sha(f) for f in dest.iterdir() if f.is_file()}})
    dump(folder/'generation_receipt.json',receipt)


def progress_snapshot(folder,p,trackers=None):
    folder=Path(folder);phase_name=read_json(folder/'phase.json')['phase'] if (folder/'phase.json').exists() else 'starting'
    paths=list((folder/'main_stages').glob('*/segment_*/calls_private.jsonl'))+list((folder/'repair_stages').glob('segment_*/calls_private.jsonl'))
    trackers={} if trackers is None else trackers
    # Reuse incremental complete-line readers. Do not reread all large raw
    # prompts/responses on every heartbeat, or count composed ledgers twice.
    for path in paths:trackers.setdefault(str(path.parent),Progress(path.parent))
    snapshots={key:value.poll() for key,value in trackers.items()}
    completed=sum(r['completed'] for r in snapshots.values());intended=sum(r['dispatched'] for r in snapshots.values())
    usable=sum(r['technically_usable'] for r in snapshots.values())
    reported=sum(r['api_reported_cost_usd'] for r in snapshots.values())
    unknown=sum(r['unknown_fee_reservation_usd'] for r in snapshots.values())
    main_done=sum(r['completed'] for key,r in snapshots.items() if str(folder/'main_stages') in key)
    schedulers=list(folder.glob('main_stages/*/scheduler_status.json'))+list(folder.glob('repair_stages/scheduler_status.json'))
    current=max(schedulers,key=lambda f:f.stat().st_mtime) if schedulers else None
    scheduler=read_json(current) if current else {}
    return {'phase':phase_name,'main_completed':main_done,'planned_calls':p['planned_calls'],'physical_completed':completed,
            'repair_completed':completed-main_done,'technical_usable_raw':usable,
            'technical_failed_raw':completed-usable,'in_flight':intended-completed,
            'reported_cost_usd':reported,'unknown_fee_reservation_usd':unknown,'scheduler':scheduler,'at_utc':NOW()}


def worker(folder):
    folder=Path(folder);config,p,_=checked(folder,authorized=True);wake=None;trackers={}
    with (folder/'worker_lock.json').open('x') as f:json.dump({'pid':os.getpid(),'started_at_utc':NOW()},f)
    if sys.platform=='darwin':wake=subprocess.Popen(['/usr/bin/caffeinate','-is','-w',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for command,stage in [('_generate','generation'),('_evaluate','evaluation')]:
            if stage=='evaluation':
                r=read_json(folder/'generation_receipt.json')
                if r['status']!='generation_and_one_repair_complete':break
                phase(folder,'evaluation')
            with (folder/f'{stage}.log').open('x') as log:
                child=subprocess.Popen([config['python'],'-u',str(ENTRY),command,'--run-dir',str(folder)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                while child.poll() is None:
                    try:atomic_json(folder/'progress.json',progress_snapshot(folder,p,trackers))
                    except (OSError,ValueError,json.JSONDecodeError):pass
                    time.sleep(5)
            if child.returncode:
                dump(folder/'worker_receipt.json',{'status':stage+'_process_failed_data_preserved','exit_code':child.returncode,'ended_at_utc':NOW()});return
        gen=read_json(folder/'generation_receipt.json')
        status='generation_repair_and_national_evaluation_complete' if (folder/'evaluation/summary.json').exists() else gen['status']
        if status=='generation_repair_and_national_evaluation_complete' and (gen['remaining_q8'] or gen['remaining_q9']):
            status='generation_and_evaluation_complete_with_remaining_technical_fields'
        atomic_json(folder/'progress.json',progress_snapshot(folder,p,trackers));dump(folder/'worker_receipt.json',{'status':status,'generation_receipt':gen,'ended_at_utc':NOW()})
    except Exception as exc:
        dump(folder/'worker_receipt.json',{'status':'worker_failed_data_preserved','error_type':type(exc).__name__,'ended_at_utc':NOW()});raise
    finally:
        if wake is not None:wake.terminate();wake.wait()


def watch(folder):
    folder=Path(folder)
    print('每10秒显示进度；Ctrl+C只退出观察，独立后台任务继续。',flush=True)
    try:
        while True:
            f=folder/'progress.json'
            if f.exists():
                s=read_json(f);scheduler=s.get('scheduler',{});cool=' | 网络等待约%.0f秒'%scheduler.get('cooldown_remaining_s',0) if scheduler.get('phase')=='network_cooldown' else ''
                print(datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S')+f" | {s['phase']} | 主批 {s['main_completed']:,}/{s['planned_calls']:,} | 补跑 {s['repair_completed']} | 原始技术失败 {s['technical_failed_raw']} | 在途 {s['in_flight']} | 已报 ${s['reported_cost_usd']:.4f} | 未知费预留 ${s['unknown_fee_reservation_usd']:.4f}"+cool,flush=True)
            else:print('等待后台初始化…',flush=True)
            if (folder/'worker_receipt.json').exists():
                result=read_json(folder/'worker_receipt.json');print(json.dumps(result,ensure_ascii=False,indent=2),flush=True);return result
            if (folder/'launch.json').exists():
                try:os.kill(read_json(folder/'launch.json')['pid'],0)
                except ProcessLookupError:
                    print('后台进程已退出但未写完成收据；原始记录保留，请查看terminal_worker.log。没有自动重发未知请求。',flush=True)
                    return {'status':'worker_not_alive_receipt_missing'}
            time.sleep(10)
    except KeyboardInterrupt:print('\n观察已退出，后台继续。',flush=True)


def run(folder,confirm=False):
    folder=Path(folder).resolve();config,p,m=checked(folder)
    if (folder/'superseded_by.json').exists():raise ValueError('This package is superseded; use the newer run directory')
    if (folder/'launch.json').exists():return watch(folder)
    if not confirm:raise ValueError('Run requires --confirm-scope-and-budget after reviewing this batch')
    from ..news_label_trial import dotenv_values
    if not (os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL/'.env').get('OPENROUTER_API_KEY')):raise ValueError('OpenRouter credential unavailable')
    print(f"主批{p['planned_calls']}次；技术失败最多自动补一轮、总物理尝试不超过{p['maximum_physical_api_attempts']}；主批+补跑合计上限${p['budget_cap_usd']:.2f}。",flush=True)
    if not(Path(config['package'])/'authorization.json').exists():
        authorize(config['package'],'User confirmed exact recent-B proxy P/synthetic prior/public E scope, fixed OpenRouter -> SiliconFlow FP8 V3.2, one main pass plus at most one technical repair per failed slot, bounded cooling and combined budget via --confirm-scope-and-budget.')
    checked(folder,authorized=True)
    with (folder/'launch_lock.json').open('x') as f:json.dump({'at_utc':NOW()},f)
    with (folder/'terminal_worker.log').open('x') as log:
        child=subprocess.Popen([config['python'],'-u',str(ENTRY),'_worker','--run-dir',str(folder)],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
    atomic_json(folder/'launch.json',{'pid':child.pid,'started_at_utc':NOW(),'independent_of_codex':True})
    return watch(folder)


def review(folder):
    """Read-only review: no credentials, authorization record, sender, or worker."""
    folder=Path(folder).resolve();config,p,m=checked(folder)
    result={'status':'offline_verified_not_started','run_dir':str(folder),
            'months':p['months'],'n_per_month':p['n_per_month'],'main_requests':p['planned_calls'],
            'maximum_physical_attempts':p['maximum_physical_api_attempts'],
            'model':p['model'],'route':p['route'],'temperature':p['temperature'],
            'budget_cap_usd':p['budget_cap_usd'],'estimated_main_cost_usd':p['estimated_main_cost_usd'],
            'population_source_waves':p['population_source_waves'],
            'micro_availability_basis':p['micro_availability_basis'],'strict_B_eligible':False,
            'authorization_exists':(Path(config['package'])/'authorization.json').exists(),
            'launch_exists':(folder/'launch.json').exists(),'new_api_calls':0}
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    f=sub.add_parser('freeze');f.add_argument('--assembly',type=Path,required=True);f.add_argument('--run-dir',type=Path,required=True);f.add_argument('--cap-usd',type=float,required=True)
    for name in ('review','run','watch','_worker','_generate','_evaluate'):
        x=sub.add_parser(name);x.add_argument('--run-dir',type=Path,required=True)
        if name=='run':x.add_argument('--confirm-scope-and-budget',action='store_true')
    a=p.parse_args(argv)
    if a.cmd=='freeze':print(json.dumps(freeze(a.assembly,a.run_dir,a.cap_usd),ensure_ascii=False,indent=2))
    elif a.cmd=='review':review(a.run_dir)
    elif a.cmd=='run':run(a.run_dir,a.confirm_scope_and_budget)
    elif a.cmd=='watch':watch(a.run_dir)
    elif a.cmd=='_worker':worker(a.run_dir)
    elif a.cmd=='_generate':generate(a.run_dir)
    elif a.cmd=='_evaluate':
        from .recent_b_evaluation import evaluate
        evaluate(a.run_dir)
