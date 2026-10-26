"""Manual continuation of never-attempted slots under the original approval.

Never changes or restarts an old ledger; every failed attempt remains existing.
No network access here. Shared dispatch and evaluation are unchanged.
"""
from pathlib import Path
from datetime import datetime,timezone

from .frozen_batch import ROOT,read_json,dump,sha


def prepare(previous,out):
    previous,out=Path(previous).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh continuation ledger required')
    p=read_json(previous/'protocol.json');m=read_json(previous/'manifest.json');r=read_json(previous/'run_receipt.json')
    a=read_json(previous/'authorization.json')
    if (p['mechanism']!='v32_news_matching' or sha(previous/'protocol.json')!=m['protocol_sha256']
            or r['status']!='stopped_no_retry' or not a['approved'] or a['cap_usd']!=15
            or a['protocol_sha256']!=m['protocol_sha256']):raise ValueError('Stopped authorized news ledger required')
    for k in ('source_sha256','files_sha256'):
        for name,h in m[k].items():
            path=ROOT/name if k=='source_sha256' else previous/name
            if sha(path)!=h:raise ValueError('Frozen evidence changed: '+name)
    allslots=read_json(previous/'slots_private.json');oldpending=read_json(previous/'pending_private.json')
    existing=read_json(previous/'existing_calls_private.json');aliases=read_json(previous/p['alias_file'])
    log=previous/'new_calls_private.jsonl';attempted={}
    for c in [__import__('json').loads(line) for line in log.read_text().splitlines() if line.strip()]:
        key=c['slot_key']
        if key in existing or key in attempted:raise ValueError('Duplicate attempt')
        attempted[key]=c;existing[key]=dict(source_file=str(log.relative_to(ROOT)),call=c)
    if len(attempted)!=r['new_calls']:raise ValueError('Attempt count mismatch')
    pending=[s for s in oldpending if s['slot_key'] not in attempted]
    if not pending or len(pending)+len(attempted)!=p['new_planned_calls']:
        raise ValueError('Only exact never-attempted suffix may continue')
    if set(aliases)&set(existing) or len(existing)+len(pending)+len(aliases)!=p['planned_calls']:
        raise ValueError('Complete original scope and immutable aliases required')
    import json
    reserve=sum(((len(json.dumps(s['messages'],ensure_ascii=False).encode())+1024)*p['price_input_per_mtok']
                 +p['max_tokens']*p['price_output_per_mtok'])/1e6 for s in pending)
    spent=r['combined_spent_or_reserved_usd']
    if spent+reserve>15:raise ValueError('Original combined cap exceeded')
    out.mkdir(parents=True)
    dump(out/'slots_private.json',allslots);dump(out/'pending_private.json',pending)
    dump(out/'existing_calls_private.json',existing);dump(out/'aliases_private.json',aliases)
    protocol=dict(p,previous_call_ledger=str(previous.relative_to(ROOT)),existing_attempted_calls=len(existing),
        new_planned_calls=len(pending),already_spent_or_reserved_usd=spent,
        remaining_conservative_reservation_usd=reserve,queue_technical_gate=None,
        technical_gate_inherited_from=str((previous/'queue_technical_gate.json').relative_to(ROOT)),
        continuation_basis='Manual continuation after free HTTP200 network check. Only never-attempted original slots; no failed request retried.',
        created_at_utc=datetime.now(timezone.utc).isoformat())
    dump(out/'protocol.json',protocol)
    sources=dict(m['source_sha256'])
    for name in ('protocol.json','manifest.json','authorization.json','run_receipt.json','queue_technical_gate.json','new_calls_private.jsonl'):
        path=previous/name;sources[str(path.relative_to(ROOT))]=sha(path)
    sources[str(Path(__file__).relative_to(ROOT))]=sha(__file__)
    dump(out/'manifest.json',dict(protocol_sha256=sha(out/'protocol.json'),source_sha256=sources,
        files_sha256={name:sha(out/name) for name in ('slots_private.json','pending_private.json','existing_calls_private.json','aliases_private.json')},
        combined_reservation_usd=spent+reserve,new_model_calls=0))
    a.update(protocol_sha256=sha(out/'protocol.json'),new_planned_calls=len(pending),
        basis='Same explicit3658-new-request/$15 approval; retain every prior failed attempt, send only453 original never-attempted slots.')
    dump(out/'authorization.json',a)
    receipt=read_json(previous/'preparation_receipt.json')
    receipt.update(continuation_never_attempted=len(pending),prior_attempted_new_calls=len(attempted),
        prior_failed_calls_retained=sum(bool(c.get('error')) for c in attempted.values()),
        combined_conservative_reserved_usd=spent+reserve)
    dump(out/'preparation_receipt.json',receipt)
    return dict(never_attempted=len(pending),failed_requests_retried=0,combined_reserved_usd=spent+reserve,cap_usd=15)
