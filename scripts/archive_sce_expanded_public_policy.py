#!/usr/bin/env python3
"""Archive public Fed statements and a Gallup topline; no model API or credentials."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/raw/expanded_policy_20261014'
URLS = {f'monetary{d}a.html': f'https://www.federalreserve.gov/newsevents/pressreleases/monetary{d}a.htm'
        for d in ('20200315','20210428','20211103','20220504','20230503','20240918','20250730')}
URLS['gallup_2025.pdf'] = 'https://news.gallup.com/file/poll/659537/2025_04_17_Trump%20Approval%20and%20Economic%20Leaders%20Topline%20and%20Tabs.pdf'

def main():
    OUT.mkdir(exist_ok=True)
    def one(item):
        name, url = item
        path = OUT / name
        if not path.exists():
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 research archive'})
            with urllib.request.urlopen(request, timeout=45) as response:
                path.write_bytes(response.read())
        data = path.read_bytes()
        print('Archived', name, len(data), flush=True)
        return {'file': str(path.relative_to(ROOT)), 'source_url': url,
                'sha256': hashlib.sha256(data).hexdigest(),
                'downloaded_at': datetime.now(timezone.utc).isoformat()}
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, URLS.items()))
    (OUT / 'download_manifest.json').write_text(json.dumps(rows, indent=2) + '\n')

if __name__ == '__main__':
    main()
