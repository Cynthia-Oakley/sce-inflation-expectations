#!/usr/bin/env python3
"""Archive a fixed small list of free official evidence; never calls an MCP/LLM."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

SOURCES = {
    'ustr_agenda_20250303.html': 'https://ustr.gov/about-us/policy-offices/press-office/press-releases/2025/march/us-trade-representative-announces-2025-trade-policy-agenda',
    'ustr_eu_statement_20250312.html': 'https://ustr.gov/about-us/policy-offices/press-office/press-releases/2025/march/ambassador-jamieson-greer-issues-statement-european-unions-announced-retaliatory-tariffs',
    'umich_202008_final.pdf': 'https://data.sca.isr.umich.edu/fetchdoc.php?docid=65950',
    'umich_202206_preliminary.pdf': 'https://data.sca.isr.umich.edu/fetchdoc.php?docid=70216',
    'umich_202502_final.pdf': 'https://data.sca.isr.umich.edu/fetchdoc.php?docid=78142',
    'audit_only_umich_202009_final.pdf': 'https://data.sca.isr.umich.edu/fetchdoc.php?docid=66156',
    'audit_only_umich_202206_final.pdf': 'https://data.sca.isr.umich.edu/fetchdoc.php?docid=70332',
    'audit_only_umich_202503_final.pdf': 'https://data.sca.isr.umich.edu/fetchdoc.php?docid=78363',
    'audit_only_umich_release_calendar.pdf': 'https://data.sca.isr.umich.edu/fetchdoc.php?docid=75443',
    'umich_usage_agreement.html': 'https://data.sca.isr.umich.edu/agreement.php',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    records = []
    for name, url in SOURCES.items():
        record = {'file': name, 'source_url': url, 'fetched_at_utc': datetime.now(timezone.utc).isoformat()}
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 research-source-archive'}), timeout=40) as response:
                body = response.read(); record['content_type'] = response.headers.get('Content-Type')
            if name.endswith('.pdf') and not body.startswith(b'%PDF'):
                raise ValueError('Expected a public PDF')
            (args.out/name).write_bytes(body)
            record.update(status='archived', bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            if name.endswith('.pdf'):
                from pypdf import PdfReader
                reader = PdfReader(args.out/name)
                (args.out/(name+'.txt')).write_text('\n'.join(p.extract_text() or '' for p in reader.pages))
                record['pages'] = len(reader.pages)
        except Exception as exc:
            record.update(status='error_no_retry', error_type=type(exc).__name__, http_status=getattr(exc, 'code', None))
        records.append(record)
        (args.out/'manifest.json').write_text(json.dumps({'records': records, 'paid_calls': 0, 'automatic_retries': 0}, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'file': name, 'status': record['status']}), flush=True)


if __name__ == '__main__':
    main()
