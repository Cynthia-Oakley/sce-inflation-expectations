"""Reuse exact archived calls and aliases; dispatch stays in the shared queue."""
from copy import deepcopy
import json
from pathlib import Path

from .frozen_batch import ROOT, verify, dump, read_json, sha
from .pending_call_ledger import key

PARAMETERS=('model','route','temperature','max_tokens','request_extra_body','expected_provider')


def reusable_call(slot,call,protocol,old_protocol):
    """Outcome-blind: failed attempts are reusable too, never silently retried."""
    return (all(protocol[k]==old_protocol[k] for k in PARAMETERS)
        and call['month']==slot['month'] and call['agent_id']==slot['agent_id']
        and call['repeat']==slot['repeat'] and call['attempt_idx']==0
        and call['prompt_sha256']==slot['prompt_sha256']
        and call['prompt_text']==json.dumps(slot['messages'],ensure_ascii=False)
        and call['temperature']==protocol['temperature'] and call['max_tokens']==protocol['max_tokens']
        and call['extra_body']==protocol['request_extra_body'])


def expand_aliases(calls,aliases):
    """Derived evaluation view; no raw file or archived response is modified."""
    result=dict(calls)
    for alias,canonical in aliases.items():
        if alias in result or canonical not in calls or canonical in aliases:
            raise ValueError('Aliases must refer directly to one actual call, without cycles')
        result[alias]=calls[canonical]
    return result


def prepare_ledger(parent,out):
    parent,out=Path(parent).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh private ledger required')
    manifest,p=verify(parent)
    if p['mechanism']!='v32_news_matching':raise ValueError('News-specific adapter required')
    checks=read_json(parent/'engineering_checks.json')
    if len(checks)!=len(manifest['jobs']) or {c['job_index'] for c in checks}!=set(range(len(manifest['jobs']))):
        raise ValueError('All configured Core dry-runs required before ledger preparation')
    sources={str((parent/'manifest.json').relative_to(ROOT)):sha(parent/'manifest.json'),
        str((parent/'protocol.json').relative_to(ROOT)):sha(parent/'protocol.json')}
    sources.update(manifest['source_sha256'])
    sources[str((parent/'engineering_checks.json').relative_to(ROOT))]=sha(parent/'engineering_checks.json')
    for c in checks:
        job=manifest['jobs'][c['job_index']]
        path=ROOT/'outputs/local_runs'/(job['run_id']+'-engineering')/'run_manifest.json'
        receipt=read_json(path)
        if (c['exit_code'] or c['run_id']!=job['run_id'] or receipt['status']!='completed'
                or receipt['protocol_sha256']!=manifest['protocol_sha256'] or receipt['llm_kind']!='scripted'
                or receipt['cost']['call_count']!=0 or receipt.get('actual_input_hashes_match') is not True):
            raise ValueError('Invalid outcome-free official Core dry-run receipt')
        sources[str(path.relative_to(ROOT))]=sha(path)
    archived={}
    for name in p['source_call_ledgers']:
        folder=ROOT/name;old=read_json(folder/'protocol.json')
        if read_json(folder/'run_receipt.json')['status']!='completed':raise ValueError('Only completed archives')
        for name2 in ('protocol.json','manifest.json','run_receipt.json','new_calls_private.jsonl'):
            path=folder/name2;sources[str(path.relative_to(ROOT))]=sha(path)
        for line in (folder/'new_calls_private.jsonl').read_text().splitlines():
            c=json.loads(line);token=(c['month'],c['agent_id'],c['repeat'],c['prompt_sha256'])
            if token in archived:raise ValueError('Ambiguous archived control call')
            archived[token]=(c,old,str((folder/'new_calls_private.jsonl').relative_to(ROOT)))
    slots=[];existing={};pending=[];aliases={};seen={};reuse_errors=0
    for job in manifest['jobs']:
        bundle=read_json(parent/str(job['month'])/f'prompts_{job["arm"]}.json')
        for aid,row in bundle['rows'].items():
            s=dict(slot_key=key(job['month'],job['arm'],job['repeat'],aid),month=job['month'],
                arm=job['arm'],repeat=job['repeat'],agent_id=aid,**row)
            slots.append(s);token=(s['month'],aid,s['repeat'],s['prompt_sha256'])
            if token in archived:
                call,old,path=archived[token]
                if not reusable_call(s,call,p,old):raise ValueError('Archived parameters or exact text mismatch')
                existing[s['slot_key']]=dict(call=call,source_file=path)
                reuse_errors+=bool(call.get('error'))
            elif token in seen:
                canonical=seen[token]
                if s['messages']!=canonical['messages']:raise ValueError('Hash collision')
                aliases[s['slot_key']]=canonical['slot_key']
            else:
                seen[token]=s;pending.append(s)
    if len(slots)!=p['planned_calls']:raise ValueError('All configured slots required')
    pending.sort(key=lambda s:sha_string('20261022|'+s['slot_key']))
    selected=[]
    # Four genuinely new calls per month. Shared results never masquerade as
    # fresh technical tests; gate uses formatting, not truth or fitting scores.
    for month in p['months']:
        selected.extend([s for s in pending if s['month']==month][:4])
    picked={s['slot_key'] for s in selected};pending=selected+[s for s in pending if s['slot_key'] not in picked]
    reserve=sum(((len(json.dumps(s['messages'],ensure_ascii=False).encode())+1024)*p['price_input_per_mtok']
                 +p['max_tokens']*p['price_output_per_mtok'])/1e6 for s in pending)
    estimate=sum((len(json.dumps(s['messages'],ensure_ascii=False).encode())/4*p['price_input_per_mtok']
                  +300*p['price_output_per_mtok'])/1e6 for s in pending)
    if reserve>p['budget_cap_usd']:raise ValueError('Unique new-call reservations exceed proposed budget')
    out.mkdir(parents=True)
    dump(out/'slots_private.json',slots);dump(out/'pending_private.json',pending)
    dump(out/'existing_calls_private.json',existing);dump(out/'aliases_private.json',aliases)
    protocol=dict(p,call_ledger_parent=str(parent.relative_to(ROOT)),new_planned_calls=len(pending),
        existing_attempted_calls=len(existing),already_spent_or_reserved_usd=0.,
        remaining_conservative_reservation_usd=reserve,alias_file='aliases_private.json',
        queue_technical_gate=dict(planned_calls=len(selected),minimum_usable_fraction=.95),
        error_policy='One new attempt per unique slot. Retain prior failures and never retry. Shared scheduler stop rules.',
        scheduler='Shared per-slot SCEOpenAILLM; Core dry-runs; exact input aliases share one response, not extra independent generations.')
    dump(out/'protocol.json',protocol)
    dump(out/'manifest.json',dict(protocol_sha256=sha(out/'protocol.json'),source_sha256=sources,
        files_sha256={n:sha(out/n) for n in ('slots_private.json','pending_private.json','existing_calls_private.json','aliases_private.json')},
        combined_reservation_usd=reserve,new_model_calls=0))
    dump(out/'authorization.json',dict(approved=False,protocol_sha256=sha(out/'protocol.json'),
        cap_usd=p['budget_cap_usd'],destination=p['destination'],new_planned_calls=len(pending),user_confirmation=None))
    receipt=dict(status='prepared_no_authorization_no_calls',new_api_calls=0,total_comparison_slots=len(slots),
        archived_reused_slots=len(existing),archived_error_slots_retained=reuse_errors,within_batch_alias_slots=len(aliases),
        archived_unique_calls_reused=len({(e['source_file'],e['call']['month'],e['call']['agent_id'],e['call']['repeat']) for e in existing.values()}),
        new_unique_requests=len(pending),estimated_new_cost_usd=estimate,conservative_new_reservation_usd=reserve,
        proposed_hard_cap_usd=p['budget_cap_usd'],technical_calls=len(selected),months=p['months'],n_by_month=p['n_by_month'])
    dump(out/'preparation_receipt.json',receipt);return receipt


def sha_string(value):
    import hashlib
    return hashlib.sha256(value.encode()).hexdigest()
