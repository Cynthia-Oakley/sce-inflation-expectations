"""Fox News / Fox Business official-sitemap archive collection for the SCE
media-mechanism workstream (NEWS_MECHANISM_PLAN_V3 section 3).

Scope and constraints (do not widen without user approval):
  - Sources: ONLY www.foxnews.com and www.foxbusiness.com official sitemaps
    (https://<host>/sitemap.xml?type=articles&page=N). No NYPost collection.
  - Read-only public GETs with timeout, per-host rate limit, a descriptive
    user agent, and raw response / error recording under <out_dir>/raw.
    robots.txt of both hosts does not disallow sitemap.xml or article pages.
  - No LLM / DeepSeek / simulation calls. Labels are deterministic heuristics
    over the frozen slim4 vocabulary (decision/topics/scope); tone/persistence
    are added later by the main agent.
  - Recall uses the same NYT keyword rule file (news_keyword_rules_v1_2.json)
    as the NYT pipeline. Sitemap entries carry no title/abstract, so the
    pre-fetch recall runs on the URL slug; after fetching the article page
    the full recall runs on title + excerpt.
  - Known limitation (documented, inherited from the 2021-06/2022-06 sample):
    sitemap `lastmod` is the last-modified time, not the publication time.
    Candidates are therefore entries whose lastmod falls inside the window;
    articles published in the window but modified later are systematically
    missed. Articles are additionally verified to have published_at inside
    the window after fetching the page.

Windows follow the NYT convention (news_selection_trial.WINDOWS): previous
month first day through the month as_of (inclusive, day level). as_of values
come from outputs/sce_monthly_fine_full_assembly_20261023_v3/prompts/<month>/
environment.json and are read, never hardcoded, by the CLI.

Resume: all fetched sitemap pages and article pages are persisted under
<out_dir>/raw and indexed in <out_dir>/state.json; re-running collect_month
performs no network fetches for work already recorded. Outputs are written
to a temp file and atomically renamed, so an interrupted run never leaves a
truncated JSON.
"""
from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from .experiments.media_mechanism_trial import (  # noqa: F401  (single source)
    INFLATION_PATTERN, SCE_PATTERN, article_id)
from .news_selection_trial import RULE_FILE, RecallRules, normalize

USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0 Safari/537.36 '
              'SCE-ResearchBot/1.0 (academic research; read-only; contact: local)')
FOX_DOMAINS = ('https://www.foxnews.com', 'https://www.foxbusiness.com')
SITEMAP_PAGE_SIZE = 5000
ASSEMBLY_ENV = ('outputs/sce_monthly_fine_full_assembly_20261023_v3/'
                'prompts/{month}/environment.json')

DECISIONS = ('keep', 'background', 'exclude', 'uncertain')
TOPICS = ('living_prices', 'supply_costs', 'employment_income_consumption',
          'policy', 'economic_outlook', 'other_economic')
SCOPES = ('us_national', 'us_local', 'us_unspecified', 'us_and_global',
          'global', 'non_us', 'unspecified')

# Deterministic strong/object-term -> topics mapping (heuristic labels).
STRONG_TERM_TOPICS = {
    'inflation': 'living_prices', 'deflation': 'living_prices',
    'consumer price': 'living_prices', 'consumer prices': 'living_prices',
    'cost of living': 'living_prices', 'gasoline': 'living_prices',
    'gas price': 'living_prices', 'gas prices': 'living_prices',
    'prices at the pump': 'living_prices', 'utility bills': 'living_prices',
    'electricity prices': 'living_prices', 'natural gas prices': 'living_prices',
    'food prices': 'living_prices', 'grocery prices': 'living_prices',
    'rent': 'living_prices', 'rents': 'living_prices',
    'rental assistance': 'living_prices', 'home prices': 'living_prices',
    'housing market': 'living_prices', 'mortgage': 'living_prices',
    'mortgages': 'living_prices', 'fuel costs': 'living_prices',
    'oil price': 'supply_costs', 'oil prices': 'supply_costs',
    'crude oil': 'supply_costs', 'opec': 'supply_costs',
    'supply chain': 'supply_costs', 'supply chains': 'supply_costs',
    'chip shortage': 'supply_costs', 'meatpacking': 'supply_costs',
    'meat plants': 'supply_costs', 'food processing': 'supply_costs',
    'producer prices': 'supply_costs', 'wholesale prices': 'supply_costs',
    'jobs report': 'employment_income_consumption',
    'jobless': 'employment_income_consumption',
    'unemployment': 'employment_income_consumption',
    'unemployment benefits': 'employment_income_consumption',
    'wage': 'employment_income_consumption', 'wages': 'employment_income_consumption',
    'retail sales': 'employment_income_consumption',
    'retail spending': 'employment_income_consumption',
    'consumer spending': 'employment_income_consumption',
    'household spending': 'employment_income_consumption',
    'hiring': 'employment_income_consumption', 'layoffs': 'employment_income_consumption',
    'federal reserve': 'policy', 'interest rate': 'policy',
    'interest rates': 'policy', 'monetary policy': 'policy',
    'fiscal policy': 'policy', 'stimulus': 'policy',
    'relief payments': 'policy', 'spending bill': 'policy',
    'infrastructure bill': 'policy', 'tariff': 'policy', 'tariffs': 'policy',
    'trade war': 'policy',
    'economic recovery': 'economic_outlook', 'economic rebound': 'economic_outlook',
    'recession': 'economic_outlook',
}
OBJECT_TERM_TOPICS = {
    'beef': 'living_prices', 'meat': 'living_prices', 'poultry': 'living_prices',
    'grocery': 'living_prices', 'groceries': 'living_prices',
    'supermarket': 'living_prices', 'household goods': 'living_prices',
    'clothing': 'living_prices', 'apparel': 'living_prices',
    'appliance': 'living_prices', 'appliances': 'living_prices',
    'electricity': 'living_prices', 'used cars': 'living_prices',
    'grain': 'supply_costs', 'wheat': 'supply_costs', 'natural gas': 'supply_costs',
    'pipeline': 'supply_costs', 'factory': 'supply_costs', 'factories': 'supply_costs',
    'plant': 'supply_costs', 'plants': 'supply_costs', 'shipping': 'supply_costs',
    'port': 'supply_costs', 'ports': 'supply_costs',
    'semiconductor': 'supply_costs', 'semiconductors': 'supply_costs',
    'lumber': 'supply_costs',
}
US_MARKERS = ('u.s.', 'united states', 'america', 'americans', 'american',
              'federal reserve', 'the fed', 'white house', 'washington',
              'capitol hill', 'congress', 'treasury')
US_LOCAL_MARKERS = ('california', 'texas', 'florida', 'new york', 'ohio',
                    'michigan', 'pennsylvania', 'illinois', 'georgia')
FOREIGN_MARKERS = ('china', 'chinese', 'europe', 'european', 'eurozone',
                   'germany', 'france', 'britain', 'u.k.', 'japan', 'india',
                   'russia', 'saudi', 'opec', 'iran', 'iraq', 'venezuela',
                   'mexico', 'global', 'worldwide', 'world market')
ENERGY_TRADE_TOPICS = ('supply_costs', 'policy', 'living_prices')

ARTICLE_TYPE_EXPLAINER = re.compile(r'^(?:what|why|how)\b.*\?', re.I)
JSON_LD_BLOCK = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
META_TAG = re.compile(r'<meta\s+([^>]+)>', re.I)
TAG_ATTR = re.compile(r'(\w+(?::\w+)?)\s*=\s*["\']([^"\']*)["\']')


class FetchError(Exception):
    """A GET failed (timeout, HTTP error, or empty body)."""


def utc_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def parse_sitemap(xml_bytes: bytes) -> list[dict]:
    """Parse one sitemap page into [{'loc', 'lastmod'}] entries."""
    root = ET.fromstring(xml_bytes)
    entries = []
    for url in root:
        loc = lastmod = None
        for child in url:
            tag = child.tag.rsplit('}', 1)[-1]
            if tag == 'loc':
                loc = (child.text or '').strip()
            elif tag == 'lastmod':
                lastmod = (child.text or '').strip()
        if loc and '/sitemap' not in loc:
            entries.append({'loc': loc, 'lastmod': lastmod})
    return entries


def split_window_entries(entries: list[dict], window_start: str, as_of: str):
    """Split sitemap entries by lastmod into [window_start, as_of] inclusive."""
    kept, dropped = [], 0
    for e in entries:
        lm = e.get('lastmod')
        if lm and window_start <= lm[:10] <= as_of[:10]:
            kept.append(e)
        else:
            dropped += 1
    return kept, dropped


def load_recall_rules() -> RecallRules:
    return RecallRules(json.loads(RULE_FILE.read_bytes()))


def recall_text(rules: RecallRules, title: str, excerpt: str) -> list[dict]:
    """NYT-compatible keyword recall on plain text (mirrors RecallRules.classify)."""
    doc = {'headline': {'main': title or ''}, 'abstract': excerpt or '',
           'snippet': '', 'section_name': None, 'news_desk': None}
    return rules.classify(doc)


def is_sce_report(text: str) -> bool:
    """True when title/excerpt text reports SCE expectations (same pattern as
    media_mechanism_trial.SCE_PATTERN, applied to plain text)."""
    return bool(SCE_PATTERN.search(text))


def slug_recall(rules: RecallRules, url: str) -> bool:
    """Cheap pre-fetch recall on the URL slug (hyphens -> spaces)."""
    slug = url.rstrip('/').rsplit('/', 1)[-1]
    text = normalize(slug.replace('-', ' '))
    return bool(rules.patterns['strong_terms'].search(text))


def heuristic_label(hits: list[dict], url: str) -> dict:
    """Deterministic decision/topics/scope over the frozen slim4 vocabulary.

    decision: keep when a direct (strong-term) hit or an object/price-change
    pair exists; background when only general-economic-context matched;
    exclude when nothing matched. Scope is a keyword heuristic with
    us_unspecified as the safe default; it is NOT an LLM label.
    """
    rules_hit = {h['rule'] for h in hits}
    strong = sorted({term for h in hits if h['rule'] == 'direct_economic_terms'
                     for term in h['evidence']})
    objects = sorted({pair[0] for h in hits if h['rule'] == 'object_and_change'
                      for pair in h['evidence']})
    if 'direct_economic_terms' in rules_hit or 'object_and_change' in rules_hit \
            or 'price_and_change' in rules_hit:
        decision = 'keep'
    elif 'general_economic_context' in rules_hit:
        decision = 'background'
    else:
        decision = 'exclude'
    topics = set()
    for term in strong:
        topic = STRONG_TERM_TOPICS.get(term)
        if topic:
            topics.add(topic)
    for obj in objects:
        topic = OBJECT_TERM_TOPICS.get(obj)
        if topic:
            topics.add(topic)
    if decision == 'background':
        topics.add('economic_outlook')
    if not topics and decision != 'exclude':
        topics.add('other_economic')
    topics = sorted(topics)

    text = ' '.join(
        str(term) for h in hits for term in (h.get('evidence') or [])
        if isinstance(term, str))
    text = ' ' + normalize(text) + ' '
    us = any(m in text for m in US_MARKERS)
    local = any(m in text for m in US_LOCAL_MARKERS)
    foreign = any(m in text for m in FOREIGN_MARKERS)
    if foreign and us:
        scope = 'us_and_global'
    elif foreign:
        scope = 'global' if any(t in ENERGY_TRADE_TOPICS for t in topics) else 'non_us'
    elif us and local:
        scope = 'us_local'
    elif us:
        scope = 'us_national'
    else:
        scope = 'us_unspecified'
    return {'decision': decision, 'topics': topics, 'scope': scope,
            'label_method': 'heuristic_keyword_v1_pending_llm_verification'}


def _meta_content(html: str, key: str, attr: str = 'property') -> str | None:
    for tag in META_TAG.finditer(html):
        attrs = dict(TAG_ATTR.findall(tag.group(1)))
        if attrs.get(attr) == key and attrs.get('content'):
            return attrs['content'].strip()
    return None


def parse_article_html(html_bytes: bytes, url: str) -> dict:
    """Extract title / published_at / excerpt from a Fox article page.

    Prefers JSON-LD NewsArticle data; falls back to OpenGraph / meta tags.
    """
    html = html_bytes.decode('utf-8', 'replace')
    title = published = excerpt = None
    for block in JSON_LD_BLOCK.finditer(html):
        try:
            data = json.loads(block.group(1).strip())
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            node = item.get('@graph', [item])
            node = node if isinstance(node, list) else [node]
            for n in node:
                if not isinstance(n, dict):
                    continue
                if 'NewsArticle' in str(n.get('@type', '')):
                    title = title or n.get('headline')
                    published = published or n.get('datePublished')
                    excerpt = excerpt or n.get('description')
    title = title or _meta_content(html, 'og:title') or _meta_content(html, 'title', 'name')
    published = published or _meta_content(html, 'article:published_time')
    excerpt = excerpt or _meta_content(html, 'description', 'name') or ''
    if not published:
        raise ValueError('no publication date on page: ' + url)
    return {'title': title or '', 'published_at': published, 'excerpt': excerpt or ''}


def source_name(url: str) -> str:
    return 'Fox Business' if 'foxbusiness.com' in url else 'Fox News'


def text_sha256(headline: str, abstract: str) -> str:
    return hashlib.sha256((headline + '\n' + abstract).encode()).hexdigest()


class UrlLibFetcher:
    """Read-only GET with timeout, UA, per-host rate limit and bounded retries.
    Every attempt (success or failure) is recorded by collect_month into
    <out_dir>/raw/http_log.jsonl."""

    def __init__(self, min_interval: float = 2.0, timeout: float = 30.0,
                 max_retries: int = 2, sleep=time.sleep):
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.sleep = sleep
        self._last: dict[str, float] = {}

    def fetch(self, url: str, timeout: float | None = None) -> bytes:
        host = url.split('/')[2]
        wait = self.min_interval - (time.monotonic() - self._last.get(host, 0.0))
        if wait > 0:
            self.sleep(wait)
        self._last[host] = time.monotonic()
        attempt, err = 0, None
        while attempt <= self.max_retries:
            attempt += 1
            try:
                req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                    body = resp.read()
                if not body:
                    raise FetchError('empty body')
                return body
            except (urllib.error.URLError, TimeoutError, FetchError, OSError,
                    http.client.HTTPException) as exc:
                err = str(exc)
                if attempt <= self.max_retries:
                    self.sleep(min(2.0 * attempt, 5.0))
        raise FetchError(f'{err} (after {attempt} attempts)')


def record_http(out_dir: Path, url: str, status, size: int, error=None) -> None:
    record = {'fetched_at': utc_now_iso(), 'url': url, 'status': status,
              'size': size}
    if error:
        record['error'] = error
    with (Path(out_dir) / 'raw' / 'http_log.jsonl').open('a') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def _load_state(out_dir: Path) -> dict:
    path = Path(out_dir) / 'state.json'
    if path.exists():
        return json.loads(path.read_text())
    return {'sitemap_pages': {}, 'articles': {}, 'wayback': {}}


def collect_month(fetcher, out_dir: Path, month: int, window_start: str,
                  as_of: str, domains=FOX_DOMAINS,
                  page_limit: int = 400) -> dict:
    """Resumable per-month pipeline: sitemap -> slug recall -> article fetch
    -> keyword recall -> SCE exclusion -> heuristic labels -> candidates.json.

    Returns {'candidates': [...], 'funnel': {...}} and persists everything
    under out_dir (raw/ bodies, state.json, candidates.json). Re-running with
    an existing state performs no network fetches for completed work.
    """
    out_dir = Path(out_dir)
    (out_dir / 'raw').mkdir(parents=True, exist_ok=True)
    (out_dir / 'raw' / 'sitemaps').mkdir(parents=True, exist_ok=True)
    (out_dir / 'raw' / 'articles').mkdir(parents=True, exist_ok=True)
    state = _load_state(out_dir)
    rules = load_recall_rules()
    observed_at = utc_now_iso()
    funnel = {'sitemap_pages_scanned': 0, 'sitemap_entries_seen': 0,
              'sitemap_entries_in_window': 0, 'slug_recalled': 0,
              'article_fetch_ok': 0, 'article_fetch_failed': 0,
              'published_in_window': 0, 'published_out_of_window': 0,
              'excluded_sce_report': 0, 'dropped_no_keyword_hit': 0,
              'eligible': 0, 'decision_counts': {}}

    window_urls: dict[str, dict] = {}
    for domain in domains:
        page = 0
        while page < page_limit:
            page += 1
            key = f'{domain} page {page}'
            if key in state['sitemap_pages']:
                funnel['sitemap_pages_scanned'] += 1
                info = state['sitemap_pages'][key]
                if info.get('error') or not info.get('entry_count'):
                    break
                # Rebuild window entries from the persisted raw page so a
                # resumed run reconstructs the same candidate set offline.
                raw_path = (out_dir / 'raw' / 'sitemaps' /
                            f"{domain.split('//')[1]}-page-{page:04d}.xml.gz")
                entries = parse_sitemap(gzip.decompress(raw_path.read_bytes()))
                funnel['sitemap_entries_seen'] += len(entries)
                for e in entries:
                    kept, _ = split_window_entries([e], window_start, as_of)
                    if kept:
                        funnel['sitemap_entries_in_window'] += 1
                        window_urls.setdefault(e['loc'], e)
                # Entries within one page are not strictly sorted by lastmod
                # (observed: a page can straddle the window), so only stop
                # AFTER ingesting a page whose newest entry is already below
                # the window start.
                newest = info.get('max_lastmod')
                if not entries or (newest and newest[:10] < window_start[:10]):
                    break
                continue
            # foxbusiness serves its first page only at the bare URL
            # (?page=1 returns 404); foxnews 301-redirects page=1 to it.
            url = (f'{domain}/sitemap.xml?type=articles' if page == 1
                   else f'{domain}/sitemap.xml?type=articles&page={page}')
            try:
                body = fetcher.fetch(url)
                record_http(out_dir, url, 200, len(body))
            except FetchError as exc:
                record_http(out_dir, url, None, 0, str(exc))
                if page == 1:
                    raise
                state['sitemap_pages'][key] = {'error': str(exc), 'page': page}
                _atomic_write_json(out_dir / 'state.json', state)
                break
            entries = parse_sitemap(body)
            lastmods = sorted(e['lastmod'] or '' for e in entries)
            page_info = {'page': page, 'entry_count': len(entries),
                         'min_lastmod': lastmods[0] if lastmods else None,
                         'max_lastmod': lastmods[-1] if lastmods else None,
                         'body_sha256': hashlib.sha256(body).hexdigest()}
            state['sitemap_pages'][key] = page_info
            (out_dir / 'raw' / 'sitemaps' /
             f"{domain.split('//')[1]}-page-{page:04d}.xml.gz").write_bytes(gzip.compress(body))
            _atomic_write_json(out_dir / 'state.json', state)
            funnel['sitemap_pages_scanned'] += 1
            funnel['sitemap_entries_seen'] += len(entries)
            for e in entries:
                kept, _ = split_window_entries([e], window_start, as_of)
                if kept:
                    funnel['sitemap_entries_in_window'] += 1
                    window_urls.setdefault(e['loc'], e)
            # Same straddling-page guard on the fresh path: ingest the page's
            # entries before deciding to stop.
            newest = page_info['max_lastmod']
            if not entries or (newest and newest[:10] < window_start[:10]):
                break

    slug_hits = {u: e for u, e in window_urls.items() if slug_recall(rules, u)}
    funnel['slug_recalled'] = len(slug_hits)

    candidates: list[dict] = []
    for url in sorted(slug_hits):
        key = hashlib.sha256(url.encode()).hexdigest()[:24]
        article_state = state['articles'].get(key)
        if article_state is None:
            try:
                body = fetcher.fetch(url)
                record_http(out_dir, url, 200, len(body))
                article_state = {'url': url, 'body_sha256': hashlib.sha256(body).hexdigest(),
                                 'fetched_at': utc_now_iso()}
                state['articles'][key] = article_state
                (out_dir / 'raw' / 'articles' / f'{key}.html.gz').write_bytes(
                    gzip.compress(body))
                _atomic_write_json(out_dir / 'state.json', state)
            except FetchError as exc:
                record_http(out_dir, url, None, 0, str(exc))
                state['articles'][key] = {'url': url, 'error': str(exc),
                                          'fetched_at': utc_now_iso()}
                _atomic_write_json(out_dir / 'state.json', state)
                funnel['article_fetch_failed'] += 1
                continue
        if 'error' in article_state:
            funnel['article_fetch_failed'] += 1
            continue
        funnel['article_fetch_ok'] += 1
        body = gzip.decompress((out_dir / 'raw' / 'articles' / f'{key}.html.gz').read_bytes())
        try:
            meta = parse_article_html(body, url)
        except ValueError:
            funnel['published_out_of_window'] += 1
            continue
        if not (window_start <= meta['published_at'][:10] <= as_of[:10]):
            funnel['published_out_of_window'] += 1
            continue
        funnel['published_in_window'] += 1
        text = ' '.join([meta['title'], meta['excerpt']])
        if is_sce_report(text):
            funnel['excluded_sce_report'] += 1
            continue
        hits = recall_text(rules, meta['title'], meta['excerpt'])
        if not hits:
            funnel['dropped_no_keyword_hit'] += 1
            continue
        label = heuristic_label(hits, url)
        candidate = {
            'source': source_name(url),
            'article_type': 'explainer' if ARTICLE_TYPE_EXPLAINER.search(meta['title'])
            else 'news',
            'title': meta['title'],
            'original_url': url,
            'published_at': meta['published_at'],
            'excerpt_lead': meta['excerpt'][:1200],
            'observed_at': observed_at,
            'text_vintage_status': 'live_page_observed_' + observed_at[:10]
                                   + '_not_archive_certified',
            'source_access_status': article_state.get('error') or 'original_site_accessible',
            'sitemap_lastmod': slug_hits[url]['lastmod'],
            'recall_hits': hits,
            'label': label,
            'article_id': article_id(url, meta['title'], meta['excerpt']),
            'text_sha256': text_sha256(meta['title'], meta['excerpt']),
            'wayback': {'status': 'unverified'},
            'evidence_limitations': (
                'published_at 取自页面 JSON-LD/meta 结构化数据；sitemap lastmod '
                '为最后修改时间，窗口内 lastmod 之外的文章未召回；未与历史存档比对。'),
        }
        candidates.append(candidate)
        funnel['eligible'] += 1
        funnel['decision_counts'][label['decision']] = \
            funnel['decision_counts'].get(label['decision'], 0) + 1

    candidates.sort(key=lambda c: (c['published_at'], c['article_id']))
    payload = {'schema': 'sce_fox_sitemap_candidates/v1', 'month': month,
               'window_start': window_start, 'as_of': as_of,
               'domains': list(domains), 'observed_at': observed_at,
               'label_method': 'heuristic_keyword_v1_pending_llm_verification',
               'funnel': funnel, 'candidates': candidates}
    _atomic_write_json(out_dir / 'candidates.json', payload)
    return {'candidates': candidates, 'funnel': funnel}


def parse_cdx_json(body: bytes) -> list[dict]:
    rows = json.loads(body.decode('utf-8', 'replace'))
    if not rows:
        return []
    header, data = rows[0], rows[1:]
    keys = [str(h) for h in header]
    return [dict(zip(keys, row)) for row in data if isinstance(row, list)]


def verify_wayback(fetcher, url: str, published_at: str) -> dict:
    """Wayback CDX check for one candidate URL (read-only public API).

    Marks archive_verified only when >=1 HTTP-200 capture exists; otherwise
    unverified with the recorded error. Never fabricates capture data.
    """
    cdx_url = ('https://web.archive.org/cdx/search/cdx?url='
               + re.sub(r'^https?://(www\.)?', '', url)
               + '&output=json&limit=200&filter=statuscode:200')
    try:
        body = fetcher.fetch(cdx_url, timeout=45.0)
        captures = [c for c in parse_cdx_json(body) if c.get('statuscode') == '200']
    except (FetchError, ValueError) as exc:
        return {'status': 'unverified', 'error': str(exc), 'checked_at': utc_now_iso()}
    if not captures:
        return {'status': 'unverified', 'error': 'no 200 capture in CDX',
                'checked_at': utc_now_iso(), 'capture_count': 0}
    stamps = sorted(c['timestamp'] for c in captures)
    pub = re.sub(r'\D', '', published_at)[:14]
    after = [s for s in stamps if s >= pub]
    return {'status': 'archive_verified', 'capture_count': len(captures),
            'earliest_capture': stamps[0], 'latest_capture': stamps[-1],
            'first_capture_at_or_after_pub': after[0] if after else None,
            'checked_at': utc_now_iso()}


def import_existing_fox(external_dir: Path, months=(202106, 202206)) -> dict[str, list]:
    """Take Fox-only candidates from the existing 2021-06/2022-06 samples.

    NYPost rows are never imported (robots restriction + plan decision).
    Existing manual labels (price_content/tone/persistence) are preserved;
    they are NOT re-labeled here.
    """
    external_dir = Path(external_dir)
    out: dict[str, list] = {}
    for month in months:
        rows: list[dict] = []
        combined = read_json(external_dir / 'external_candidates.json')['windows'][
            str(month)]['candidates']
        combined += read_json(external_dir / f'external_may_{month // 100}.json')['candidates']
        seen = set()
        for raw in combined:
            if not str(raw.get('source', '')).startswith('Fox'):
                continue
            if raw['original_url'] in seen:
                continue
            seen.add(raw['original_url'])
            rows.append(dict(raw))
        rows.sort(key=lambda r: (r['published_at'], r['original_url']))
        out[str(month)] = rows
    return out


def read_json(path) -> dict:
    return json.loads(Path(path).read_text())


def window_for_month(root: Path, month: int):
    """NYT-style window: previous month first day .. assembly as_of (day level)."""
    env = read_json(Path(root) / ASSEMBLY_ENV.format(month=month))
    as_of = env['provider_args']['targets'][0]['as_of']
    year, mon = month // 100, month % 100
    prev_year, prev_mon = (year - 1, 12) if mon == 1 else (year, mon - 1)
    return f'{prev_year:04d}-{prev_mon:02d}-01', as_of
