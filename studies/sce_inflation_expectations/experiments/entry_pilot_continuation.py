"""Prepare a human-approved exception after one connection failure in the gate.

Never resend failed or successful slots. Transport and ledger merge reuse the
existing continuation runner; this module changes no model or input fields.
"""
from copy import deepcopy
import json
from pathlib import Path

from .frozen_batch import ROOT, read_json, dump, sha
from .state_continuity_execution import verify, reserve


def validate_attempts(rows, intents, allkeys):
    attempted={r['reuse_key'] for r in rows}
    if len(attempted)!=len(rows) or len(rows)!=len(intents) or {r['reuse_key'] for r in intents}!=attempted:
        raise ValueError('Every prior dispatch must have one unambiguous immutable attempt')
    usable=[r for r in rows if r['technical_usable']]
    failed=[r for r in rows if not r['technical_usable']]
    if len(rows)!=16 or len(usable)!=15 or len(failed)!=1 or failed[0]['error']!='APIConnectionError':
        raise ValueError('Exception only covers 15 valid replies plus one connection failure')
    if not attempted<=allkeys or len(allkeys)!=288:
        raise ValueError('Original exact 288-slot scope required')
    return sorted(allkeys-attempted)


def prepare(parent,calls,out):
    parent,calls,out=(Path(p).resolve() for p in (parent,calls,out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh continuation folder required')
    p,m=verify(parent)
    if p['mechanism']!='entry_initialization_pilot_v1':raise ValueError('Only the authorized entry pilot')
    auth=read_json(parent/'authorization.json');cm=read_json(calls/'manifest.json');receipt=read_json(calls/'receipt.json')
    if not auth['approved'] or any(r['protocol_sha256']!=m['protocol_sha256'] for r in (auth,cm,receipt)):
        raise ValueError('Original authorization/ledger provenance required')
    if receipt['status']!='stopped_no_retry' or read_json(calls/'technical_gate.json')['passed']:
        raise ValueError('Original failed gate must stay unchanged')
    for name,digest in cm['files_sha256'].items():
        if sha(calls/name)!=digest:raise ValueError('Original ledger changed')
    rows=[json.loads(s) for s in (calls/'calls_private.jsonl').read_text().splitlines()]
    intents=[json.loads(s) for s in (calls/'dispatch_private.jsonl').read_text().splitlines()]
    nodes=read_json(ROOT/p['preparation']/'state_dependencies_private.json')
    pending=validate_attempts(rows,intents,{r['logical_reuse_key'] for r in nodes})
    if len(pending)!=272 or receipt['attempts']!=16:raise ValueError('Exact pending scope required')
    accounted=sum(r['api_reported_cost_usd'] if r['api_reported_cost_usd'] is not None else r['request_reservation_usd'] for r in rows)
    p=deepcopy(p)
    p.update(continuation_of=str(parent.relative_to(ROOT)),existing_calls=str(calls.relative_to(ROOT)),
             existing_attempts=16,new_planned_calls=272,already_spent_or_reserved_usd=accounted,
             concurrency_stages=[{'after_completed':0,'workers':32}],
             continuation_policy='Human confirmation required: retain all 16 attempts, never retry the connection failure; send only 272 never-attempted slots once. Same fatal/connection-stop rules.',
             technical_gate_exception={'original_gate_passed':False,'valid_received':15,'connection_failures':1,
                                       'original_gate_unchanged':True,'requires_explicit_human_confirmation':True},
             full_conservative_reservation_usd=accounted+len(pending)*reserve(p,p['max_prompt_bytes']))
    if p['full_conservative_reservation_usd']>p['budget_cap_usd']:raise ValueError('Original budget exceeded')
    evidence=dict(m['source_sha256'])
    for file in [Path(__file__),Path(__file__).with_name('state_continuity_continuation.py'),
                 ROOT/'scripts/continue_sce_state_continuity.py',ROOT/'scripts/prepare_sce_entry_pilot_continuation.py',
                 parent/'protocol.json',parent/'manifest.json',parent/'authorization.json',
                 calls/'manifest.json',calls/'technical_gate.json',*[calls/name for name in cm['files_sha256']]]:
        evidence[str(file.relative_to(ROOT))]=sha(file)
    out.mkdir(parents=True);dump(out/'protocol.json',p);dump(out/'pending_keys_private.json',pending)
    evidence[str((out/'pending_keys_private.json').relative_to(ROOT))]=sha(out/'pending_keys_private.json')
    dump(out/'manifest.json',{'protocol_sha256':sha(out/'protocol.json'),'source_sha256':evidence,'new_api_calls':0,
                            'human_continuation_authorization_required':True})
    return {'existing_attempts':16,'valid_replies_retained':15,'failures_not_retried':1,'never_attempted':272,
            'concurrency':32,'spent_or_reserved_usd':accounted,
            'combined_conservative_reservation_usd':p['full_conservative_reservation_usd'],'budget_cap_usd':p['budget_cap_usd']}
