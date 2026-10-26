#!/usr/bin/env python3
"""Once-launch frozen public-news parts; stop the chain on any incomplete part."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations import news_label_trial as base
from studies.sce_inflation_expectations.news_evidence_suffix_adapter import validate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--authorization-note')
    p.add_argument('--prior-chain',type=Path,help='Reuse finished parts and only never-attempted requests; no API retries')
    a=p.parse_args();summary=json.loads((a.inputs/'summary.json').read_text())
    parts=summary['parts'];cap=sum(x['package_cap_usd'] for x in parts)
    if cap!=summary['proposed_total_cap_usd'] or any(x['package_cap_usd']!=.25 for x in parts):
        raise ValueError('Original disjoint part budgets required')
    if a.out.exists():raise ValueError('Fresh chain output required; never auto-restart')
    if a.execute and not a.authorization_note:raise ValueError('Explicit batch authorization note required')
    prior_map={}
    if a.prior_chain:
        prior_receipt=json.loads((a.prior_chain/'chain_receipt.json').read_text())
        if prior_receipt['status'] not in ('stopped_no_retry','failed'):
            raise ValueError('Only a stopped chain may be continued')
        prior_map=prior_receipt.get('part_ledgers',{})
    # All parts pass the existing schema/hash/cost checks before any paid call.
    for part in parts:
        base.main(['--inputs',str(ROOT/part['folder']),'--out',str(a.out/f"part_{part['part']:02d}")])
    if not a.execute:return
    a.out.mkdir(parents=True)
    snapshot=a.out/'source_snapshot';snapshot.mkdir()
    source_root=Path(__file__).resolve().parents[1]
    for path in [Path(__file__),source_root/'studies/sce_inflation_expectations/news_evidence_suffix_adapter.py',
                 source_root/'studies/sce_inflation_expectations/news_label_quote_adapter.py']:
        (snapshot/path.name).write_bytes(path.read_bytes())
    record=dict(status='running',cap_usd=cap,parts_completed=0,automatic_retries=0,
        authorization_note=a.authorization_note,parts=parts,
        execution_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        prior_chain=str(a.prior_chain) if a.prior_chain else None,part_ledgers={})
    base.validate_with_evidence_shortening=validate
    try:
        for part in parts:
            folder=a.out/f"part_{part['part']:02d}"
            previous=(Path(prior_map[str(part['part'])]) if str(part['part']) in prior_map else
                      a.prior_chain/f"part_{part['part']:02d}") if a.prior_chain else None
            if previous and (previous/'state.json').exists():
                prior_state=json.loads((previous/'state.json').read_text())
                expected=json.loads((ROOT/part['folder']/'summary.json').read_text())
                if prior_state['input_request_file_sha256']!=expected['request_file_sha256']:
                    raise ValueError('Prior part belongs to a different frozen input')
                if prior_state['status']=='completed':
                    record['part_ledgers'][str(part['part'])]=str(previous.resolve())
                    record['parts_completed']+=1;continue
            argv=['--inputs',str(ROOT/part['folder']),'--out',str(folder),'--execute',
                  '--authorization-note',a.authorization_note]
            if previous and (previous/'state.json').exists():argv+=['--prior-run',str(previous)]
            base.main(argv)
            record['part_ledgers'][str(part['part'])]=str(folder.resolve())
            state=json.loads((folder/'state.json').read_text())
            if state['status']!='completed':
                record.update(status='stopped_no_retry',stopped_part=part['part']);break
            record['parts_completed']+=1
        else:record['status']='completed'
    except Exception as exc:
        record.update(status='failed',error_type=type(exc).__name__);raise
    finally:
        paths={Path(v)/'state.json' for v in record['part_ledgers'].values()}
        paths.update(a.out.glob('part_*/state.json'))
        record['reported_or_reserved_usd']=sum(json.loads(f.read_text()).get('spent_or_reserved_upper_usd',0) for f in paths)
        (a.out/'chain_receipt.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
