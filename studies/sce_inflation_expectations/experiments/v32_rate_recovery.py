"""Explicit manual 429 completion; retain successes and every original failure.

This prepares reviewable files only. The existing scheduler performs paid calls
after a NEW matching authorization. No model retry or provider fallback here.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .frozen_batch import ROOT,read_json,dump,sha
from ..q9_normalization import response_view


def partition(slots,calls):
    index={r['slot_key']:r for r in slots};existing={};failed=[];seen=set()
    for c in calls:
        key=c['slot_key']
        if key in seen or key not in index:raise ValueError('Unknown or duplicated first-stage slot')
        seen.add(key);s=index[key]
        if (c['prompt_sha256']!=s['prompt_sha256']
                or c['prompt_text']!=json.dumps(s['messages'],ensure_ascii=False)
                or hashlib.sha256(c['raw_response_text'].encode()).hexdigest()!=c['raw_response_sha256']):
            raise ValueError('First-stage input or raw reply changed')
        if c.get('error'):
            if c.get('error_http_status')!=429:raise ValueError('Only the explicitly registered twelve 429s may be resent')
            failed.append(deepcopy(s))
        else:
            if (c.get('returned_model')!='deepseek/deepseek-v3.2' or c.get('returned_provider')!='AtlasCloud'
                    or c.get('finish_reason')!='stop'):
                raise ValueError('Successful original model/provider/finish required')
            response_view(c['raw_response_text']);existing[key]=c
    if len(calls)!=16 or len(existing)!=4 or len(failed)!=12:
        raise ValueError('Registered four successes and twelve 429 failures required')
    return existing,failed


def checked(folder):
    p=read_json(folder/'protocol.json');m=read_json(folder/'manifest.json')
    if sha(folder/'protocol.json')!=m['protocol_sha256']:raise ValueError('Protocol changed')
    for name,digest in m['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Source changed: '+name)
    for name,digest in m['files_sha256'].items():
        if sha(folder/name)!=digest:raise ValueError('Frozen input changed')
    return p,m


def write_package(parent,out,p,m,existing,pending,*,approved,confirmation,phase):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored recovery directory required')
    receipt=read_json(parent/'run_receipt.json');slots=read_json(parent/'slots_private.json')
    protocol={**p,'previous_call_ledger':str(parent.relative_to(ROOT)),
        'recovery_phase':phase,'max_workers':2,'new_planned_calls':len(pending),
        'existing_attempted_calls':receipt['original_attempts']+receipt['new_calls'],
        'already_spent_or_reserved_usd':receipt['combined_spent_or_reserved_usd'],
        'error_policy':'Explicit one-time manual resend of twelve registered 429 slots only; zero automatic retries. Stop again on 429. Preserve four original successes; tail only after combined sixteen-format check.'}
    protocol.pop('queue_technical_gate',None)
    reserve=sum(((len(json.dumps(s['messages'],ensure_ascii=False).encode())+1024)*p['price_input_per_mtok']
                 +1024*p['price_output_per_mtok'])/1e6 for s in slots if s['slot_key'] not in existing)
    if receipt['combined_spent_or_reserved_usd']+reserve>4:raise ValueError('Original $4 total cap exceeded')
    sources=dict(m['source_sha256'])
    for name in ('protocol.json','manifest.json','authorization.json','run_receipt.json','new_calls_private.jsonl'):
        f=parent/name;sources[str(f.relative_to(ROOT))]=sha(f)
    sources[str(Path(__file__).relative_to(ROOT))]=sha(Path(__file__))
    out.mkdir();dump(out/'slots_private.json',slots);dump(out/'existing_calls_private.json',existing)
    dump(out/'pending_private.json',pending);dump(out/'protocol.json',protocol)
    dump(out/'manifest.json',dict(protocol_sha256=sha(out/'protocol.json'),source_sha256=sources,
        files_sha256={n:sha(out/n) for n in ('slots_private.json','existing_calls_private.json','pending_private.json')},
        new_model_calls=0,combined_reservation_usd=receipt['combined_spent_or_reserved_usd']+reserve))
    dump(out/'authorization.json',dict(approved=approved,protocol_sha256=sha(out/'protocol.json'),
        cap_usd=4,planned_calls=768,original_approved_unique_slots=768,maximum_all_attempts=780,
        new_planned_calls=len(pending),destination=p['destination'],user_confirmation=confirmation))
    return dict(new_calls=len(pending),max_concurrency=2,cap_usd=4,
        total_reserved_usd=receipt['combined_spent_or_reserved_usd']+reserve,approved=approved)


def prepare_retry(parent,out):
    parent=Path(parent).resolve();p,m=checked(parent)
    if (p['mechanism']!='v32_same_input' or p['new_planned_calls']!=768
            or read_json(parent/'run_receipt.json')['status']!='stopped_no_retry'):
        raise ValueError('Only the initial stopped V3.2 package can be manually completed')
    marker=parent/'manual_completion_registration.json'
    if marker.exists():raise ValueError('A manual completion is already registered')
    calls=[json.loads(s) for s in (parent/'new_calls_private.jsonl').read_text().splitlines()]
    good,failed=partition(read_json(parent/'slots_private.json'),calls)
    existing={k:dict(source_file=str((parent/'new_calls_private.jsonl').relative_to(ROOT)),call=v) for k,v in good.items()}
    p={**p,'original_failed_ledger':str(parent.relative_to(ROOT)),
        'approved_manual_retry_slot_keys':[r['slot_key'] for r in failed],
        'original_rate_limit_failures':12,'manual_retry_round_limit':1}
    result=write_package(parent,out,p,m,existing,failed,approved=False,confirmation=None,phase='manual_twelve_429_once')
    dump(marker,dict(recovery=str(Path(out).resolve().relative_to(ROOT)),unique_slots=768,max_attempts=780))
    return result


def prepare_remainder(parent,out):
    parent=Path(parent).resolve();p,m=checked(parent);auth=read_json(parent/'authorization.json')
    if not auth['approved'] or not auth.get('user_confirmation'):raise ValueError('Explicit manual completion authorization required')
    if p.get('recovery_phase')!='manual_twelve_429_once' or read_json(parent/'run_receipt.json')['status']!='completed':
        raise ValueError('Complete the twelve manual attempts before continuing')
    calls=[json.loads(s) for s in (parent/'new_calls_private.jsonl').read_text().splitlines()]
    if len(calls)!=12 or {c['slot_key'] for c in calls}!=set(p['approved_manual_retry_slot_keys']):
        raise ValueError('Exact twelve registered retries required')
    existing=read_json(parent/'existing_calls_private.json')
    for c in calls:
        if (c.get('error') or c['finish_reason']!='stop' or c['returned_provider']!='AtlasCloud'
                or c['returned_model']!='deepseek/deepseek-v3.2'):
            raise ValueError('Manual technical completion failed; do not expand')
        response_view(c['raw_response_text'])
        existing[c['slot_key']]=dict(source_file=str((parent/'new_calls_private.jsonl').relative_to(ROOT)),call=c)
    if len(existing)!=16:raise ValueError('All original sixteen slots must now be usable')
    pending=[r for r in read_json(parent/'slots_private.json') if r['slot_key'] not in existing]
    if len(pending)!=752:raise ValueError('Only the 752 never-attempted original slots may continue')
    result=write_package(parent,out,p,m,existing,pending,approved=True,
        confirmation=auth['user_confirmation'],phase='remaining_752_after_manual_technical_pass')
    dump(Path(out)/'combined_technical_gate.json',dict(unique_slots=16,usable=16,passed=True,
        original_successes=4,manual_retries=12,truth_read=False))
    return result
