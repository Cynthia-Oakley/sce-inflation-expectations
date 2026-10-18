#!/usr/bin/env python3
"""Audit a completed fixed Event probe and hash-linked official source archive."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.event_probe_audit import audit_payload


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--official', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists(): raise ValueError('Use a fresh audit output directory')
    read = lambda p: json.loads(p.read_text())
    p = read(args.folder/'protocol.json'); a = read(args.folder/'authorization.json'); c = read(args.folder/'completion.json')
    assert a['approved'] and sha(args.folder/'protocol.json') == a['protocol_sha256'] == c['protocol_sha256']
    assert c['attempts'] == p['planned_calls'] == 12 and c['automatic_retries'] == 0
    ledger = [json.loads(line) for line in (args.folder/'ledger.jsonl').read_text().splitlines()]
    completed = {r['job_id']: r for r in ledger if r['event'] == 'attempt_completed'}
    assert len(completed) == 12 and len([r for r in ledger if r['event'] == 'attempt_started']) == 12
    rows, sources = [], {}
    for job in p['jobs']:
        path = args.folder/('raw_'+job['job_id']+'.json')
        assert sha(path) == completed[job['job_id']]['raw_sha256']
        payload = read(path); arg = job['arguments']
        expected = f"{arg['year']:04d}-{arg['month']:02d}"
        assert payload['target_date'] == expected and payload['source_name'] == arg['source']
        month = expected.replace('-', '')
        env = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'/month/'environment.json'
        as_of = read(env)['provider_args']['targets'][0]['as_of']
        row = audit_payload(arg['source'], payload, as_of)
        row.update(job_id=job['job_id'], raw_sha256=sha(path)); rows.append(row)
        sources[str(path.resolve().relative_to(ROOT))] = sha(path)
    official = read(args.official/'manifest.json')
    for item in official['records']:
        if item['status'] == 'archived':
            assert sha(args.official/item['file']) == item['sha256']
    result = {'status': 'completed_twelve_event_probe_and_content_audit', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'attempts': 12, 'top_level_status_counts': dict(Counter(r['tool_status'] for r in rows)),
              'classification_counts': dict(Counter(r['classification'] for r in rows)),
              'maximum_estimated_charge_not_bill_usd': c['maximum_estimated_charge_usd_not_bill'],
              'approved_cap_usd': a['cap_usd'], 'automatic_retries': 0, 'new_simulation_calls': 0,
              'started_at_utc': c['started_at_utc'], 'finished_at_utc': c['finished_at_utc'],
              'automatic_admissions': 0, 'rows': rows,
              'official_archive_records': official['records'],
              'source_sha256': {**sources, str((args.folder/'protocol.json').resolve().relative_to(ROOT)): sha(args.folder/'protocol.json'),
                                str((args.folder/'ledger.jsonl').resolve().relative_to(ROOT)): sha(args.folder/'ledger.jsonl')},
              'note': 'No missing value is replaced by zero. Direct official releases are separately curated after this source-level screen; this does not certify the simulation as strict B.'}
    args.out.mkdir(parents=True)
    (args.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','attempts','top_level_status_counts','classification_counts','maximum_estimated_charge_not_bill_usd')},ensure_ascii=False))


if __name__ == '__main__':
    main()
