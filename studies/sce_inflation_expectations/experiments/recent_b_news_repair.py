"""Resumable official NYT repair for the sampled-date B news windows."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from .full_a_core_normal import ROOT, sha
from ..news_label_trial import dotenv_values

MONTH = '2026-01'
SEARCH_ROOT = 'https://api.nytimes.com/svc/search/v2/articlesearch.json'
ARCHIVE_ROOT = 'https://api.nytimes.com/svc/archive/v1/2026/1.json'
TEXT_FIELDS = ('headline', 'abstract', 'snippet')
REQUIRED_FIELDS = (
    'headline', 'abstract', 'snippet', 'pub_date', '_id', 'uri', 'web_url',
    'document_type', 'section_name', 'news_desk', 'print_section', 'print_page',
)


def now():
    return datetime.now(timezone.utc).isoformat()


def source_identity(row):
    return row.get('_id') or row.get('uri') or row.get('web_url') or ''


def text_fingerprint(row):
    headline = row.get('headline') or {}
    text = {
        'headline': headline.get('main') or '' if isinstance(headline, dict) else '',
        'abstract': row.get('abstract') or '',
        'snippet': row.get('snippet') or '',
    }
    payload = json.dumps(text, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def search_log_url(begin_day, end_day, page):
    query = urllib.parse.urlencode({
        'begin_date': f'202601{begin_day:02d}',
        'end_date': f'202601{end_day:02d}',
        'page': page,
    })
    return SEARCH_ROOT + '?' + query


def read_search_page(path, page):
    payload = json.loads(Path(path).read_text())
    response = payload.get('response', {})
    docs = response.get('docs')
    metadata = response.get('metadata') or response.get('meta') or {}
    if docs is None and metadata.get('hits') is not None \
            and metadata.get('offset', 0) >= metadata['hits']:
        docs = []
        response['docs'] = docs
    if not isinstance(docs, list):
        raise ValueError(f'Article Search response.docs list required on page {page}')
    for row in docs:
        stamp = row.get('pub_date', '')
        if not ('2026-01-08' <= stamp[:10] <= '2026-01-31'):
            raise ValueError('Article outside requested January repair days')
    return payload


def search_page_terminal(payload):
    response = payload['response']
    docs = response['docs']
    if len(docs) < 10:
        return True
    metadata = response.get('metadata') or response.get('meta') or {}
    hits = metadata.get('hits')
    offset = metadata.get('offset', 0)
    return hits is not None and offset + len(docs) >= hits


def _download(url, attempts=4):
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'sce-research/1.0'})
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.read(), response.status, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt + 1 == attempts:
                raise
            retry_after = exc.headers.get('Retry-After')
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 5 * (attempt + 1)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f'Article Search failed after {attempts} attempts: {last}')


def fetch_january_search(out, begin_day=8, end_day=31, delay=12.0, max_pages=450):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    key = os.environ.get('NYT_ARCHIVE_API_KEY') or dotenv_values(ROOT / '.env').get('NYT_ARCHIVE_API_KEY')
    if not key:
        raise ValueError('NYT_ARCHIVE_API_KEY missing')
    log_path = out / 'fetch_log.jsonl'
    last_request = None
    pages = []
    for page in range(max_pages):
        path = out / f'page_{page:04d}.json'
        if path.exists():
            payload = read_search_page(path, page)
        else:
            if last_request is not None:
                time.sleep(max(0.0, delay - (time.monotonic() - last_request)))
            url = search_log_url(begin_day, end_day, page) + '&api-key=' + urllib.parse.quote(key)
            started = now()
            last_request = time.monotonic()
            try:
                raw, status, headers = _download(url)
                path.write_bytes(raw)
                payload = read_search_page(path, page)
                record = {
                    'type': 'page_fetched', 'page': page, 'at_utc': started,
                    'http_status': status, 'source_url': search_log_url(begin_day, end_day, page),
                    'path': path.name, 'sha256': sha(path), 'bytes': len(raw),
                    'n_docs': len(payload['response']['docs']),
                    'rate_limit_headers': {k: v for k, v in headers.items()
                                           if 'rate' in k.lower() or 'retry' in k.lower()},
                }
            except Exception as exc:
                record = {
                    'type': 'page_failed', 'page': page, 'at_utc': started,
                    'source_url': search_log_url(begin_day, end_day, page),
                    'error_type': type(exc).__name__, 'error': str(exc)[:300],
                }
                with log_path.open('a') as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + '\n')
                raise
            with log_path.open('a') as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + '\n')
            print(json.dumps({k: record[k] for k in ('page', 'http_status', 'n_docs', 'sha256')}), flush=True)
        pages.append(payload)
        docs = payload['response']['docs']
        if search_page_terminal(payload):
            metadata = payload['response'].get('metadata') or payload['response'].get('meta') or {}
            completion = {
                'status': 'article_search_days_exhausted', 'month': MONTH,
                'begin_day': begin_day, 'end_day': end_day,
                'first_page': 0, 'terminal_page': page, 'pages': len(pages),
                'terminal_page_docs': len(docs), 'source_hits': metadata.get('hits'),
                'finished_at_utc': now(),
                'source_url_without_key': search_log_url(begin_day, end_day, page).split('&page=')[0],
                'page_size_observed': 10,
            }
            (out / 'search_complete.json').write_text(json.dumps(completion, ensure_ascii=False, indent=2) + '\n')
            return pages
    raise ValueError(f'Article Search still has full pages after {max_pages} pages; completeness not established')


def merge_january_archive(archive, search_pages):
    merged = {}
    duplicate_rows = 0
    search_rows = 0
    for source, rows in (
        ('official_archive_refresh', archive.get('response', {}).get('docs', [])),
        ('official_article_search', [row for page in search_pages
                                     for row in page.get('response', {}).get('docs', [])]),
    ):
        if source == 'official_article_search':
            search_rows = len(rows)
        for row in rows:
            stamp = row.get('pub_date', '')
            if stamp[:7] != MONTH:
                raise ValueError('Source article outside 2026-01')
            identity = source_identity(row)
            if not identity:
                raise ValueError('Source article has no source identity')
            fingerprint = text_fingerprint(row)
            key = (identity, fingerprint)
            if key in merged:
                duplicate_rows += 1
                continue
            if any(existing[0] == identity for existing in merged):
                raise ValueError('Conflicting source identity/text versions require explicit review: ' + identity)
            merged[key] = row
    docs = sorted(merged.values(), key=lambda row: (row['pub_date'], source_identity(row), text_fingerprint(row)))
    observed = sorted({int(row['pub_date'][8:10]) for row in docs})
    missing = [day for day in range(1, 32) if day not in observed]
    if missing:
        raise ValueError('Incomplete January coverage: ' + json.dumps(missing))
    receipt = {
        'n_docs': len(docs), 'search_docs_before_deduplication': search_rows,
        'duplicate_identity_text_rows': duplicate_rows,
        'observed_days': observed, 'unobserved_required_days': missing,
        'screen_passed': True,
        'meaning': 'Daily coverage and identity/text deduplication, not proof of historical text vintage',
    }
    return {'status': 'OK', 'response': {'docs': docs}}, receipt


def load_daily_search_pages(search_root):
    search_root = Path(search_root)
    pages = []
    evidence = []
    for day in range(8, 32):
        folder = search_root / f'day_{day:02d}'
        completion = json.loads((folder / 'search_complete.json').read_text())
        if completion['begin_day'] != day or completion['end_day'] != day:
            raise ValueError('Daily search completion has the wrong date range')
        for page in range(completion['pages']):
            path = folder / f'page_{page:04d}.json'
            payload = read_search_page(path, page)
            if any(row['pub_date'][:10] != f'2026-01-{day:02d}'
                   for row in payload['response']['docs']):
                raise ValueError('Daily search page contains another publication day')
            pages.append(payload)
            evidence.append({
                'day': day, 'page': page, 'path': str(path), 'sha256': sha(path),
                'bytes': path.stat().st_size, 'n_docs': len(payload['response']['docs']),
                'http_status': 200,
            })
    return pages, evidence


def fetch_january_by_day(repair_root, delay=12.0, max_pages_per_day=100):
    repair_root = Path(repair_root)
    search_root = repair_root / 'article_search_by_day/2026-01'
    made_request = False
    for day in range(8, 32):
        folder = search_root / f'day_{day:02d}'
        if (folder / 'search_complete.json').exists():
            continue
        if made_request:
            time.sleep(delay)
        fetch_january_search(folder, begin_day=day, end_day=day, delay=delay,
                             max_pages=max_pages_per_day)
        made_request = True
    pages, _ = load_daily_search_pages(search_root)
    return pages


def finalize_january(repair_root, archive_path=None):
    repair_root = Path(repair_root)
    archive_path = Path(archive_path) if archive_path else repair_root / 'official_archive_refresh/2026-01.json'
    search_root = repair_root / 'article_search_by_day/2026-01'
    pages, page_evidence = load_daily_search_pages(search_root)
    merged, receipt = merge_january_archive(json.loads(archive_path.read_text()), pages)
    destination = repair_root / '2026-01.json'
    meta_path = repair_root / '2026-01.meta.json'
    if destination.exists() or meta_path.exists():
        raise ValueError('January merged output already exists; use a fresh repair version')
    destination.write_text(json.dumps(merged, ensure_ascii=False, separators=(',', ':')) + '\n')
    meta = {
        'month': MONTH, 'fetched_at': now(), 'transformed_at_utc': now(),
        'source_type': 'merged_official_archive_and_daily_article_search_not_unmodified_month_archive',
        'source_urls_without_keys': [ARCHIVE_ROOT] + [
            search_log_url(day, day, 0).split('&page=')[0] for day in range(8, 32)
        ],
        'archive_source': {
            'path': str(archive_path), 'sha256': sha(archive_path), 'bytes': archive_path.stat().st_size,
        },
        'article_search_pages': page_evidence,
        'n_docs': receipt['n_docs'], 'sha256': sha(destination), 'bytes': destination.stat().st_size,
        'coverage': receipt,
        'limitations': 'Later retrieval does not certify the historical article text vintage; missing print fields remain unknown.',
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'path': str(destination), 'sha256': meta['sha256'], **receipt}, ensure_ascii=False))
    return meta


def repair_manifest(root, archive, meta, label_paths, receipt_files):
    root = Path(root).resolve()
    archive = Path(archive).resolve()
    meta = Path(meta).resolve()
    return {
        'schema': 'sce_B_news_repair_overlay/v1',
        'archive_overrides': {
            MONTH: {
                'path': str(archive.relative_to(root)), 'sha256': sha(archive),
                'meta_path': str(meta.relative_to(root)), 'meta_sha256': sha(meta),
            },
        },
        'base_label_overlays': [
            {'path': str(Path(path).resolve().relative_to(root)), 'sha256': sha(Path(path))}
            for path in label_paths
        ],
        'receipt_files': receipt_files,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    fetch = sub.add_parser('fetch-january')
    fetch.add_argument('--repair-root', type=Path, default=ROOT / 'data/raw/nyt_archive_repairs/20261026')
    fetch.add_argument('--delay', type=float, default=12.0)
    fetch.add_argument('--max-pages-per-day', type=int, default=100)
    final = sub.add_parser('finalize-january')
    final.add_argument('--repair-root', type=Path, default=ROOT / 'data/raw/nyt_archive_repairs/20261026')
    args = parser.parse_args()
    if args.command == 'fetch-january':
        pages = fetch_january_by_day(args.repair_root, delay=args.delay,
                                     max_pages_per_day=args.max_pages_per_day)
        if not any(row for page in pages for row in page.get('response', {}).get('docs', [])):
            raise ValueError('No January repair articles found')
        finalize_january(args.repair_root)
    else:
        finalize_january(args.repair_root)


if __name__ == '__main__':
    main()
