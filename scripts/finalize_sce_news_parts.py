#!/usr/bin/env python3
"""Accept a finished news chain and verify no duplicate paid requests or relabeling."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.news_label_trial import prior_call_chain,guarded_payload
from studies.sce_inflation_expectations.news_evidence_suffix_adapter import validate


def finalize(inputs,run,out):
    inputs,run,out=map(Path,(inputs,run,out))
    if out.exists():raise ValueError('Fresh acceptance output required')
    plan=json.loads((inputs/'summary.json').read_text());receipt=json.loads((run/'chain_receipt.json').read_text())
    if receipt['status']!='completed':raise ValueError('Complete chain required before acceptance')
    labels={};calls=0;format_stops=0;cost=0.;repairs=Counter();source={}
    semantic=('decision','topics','scope','claim_type','reason_zh')
    for part in plan['parts']:
        folder=Path(receipt['part_ledgers'][str(part['part'])])
        state=json.loads((folder/'state.json').read_text())
        requests={r['batch_id']:r for r in map(json.loads,(ROOT/part['folder']/'requests_prepared.jsonl').read_text().splitlines())}
        if state['status']!='completed':raise ValueError('Incomplete final part')
        records=prior_call_chain(folder)
        if len(records)!=len(requests) or len({r['batch_id'] for _,r in records})!=len(records):
            raise ValueError('Every frozen request must have exactly one remote attempt')
        stored=[json.loads(line)['label'] for line in (folder/'labels.jsonl').read_text().splitlines()]
        actual={r['article_id']:r for r in stored}
        if len(actual)!=len(stored):raise ValueError('Duplicate derived labels')
        replay={}
        for directory,call in records:
            if call.get('http_status')!=200:raise ValueError('This complete chain must have a saved HTTP200 response per request')
            path=directory/f"response_{call['batch_id']:03d}.json";raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=call['response_sha256']:raise ValueError('Raw response changed')
            response=json.loads(raw)
            derived,changes=validate(response['choices'][0]['message']['content'],guarded_payload(requests[call['batch_id']]))
            repairs.update(r['kind'] for r in changes)
            for r in derived:
                if r['article_id'] in replay:raise ValueError('Cross-batch duplicate news ID')
                replay[r['article_id']]=r
            calls+=1;format_stops+=bool(call.get('error_type'))
        if set(replay)!=set(actual) or any(any(actual[k].get(f)!=replay[k].get(f) for f in semantic) for k in actual):
            raise ValueError('Stored classifications differ from original received classifications')
        for key,row in actual.items():
            if key in labels:raise ValueError('Cross-part article duplicate')
            labels[key]=row
        cost+=state['spent_or_reserved_upper_usd']
        source[str(folder/'state.json')]=hashlib.sha256((folder/'state.json').read_bytes()).hexdigest()
    if len(labels)!=plan['unique_new_articles'] or calls!=plan['new_batches'] or cost>plan['proposed_total_cap_usd']:
        raise ValueError('Expected exact articles/request count and total budget')
    out.mkdir(parents=True)
    (out/'labels.jsonl').write_text(''.join(json.dumps({'label':labels[k]},ensure_ascii=False)+'\n' for k in sorted(labels)))
    result=dict(status='accepted_complete',completed_at_utc=datetime.now(timezone.utc).isoformat(),
        accepted_articles=len(labels),unique_remote_requests=calls,automatic_retries=0,classification_changes=0,
        transport_errors=0,original_format_stops_recovered_offline=format_stops,api_calls_for_acceptance=0,
        decisions=dict(Counter(r['decision'] for r in labels.values())),repair_counts=dict(repairs),
        usage_cost_estimate_peak_uncached_usd=cost,cap_usd=plan['proposed_total_cap_usd'],
        source_sha256=source,receipt=str(run/'chain_receipt.json'),
        note='Same original model classifications; unverifiable quotes explicitly removed in derived metadata. Raw replies and initial format failures retained. Cost is a token-based estimate, not account billing.')
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inputs','run','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(finalize(a.inputs,a.run,a.out),ensure_ascii=False,indent=2))
