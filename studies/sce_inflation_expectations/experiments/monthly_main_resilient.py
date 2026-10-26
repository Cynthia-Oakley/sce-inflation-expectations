"""Bounded cooling/continuation over the unchanged one-attempt queue.

Each queue segment is immutable. A transient stop drains its calls, cools down,
then starts a fresh segment containing only never-dispatched keys. No request,
including a failed request, is retried. The original study protocol stays pinned;
an independently pinned execution addendum declares the transport changes.
"""
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from threading import Lock

from . import monthly_main_continuation as base
from .monthly_main_background import Progress, atomic_json, current_phase, status
from .monthly_main_console import progress_line
from .state_continuity_execution import execute, live_sender, load_inputs
from .frozen_batch import ROOT, OFFICIAL, read_json, dump, sha

ENTRY=ROOT/'scripts/run_sce_resilient_main.py'
POLICY=dict(version='bounded_never_dispatched_continuation_v1',initial_workers=32,max_workers=64,
    min_workers=8,scale_up_after_completed=256,healthy_segment_min_successes=128,
    healthy_segment_min_ratio=.95,recoverable_statuses=[408,429,500,502,503,504,520,521,522,523,524,529],
    cooldown_seconds=[30,60,120,240,300],max_unhealthy_recoveries=5,
    max_total_cooldown_seconds=1800,max_total_recoveries=50,
    retries_per_dispatched_position=0,provider_fallback=False,
    overrides='Transport stop/concurrency handling only; all original scientific inputs and total budget retained.')


def prepare(**kwargs):
    result=base.prepare(**kwargs)
    package=Path(kwargs['out']).resolve()/'package';supervisor=package.parent/'supervisor'
    dump(package/'execution_policy.json',POLICY)
    spec=read_json(package/'resume.json')
    spec['execution_policy_sha256']=sha(package/'execution_policy.json')
    spec['policy']='Retain every dispatched position; bounded cooling after recoverable transport stops; continue only never-dispatched positions.'
    dump(package/'resume.json',spec)
    manifest=read_json(package/'manifest.json')
    for f in (Path(__file__),ENTRY,Path(__file__).with_name('monthly_main_console.py'),
              package/'execution_policy.json',package/'resume.json'):
        manifest['source_sha256'][str(f.relative_to(ROOT))]=sha(f)
    dump(package/'manifest.json',manifest)
    config=read_json(supervisor/'config.json');config['resume_sha256']=sha(package/'resume.json')
    config['execution_policy_sha256']=spec['execution_policy_sha256']
    atomic_json(supervisor/'config.json',config)
    return dict(result,execution_policy=POLICY,new_api_calls=0)


def checked(folder,authorization=True):
    config,p,m=base.checked(folder,authorization=authorization)
    package=Path(config['paths']['package']);policy=read_json(package/'execution_policy.json')
    if sha(package/'execution_policy.json')!=config['execution_policy_sha256'] or policy!=POLICY:
        raise ValueError('Execution addendum changed')
    return config,p,m,policy


def recoverable(row,policy):
    if row.get('error') in ('APIConnectionError','APITimeoutError'):return True
    return row.get('error_http_status') in policy['recoverable_statuses']


def can_recover(receipt,rows,policy):
    # A provider/charge/auth/unknown failure anywhere in the drained segment wins.
    if any(r.get('fatal') and not recoverable(r,policy) for r in rows):return False
    reason=receipt.get('halt_reason')
    candidates=[r for r in rows if r.get('error')==reason]
    return bool(candidates) and all(recoverable(r,policy) for r in candidates)


def cooldown(seconds,path,details):
    end=time.monotonic()+seconds
    while True:
        remaining=max(0.,end-time.monotonic())
        atomic_json(path,dict(details,phase='network_cooldown',cooldown_remaining_s=remaining,
                             at_utc=base.now()))
        if remaining<=0:return
        time.sleep(min(5,remaining))


def safe_sender(send):
    """Retain only safe exception metadata; never exception bodies or headers."""
    lock=Lock()
    def wrapped(messages):
        try:return send(messages)
        except Exception as exc:
            # The queue itself records exception type/status and preserves the failure.
            # Capture numeric Retry-After on this thread via a lightweight exception attribute.
            response=getattr(exc,'response',None)
            header=getattr(response,'headers',{}).get('Retry-After') if response is not None else None
            delay=None
            if header:
                try:delay=max(0.,float(header))
                except (TypeError,ValueError):
                    try:delay=max(0.,(parsedate_to_datetime(header)-datetime.now(timezone.utc)).total_seconds())
                    except (TypeError,ValueError,OverflowError):pass
            # Unchanged queue intentionally omits arbitrary attributes, so a bounded
            # shared sender hint is supplied separately by the controller below.
            if delay is not None and math.isfinite(delay):
                with lock:wrapped.retry_after_s=max(wrapped.retry_after_s,delay)
            raise
    wrapped.retry_after_s=0.
    return wrapped


def execute_segments(p,nodes,inputs,old_rows,out,send,policy=POLICY,*,engineering_only=False,
                     cool=cooldown,emit=lambda value:None):
    out=Path(out)
    if out.exists():raise ValueError('Fresh resilient call directory required')
    out.mkdir();all_rows=list(old_rows);segments=[];started=time.monotonic()
    workers=policy['initial_workers'];unhealthy=0;recoveries=0;total_cooling=0.;global_stop=None
    sender=safe_sender(send)
    status_path=out/'scheduler_status.json'
    while len(all_rows)<p['planned_calls']:
        index=len(segments)+1;folder=out/f'segment_{index:04d}'
        execution=deepcopy(p)
        execution['concurrency_stages']=[dict(after_completed=0,workers=workers),
            dict(after_completed=policy['scale_up_after_completed'],workers=policy['max_workers'])]
        sender.retry_after_s=0.
        atomic_json(status_path,dict(phase='generation_or_initial_validation',segment=index,
            workers=workers,max_workers=policy['max_workers'],recovery_cycles=recoveries,
            total_cooldown_seconds=total_cooling,at_utc=base.now()))
        emit(f'开始段{index}：已保留{len(all_rows)}次，初始并发{workers}，最多{policy["max_workers"]}；失败不重发。')
        receipt=execute(execution,nodes,inputs,folder,sender,completed_calls=all_rows,
                        engineering_only=engineering_only,emit=emit)
        rows=base.lines(folder/'calls_private.jsonl');all_rows.extend(rows)
        dump(folder/'manifest.json',dict(files_sha256={n:sha(folder/n) for n in ('receipt.json',*base.LEDGERS)}))
        segments.append(dict(folder=folder.name,attempts=len(rows),receipt=receipt))
        # Strong guards remain effective even if the final attempted slot was fatal.
        hard_rows=[r for r in rows if r.get('fatal') and not recoverable(r,policy)]
        if hard_rows:
            global_stop=hard_rows[0]['error'];break
        if len(all_rows)==p['planned_calls']:break
        if not rows or not can_recover(receipt,rows,policy):
            global_stop=receipt.get('halt_reason') or 'Nonrecoverable or zero-progress segment';break
        successes=sum(not r.get('error') for r in rows)
        if successes>=policy['healthy_segment_min_successes'] and successes/len(rows)>=policy['healthy_segment_min_ratio']:
            unhealthy=0
        unhealthy+=1
        if unhealthy>policy['max_unhealthy_recoveries'] or recoveries>=policy['max_total_recoveries']:
            global_stop='Persistent transient failures exceeded bounded recovery cycles';break
        delay=max(policy['cooldown_seconds'][min(unhealthy-1,len(policy['cooldown_seconds'])-1)],sender.retry_after_s)
        if total_cooling+delay>policy['max_total_cooldown_seconds']:
            global_stop='Total cooldown time cap reached';break
        recoveries+=1;total_cooling+=delay
        workers=max(policy['min_workers'],receipt['peak_in_flight']//2)
        details=dict(segment=index,workers=workers,max_workers=policy['max_workers'],
            recovery_cycles=recoveries,unhealthy_recoveries=unhealthy,
            last_transient_error=receipt['halt_reason'],total_cooldown_seconds=total_cooling)
        emit(f'临时故障{receipt["halt_reason"]}：在途已收齐，冷却{delay:g}秒，随后以{workers}并发继续未发送位置。')
        cool(delay,status_path,details)
    # Each immutable segment is the immediate archive; flat ledgers are composed once.
    for name in base.LEDGERS:
        with (out/name).open('xb') as dst:
            for s in segments:
                with (out/s['folder']/name).open('rb') as src:shutil.copyfileobj(src,dst)
    if not segments:raise ValueError('No pending positions')
    last=segments[-1]['receipt'];new_count=len(all_rows)-len(old_rows)
    completed=len(all_rows)==p['planned_calls'] and global_stop is None
    result=dict(last,status='completed' if completed else 'stopped_no_retry',attempts=new_count,
        completed_calls=new_count,logical_positions=len(all_rows),halt_reason=global_stop,
        peak_in_flight=max(s['receipt']['peak_in_flight'] for s in segments),
        seconds=time.monotonic()-started,recovery_cycles=recoveries,
        total_cooldown_seconds=total_cooling,segments=len(segments),
        automatic_retries=0,automatic_never_dispatched_continuations=recoveries,
        actual_model_results=not engineering_only,existing_attempts_retained=len(old_rows),
        new_planned_calls=p['planned_calls']-len(old_rows))
    dump(out/'receipt.json',result);dump(out/'segments.json',segments)
    atomic_json(status_path,dict(phase='generation_complete' if completed else 'generation_stopped',
        recovery_cycles=recoveries,total_cooldown_seconds=total_cooling,
        halt_reason=global_stop,at_utc=base.now()))
    return result


def generate(folder):
    config,p,m,policy=checked(folder);paths=config['paths'];package=Path(paths['package'])
    if any(Path(paths[k]).exists() for k in ('calls','combined','evaluation','readout')):
        raise ValueError('Fresh outputs required')
    nodes=read_json(ROOT/p['preparation']/'state_dependencies_private.json')
    old=Path(paths['previous_calls']);rows=base.lines(old/'calls_private.jsonl')
    pending=base.audit_attempts(nodes,rows,base.lines(old/'dispatch_private.jsonl'),base.lines(old/'positions_private.jsonl'))
    if pending!=read_json(package/'pending_keys_private.json'):raise ValueError('Pending keys changed')
    inputs=load_inputs(ROOT/p['input_templates'],p['months']);send=live_sender(p)
    with (package/'execution_registration.json').open('x') as stream:
        json.dump(dict(started_at_utc=base.now(),execution_policy_sha256=config['execution_policy_sha256']),stream)
    receipt=execute_segments(p,nodes,inputs,rows,paths['calls'],send,policy,emit=lambda s:print(s,flush=True))
    receipt.update(protocol_sha256=m['protocol_sha256'],execution_policy_sha256=config['execution_policy_sha256'])
    calls=Path(paths['calls']);dump(calls/'receipt.json',receipt)
    dump(calls/'manifest.json',dict(protocol_sha256=m['protocol_sha256'],
        files_sha256={n:sha(calls/n) for n in ('receipt.json','segments.json',*base.LEDGERS)}))
    return base.merge(paths,receipt,m['protocol_sha256'])


def pipeline(folder):
    config,p,_,_=checked(folder);paths=config['paths'];folder=Path(folder)
    commands=[
        [config['python'],'-u',str(ENTRY),'_generate','--run-dir',str(folder)],
        [config['python'],'-u',str(ROOT/'scripts/evaluate_sce_monthly_reconstruction.py'),'evaluate',
         '--package',paths['package'],'--calls',paths['combined'],'--truth',paths['truth'],'--out',paths['evaluation']],
        [config['python'],'-u',str(ROOT/'scripts/readout_sce_monthly_main.py'),'--package',paths['package'],
         '--evaluation',paths['evaluation'],'--truth',paths['truth'],'--registry',paths['registry'],'--out',paths['readout']]]
    for i,command in enumerate(commands):
        with (folder/f'phase_{i+1}.log').open('x') as log:
            result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            answer=dict(status='resilient_phase_failed_no_restart',phase=i+1,exit_code=result.returncode)
            atomic_json(folder/'pipeline_receipt.json',answer);return answer
        if i==0:
            receipt=read_json(Path(paths['combined'])/'receipt.json')
            if receipt['status']!='completed' or receipt['attempts']!=p['planned_calls']:
                answer=dict(status='generation_stopped_no_evaluation',receipt=receipt)
                atomic_json(folder/'pipeline_receipt.json',answer);return answer
    answer=dict(status='generation_and_separate_process_evaluation_complete')
    atomic_json(folder/'pipeline_receipt.json',answer);return answer


def poll_segments(old,trackers,calls):
    total=deepcopy(old.poll())
    for folder in sorted(Path(calls).glob('segment_*')):
        if folder.is_dir():trackers.setdefault(folder.name,Progress(folder))
    for tracker in trackers.values():
        current=tracker.poll()
        for key,value in current.items():
            if key=='completed_by_month':
                for month,n in value.items():total[key][month]=total[key].get(month,0)+n
            else:total[key]+=value
    return total


def worker(folder):
    folder=Path(folder).resolve();config,p,_,_=checked(folder);paths=config['paths']
    if not (folder/'launch_lock.json').exists():raise ValueError('Use run')
    with (folder/'worker_lock.json').open('x') as stream:json.dump(dict(pid=os.getpid(),at_utc=base.now()),stream)
    wake=None
    try:
        if sys.platform=='darwin':wake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        old=Progress(paths['previous_calls']);trackers={};started=time.monotonic()
        initial=read_json(Path(paths['package'])/'resume.json')['prior_attempts']
        with (folder/'pipeline.log').open('x') as log:
            child=subprocess.Popen([config['python'],'-u',str(ENTRY),'_pipeline','--run-dir',str(folder)],
                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,close_fds=True)
            while True:
                code=child.poll()
                try:
                    progress=poll_segments(old,trackers,paths['calls'])
                    progress.update(at_utc=base.now(),worker_pid=os.getpid(),pipeline_pid=child.pid,
                        elapsed_seconds=time.monotonic()-started,planned_calls=p['planned_calls'],budget_cap_usd=p['budget_cap_usd'],
                        previous_attempts=initial,new_attempts=progress['completed']-initial,
                        never_dispatched=p['planned_calls']-progress['dispatched'],
                        phase=current_phase(dict(paths,calls=paths['combined'])))
                    scheduler=Path(paths['calls'])/'scheduler_status.json'
                    if scheduler.exists():
                        value=read_json(scheduler);progress['scheduler']=value
                        if value['phase']=='network_cooldown':progress['phase']='network_cooldown'
                    atomic_json(folder/'progress.json',progress)
                except Exception as exc:print('Progress read unavailable: '+type(exc).__name__,flush=True)
                if code is not None:break
                time.sleep(10)
        receipt=read_json(folder/'pipeline_receipt.json') if (folder/'pipeline_receipt.json').exists() else dict(status='no_pipeline_receipt')
        receipt.update(ended_at_utc=base.now(),exit_code=code,automatic_restarts=0,automatic_retries_added=0)
        atomic_json(folder/'worker_receipt.json',receipt);return receipt
    except Exception as exc:
        atomic_json(folder/'worker_receipt.json',dict(status='resilient_worker_failed_no_restart',error_type=type(exc).__name__,ended_at_utc=base.now()))
        raise
    finally:
        if wake is not None:wake.terminate();wake.wait()


def watch(folder):
    folder=Path(folder)
    print('每10秒读取本地进度；Ctrl+C只退出观察，后台任务继续。',flush=True)
    try:
        while True:
            path=folder/'progress.json'
            if path.exists():
                progress=read_json(path);view=dict(progress);scheduler=progress.get('scheduler',{})
                if progress['phase']=='network_cooldown':view['phase']='网络冷却中'
                line=progress_line(view)
                if progress['phase']=='network_cooldown':
                    line+=f" | 冷却剩余约{scheduler.get('cooldown_remaining_s',0):.0f}秒 | 恢复后并发{scheduler.get('workers')}"
                line+=f" | 已恢复{scheduler.get('recovery_cycles',0)}轮"
                print(line,flush=True)
            else:print(datetime.now().strftime('%H:%M:%S')+' | 等待初始化…',flush=True)
            if (folder/'worker_receipt.json').exists():
                value=read_json(folder/'worker_receipt.json')
                print('任务结束：'+value['status']+'；'+str(value.get('receipt',{}).get('halt_reason') or ''),flush=True)
                return value
            time.sleep(10)
    except KeyboardInterrupt:
        print('\n已退出观察，后台继续。',flush=True);return dict(status='observer_detached')


def run(folder,confirm_continuation=False):
    folder=Path(folder).resolve()
    if not confirm_continuation:raise ValueError('Explicit --confirm-continuation required')
    config,p,_,policy=checked(folder,authorization=False);package=Path(config['paths']['package'])
    if any(f.exists() for f in (folder/'launch_lock.json',folder/'worker_lock.json',package/'execution_registration.json')):
        raise ValueError('Already launched; use watch, never remove locks')
    spec=read_json(package/'resume.json')
    print(f"保留{spec['prior_attempts']}次，仅新增{spec['new_requests']}次；全批累计上限${p['budget_cap_usd']}。",flush=True)
    print('临时错误自动冷却，失败不重发；32起步、最多64、恢复降至最低8；持续5轮无法恢复或累计冷却30分钟则停止。',flush=True)
    from ..news_label_trial import dotenv_values
    if not(os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL/'.env').get('OPENROUTER_API_KEY')):raise ValueError('Credential unavailable')
    if not(package/'authorization.json').exists():
        base.authorize(folder,'User manually confirmed bounded resilient continuation via --confirm-continuation. '
            f"Retain {spec['prior_attempts']}, at most {spec['new_requests']} new never-dispatched positions; same ${p['budget_cap_usd']} total cap, "
            'same model/provider/inputs; approve pinned execution_policy.json cooling/concurrency addendum; no retry of dispatched slots.')
    checked(folder)
    with (folder/'launch_lock.json').open('x') as stream:json.dump(dict(at_utc=base.now(),automatic_restart=False),stream)
    with (folder/'terminal_worker.log').open('x') as log:
        child=subprocess.Popen([config['python'],'-u',str(ENTRY),'_worker','--run-dir',str(folder)],
            cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
    atomic_json(folder/'launch.json',dict(pid=child.pid,method='manual_terminal_resilient_console',at_utc=base.now()))
    return watch(folder)
