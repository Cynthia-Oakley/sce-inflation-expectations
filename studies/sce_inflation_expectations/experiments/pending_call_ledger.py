"""Resume never-attempted frozen survey slots; preserve failures without retry.

This is a transport scheduler over the existing SCEOpenAILLM, not a new social
simulator. All prompts and parameters come from the authorized official-engine
package. Old raw calls remain immutable and are indexed as existing evidence.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from threading import local
from time import perf_counter

from .frozen_batch import ROOT, OFFICIAL, verify, authorize, dump, read_json, sha
from .staged_rosters import job_directory
from ..model import SCEOpenAILLM
from ..model_counterfactual import preflight
from ..news_label_trial import dotenv_values


def key(month, arm, repeat, aid):
    return hashlib.sha256(f'{month}|{arm}|{repeat}|{aid}'.encode()).hexdigest()


def prepare_fresh(parent, out):
    """Use the existing per-slot transport from the START of an authorized batch.

    All configured Core dry-runs and scope/budget checks remain mandatory. This
    scheduler records isolated failures without retrying or losing a whole job.
    """
    parent, out = Path(parent).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored call ledger required')
    manifest, protocol = verify(parent)
    authorize(parent, manifest, protocol)
    registration = parent/'call_ledger_registration.json'
    if registration.exists():
        raise ValueError('This batch already has a registered live ledger; never create a second fresh ledger')
    if (protocol.get('mechanism') not in ('price_background_qwen', 'v32_same_input')
            or protocol.get('q9_postprocessing') != 'proportional_nonnegative_v1'):
        raise ValueError('Registered normalized price-background batch required')
    slots = []
    for job in manifest['jobs']:
        audit = ROOT/'outputs/local_runs'/job['run_id']
        if audit.exists():
            raise ValueError('Fresh transport may not duplicate a previously started Core job')
        bundle = read_json(job_directory(parent, protocol, job)/f'prompts_{job["arm"]}.json')
        for aid, row in bundle['rows'].items():
            slots.append(dict(slot_key=key(job['month'],job['arm'],job['repeat'],aid),
                month=job['month'], arm=job['arm'], repeat=job['repeat'], agent_id=aid, **row))
    if len(slots) != protocol['planned_calls'] or len({s['slot_key'] for s in slots}) != len(slots):
        raise ValueError('Exact unique registered slots required')
    # Fixed outcome-blind interleaving, so arms/months do not run in long blocks.
    slots.sort(key=lambda s:hashlib.sha256(('20261021|'+s['slot_key']).encode()).hexdigest())
    if protocol.get('mechanism') == 'v32_same_input':
        gate = protocol['queue_technical_gate']
        selected = [s for month in protocol['months']
                    for s in [r for r in slots if r['month'] == month][:gate['per_month']]]
        ids = {s['slot_key'] for s in selected}
        slots = selected + [s for s in slots if s['slot_key'] not in ids]
    reserve = sum(((len(json.dumps(s['messages'],ensure_ascii=False).encode())+1024)*protocol['price_input_per_mtok']
                   +protocol['max_tokens']*protocol['price_output_per_mtok'])/1e6 for s in slots)
    if reserve > protocol['budget_cap_usd']:
        raise ValueError('Full one-attempt reservation exceeds authorized cap')
    out.mkdir(parents=True)
    dump(out/'slots_private.json',slots); dump(out/'pending_private.json',slots)
    dump(out/'existing_calls_private.json',{})
    p = {**protocol, 'call_ledger_parent':str(parent.relative_to(ROOT)),
        'existing_attempted_calls':0, 'new_planned_calls':len(slots),
        'already_spent_or_reserved_usd':0., 'remaining_conservative_reservation_usd':reserve,
        'scheduler':'Existing per-slot SCEOpenAILLM; Core dry-runs, but live calls outside Core loop.',
        'dispatch_seed':20261021, 'error_policy':'One attempt per slot. Isolated connection/timeout failures remain missing; stop on fatal errors or three consecutive transient errors. Never resend a failed slot.',
        'created_at_utc':datetime.now(timezone.utc).isoformat()}
    dump(out/'protocol.json',p)
    sources = {str((parent/n).relative_to(ROOT)):sha(parent/n)
               for n in ('manifest.json','protocol.json','authorization.json','engineering_checks.json')}
    sources.update(manifest['source_sha256'])
    for check in read_json(parent/'engineering_checks.json'):
        f=ROOT/'outputs/local_runs'/(check['run_id']+'-engineering')/'run_manifest.json'
        sources[str(f.relative_to(ROOT))]=sha(f)
    dump(out/'manifest.json',dict(protocol_sha256=sha(out/'protocol.json'),source_sha256=sources,
        files_sha256={n:sha(out/n) for n in ('slots_private.json','existing_calls_private.json','pending_private.json')},
        new_model_calls=0,combined_reservation_usd=reserve))
    auth = read_json(parent/'authorization.json')
    auth.update(protocol_sha256=sha(out/'protocol.json'),original_approved_total_calls=len(slots),new_planned_calls=len(slots))
    dump(out/'authorization.json',auth)
    # This is outside the frozen input manifest: it records the chosen live execution,
    # without altering the registered protocol or original messages.
    with registration.open('x') as handle:
        json.dump(dict(ledger=str(out.relative_to(ROOT)), protocol_sha256=manifest['protocol_sha256']),handle)
        handle.write('\n')
    return dict(new_never_attempted=len(slots),conservative_reservation_usd=reserve)


def prepare(parent, out):
    parent, out = Path(parent).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'): raise ValueError('Fresh ignored ledger required')
    manifest, protocol = verify(parent); auth = read_json(parent/'authorization.json')
    if not auth['approved'] or protocol.get('q9_postprocessing') != 'proportional_nonnegative_v1':
        raise ValueError('Authorized normalized parent required')
    slots = {}; existing = {}; evidence = {}; spent = 0.
    for job in manifest['jobs']:
        bundle = read_json(job_directory(parent,protocol,job)/f'prompts_{job["arm"]}.json')
        for aid,row in bundle['rows'].items():
            token = key(job['month'],job['arm'],job['repeat'],aid)
            if token in slots: raise ValueError('Duplicate planned slot')
            slots[token]={'slot_key':token,'month':job['month'],'arm':job['arm'],'repeat':job['repeat'],
                'agent_id':aid,**row}
        audit = ROOT/'outputs/local_runs'/job['run_id']; f = audit/'llm_calls.jsonl'
        if f.exists():
            evidence[str(f.relative_to(ROOT))]=sha(f)
            for line in f.read_text().splitlines():
                c=json.loads(line); token=key(job['month'],job['arm'],job['repeat'],c['agent_id'])
                if token in existing or c['prompt_sha256']!=slots[token]['prompt_sha256'] or c['attempt_idx']!=0:
                    raise ValueError('Duplicate or altered original call')
                if c['prompt_text']!=json.dumps(slots[token]['messages'],ensure_ascii=False):
                    raise ValueError('Original message mismatch')
                existing[token]={'source_file':str(f.relative_to(ROOT)),'call':c}
        receipt = audit/'run_manifest.json'
        if receipt.exists():
            evidence[str(receipt.relative_to(ROOT))]=sha(receipt)
            spent+=read_json(receipt)['cost']['estimated_cost_usd']
    pending=[r for token,r in slots.items() if token not in existing]
    reserve=sum(((len(json.dumps(r['messages'],ensure_ascii=False).encode())+1024)*protocol['price_input_per_mtok']
                 +protocol['max_tokens']*protocol['price_output_per_mtok'])/1e6 for r in pending)
    if len(slots)!=3456 or len(existing)!=1499 or len(pending)!=1957 or spent+reserve>16:
        raise ValueError('Known 1499 attempted /1957 never-sent scope or combined budget mismatch')
    out.mkdir();dump(out/'slots_private.json',list(slots.values()));dump(out/'existing_calls_private.json',existing)
    dump(out/'pending_private.json',pending)
    metadata=ROOT/'data/raw/mcp_checks/2026-10-20_qwen_network_recovery_free_v1/qwen_endpoints.json'
    preflight({'route_candidate':protocol['route'],'input_price_per_million':protocol['price_input_per_mtok'],
        'output_price_per_million':protocol['price_output_per_mtok']},read_json(metadata))
    p={**protocol,'provider_metadata':str(metadata.relative_to(ROOT)),
       'call_ledger_parent':str(parent.relative_to(ROOT)),'existing_attempted_calls':len(existing),
       'new_planned_calls':len(pending),'already_spent_or_reserved_usd':spent,'remaining_conservative_reservation_usd':reserve,
       'error_policy':'Every slot attempted at most once. Existing failed slots stay missing. Continue past isolated transient errors; stop on fatal error or three consecutive transient errors.',
       'scheduler':'Per-slot SCEOpenAILLM transport, unchanged frozen messages/params; not SocioVerse Core loop for the remaining requests.',
       'created_at_utc':datetime.now(timezone.utc).isoformat()}
    dump(out/'protocol.json',p)
    sources={str((parent/n).relative_to(ROOT)):sha(parent/n) for n in ['protocol.json','manifest.json','authorization.json']}
    sources.update(evidence)
    sources[str(metadata.relative_to(ROOT))]=sha(metadata)
    sources[str(Path(__file__).relative_to(ROOT))]=sha(Path(__file__))
    for n in ['model.py','model_counterfactual.py','q9_normalization.py']:
        f=ROOT/'studies/sce_inflation_expectations'/n;sources[str(f.relative_to(ROOT))]=sha(f)
    dump(out/'manifest.json',{'protocol_sha256':sha(out/'protocol.json'),'source_sha256':sources,
        'files_sha256':{n:sha(out/n) for n in ['slots_private.json','existing_calls_private.json','pending_private.json']},
        'new_model_calls':0,'combined_reservation_usd':spent+reserve})
    dump(out/'authorization.json',{'approved':True,'protocol_sha256':sha(out/'protocol.json'),
        'original_approved_total_calls':3456,'cap_usd':16,'new_planned_calls':len(pending),
        'destination':protocol['destination'],'user_confirmation':auth['user_confirmation'],
        'basis':'Same explicitly approved scope; only never-attempted slots. No retry of 14 failed calls, no new fields or budget.'})
    return {'existing_attempts':len(existing),'new_never_attempted':len(pending),'combined_reserved_usd':spent+reserve}


def prepare_remaining(previous, out, limit=128):
    """Fresh short chunk, excluding EVERY earlier attempt including failures."""
    previous,out=Path(previous).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs') or not 1<=limit<=256:
        raise ValueError('Fresh bounded short chunk required')
    old=read_json(previous/'manifest.json');p=read_json(previous/'protocol.json');receipt=read_json(previous/'run_receipt.json')
    if sha(previous/'protocol.json')!=old['protocol_sha256'] or receipt['status'] not in ('completed','stopped_no_retry'):
        raise ValueError('Finished previous transport process required')
    for n,h in old['files_sha256'].items():
        if sha(previous/n)!=h:raise ValueError('Previous slot data changed')
    sources={n:h for n,h in old['source_sha256'].items() if not n.endswith('.py')}
    for n,h in sources.items():
        if sha(ROOT/n)!=h:raise ValueError('Previous raw evidence changed')
    existing=read_json(previous/'existing_calls_private.json');slots=read_json(previous/'slots_private.json')
    f=previous/'new_calls_private.jsonl';sources[str(f.relative_to(ROOT))]=sha(f)
    for line in f.read_text().splitlines():
        c=json.loads(line)
        if c['slot_key'] in existing:raise ValueError('Previous ledger duplicated a slot')
        existing[c['slot_key']]={'source_file':str(f.relative_to(ROOT)),'call':c}
    pending=[r for r in slots if r['slot_key'] not in existing]
    if not pending or len(existing)+len(pending)!=p['planned_calls']:raise ValueError('Nonempty remaining original scope required')
    reserve=sum(((len(json.dumps(r['messages'],ensure_ascii=False).encode())+1024)*p['price_input_per_mtok']
                  +p['max_tokens']*p['price_output_per_mtok'])/1e6 for r in pending)
    spent=receipt['combined_spent_or_reserved_usd']
    if spent+reserve>p['budget_cap_usd']:raise ValueError('Original combined budget exceeded')
    out.mkdir();dump(out/'slots_private.json',slots);dump(out/'existing_calls_private.json',existing);dump(out/'pending_private.json',pending[:limit])
    p={**p,'previous_call_ledger':str(previous.relative_to(ROOT)),'existing_attempted_calls':len(existing),
       'new_planned_calls':len(pending[:limit]),'all_remaining_before_chunk':len(pending),
       'remaining_after_chunk':max(0,len(pending)-limit),'already_spent_or_reserved_usd':spent,
       'remaining_conservative_reservation_usd':reserve,'created_at_utc':datetime.now(timezone.utc).isoformat()}
    dump(out/'protocol.json',p)
    for n in ['protocol.json','manifest.json','run_receipt.json','authorization.json']:
        sources[str((previous/n).relative_to(ROOT))]=sha(previous/n)
    sources[str(Path(__file__).relative_to(ROOT))]=sha(Path(__file__))
    for n in ['model.py','model_counterfactual.py','q9_normalization.py']:
        q=ROOT/'studies/sce_inflation_expectations'/n;sources[str(q.relative_to(ROOT))]=sha(q)
    dump(out/'manifest.json',{'protocol_sha256':sha(out/'protocol.json'),'source_sha256':sources,
        'files_sha256':{n:sha(out/n) for n in ['slots_private.json','existing_calls_private.json','pending_private.json']},
        'combined_reservation_usd':spent+reserve,'new_model_calls':0})
    a=read_json(previous/'authorization.json');a.update(protocol_sha256=sha(out/'protocol.json'),new_planned_calls=len(pending[:limit]))
    dump(out/'authorization.json',a)
    return {'already_attempted':len(existing),'new_chunk':len(pending[:limit]),'remaining_after_chunk':p['remaining_after_chunk']}


def run(folder, workers=12):
    folder=Path(folder).resolve();m=read_json(folder/'manifest.json');p=read_json(folder/'protocol.json');a=read_json(folder/'authorization.json')
    if (not a.get('approved') or a['protocol_sha256']!=sha(folder/'protocol.json')
            or m['protocol_sha256']!=sha(folder/'protocol.json')
            or a['cap_usd']!=p['budget_cap_usd'] or a['destination']!=p['destination']
            or not 1<=workers<=p.get('max_workers',16)):
        raise ValueError('Matching authorization and bounded workers required')
    for name,digest in m['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Pinned source changed')
    for name,digest in m['files_sha256'].items():
        if sha(folder/name)!=digest:raise ValueError('Frozen ledger changed')
    if (folder/'execution_started.json').exists():raise ValueError('No automatic ledger restart')
    pending=read_json(folder/'pending_private.json')
    gate=p.get('queue_technical_gate')
    if gate and (p.get('existing_attempted_calls') != 0 or gate['planned_calls'] >= len(pending)):
        raise ValueError('Technical gate is only valid at the start of a fresh complete queue')
    directory=read_json(ROOT/p['provider_metadata']);preflight({'route_candidate':p['route'],
        'input_price_per_million':p['price_input_per_mtok'],'output_price_per_million':p['price_output_per_mtok']},directory)
    values=dotenv_values(OFFICIAL/'.env');secret=os.environ.get('OPENROUTER_API_KEY') or values.get('OPENROUTER_API_KEY')
    if not secret:raise ValueError('OpenRouter key missing')
    os.environ['SV_LLM_BASE_URL']=p['destination'];os.environ['SV_LLM_API_KEY']=secret
    dump(folder/'execution_started.json',{'at_utc':datetime.now(timezone.utc).isoformat(),'max_new_calls':len(pending),'automatic_retries':0})
    state=local();started=perf_counter();count=0;reported=0.;accounted=p['already_spent_or_reserved_usd'];consecutive=0;halt=False
    def one(slot):
        if not hasattr(state,'llm'):
            state.llm=SCEOpenAILLM(model=p['model'],temperature=p['temperature'],max_tokens=p['max_tokens'],
                extra_body=p['request_extra_body'],response_format='json_object',timeout_s=p.get('timeout_s',60))
        size=len(json.dumps(slot['messages'],ensure_ascii=False).encode())
        bound=((size+1024)*p['price_input_per_mtok']+p['max_tokens']*p['price_output_per_mtok'])/1e6
        row={k:slot[k] for k in ['slot_key','month','arm','repeat','agent_id','prompt_sha256']}
        row.update(prompt_text=json.dumps(slot['messages'],ensure_ascii=False),attempt_idx=0,
            requested_model=p['model'],temperature=p['temperature'],max_tokens=p['max_tokens'],
            extra_body=p['request_extra_body'],response_format='json_object',timestamp_utc=datetime.now(timezone.utc).isoformat(),
            returned_model=None,returned_provider=None,finish_reason=None,usage=None,raw_response_text='',error=None,
            api_reported_cost_usd=None,request_reservation_usd=bound,error_http_status=None)
        fatal=False
        try:
            reply,latency=state.llm.chat(slot['messages']);choice=reply.choices[0];usage=getattr(reply,'usage',None)
            text=choice.message.content or ''
            row.update(returned_model=reply.model,returned_provider=getattr(reply,'provider',None),
                finish_reason=choice.finish_reason,raw_response_text=text,latency_ms=latency,request_id=reply.id,
                usage=usage.model_dump() if usage else None,api_reported_cost_usd=getattr(usage,'cost',None))
            if row['returned_model']!=p['model'] or row['returned_provider']!=p.get('expected_provider','DeepInfra'):
                row['error']='Locked model/provider mismatch';fatal=True
            fee=row['api_reported_cost_usd']
            if fee is not None and (type(fee) not in (int,float) or not math.isfinite(fee) or fee<0 or fee>bound+1e-9):
                row['error']='Invalid/excess reported charge';fatal=True
        except Exception as exc:
            row['error']=type(exc).__name__+': '+str(exc).replace(secret,'<redacted>')[:500]
            row['error_http_status']=getattr(exc,'status_code',None)
            fatal=type(exc).__name__ not in ('APIConnectionError','APITimeoutError')
        row['raw_response_sha256']=hashlib.sha256(row['raw_response_text'].encode()).hexdigest()
        row['finished_at_utc']=datetime.now(timezone.utc).isoformat()
        return row,fatal
    cursor=0;gate_rows=[];gate_checked=False
    phase_limit=gate['planned_calls'] if gate else len(pending)
    with (folder/'new_calls_private.jsonl').open('x') as log, ThreadPoolExecutor(max_workers=workers) as pool:
        active={}
        while cursor<phase_limit and len(active)<workers:
            r=pending[cursor];active[pool.submit(one,r)]=r;cursor+=1
        while active:
            done,_=wait(active,return_when=FIRST_COMPLETED)
            for future in done:
                active.pop(future);row,fatal=future.result();log.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');log.flush();count+=1
                fee=row['api_reported_cost_usd'];charge=fee if fee is not None else row['request_reservation_usd']
                accounted+=charge;reported+=fee or 0.;consecutive=consecutive+1 if row['error'] else 0
                halt|=fatal or consecutive>=3 or accounted>p['budget_cap_usd']
                if gate and not gate_checked:gate_rows.append(row)
                if count%100==0:print(f'{count}/{len(pending)} new slots, reported ${reported:.4f}',flush=True)
            if gate and not gate_checked and not active and cursor==phase_limit:
                from ..q9_normalization import response_view,response_point
                usable=0
                for row in gate_rows:
                    try:
                        response_view(row['raw_response_text'])
                        point=response_point(row['raw_response_text'])
                        ok=(not row['error'] and row['finish_reason']=='stop' and point is not None)
                    except (ValueError,TypeError):ok=False
                    usable+=bool(ok)
                gate_checked=True
                passed=usable/len(gate_rows)>=gate['minimum_usable_fraction'] and not halt
                dump(folder/'queue_technical_gate.json',dict(calls=len(gate_rows),usable=usable,
                    passed=passed,normalized_q9_allowed=True,new_extra_calls=0,truth_read=False))
                halt|=not passed
                phase_limit=len(pending)
                print(f'Technical gate {usable}/{len(gate_rows)}: '+('passed' if passed else 'stopped'),flush=True)
            while not halt and cursor<phase_limit and len(active)<workers:
                r=pending[cursor];active[pool.submit(one,r)]=r;cursor+=1
    receipt={'status':'completed' if count==len(pending) else 'stopped_no_retry','new_calls':count,
        'original_attempts':p['existing_attempted_calls'],'api_reported_new_cost_usd':reported,
        'combined_spent_or_reserved_usd':accounted,'cap_usd':p['budget_cap_usd'],'seconds':perf_counter()-started,'automatic_retries':0}
    receipt.update(max_concurrent_requests=workers,technical_gate_completed=gate_checked if gate else None)
    dump(folder/'run_receipt.json',receipt);print(json.dumps(receipt,indent=2),flush=True)
    return receipt
