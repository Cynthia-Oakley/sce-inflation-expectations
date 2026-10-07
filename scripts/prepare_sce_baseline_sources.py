#!/usr/bin/env python3
"""Archive public release evidence for offline SCE benchmarks. No credentials."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'data/raw/sce_baselines_20261007'
BASE = 'https://www.newyorkfed.org'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.current = [dict(attrs).get('href', ''), '']

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.links.append(self.current)
            self.current = None


def clean(html):
    html = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', html, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', html))).strip()


def release_evidence(html, url):
    text = clean(html)
    lead_start = re.search(r'NEW YORK\s*[—–-]', text)
    if lead_start is None:
        return None
    start = lead_start.start()
    lead = text[start:start + 1300]
    month_names = '|'.join(datetime(2000, m, 1).strftime('%B') for m in range(1, 13))
    ref = re.search(r'(' + month_names + r') (20\d\d) Survey of Consumer Expectations', lead)
    if not ref:
        return None  # Separate housing/spending/labor-market modules are excluded.
    reference = datetime.strptime(ref.group(0).split(' Survey')[0], '%B %Y').strftime('%Y-%m')
    stamp = re.findall(r'(?:' + month_names + r') \d{1,2}, 20\d\d', text[:start])
    if not stamp:
        raise ValueError(f'No visible publication date: {url}')
    published = datetime.strptime(stamp[-1], '%B %d, %Y').strftime('%Y-%m-%d')
    date_in_url = re.search(r'/(\d{8})(?:[/?]|$)', url)
    if date_in_url and datetime.strptime(date_in_url[1], '%Y%m%d').strftime('%Y-%m-%d') != published:
        raise ValueError(f'URL/date disagreement: {url}')
    points = [clean(x) for x in re.findall(r'<li\b[^>]*>(.*?)</li>', html, re.S | re.I)]
    relevant = [x for x in points if re.search(r'inflation expectation', x, re.I)
                and re.search(r'one.?year|short.?term|one- and|year-ahead', x, re.I)]
    if not relevant:
        # Older releases sometimes use paragraph formatting.
        relevant = [clean(x) for x in re.findall(r'<p\b[^>]*>(.*?)</p>', html, re.S | re.I)
                    if re.search(r'inflation expectation', clean(x), re.I)
                    and re.search(r'one.?year|short.?term|one- and|year-ahead', clean(x), re.I)]
    return dict(reference_period=reference, published_date=published, source_url=url,
                inflation_passages=relevant[:2], lead=lead[:550])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    index = args.root / 'nyfed_press_index.html'
    if args.fetch and not index.exists():
        import httpx
        response = httpx.get(BASE + '/press', timeout=45, follow_redirects=True)
        response.raise_for_status()
        index.write_bytes(response.content)
    p = Links()
    p.feed(index.read_text())
    links = {BASE + url: title.strip() for url, title in p.links
             if re.search(r'/newsevents/news/research/20(?:19|2[0-5])/\d{8}', url)
             and not re.search(r'debt|housing survey|household spending survey|labor market survey', title, re.I)}

    def load(item):
        url, title = item
        dest = args.root / (url.rsplit('/', 1)[-1] + '.html')
        if args.fetch and not dest.exists():
            import httpx
            response = httpx.get(url, timeout=45, follow_redirects=True)
            response.raise_for_status()
            dest.write_bytes(response.content)
        rec = release_evidence(dest.read_text(), url)
        if rec is not None:
            rec.update(file=str(dest.relative_to(ROOT)), title=title,
                       sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
        return rec

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = [r for r in pool.map(load, sorted(links.items())) if r is not None]
    records.sort(key=lambda x: (x['reference_period'], x['published_date']))
    manifest = dict(retrieved_at=datetime.now(timezone.utc).isoformat(),
                    index_url=BASE + '/press',
                    index_sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
                    extraction='visible release date and reference month; original archived web page',
                    records=records)
    (args.root / 'release_evidence.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    if not records:
        raise ValueError('No core SCE releases extracted; inspect archived source layout.')
    print(json.dumps({'core_releases': len(records), 'first': records[0]['reference_period'],
                      'last': records[-1]['reference_period']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
