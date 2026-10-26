"""Independent Terminal controller for Kimi's frozen media V3 messages.

Preparation/review/watch are offline. Paid sending requires a deliberate human
Terminal invocation with the exact scope/budget flag; no automatic repair pass.
"""
import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .frozen_batch import ROOT, OFFICIAL, dump, read_json, sha, verify
from .monthly_main_background import atomic_json
from .monthly_main_resilient import POLICY
from .state_continuity_execution import live_sender, reserve
from . import frozen_message_queue as queue
from ..prior_belief_experiment import message_hash

ENTRY = ROOT/'scripts/run_sce_media_mechanism_terminal.py'
METADATA = ROOT/'data/raw/mcp_checks/2026-10-21_v32_fullperiod_free_v1/deepseek_v32_endpoints.json'


def slots_for(package, manifest, protocol):
    slots = []
    for job in manifest['jobs']:
        relative = f"{job['month']}/prompts_{job['arm']}.json"
        bundle = read_json(package/relative)
        for aid, row in sorted(bundle['rows'].items()):
            if message_hash(row['messages']) != row['prompt_sha256']:
                raise ValueError('Original prompt digest mismatch')
            size = len(json.dumps(row['messages'], ensure_ascii=False).encode())
            slots.append(dict(key=f"{job['month']}|{job['arm']}|{job['repeat']}|{aid}",
                month=job['month'], arm=job['arm'], repeat=job['repeat'], agent_id=aid,
                prompt_file=relative, prompt_sha256=row['prompt_sha256'], messages=row['messages'],
                reserved_usd=reserve(protocol, size)))
    # Interleave arms and repeats for the technical sample; never select by truth.
    import hashlib
    slots.sort(key=lambda s: hashlib.sha256(('media_v3_transport|'+s['key']).encode()).digest())
    if len(slots) != protocol['planned_calls'] or len({s['key'] for s in slots}) != len(slots):
        raise ValueError('Frozen request count mismatch')
    return slots


def prepare(package, out):
    package, out = Path(package).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh project output directory required')
    manifest, p = verify(package)
    if p['mechanism'] != 'v32_news_mechanism_v3':
        raise ValueError('Only registered media V3 supported')
    # Refuse parallel ownership by the old job-level live entry.
    for job in manifest['jobs']:
        if (ROOT/'outputs/local_runs'/job['run_id']).exists():
            raise ValueError('Existing live job must be reconciled before this adapter')
    checks = read_json(package/'engineering_checks.json')
    if len(checks) != len(manifest['jobs']):
        raise ValueError('Every official Core offline unit required')
    for i, job in enumerate(manifest['jobs']):
        check = next(c for c in checks if c['job_index'] == i)
        receipt = read_json(ROOT/'outputs/local_runs'/(job['run_id']+'-engineering')/'run_manifest.json')
        if (check['exit_code'] or check['run_id'] != job['run_id'] or receipt['status'] != 'completed'
            or receipt['llm_kind'] != 'scripted' or receipt['cost']['call_count'] != 0
            or not receipt['actual_input_hashes_match'] or receipt['protocol_sha256'] != manifest['protocol_sha256']):
            raise ValueError('Invalid official Core acceptance')
    protocol = dict(p, provider_metadata=str(METADATA.relative_to(ROOT)), timeout_s=120,
                    budget_mode='spent_plus_inflight_reservation')
    slots = slots_for(package, manifest, protocol)
    out.mkdir(parents=True, mode=0o700)
    policy = deepcopy(POLICY)
    dump(out/'execution_policy.json', policy)
    dump(out/'slot_index_private.json', [{k:v for k,v in s.items() if k != 'messages'} for s in slots])
    # Pin input/scientific source files without modifying the original package.
    pins = {str((package/k).relative_to(ROOT)): v for k,v in manifest['prepared_file_sha256'].items()}
    pins.update(manifest['source_sha256'])
    for path in [package/'protocol.json', package/'manifest.json', package/'engineering_checks.json',
                 METADATA, ENTRY, Path(__file__), Path(queue.__file__),
                 ROOT/'studies/sce_inflation_expectations/experiments/monthly_main_resilient.py',
                 ROOT/'studies/sce_inflation_expectations/experiments/state_continuity_execution.py',
                 ROOT/'studies/sce_inflation_expectations/experiments/monthly_main_background.py',
                 ROOT/'studies/sce_inflation_expectations/experiments/frozen_batch.py',
                 ROOT/'studies/sce_inflation_expectations/model.py',
                 ROOT/'studies/sce_inflation_expectations/model_counterfactual.py',
                 ROOT/'studies/sce_inflation_expectations/prior_belief_experiment.py',
                 ROOT/'studies/sce_inflation_expectations/q9_normalization.py',
                 ROOT/'studies/sce_inflation_expectations/evaluation/media_mechanism_terminal.py',
                 ROOT/'studies/sce_inflation_expectations/evaluation/metrics.py',
                 ROOT/'studies/sce_inflation_expectations/evaluation/cognition.py',
                 ROOT/'studies/sce_inflation_expectations/scoring/sce_q9.py',
                 ROOT/'studies/sce_inflation_expectations/scoring/sce_q9_frozen.py',
                 ROOT/'studies/sce_inflation_expectations/scoring/beta_fit_kernel.py',
                 out/'execution_policy.json', out/'slot_index_private.json']:
        pins[str(path.relative_to(ROOT))] = sha(path)
    dump(out/'config.json', dict(package=str(package), run_dir=str(out), python=sys.executable,
        original_protocol_sha256=manifest['protocol_sha256'], original_manifest_sha256=sha(package/'manifest.json'),
        prepared_at_utc=queue.now(), planned_calls=p['planned_calls'], budget_cap_usd=p['budget_cap_usd'],
        destination=p['destination'], model=p['model'], route=p['route'], estimated_cost_usd=manifest['estimated_cost_all_slots_usd'],
        maximum_physical_attempts=p['planned_calls'], automatic_retries=0, provider_fallbacks=0,
        transport_addendum='Per-request durable intent, bounded cooldown, manual resume never-dispatched only; no prompt changes or automatic failed-slot retries.',
        source_sha256=pins, truth_in_generation=False, new_api_calls=0))
    for name in ('frozen_message_queue.py', 'media_mechanism_terminal.py'):
        shutil.copyfile(Path(__file__).with_name(name), out/name)
    return review(out)


def checked(folder, authorized=False):
    folder = Path(folder).resolve()
    c = read_json(folder/'config.json')
    for relative, digest in c['source_sha256'].items():
        path = (ROOT/relative).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError('Frozen source/input changed: '+relative)
    package = Path(c['package'])
    p = read_json(package/'protocol.json')
    if sha(package/'protocol.json') != c['original_protocol_sha256']:
        raise ValueError('Original protocol changed')
    p = dict(p, timeout_s=120, provider_metadata=str(METADATA.relative_to(ROOT)),
             budget_mode='spent_plus_inflight_reservation')
    if authorized:
        a = read_json(folder/'authorization.json')
        if (not a.get('approved') or a['config_sha256'] != sha(folder/'config.json')
            or a['user_confirmation'] != '--confirm-scope-and-budget'):
            raise ValueError('Exact terminal authorization required')
    return c, p


def review(folder):
    c,p = checked(folder)
    intents,replies = queue.archive(folder)
    return dict(status='prepared_not_started' if not intents else 'has_archived_attempts',
        planned_calls=p['planned_calls'], **queue.account(intents,replies),
        estimated_cost_usd=c['estimated_cost_usd'], budget_cap_usd=p['budget_cap_usd'],
        months=p['months'], arms=p['arms'], repeats=p['generation_repeats'],
        destination=p['destination'], model=p['model'], route=p['route'],
        automatic_retries=0, prompt_bytes_unchanged=True, new_api_calls=0,
        authorization_exists=(Path(folder)/'authorization.json').exists())


def worker(folder, round_dir, lock_fd):
    folder, round_dir = Path(folder), Path(round_dir)
    # Descriptor inherited from launch: prevents all simultaneous launch paths.
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    wake = None
    try:
        c,p = checked(folder, authorized=True)
        if sys.platform == 'darwin':
            wake = subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        slots = slots_for(Path(c['package']), read_json(Path(c['package'])/'manifest.json'), p)
        old_intents, old_replies = queue.archive(folder)
        keys = {s['key']:s for s in slots}
        if any(r['key'] not in keys or r['prompt_sha256'] != keys[r['key']]['prompt_sha256']
               or r['reserved_usd'] != keys[r['key']]['reserved_usd'] for r in old_intents):
            raise ValueError('Continuation intent differs from frozen scope')
        # A prior hard failure requires operator reconciliation, not a resume flag.
        policy = read_json(folder/'execution_policy.json')
        if any(r.get('error') and not queue.recoverable(r,policy) for r in old_replies):
            raise ValueError('Prior hard failure requires explicit reconciliation')
        send = live_sender(p)
        def publish(value):
            atomic_json(folder/'progress.json', dict(value, planned_calls=p['planned_calls']))
        receipt = queue.run_segments(p, slots, folder, round_dir, send, policy, publish=publish)
        dump(round_dir/'generation_receipt.json',receipt)
        if receipt['status'] == 'completed':
            publish(dict(phase='evaluation',at_utc=queue.now(),**receipt))
            with (round_dir/'evaluation.log').open('x') as log:
                code = subprocess.run([c['python'],'-u',str(ENTRY),'evaluate','--run-dir',str(folder),
                                       '--out',str(round_dir/'evaluation')], cwd=ROOT,
                                      stdout=log,stderr=subprocess.STDOUT).returncode
            status = 'generation_and_evaluation_complete' if code == 0 else 'evaluation_failed_data_preserved'
        else:
            code, status = 0, 'generation_stopped_data_preserved'
        final = dict(status=status, receipt=receipt, exit_code=code, ended_at_utc=queue.now(),
                     generation_backend='local_frozen_message_adapter_after_official_Core_offline_acceptance',
                     automatic_retries=0, automatic_process_restarts=0)
        dump(round_dir/'worker_receipt.json',final)
        atomic_json(folder/'latest_receipt.json',dict(final,round_dir=str(round_dir)))
    except Exception as exc:
        final = dict(status='worker_failed_data_preserved', error_type=type(exc).__name__,ended_at_utc=queue.now())
        dump(round_dir/'worker_receipt.json',final)
        atomic_json(folder/'latest_receipt.json',dict(final,round_dir=str(round_dir)))
        raise
    finally:
        if wake is not None:
            wake.terminate()
            wake.wait()
        os.close(lock_fd)


def watch(folder):
    folder = Path(folder)
    print('每10秒读取本地进度；Ctrl+C只退出观察，后台继续。',flush=True)
    try:
        while True:
            launch = read_json(folder/'latest_launch.json') if (folder/'latest_launch.json').exists() else None
            if launch and (Path(launch['round_dir'])/'worker_receipt.json').exists():
                result = read_json(Path(launch['round_dir'])/'worker_receipt.json')
                print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
                return result
            path = folder/'progress.json'
            value = read_json(path) if path.exists() else {}
            cooling = folder/'scheduler_status.json'
            extra = read_json(cooling) if cooling.exists() else {}
            age = ''
            if value.get('at_utc'):
                from datetime import datetime, timezone
                seconds = (datetime.now(timezone.utc)-datetime.fromisoformat(value['at_utc'])).total_seconds()
                if seconds > 60: age = f' | 进度{seconds:.0f}秒未刷新，请查看日志'
            print(time.strftime('%H:%M:%S')+f" | {value.get('phase','等待初始化')}"
                +f" | 已发 {value.get('attempts',0):,}/6,720 | 回包 {value.get('completed',0):,}"
                +f" | 可用 {value.get('usable',0):,}"
                +f" | 在途 {value.get('in_flight',0)} | 已计及预留 ${value.get('spent_or_reserved_usd',0):.4f}"
                +(f" | 冷却剩余 {extra['cooldown_remaining_s']:.0f}秒" if extra.get('cooldown_remaining_s',0)>0 else '')+age,flush=True)
            time.sleep(10)
    except KeyboardInterrupt:
        print('\n已退出观察；没有停止或重启模拟。',flush=True)


def run(folder, confirm=False, resume=False):
    if not confirm:
        raise ValueError('Review scope and budget, then explicitly use --confirm-scope-and-budget')
    folder = Path(folder).resolve()
    c,p = checked(folder)
    prior_rounds = sorted(folder.glob('round_*'))
    if bool(prior_rounds) != bool(resume):
        raise ValueError('Use run once; subsequent operator-approved continuation uses resume')
    intents,replies = queue.archive(folder)
    balance = queue.account(intents,replies)
    if len(intents) == p['planned_calls']:
        raise ValueError('Every slot already attempted; evaluate offline, do not resend failures')
    if any(r.get('error') and not queue.recoverable(r,POLICY) for r in replies):
        raise ValueError('Prior hard failure requires explicit reconciliation')
    from ..news_label_trial import dotenv_values
    if not(os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL/'.env').get('OPENROUTER_API_KEY')):
        raise ValueError('OpenRouter credential unavailable; never put it in the command line')
    lock = os.open(folder/'execution.lock',os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not (folder/'authorization.json').exists():
            dump(folder/'authorization.json',dict(approved=True,config_sha256=sha(folder/'config.json'),
                 user_confirmation='--confirm-scope-and-budget',at_utc=queue.now(),
                 destination=p['destination'],model=p['model'],route=p['route'],planned_calls=p['planned_calls'],
                 budget_cap_usd=p['budget_cap_usd'],automatic_failed_slot_retries=0))
        checked(folder, authorized=True)
        round_dir = folder/f'round_{len(prior_rounds)+1:04d}'
        round_dir.mkdir(exist_ok=False)
        dump(round_dir/'launch_intent.json',dict(operator_action='resume' if resume else 'run',
            previous_attempts=len(intents),unresolved_intents=balance['unresolved'],
            total_budget_cap_usd=p['budget_cap_usd'],at_utc=queue.now()))
        print(f"本批7个月×5组×96人×2遍，共6720请求；已发{len(intents)}，仅发剩余{6720-len(intents)}。"
              +f"预计总费${c['estimated_cost_usd']:.2f}，累计硬上限${p['budget_cap_usd']:.5f}。",flush=True)
        with (round_dir/'worker.log').open('x') as log:
            child = subprocess.Popen([c['python'],'-u',str(ENTRY),'_worker','--run-dir',str(folder),
                  '--round-dir',str(round_dir),'--lock-fd',str(lock)],cwd=ROOT,stdin=subprocess.DEVNULL,
                  stdout=log,stderr=subprocess.STDOUT,start_new_session=True,pass_fds=(lock,))
        atomic_json(folder/'latest_launch.json',dict(pid=child.pid,round_dir=str(round_dir),at_utc=queue.now()))
    finally:
        os.close(lock)
    print(f'独立后台PID {child.pid}；不会依赖Codex逐批调度。',flush=True)
    return watch(folder)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action',required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--package',type=Path,required=True)
    prep.add_argument('--run-dir',type=Path,required=True)
    for action in ('review','run','resume','watch','evaluate','_worker'):
        cmd = sub.add_parser(action)
        cmd.add_argument('--run-dir',type=Path,required=True)
        if action in ('run','resume'):cmd.add_argument('--confirm-scope-and-budget',action='store_true')
        if action == 'evaluate':cmd.add_argument('--out',type=Path,required=True)
        if action == '_worker':
            cmd.add_argument('--round-dir',type=Path,required=True)
            cmd.add_argument('--lock-fd',type=int,required=True)
    args = parser.parse_args(argv)
    if args.action == 'prepare':print(json.dumps(prepare(args.package,args.run_dir),ensure_ascii=False,indent=2))
    elif args.action == 'review':print(json.dumps(review(args.run_dir),ensure_ascii=False,indent=2))
    elif args.action in ('run','resume'):run(args.run_dir,args.confirm_scope_and_budget,args.action=='resume')
    elif args.action == 'watch':watch(args.run_dir)
    elif args.action == '_worker':worker(args.run_dir,args.round_dir,args.lock_fd)
    else:
        from ..evaluation.media_mechanism_terminal import evaluate
        print(json.dumps(evaluate(args.run_dir,args.out),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
