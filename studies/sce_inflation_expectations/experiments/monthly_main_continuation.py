"""Resume an independent-month run without resending any dispatched position.

The original protocol, prompts, queue, scorer and truth files stay immutable.
Only orchestration/provenance changes: retain old attempts, append new attempts,
then evaluate the combined ledger against the original frozen protocol.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

from .frozen_batch import ROOT, OFFICIAL, read_json, dump, sha
from .state_continuity_execution import verify, execute, load_inputs, live_sender, node_key, reserve
from .monthly_main_background import Progress, atomic_json, current_phase, status
from .monthly_main_pipeline import plan

ENTRY = ROOT / 'scripts/continue_sce_monthly_main.py'
LEDGERS = ('calls_private.jsonl', 'positions_private.jsonl', 'dispatch_private.jsonl')


def now():
    return datetime.now(timezone.utc).isoformat()


def lines(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream]


def audit_attempts(nodes, rows, intents, positions):
    allkeys = {n['logical_reuse_key'] for n in nodes}
    keys = [r['reuse_key'] for r in rows]
    intended = [r['reuse_key'] for r in intents]
    if (len(keys) != len(set(keys)) or len(intended) != len(set(intended))
            or set(keys) != set(intended) or not set(keys) <= allkeys):
        raise ValueError('Unresolved or duplicated dispatch: never infer it is unattempted')
    expected = {node_key(n): n for n in nodes}
    attempted_positions = [node_key(n) for r in rows for n in r['nodes']]
    actual_positions = [node_key(n) for n in positions]
    if (len(actual_positions) != len(set(actual_positions))
            or set(actual_positions) != set(attempted_positions)):
        raise ValueError('Position ledger mismatch')
    by_intent = {r['reuse_key']: r for r in intents}
    for row in rows:
        if row['prompt_sha256'] != by_intent[row['reuse_key']]['prompt_sha256']:
            raise ValueError('Prior prompt/dispatch mismatch')
        if any(n != expected.get(node_key(n)) for n in row['nodes']):
            raise ValueError('Prior respondent positions changed')
    return sorted(allkeys - set(keys))


def prepare(parent, calls, truth, registry, out):
    parent, calls, truth, registry, out = [Path(p).resolve() for p in (parent, calls, truth, registry, out)]
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh private resume directory required')
    p, m = verify(parent)
    receipt, cm, auth = [read_json(f) for f in (calls/'receipt.json', calls/'manifest.json', parent/'authorization.json')]
    if (p['mechanism'] != 'monthly_reconstruction_v1' or not auth.get('approved')
            or receipt['status'] != 'stopped_no_retry'
            or any(x['protocol_sha256'] != m['protocol_sha256'] for x in (receipt, cm, auth))):
        raise ValueError('An authorized stopped independent-month batch is required')
    for name, digest in cm['files_sha256'].items():
        if sha(calls/name) != digest:
            raise ValueError('Prior immutable ledger changed: ' + name)
    if not read_json(calls/'technical_gate.json')['passed']:
        raise ValueError('Original technical gate must have passed')
    nodes = read_json(ROOT/p['preparation']/'state_dependencies_private.json')
    if any(n['dependency'] is not None for n in nodes):
        raise ValueError('This adapter does not resume recursive state dependencies')
    rows = lines(calls/'calls_private.jsonl')
    intents = lines(calls/'dispatch_private.jsonl')
    positions = lines(calls/'positions_private.jsonl')
    pending = audit_attempts(nodes, rows, intents, positions)
    if len(rows) != receipt['attempts'] or len(rows) + len(pending) != p['planned_calls'] or not pending:
        raise ValueError('Exact nonempty remaining scope required')
    accounted = sum(r['api_reported_cost_usd'] if r['api_reported_cost_usd'] is not None
                    else r['request_reservation_usd'] for r in rows)
    if accounted + reserve(p, p['max_prompt_bytes']) > p['budget_cap_usd']:
        raise ValueError('No budget room for a further request')
    if p.get('budget_mode') != 'spent_plus_inflight_reservation':
        raise ValueError('Original rolling budget guard required')
    package, supervisor = out/'package', out/'supervisor'
    paths = dict(parent=str(parent), previous_calls=str(calls), package=str(package), calls=str(out/'calls'),
                 combined=str(out/'combined'), truth=str(truth), registry=str(registry),
                 evaluation=str(out/'evaluation'), readout=str(out/'readout'))
    package.mkdir(parents=True); supervisor.mkdir()
    shutil.copyfile(parent/'protocol.json', package/'protocol.json')
    dump(package/'pending_keys_private.json', pending)
    spec = dict(paths=paths, protocol_sha256=m['protocol_sha256'], prior_attempts=len(rows),
                prior_errors=sum(bool(r['error']) for r in rows), new_requests=len(pending),
                prior_spent_or_reserved_usd=accounted, budget_cap_usd=p['budget_cap_usd'],
                whole_remaining_worst_case_usd=len(pending)*reserve(p, p['max_prompt_bytes']),
                policy='Only never-dispatched keys once; retain every prior success/failure; original stop/budget/provider rules.',
                prepared_at_utc=now())
    dump(package/'resume.json', spec)
    evidence = dict(m['source_sha256'])
    for f in (Path(__file__), ENTRY, Path(__file__).with_name('monthly_main_background.py'),
              Path(__file__).with_name('monthly_main_pipeline.py'),
              parent/'protocol.json', parent/'manifest.json', parent/'authorization.json',
              calls/'manifest.json', calls/'technical_gate.json',
              *[calls/n for n in cm['files_sha256']], package/'pending_keys_private.json', package/'resume.json'):
        evidence[str(f.relative_to(ROOT))] = sha(f)
    dump(package/'manifest.json', dict(protocol_sha256=m['protocol_sha256'], source_sha256=evidence,
         original_protocol_retained=True, new_api_calls=0))
    # Existing offline validator checks truth/source hashes, without reading target values or sending API requests.
    plan(package, paths['combined'], truth, paths['evaluation'], registry, paths['readout'])
    atomic_json(supervisor/'config.json', dict(paths=paths, python=sys.executable,
                planned_calls=p['planned_calls'], budget_cap_usd=p['budget_cap_usd'],
                protocol_sha256=m['protocol_sha256'], resume_sha256=sha(package/'resume.json')))
    return {k: spec[k] for k in ('prior_attempts', 'prior_errors', 'new_requests', 'prior_spent_or_reserved_usd', 'budget_cap_usd')}


def checked(folder, *, authorization=True):
    folder = Path(folder).resolve(); config = read_json(folder/'config.json')
    package = Path(config['paths']['package']); p, m = verify(package)
    if config['resume_sha256'] != sha(package/'resume.json'):
        raise ValueError('Resume specification changed')
    if authorization:
        auth = read_json(package/'authorization.json')
        if not auth.get('approved') or auth.get('resume_sha256') != config['resume_sha256']:
            raise ValueError('Explicit manual continuation authorization required')
        for key in ('planned_calls','budget_cap_usd','destination','model','route'):
            if auth.get(key) != p[key]: raise ValueError('Authorization scope mismatch')
        if auth.get('protocol_sha256') != m['protocol_sha256']:
            raise ValueError('Authorization protocol mismatch')
    return config, p, m


def authorize(folder, confirmation):
    config, p, m = checked(folder, authorization=False)
    if not confirmation.strip(): raise ValueError('Explicit human continuation confirmation required')
    spec = read_json(Path(config['paths']['package'])/'resume.json')
    auth = dict(approved=True, human_confirmation=confirmation, at_utc=now(),
                protocol_sha256=m['protocol_sha256'], resume_sha256=config['resume_sha256'],
                new_requests=spec['new_requests'], retained_attempts=spec['prior_attempts'],
                **{k:p[k] for k in ('planned_calls','budget_cap_usd','destination','model','route')})
    with (Path(config['paths']['package'])/'authorization.json').open('x') as stream:
        json.dump(auth, stream, ensure_ascii=False, indent=2)
    return dict(authorized_new_requests=spec['new_requests'], new_api_calls=0)


def merge(paths, new_receipt, protocol_sha):
    old, new, combined = [Path(paths[k]) for k in ('previous_calls','calls','combined')]
    combined.mkdir()
    for name in LEDGERS:
        with (combined/name).open('xb') as dst:
            for component in (old/name, new/name):
                with component.open('rb') as src: shutil.copyfileobj(src, dst)
    previous = read_json(old/'receipt.json')
    total = dict(new_receipt, attempts=previous['attempts']+new_receipt['attempts'],
                 completed_calls=previous['completed_calls']+new_receipt['completed_calls'],
                 protocol_sha256=protocol_sha, seconds=previous['seconds']+new_receipt['seconds'],
                 old_attempts_preserved=previous['attempts'], continuation_new_attempts=new_receipt['attempts'],
                 prior_peak_in_flight=previous['peak_in_flight'],
                 peak_in_flight=max(previous['peak_in_flight'],new_receipt['peak_in_flight']))
    dump(combined/'receipt.json', total)
    shutil.copyfile(old/'technical_gate.json', combined/'technical_gate.json')
    files = ('receipt.json','technical_gate.json',*LEDGERS)
    dump(combined/'manifest.json', dict(protocol_sha256=protocol_sha,
        files_sha256={n:sha(combined/n) for n in files},
        immutable_components={str((base/n).relative_to(ROOT)):sha(base/n) for base in (old,new) for n in LEDGERS},
        continuation_spec_sha256=sha(Path(paths['package'])/'resume.json')))
    return total


def generate(folder):
    config, p, m = checked(folder); paths = config['paths']; package = Path(paths['package'])
    for key in ('calls','combined','evaluation','readout'):
        if Path(paths[key]).exists(): raise ValueError('Fresh continuation outputs required')
    nodes = read_json(ROOT/p['preparation']/'state_dependencies_private.json')
    old = Path(paths['previous_calls'])
    rows = lines(old/'calls_private.jsonl')
    pending = audit_attempts(nodes, rows, lines(old/'dispatch_private.jsonl'), lines(old/'positions_private.jsonl'))
    if pending != read_json(package/'pending_keys_private.json'):
        raise ValueError('Never-attempted selection changed')
    inputs = load_inputs(ROOT/p['input_templates'],p['months'])
    send = live_sender(p)
    with (package/'execution_registration.json').open('x') as stream:
        json.dump(dict(started_at_utc=now(), new_output=paths['calls'], combined=paths['combined']),stream)
    receipt = execute(p,nodes,inputs,paths['calls'],send,completed_calls=rows,emit=lambda s:print(s,flush=True))
    receipt['protocol_sha256'] = m['protocol_sha256']
    dump(Path(paths['calls'])/'receipt.json',receipt)
    dump(Path(paths['calls'])/'manifest.json',dict(protocol_sha256=m['protocol_sha256'],
        files_sha256={n:sha(Path(paths['calls'])/n) for n in ('receipt.json',*LEDGERS)}))
    return merge(paths,receipt,m['protocol_sha256'])


def pipeline(folder):
    config, p, _ = checked(folder); paths=config['paths']; folder=Path(folder)
    phases = [
        [config['python'],'-u',str(ENTRY),'_generate','--run-dir',str(folder)],
        [config['python'],'-u',str(ROOT/'scripts/evaluate_sce_monthly_reconstruction.py'),'evaluate',
         '--package',paths['package'],'--calls',paths['combined'],'--truth',paths['truth'],'--out',paths['evaluation']],
        [config['python'],'-u',str(ROOT/'scripts/readout_sce_monthly_main.py'),
         '--package',paths['package'],'--evaluation',paths['evaluation'],'--truth',paths['truth'],
         '--registry',paths['registry'],'--out',paths['readout']]]
    for i, command in enumerate(phases):
        with (folder/f'phase_{i+1}.log').open('x') as stream:
            result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode:
            receipt=dict(status='resume_phase_failed_no_restart',phase=i+1,exit_code=result.returncode)
            atomic_json(folder/'pipeline_receipt.json',receipt);return receipt
        if i==0:
            receipt=read_json(Path(paths['combined'])/'receipt.json')
            if receipt['status']!='completed' or receipt['attempts']!=p['planned_calls']:
                result=dict(status='generation_stopped_no_evaluation',receipt=receipt)
                atomic_json(folder/'pipeline_receipt.json',result);return result
    result=dict(status='generation_and_separate_process_evaluation_complete')
    atomic_json(folder/'pipeline_receipt.json',result);return result


def combined_progress(old_progress,new_progress):
    old,new=old_progress.poll(),new_progress.poll()
    result={k:old[k]+new[k] for k in old if k!='completed_by_month'}
    result['completed_by_month']=dict(old['completed_by_month'])
    for k,v in new['completed_by_month'].items():
        result['completed_by_month'][k]=result['completed_by_month'].get(k,0)+v
    result.update(previous_attempts=old['completed'],new_attempts=new['completed'])
    return result


def worker(folder):
    folder=Path(folder).resolve();config,p,_=checked(folder);paths=config['paths']
    if not (folder/'launch_lock.json').exists():raise ValueError('Use start')
    with (folder/'worker_lock.json').open('x') as stream:json.dump(dict(pid=os.getpid(),at_utc=now()),stream)
    wake=None
    try:
        if sys.platform=='darwin':
            wake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        old,new=Progress(paths['previous_calls']),Progress(paths['calls']);started=time.monotonic()
        with (folder/'pipeline.log').open('x') as stream:
            child=subprocess.Popen([config['python'],'-u',str(ENTRY),'_pipeline','--run-dir',str(folder)],
                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,close_fds=True)
            while True:
                code=child.poll()
                try:
                    progress=combined_progress(old,new)
                    progress.update(at_utc=now(),worker_pid=os.getpid(),pipeline_pid=child.pid,
                        elapsed_seconds=time.monotonic()-started,planned_calls=p['planned_calls'],
                        budget_cap_usd=p['budget_cap_usd'],never_dispatched=p['planned_calls']-progress['dispatched'],
                        phase=current_phase(dict(paths,calls=paths['combined'])))
                    atomic_json(folder/'progress.json',progress)
                except Exception as exc:print('Progress read unavailable: '+type(exc).__name__,flush=True)
                if code is not None:break
                time.sleep(10)
        receipt=read_json(folder/'pipeline_receipt.json') if (folder/'pipeline_receipt.json').exists() else dict(status='no_pipeline_receipt')
        receipt.update(ended_at_utc=now(),exit_code=code,automatic_restarts=0,automatic_retries_added=0)
        atomic_json(folder/'worker_receipt.json',receipt)
        return receipt
    except Exception as exc:
        atomic_json(folder/'worker_receipt.json',dict(status='resume_worker_failed_no_restart',error_type=type(exc).__name__,ended_at_utc=now()))
        raise
    finally:
        if wake is not None:wake.terminate();wake.wait()


def start(folder):
    folder=Path(folder).resolve();config,_,_=checked(folder)
    if (Path(config['paths']['package'])/'execution_registration.json').exists():
        raise ValueError('Attempted continuation cannot be restarted')
    from ..news_label_trial import dotenv_values
    if not (os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL/'.env').get('OPENROUTER_API_KEY')):
        raise ValueError('OpenRouter key unavailable')
    if sys.platform!='darwin':raise ValueError('This independent launcher is for macOS launchd')
    with (folder/'launch_lock.json').open('x') as stream:json.dump(dict(at_utc=now(),automatic_restart=False),stream)
    label='local.sce.resume.'+folder.parent.name.lower().replace('_','-')
    job=dict(Label=label,ProgramArguments=[config['python'],'-u',str(ENTRY),'_worker','--run-dir',str(folder)],
        WorkingDirectory=str(ROOT),RunAtLoad=True,KeepAlive=False,
        StandardOutPath=str(folder/'supervisor.log'),StandardErrorPath=str(folder/'supervisor.stderr.log'))
    plist=folder/'one_shot_launchd.plist'
    with plist.open('xb') as stream:plistlib.dump(job,stream)
    os.chmod(plist,0o600)
    domain='gui/'+str(os.getuid())
    result=subprocess.run(['/bin/launchctl','bootstrap',domain,str(plist)],capture_output=True,text=True)
    atomic_json(folder/'launch.json',dict(method='macOS_one_shot_launchd',label=label,domain=domain,
        exit_code=result.returncode,at_utc=now(),automatic_restart=False))
    if result.returncode:raise RuntimeError('launchctl bootstrap failed; inspect launch.json; do not relaunch blindly')
    return dict(status='launched_check_progress',run_dir=str(folder),budget_cap_usd=config['budget_cap_usd'])
