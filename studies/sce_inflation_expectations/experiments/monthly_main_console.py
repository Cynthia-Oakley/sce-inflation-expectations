"""Human-operated terminal console over the existing immutable continuation.

Prepare/watch never call a model. Run requires the explicit confirmation flag;
it starts exactly one detached existing worker and displays its local progress.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from . import monthly_main_continuation as resume
from .frozen_batch import ROOT, OFFICIAL, read_json, dump, sha
from .monthly_main_background import atomic_json

ENTRY=ROOT/'scripts/run_sce_monthly_main_console.py'


def prepare(**kwargs):
    result=resume.prepare(**kwargs)
    package=Path(kwargs['out']).resolve()/'package'
    manifest=read_json(package/'manifest.json')
    for file in (Path(__file__),ENTRY):
        manifest['source_sha256'][str(file.relative_to(ROOT))]=sha(file)
    dump(package/'manifest.json',manifest)
    return dict(result,new_api_calls=0,requires_manual_run_confirmation=True)


def progress_line(progress):
    labels={'generation_or_initial_validation':'模拟中', 'micro_evaluation':'微观评价',
            'macro_readout':'总体评价', 'aggregate_readout_written':'结果已写入',
            'generation_stopped':'模拟已停止'}
    stamp=datetime.fromisoformat(progress['at_utc'])
    age=(datetime.now(timezone.utc)-stamp).total_seconds()
    stale=' | 注意：进度已超过60秒未更新' if age>60 else ''
    return (f"{stamp.astimezone().strftime('%H:%M:%S')} | {labels.get(progress['phase'],progress['phase'])}"
            f" | 累计 {progress['completed']:,}/{progress['planned_calls']:,}"
            f" | 本次 {progress.get('new_attempts',0):,}"
            f" | 可用 {progress['technically_usable']:,} | 失败 {progress['errors']}"
            f" | 在途 {progress['dispatched_without_local_result']}"
            f" | 已报 ${progress['api_reported_cost_usd']:.4f}"
            f" | 未知费用预留 ${progress['unknown_fee_reservation_usd']:.4f}{stale}")


def watch(folder, interval=10):
    folder=Path(folder).resolve()
    print('只读取本地进度，不调用API。Ctrl+C退出观察；已启动的模拟继续运行。',flush=True)
    try:
        while True:
            path=folder/'progress.json'
            print(progress_line(read_json(path)) if path.exists() else
                  datetime.now().strftime('%H:%M:%S')+' | 等待后台初始化和进度文件…',flush=True)
            receipt=folder/'worker_receipt.json'
            if receipt.exists():
                value=read_json(receipt)
                reason=value.get('receipt',{}).get('halt_reason')
                print('任务结束：'+value['status']+('；停止原因：'+reason if reason else ''),flush=True)
                return value
            time.sleep(interval)
    except KeyboardInterrupt:
        print('\n已退出观察；没有停止或重新启动模拟。',flush=True)
        return dict(status='observer_detached_worker_unchanged')


def run(folder, *, confirm_continuation=False):
    folder=Path(folder).resolve()
    if not confirm_continuation:raise ValueError('Manual --confirm-continuation flag required')
    config,protocol,_=resume.checked(folder,authorization=False)
    package=Path(config['paths']['package']);spec=read_json(package/'resume.json')
    if any(p.exists() for p in (folder/'launch_lock.json',folder/'worker_lock.json',package/'execution_registration.json')):
        raise ValueError('This run was already launched; use watch instead, never delete its locks')
    print(f"确认续跑：保留 {spec['prior_attempts']:,} 次，新增最多 {spec['new_requests']:,} 个未发送位置；"
          f"全批累计上限 ${protocol['budget_cap_usd']:.2f}，旧已计/预留 ${spec['prior_spent_or_reserved_usd']:.4f}。",flush=True)
    from ..news_label_trial import dotenv_values
    if not (os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL/'.env').get('OPENROUTER_API_KEY')):
        raise ValueError('OpenRouter credential unavailable; do not paste it into the terminal command')
    if not (package/'authorization.json').exists():
        resume.authorize(folder,'User manually invoked terminal run with --confirm-continuation; '
                         f"retain {spec['prior_attempts']} attempts, send only {spec['new_requests']} never-dispatched positions; "
                         f"original total cap ${protocol['budget_cap_usd']}, original model/provider/stop rules.")
    resume.checked(folder)
    with (folder/'launch_lock.json').open('x') as stream:
        json.dump(dict(at_utc=resume.now(),method='manual_terminal_console',automatic_restart=False),stream)
    with (folder/'terminal_worker.log').open('x') as log:
        child=subprocess.Popen([config['python'],'-u',str(resume.ENTRY),'_worker','--run-dir',str(folder)],
            cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
            start_new_session=True,close_fds=True)
    atomic_json(folder/'launch.json',dict(pid=child.pid,at_utc=resume.now(),method='manual_terminal_console',automatic_restart=False))
    print(f'后台PID {child.pid}；现在每10秒显示一次进度。',flush=True)
    return watch(folder)
