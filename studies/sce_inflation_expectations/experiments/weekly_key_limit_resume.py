"""Scoped continuation after the user raised the weekly run's API-key limit.

The original inputs, ledgers and frozen source files stay unchanged. Only the
exact already archived budget-denied reply may enter its one-time repair slot.
New account errors are still hard stops. The ordinary weekly worker, budget
guard, checkpoint validation and repair-once ledger remain in control.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

from . import weekly_terminal as weekly
from . import frozen_message_queue as queue
from .frozen_batch import ROOT, read_json as read, dump, sha
from ..submission_tools.reproduce import no_network

ENTRY=ROOT/'scripts/resume_sce_weekly_key_limit.py'
APPENDIX='key_limit_resume_20261027'
EXPECTED_PROTOCOL='62b99b60fda2d0ff5c31380499aa9539b7eef46f1ac57de25cf5ec2a06873faf'
SOURCE_PATHS=(ENTRY,Path(__file__),ROOT/'scripts/evaluate_sce_weekly_compat.py',
              ROOT/'studies/sce_inflation_expectations/experiments/weekly_partial_readout.py')


def record_hash(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def inventory(folder):
    folder=Path(folder).resolve();protocol,manifest=weekly.checked(folder,authorized=True)
    if manifest['protocol_sha256']!=EXPECTED_PROTOCOL:
        raise ValueError('This continuation is scoped to the approved weekly run only')
    plan=read(ROOT/protocol['inputs']/'weekly_plan.json')
    attempts=0;remaining=0;unknown=0;errors=[];sealed=0;reported=spent=0.
    for point in plan:
        wave=folder/'waves'/point['step_key']
        done=(folder/'checkpoints'/point['step_key']).is_dir()
        sealed+=done
        for stage in ('main','repair'):
            intents,replies=queue.archive(wave/stage);account=queue.account(intents,replies)
            attempts+=account['attempts'];unknown+=account['unresolved']
            reported+=account['reported_cost_usd'];spent+=account['spent_or_reserved_usd']
            if stage=='main':remaining+=300-len(intents)
            if not done:
                for reply in replies:
                    if reply.get('error') and not weekly.transport.recoverable(reply,read(folder/'package/execution_policy.json')):
                        errors.append(dict(week=point['step_key'],stage=stage,key=reply['key'],
                                           record_sha256=record_hash(reply),reply=reply))
    return protocol,manifest,dict(sealed_weeks=sealed,remaining_main=remaining,
        physical_attempts=attempts,unknown_inflight=unknown,hard_rows=errors,
        reported_cost_usd=reported,spent_or_reserved_usd=spent)


def prepare(folder, *, key_limit_raised=False):
    if not key_limit_raised:raise ValueError('User confirmation that API-key limit was raised is required')
    folder=Path(folder).resolve()
    with no_network():
        protocol,manifest,info=inventory(folder)
        dest=folder/APPENDIX
        if dest.exists():return validate(folder)
        if info['unknown_inflight'] or info['sealed_weeks']!=35 or info['remaining_main']!=3369:
            raise ValueError('Stopped-run scope changed; inspect before preparing another continuation')
        hard=info['hard_rows']
        if len(hard)!=1 or hard[0]['week']!='w20260710' or hard[0]['stage']!='main':
            raise ValueError('Exactly one archived July 10 main hard failure required')
        row=hard[0]['reply']
        if row.get('error')!='PermissionDeniedError' or row.get('error_http_status')!=403:
            raise ValueError('Only the confirmed historical key-budget HTTP403 is eligible')
        # No repair may have been attempted for this stopped wave yet.
        if queue.archive(folder/'waves/w20260710/repair')[0]:
            raise ValueError('Do not prepare over an existing repair attempt')
        dest.mkdir()
        shutil.copyfile(folder/'generation_receipt.json',dest/'generation_before_resume.json')
        for path in SOURCE_PATHS:
            copy=dest/'source_snapshot'/path.relative_to(ROOT);copy.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,copy)
        appendix=dict(schema='sce_weekly_exact_key_budget_resume/v1',
            protocol_sha256=manifest['protocol_sha256'],budget_cap_usd=protocol['budget_cap_usd'],
            user_confirmation='用户表示已经提高API Key额度，要求从原进度接续；仅处理已登记的一次额度拒绝，原$15总预算不变。',
            allowed_original_reply=dict(week=hard[0]['week'],stage=hard[0]['stage'],key=hard[0]['key'],
                                        record_sha256=hard[0]['record_sha256']),
            sealed_weeks_at_preparation=info['sealed_weeks'],never_dispatched_main_at_preparation=info['remaining_main'],
            known_manual_repair_slots=1,physical_attempts_before=info['physical_attempts'],
            new_errors_still_hard_stop=True,scientific_configuration_unchanged=True,
            source_sha256={str(p.relative_to(ROOT)):sha(p) for p in SOURCE_PATHS},
            stopped_receipt_sha256=sha(dest/'generation_before_resume.json'),
            prepared_at_utc=queue.now(),new_model_API_calls=0)
        dump(dest/'appendix_private.json',appendix)
        return validate(folder)


def validate(folder):
    folder=Path(folder).resolve();protocol,manifest=weekly.checked(folder,authorized=True)
    dest=folder/APPENDIX;appendix=read(dest/'appendix_private.json')
    if (appendix['protocol_sha256']!=EXPECTED_PROTOCOL or manifest['protocol_sha256']!=EXPECTED_PROTOCOL
            or appendix['budget_cap_usd']!=protocol['budget_cap_usd'] or protocol['budget_cap_usd']!=15):
        raise ValueError('Original scope/budget does not match the continuation appendix')
    for rel,digest in appendix['source_sha256'].items():
        if sha(ROOT/rel)!=digest or sha(dest/'source_snapshot'/rel)!=digest:
            raise ValueError('Continuation source changed: '+rel)
    if sha(dest/'generation_before_resume.json')!=appendix['stopped_receipt_sha256']:
        raise ValueError('Stopped receipt snapshot changed')
    allowed=appendix['allowed_original_reply']
    _,rows=queue.archive(folder/'waves'/allowed['week']/allowed['stage'])
    matches=[r for r in rows if r['key']==allowed['key']]
    if len(matches)!=1 or record_hash(matches[0])!=allowed['record_sha256']:
        raise ValueError('Acknowledged historical HTTP403 record changed')
    return appendix


@contextmanager
def exact_historical_exception(allowed):
    original=weekly.transport.recoverable
    def scoped(row,policy):
        if (row.get('key')==allowed['key'] and row.get('error')=='PermissionDeniedError'
                and row.get('error_http_status')==403 and record_hash(row)==allowed['record_sha256']):
            return True
        return original(row,policy)
    weekly.transport.recoverable=scoped
    try:yield
    finally:weekly.transport.recoverable=original


def evaluate_compatible(folder):
    spec=importlib.util.spec_from_file_location('sce_weekly_final_compat',ROOT/'scripts/evaluate_sce_weekly_compat.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.evaluate_compatible(folder)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['inspect','prepare','run','_worker','_generate','_evaluate'])
    parser.add_argument('--run-dir',required=True,type=Path)
    parser.add_argument('--key-limit-raised',action='store_true');parser.add_argument('--confirm-live',action='store_true')
    args=parser.parse_args();folder=args.run_dir.resolve()
    weekly.ENTRY=ENTRY  # Child workers use this adapter; frozen file bytes do not change.
    if args.command=='inspect':
        with no_network():_,_,info=inventory(folder)
        print(json.dumps({k:v for k,v in info.items() if k!='hard_rows'},ensure_ascii=False,indent=2));return
    if args.command in ('prepare','run'):
        # Check active lock before creating an appendix or launching a second worker.
        with (folder/'active.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Weekly worker is already active; use watch')
            appendix=prepare(folder,key_limit_raised=args.key_limit_raised)
        if args.command=='prepare':
            print(json.dumps(dict(status='scoped_resume_ready_not_started',remaining_main=3369,
                known_manual_repair_slots=1,budget_cap_usd=15,new_model_API_calls=0),indent=2));return
        result=weekly.launch(folder,confirm=args.confirm_live,resume=True)
    else:
        appendix=validate(folder)
        if args.command=='_worker':weekly.worker(folder);return
        if args.command=='_generate':
            with exact_historical_exception(appendix['allowed_original_reply']):result=weekly.generate(folder)
        else:result=evaluate_compatible(folder)
    print(json.dumps(result,ensure_ascii=False,indent=2))
