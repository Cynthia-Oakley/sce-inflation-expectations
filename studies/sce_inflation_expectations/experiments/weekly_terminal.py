"""Independent, release-calibrated weekly runner over the frozen transport.

Every completed week is an atomic checkpoint. Generation has no evaluator or
target reader. A separate process scores sealed snapshots after generation.
"""
import argparse
from copy import deepcopy
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from .frozen_batch import ROOT, OFFICIAL, read_json as read, dump, sha
from . import full_a_personal_terminal as transport
from . import frozen_message_queue as queue
from .monthly_main_background import atomic_json
from .state_continuity_execution import verify, authorize, live_sender
from .weekly_inputs import render
from .weekly_state import initialize_state, reset_state, advance_state
from .weekly_release_protocol import aware
from .state_continuity_inputs import density_center
from ..prior_belief_experiment import message_hash
from ..q9_normalization import response_point, response_view
from ..submission_tools.reproduce import no_network

ENTRY = ROOT / 'scripts/run_sce_weekly.py'
CATALOG = ROOT / 'data/evaluation/sce_recent_b_evaluation_20261025_v1/aggregate_inputs.json'
PARAMS = ROOT / 'outputs/sce_recent_b_review_materials_20261026_v2/macro_parameters.json'


def _validate_files(base, hashes):
    base = Path(base).resolve()
    for rel, digest in hashes.items():
        path = (base / rel).resolve()
        if not path.is_relative_to(base) or not path.is_file() or sha(path) != digest:
            raise ValueError('Bound source/output changed: ' + rel)


def prepare(inputs, folder, cap=15.):
    inputs, folder = Path(inputs).resolve(), Path(folder).resolve()
    if folder.exists() or not folder.is_relative_to(ROOT/'outputs') or not 0 < cap <= 20:
        raise ValueError('Fresh outputs directory and explicit candidate cap <=20 required')
    with no_network():
        summary = read(inputs/'summary.json'); manifest = read(inputs/'manifest.json')
        _validate_files(ROOT, manifest['source_sha256']); _validate_files(inputs, manifest['files_sha256'])
        if summary['status'] != 'weekly_inputs_and_scripted_core_ready' or summary['official_core_units'] != 47:
            raise ValueError('All 47 official Core units required')
        old = read(ROOT/'outputs/sce_recent_b_sampled_terminal_20261026_v1/package/protocol.json')
        p = {k: deepcopy(old[k]) for k in ('model','destination','route','expected_provider','request_extra_body',
                                          'provider_metadata')}
        p.update(schema='sce_release_calibrated_weekly/v1', inputs=str(inputs.relative_to(ROOT)),
            planned_calls=14100, n_per_week=300, weekly_points=47, maximum_physical_attempts=28200,
            temperature=.5, thinking='disabled', response_format='json_object', max_tokens=1024,
            timeout_s=120, retry_max=0, provider_fallback=False, budget_cap_usd=float(cap),
            price_input_per_mtok=.259, price_output_per_mtok=.8,
            max_prompt_chars=summary['max_prompt_chars'], max_prompt_bytes=summary['max_prompt_bytes'],
            technical_gate={'minimum_format_ratio':.95}, entry_exit=False, Normal=False,
            public_reset='Only new past SCE releases, at next weekly cutoff; fixed joint donor method and +/-0.05pp band',
            news='Unique seen-ID memory; floor(monthly tier * elapsed calendar day / days in month); no bootstrap/backfill',
            estimate_main_cost_usd=summary['estimated_main_cost_usd'], target_truth_in_generation=False,
            evaluation_catalog_only=str(CATALOG.relative_to(ROOT)),
            parameter_source=str(PARAMS.relative_to(ROOT)),
            direction_epsilon_pp=.1, evaluation_anomaly_threshold_pp=.3,
            evaluation='One last-week forecast per survey month; MAE/RMSE; 7/14/21-day panels descriptive; no real weekly micro truth',
            model_knowledge_limit='Retrospective cutoff backtest, not a historically sealed ex-ante prediction',
            created_at_utc=queue.now())
        folder.mkdir(); (folder/'package').mkdir()
        policy = transport._policy(); policy['batch_slots'] = 300
        dump(folder/'package/protocol.json', p); dump(folder/'package/execution_policy.json', policy)
        sources = {**manifest['source_sha256'],
            str((inputs/'manifest.json').relative_to(ROOT)): sha(inputs/'manifest.json'),
            **{str((inputs/k).relative_to(ROOT)):v for k,v in manifest['files_sha256'].items()}}
        code = [Path(__file__), ENTRY, Path(__file__).with_name('weekly_evaluation.py'), Path(__file__).with_name('weekly_inputs.py'),
                Path(__file__).with_name('weekly_state.py'),Path(__file__).with_name('weekly_release_protocol.py'),
                Path(__file__).with_name('full_a_personal_terminal.py'),Path(__file__).with_name('frozen_message_queue.py'),
                Path(__file__).with_name('monthly_main_resilient.py'),Path(__file__).with_name('state_continuity_execution.py'),
                Path(__file__).with_name('state_continuity_inputs.py'),Path(__file__).with_name('recent_b_review_materials.py'),
                ROOT/'studies/sce_inflation_expectations/q9_normalization.py',
                ROOT/'studies/sce_inflation_expectations/evaluation/metrics.py',
                ROOT/'studies/sce_inflation_expectations/scoring/sce_q9_frozen.py',
                ROOT/'studies/sce_inflation_expectations/scoring/sce_q9.py',
                ROOT/'studies/sce_inflation_expectations/scoring/beta_fit_kernel.py',
                *transport.RUNTIME_SOURCE_PATHS]
        for path in code:
            sources[str(path.relative_to(ROOT))] = sha(path)
            dest = folder/'source_snapshot'/path.relative_to(ROOT); dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
        sources[str((folder/'package/execution_policy.json').relative_to(ROOT))] = sha(folder/'package/execution_policy.json')
        sources[str(PARAMS.relative_to(ROOT))] = sha(PARAMS)
        sources[p['provider_metadata']] = sha(ROOT/p['provider_metadata'])
        dump(folder/'package/manifest.json', dict(protocol_sha256=sha(folder/'package/protocol.json'),
            source_sha256=sources, new_api_calls=0, authorization_written=False))
        return dict(status='weekly_run_candidate_not_authorized', planned_main_calls=14100,
                    estimate_main_cost_usd=p['estimate_main_cost_usd'], budget_cap_usd=cap, new_API_calls=0)


def checked(folder, authorized=False):
    p, m = verify(Path(folder)/'package')
    if (p['schema']!='sce_release_calibrated_weekly/v1' or p['planned_calls']!=14100
            or p['n_per_week']!=300 or p['weekly_points']!=47 or p['budget_cap_usd']>20):
        raise ValueError('Weekly scope changed')
    if authorized:
        a = read(Path(folder)/'package/authorization.json')
        if not a.get('approved') or a['protocol_sha256']!=m['protocol_sha256'] or not a.get('human_confirmation'):
            raise ValueError('Explicit weekly data-scope and budget approval required')
        for k in ('planned_calls','budget_cap_usd','destination','model','route'):
            if a[k]!=p[k]: raise ValueError('Authorization mismatch: '+k)
    return p, m


def state_before(previous, priors, point, expected_predecessor):
    """Only the immediately preceding same-household checkpoint can be used."""
    result = {}
    if previous and set(previous)!=set(priors):
        raise ValueError('Fixed weekly household identities changed')
    for aid, prior in priors.items():
        if previous:
            old = previous[aid]
            if old['agent_id']!=aid or aware(old['last_cutoff'])!=aware(expected_predecessor):
                raise ValueError('Cross-person or skipped-week state')
            result[aid] = (reset_state(old, point['cycle_key'], point.get('calibration_effective_at',point['anchor_known_from']), prior['fields'], center=prior['center'])
                           if old['cycle_key']!=point['cycle_key'] else deepcopy(old))
        else:
            if expected_predecessor is not None:
                raise ValueError('Only the first weekly point may initialize')
            result[aid] = initialize_state(aid, point['cycle_key'], point.get('calibration_effective_at',point['anchor_known_from']), prior['fields'], center=prior['center'])
    return result


def overlay(previous, main, repair, allowed, cutoff):
    payload = {}; provenance = {}
    for field in ('q8','q9'):
        row = main
        if not queue.fields(row)[field] and field in allowed and repair and queue.fields(repair)[field]:
            row = repair
        if queue.fields(row)[field]:
            raw = row['raw_response_text']
            if field=='q8':
                point = response_point(raw)
                if abs(point)<=100: payload['point_pct'] = point
            else:
                payload['q9'] = json.loads(raw)['q9']
            provenance[field] = 'repair' if row is repair else 'main'
        else:
            provenance[field] = 'retained_prior'
    failed_transport = not payload and bool(main.get('error') or (repair and repair.get('error')))
    result = advance_state(previous, payload, cutoff, technical_failure=failed_transport)
    for field, updated in result['steps'][-1]['field_updated_from_model'].items():
        if not updated: provenance[field] = 'retained_prior'
    result['last_response_field_sources'] = provenance
    return result


def sealed(folder, point):
    dest = folder/'checkpoints'/point['step_key']
    m = read(dest/'manifest.json'); _validate_files(dest, m['files_sha256'])
    wave = folder/'waves'/point['step_key']
    if sha(wave/'wave_plan.json')!=m['wave_plan_sha256']:
        raise ValueError('Checkpoint prompt plan changed')
    plan = read(wave/'wave_plan.json')
    if plan['cutoff'] != point['cutoff']:
        raise ValueError('Checkpoint cutoff changed')
    _validate_files(wave, plan['files_sha256'])
    _validate_files(wave, m['ledger_manifests'])
    queue.archive(wave/'main'); queue.archive(wave/'repair')
    states = read(dest/'states_private.json')
    if (set(states)!=set(read(wave/'states_before_private.json'))
            or any(s['agent_id']!=a or aware(s['last_cutoff'])!=aware(point['cutoff'])
                   or s['cycle_key']!=point['cycle_key'] for a,s in states.items())):
        raise ValueError('Sealed weekly identity/cutoff/cycle changed')
    return states, read(dest/'receipt.json')


def wave_inputs(folder, p, point, previous, expected_predecessor):
    inputs = ROOT/p['inputs']; key = point['step_key']; month = point['month']
    cycle_path = inputs/'priors/cycles_private.json'
    priors = read(cycle_path)[point['cycle_key']]['states']
    before = state_before(previous, priors, point, expected_predecessor)
    digest = hashlib.sha256(json.dumps(before, sort_keys=True, allow_nan=False).encode()).hexdigest()
    wave = folder/'waves'/key
    if (wave/'wave_plan.json').exists():
        old = read(wave/'wave_plan.json')
        if old['states_before_sha256']!=digest: raise ValueError('Predecessor changed on resume')
        _validate_files(wave, old['files_sha256'])
        return wave, read(wave/'slot_index_private.json'), read(wave/'states_before_private.json')
    templates = read(inputs/'weeks'/key/month/'templates_private.json')
    if set(templates)!=set(before): raise ValueError('Template/state identity mismatch')
    wave.mkdir(parents=True); rows = {}; slots = []
    for aid, state in before.items():
        messages = render(templates[aid], state, point['cutoff']); text = json.dumps(messages, ensure_ascii=False)
        if len(text)>p['max_prompt_chars'] or len(text.encode())>p['max_prompt_bytes']:
            raise ValueError('Dynamic prompt exceeds frozen allowance')
        digest_msg = message_hash(messages); rows[aid] = dict(messages=messages, prompt_sha256=digest_msg)
        slots.append(dict(key='weekly|'+key+'|'+aid, month=month, agent_id=aid, arm='weekly',repeat=1,
            prompt_sha256=digest_msg, reserved_usd=transport.reserve(p,len(text.encode()))))
    slots.sort(key=lambda r:hashlib.sha256(r['key'].encode()).digest())
    promptdir = wave/'frozen_messages'/month; promptdir.mkdir(parents=True)
    dump(promptdir/'prompts.json', dict(month=month,rows=rows))
    dump(wave/'states_before_private.json', before); dump(wave/'slot_index_private.json', slots)
    names = ['states_before_private.json','slot_index_private.json',f'frozen_messages/{month}/prompts.json']
    dump(wave/'wave_plan.json', dict(states_before_sha256=digest,
        files_sha256={k:sha(wave/k) for k in names}, cutoff=point['cutoff'], created_at_utc=queue.now()))
    return wave, slots, before


def generate(folder, fake_sender=None, cool=queue.cooldown):
    folder = Path(folder); engineering = fake_sender is not None
    p,_ = checked(folder, authorized=not engineering); inputs = ROOT/p['inputs']
    points = read(inputs/'weekly_plan.json'); policy = read(folder/'package/execution_policy.json')
    sender = fake_sender if engineering else live_sender(p)
    previous = {}; spent = reported = attempts = 0; receipts = []; previous_cutoff = None
    for point in points:
        key = point['step_key']; dest = folder/'checkpoints'/key
        if dest.exists():
            # Re-derive the predecessor link as well as validating sealed bytes.
            wave_inputs(folder,p,point,previous,previous_cutoff)
            previous, receipt = sealed(folder,point)
        else:
            wave, slots, before = wave_inputs(folder,p,point,previous,previous_cutoff)
            wp = {**p,'input_package_path':str(wave/'frozen_messages'),'planned_calls':300,
                  'budget_cap_usd':max(0.,p['budget_cap_usd']-spent)}
            def publish(stage, live):
                atomic_json(folder/'progress.json',dict(stage=stage,step=key,completed_weeks=len(receipts),total_weeks=47,
                    attempts=attempts+live.get('attempts',0), in_flight=live.get('in_flight',0),
                    reported_cost_usd=reported+live.get('reported_cost_usd',0),
                    spent_or_reserved_usd=spent+live.get('spent_or_reserved_usd',0),at_utc=queue.now()))
            main = transport.run_main_segments(wp,slots,wave,sender,policy,cool=cool,publish=publish,engineering_only=engineering)
            mi,mr = queue.archive(wave/'main')
            if main['status']!='completed' or any(r.get('error') and not transport.recoverable(r,policy) for r in mr):
                result = dict(status='weekly_generation_stopped_data_preserved', stopped_week=key, main=main,truth_read=False)
                atomic_json(folder/'generation_receipt.json',result); return result
            repair,ri,rr,targets = transport.run_repair_segments(wp,slots,wave,mi,mr,sender,policy,cool=cool,
                publish=publish,engineering_only=engineering)
            if repair['status'] not in ('completed','not_needed'):
                result = dict(status='weekly_repair_stopped_data_preserved',stopped_week=key,repair=repair,truth_read=False)
                atomic_json(folder/'generation_receipt.json',result); return result
            mains = {r['key']:r for r in mr}; repairs = {r['key'].removeprefix('repair1|'):r for r in rr}
            news = read(inputs/'weeks'/key/point['month']/'news_memory_after_private.json')
            states = {}; missing = dict(q8=0,q9=0)
            for slot in slots:
                aid = slot['agent_id']; k = slot['key']
                state = overlay(before[aid],mains[k],repairs.get(k),targets.get(k,{}).get('fields',[]),point['cutoff'])
                state['news_memory'] = news[aid]; states[aid] = state
                for field, good in state['steps'][-1]['field_updated_from_model'].items(): missing[field]+=not good
            a,b = queue.account(mi,mr),queue.account(ri,rr)
            receipt = dict(step_key=key,cutoff=point['cutoff'],cycle_key=point['cycle_key'],reset_required=point['reset_required'],
                main_attempts=a['attempts'],repair_attempts=b['attempts'],physical_attempts=a['attempts']+b['attempts'],
                reported_cost_usd=a['reported_cost_usd']+b['reported_cost_usd'],
                spent_or_reserved_usd=a['spent_or_reserved_usd']+b['spent_or_reserved_usd'],
                remaining_fields=missing,actual_model_results=not engineering)
            stage = folder/'checkpoints'/(key+'.staging'); stage.mkdir(parents=True,exist_ok=True)
            dump(stage/'states_private.json',states); dump(stage/'receipt.json',receipt)
            dump(stage/'manifest.json',dict(files_sha256={n:sha(stage/n) for n in ['states_private.json','receipt.json']},
                wave_plan_sha256=sha(wave/'wave_plan.json'),
                ledger_manifests={str(f.relative_to(wave)):sha(f) for f in wave.rglob('manifest.json')}))
            stage.rename(dest); previous = states
        previous_cutoff = point['cutoff']; receipts.append(receipt)
        spent += receipt['spent_or_reserved_usd']; reported += receipt['reported_cost_usd']; attempts += receipt['physical_attempts']
        if spent>p['budget_cap_usd']+1e-9: raise ValueError('Global weekly budget guard')
        atomic_json(folder/'progress.json',dict(stage='week_sealed',step=key,completed_weeks=len(receipts),total_weeks=47,
            attempts=attempts,in_flight=0,reported_cost_usd=reported,spent_or_reserved_usd=spent,at_utc=queue.now()))
        print(key+f': sealed {len(receipts)}/47; attempts {attempts}, reported ${reported:.4f}',flush=True)
    result = dict(status='weekly_generation_complete',weekly_points=47,fixed_households=300,
        main_attempts=sum(r['main_attempts'] for r in receipts),repair_attempts=sum(r['repair_attempts'] for r in receipts),
        physical_attempts=attempts,reported_cost_usd=reported,spent_or_reserved_usd=spent,
        unknown_fee_reservation_usd=spent-reported,budget_cap_usd=p['budget_cap_usd'],weekly=receipts,
        actual_model_results=not engineering,truth_read=False,Normal=False,entry_exit=False)
    atomic_json(folder/'generation_receipt.json',result); return result


def worker(folder):
    folder = Path(folder); checked(folder,authorized=True); wake = None
    with (folder/'active.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if sys.platform=='darwin':
            wake = subprocess.Popen(['/usr/bin/caffeinate','-is','-w',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            with (folder/'generation.log').open('a') as log:
                child = subprocess.run([sys.executable,str(ENTRY),'_generate','--run-dir',str(folder)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if child.returncode: raise RuntimeError('Generation process failed, data preserved')
            gen = read(folder/'generation_receipt.json')
            if gen['status']!='weekly_generation_complete':
                atomic_json(folder/'worker_receipt.json',dict(status=gen['status'],generation=gen)); return
            atomic_json(folder/'progress.json',dict(stage='evaluation',completed_weeks=47,total_weeks=47,
                attempts=gen['physical_attempts'],in_flight=0,reported_cost_usd=gen['reported_cost_usd'],
                spent_or_reserved_usd=gen['spent_or_reserved_usd'],at_utc=queue.now()))
            with (folder/'evaluation.log').open('a') as log:
                child = subprocess.run([sys.executable,str(ENTRY),'_evaluate','--run-dir',str(folder)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            atomic_json(folder/'worker_receipt.json',dict(status='generation_and_evaluation_complete' if child.returncode==0 else
                'evaluation_failed_data_preserved',exit_code=child.returncode,ended_at_utc=queue.now()))
        except Exception as exc:
            atomic_json(folder/'worker_receipt.json',dict(status='worker_failed_data_preserved',error_type=type(exc).__name__)); raise
        finally:
            if wake is not None: wake.terminate(); wake.wait()


def launch(folder, *, confirm=False, resume=False):
    folder = Path(folder).resolve();p,m=checked(folder,authorized=True)
    if not confirm: raise ValueError('Explicit confirmed weekly launch required')
    with (folder/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with (folder/'active.lock').open('a') as active:
            try: fcntl.flock(active,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError('Already running; use watch')
        if (folder/'launch.json').exists() and not resume: raise ValueError('Use explicit --resume')
        if (folder/'generation_receipt.json').exists() and read(folder/'generation_receipt.json')['status']=='weekly_generation_complete':
            raise ValueError('Generation complete; do not send again')
        from ..news_label_trial import dotenv_values
        if not(os.environ.get('OPENROUTER_API_KEY') or dotenv_values(OFFICIAL/'.env').get('OPENROUTER_API_KEY')):
            raise ValueError('OpenRouter credential unavailable')
        if (folder/'worker_receipt.json').exists():
            (folder/'worker_receipt.json').rename(folder/f'worker_before_resume_{time.time_ns()}.json')
        with (folder/'terminal_worker.log').open('a') as log:
            child = subprocess.Popen([sys.executable,'-u',str(ENTRY),'_worker','--run-dir',str(folder)],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        record=dict(pid=child.pid,protocol_sha256=m['protocol_sha256'],independent_of_codex=True,resumed=resume,started_at_utc=queue.now())
        dump(folder/'launch.json',record); dump(folder/f'launch_{child.pid}.json',record); return record


def watch(folder, once=False):
    folder=Path(folder)
    while True:
        r=read(folder/'progress.json') if (folder/'progress.json').exists() else {'stage':'starting'}
        print(datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S')+
            f" | {r.get('stage')} | {r.get('step','')} | 周点 {r.get('completed_weeks',0)}/47"+
            f" | 尝试 {r.get('attempts',0):,} | 在途 {r.get('in_flight',0)}"+
            f" | 已报 ${r.get('reported_cost_usd',0):.4f} | 计及预留 ${r.get('spent_or_reserved_usd',0):.4f}",flush=True)
        if (folder/'worker_receipt.json').exists(): print(json.dumps(read(folder/'worker_receipt.json'),ensure_ascii=False,indent=2)); return
        if once:return
        time.sleep(10)


def replay(folder, out):
    folder,out=Path(folder),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'): raise ValueError('Fresh replay directory required')
    out.mkdir();shutil.copytree(folder/'package',out/'package');seen={};counter=0
    def send(messages):
        nonlocal counter
        counter+=1;digest=message_hash(messages);seen[digest]=seen.get(digest,0)+1
        bad=counter==55
        return dict(error='APIConnectionError' if bad else None,returned_model='deepseek/deepseek-v3.2',
            returned_provider='SiliconFlow',finish_reason=None if bad else 'stop',
            api_reported_cost_usd=None if bad else .00001,
            raw_response_text='' if bad else json.dumps(dict(point_pct=3.,q9={f'bin{i}':10. for i in range(1,11)})))
    result=generate(out,fake_sender=send,cool=lambda *_:None)
    if result['status']!='weekly_generation_complete' or counter!=14101 or result['repair_attempts']!=1:
        raise ValueError('Full weekly repair replay failed')
    generate(out,fake_sender=send,cool=lambda *_:None)
    if counter!=14101:raise ValueError('Sealed weekly resume resent a request')
    result.update(status='passed_full_weekly_replay',new_real_API_calls=0,completed_resume_sends_zero=True)
    dump(out/'offline_acceptance.json',result); return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--cap',type=float,default=15.)
    for name in ('authorize','run','watch','replay','_worker','_generate','_evaluate','evaluate'):
        p=sub.add_parser(name);p.add_argument('--run-dir',type=Path,required=True)
        if name=='authorize':p.add_argument('--human-confirmation',required=True)
        if name=='run':p.add_argument('--confirm-live',action='store_true');p.add_argument('--resume',action='store_true')
        if name=='watch':p.add_argument('--once',action='store_true')
        if name=='replay':p.add_argument('--out',type=Path,required=True)
    a=parser.parse_args();cmd=a.command
    if cmd=='prepare':result=prepare(a.inputs,a.out,a.cap)
    elif cmd=='authorize':result=authorize(a.run_dir/'package',a.human_confirmation)
    elif cmd=='run':result=launch(a.run_dir,confirm=a.confirm_live,resume=a.resume)
    elif cmd=='watch':watch(a.run_dir,a.once);return
    elif cmd=='replay':result=replay(a.run_dir,a.out)
    elif cmd=='_worker':worker(a.run_dir);return
    elif cmd=='_generate':result=generate(a.run_dir)
    else:
        from .weekly_evaluation import evaluate
        result=evaluate(a.run_dir)
    print(json.dumps(result,ensure_ascii=False,indent=2))
