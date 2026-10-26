"""Offline tests for studies/sce_inflation_expectations/fox_news_archive.py.

All network access is faked through a fixture fetcher; these tests never
touch foxnews.com, foxbusiness.com or web.archive.org. Covers: sitemap
parsing, window filtering, NYT-compatible keyword recall, SCE-report
exclusion, deterministic decision/topics/scope labels (frozen vocabulary),
article-page metadata extraction, Wayback CDX parsing, resume semantics
(second run performs no new fetches) and the existing-months Fox-only
import.
"""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from studies.sce_inflation_expectations import fox_news_archive as fna  # noqa: E402

FIXTURES = REPO_ROOT / 'data' / 'fixtures' / 'fox_news_archive'


def load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeFetcher:
    """Serves canned bytes per URL and records every request."""

    def __init__(self, mapping: dict[str, bytes], fail: dict[str, str] | None = None):
        self.mapping = mapping
        self.fail = fail or {}
        self.calls: list[str] = []
        self.errors: list[dict] = []

    def fetch(self, url: str, timeout: float = 30.0) -> bytes:
        self.calls.append(url)
        if url in self.fail:
            self.errors.append({'url': url, 'error': self.fail[url]})
            raise fna.FetchError(self.fail[url])
        if url not in self.mapping:
            self.errors.append({'url': url, 'error': '404 fixture miss'})
            raise fna.FetchError('HTTP 404 (fixture miss): ' + url)
        return self.mapping[url]


class PagedFakeFetcher(FakeFetcher):
    """Serves a fresh sitemap for page=1 and an exhausted (pre-window)
    sitemap for later pages so collect_month's stop condition triggers."""

    PAGE_ONE = 'https://www.foxbusiness.com/sitemap.xml?type=articles'

    def fetch(self, url: str, timeout: float = 30.0) -> bytes:
        if 'sitemap.xml' in url and url != self.PAGE_ONE:
            self.calls.append(url)
            return OLD_SITEMAP_PAGE
        return super().fetch(url, timeout=timeout)


OLD_SITEMAP_PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.foxnews.com/us/ancient-story</loc><lastmod>2019-01-05T10:00:00-05:00</lastmod></url>
</urlset>"""


SITEMAP_PAGE_1 = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.foxbusiness.com/economy/inflation-consumer-price-index-may-2021</loc><lastmod>2021-06-10T08:41:59-04:00</lastmod></url>
<url><loc>https://www.foxnews.com/politics/some-politics-story</loc><lastmod>2021-06-09T12:00:00-04:00</lastmod></url>
<url><loc>https://www.foxbusiness.com/markets/used-cars-prices-soar-shortage</loc><lastmod>2021-06-08T09:00:00-04:00</lastmod></url>
</urlset>"""

ARTICLE_HTML = b"""<!DOCTYPE html><html><head>
<title>Consumer prices surge 5% annually, most since August 2008</title>
<meta name="description" content="The Labor Department said consumer prices surged.">
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"NewsArticle","headline":"Consumer prices surge 5% annually, most since August 2008","datePublished":"2021-06-10T08:41:59-04:00","description":"The Labor Department said consumer prices surged 5 percent."}
</script>
</head><body></body></html>"""

ARTICLE_HTML_META_ONLY = b"""<!DOCTYPE html><html><head>
<meta property="og:title" content="Gas prices keep climbing across the U.S.">
<meta property="article:published_time" content="2021-06-08T10:00:00-04:00">
<meta name="description" content="Gas prices rose again, with the national average climbing.">
</head><body></body></html>"""

SCE_ARTICLE_HTML = b"""<!DOCTYPE html><html><head>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"NewsArticle","headline":"New York Fed survey of consumer expectations shows inflation outlook rise","datePublished":"2021-06-09T10:00:00-04:00","description":"The Survey of Consumer Expectations showed higher one-year inflation expectations."}
</script>
</head><body></body></html>"""

CDX_JSON = json.dumps([
    ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
    ["com,foxbusiness)/economy/inflation-consumer-price-index-may-2021", "20210610133944",
     "https://www.foxbusiness.com/economy/inflation-consumer-price-index-may-2021",
     "text/html", "200", "BJUQ6B564YXVT2UJV4D6P6B35LOPCAGE", "20439"],
    ["com,foxbusiness)/economy/inflation-consumer-price-index-may-2021", "20220601120000",
     "https://www.foxbusiness.com/economy/inflation-consumer-price-index-may-2021",
     "text/html", "200", "XYZQ6B564YXVT2UJV4D6P6B35LOPCAGE", "20440"],
]).encode()


class TestSitemapParsing(unittest.TestCase):
    def test_parse_entries(self):
        entries = fna.parse_sitemap(SITEMAP_PAGE_1)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]['loc'],
                         'https://www.foxbusiness.com/economy/inflation-consumer-price-index-may-2021')
        self.assertEqual(entries[0]['lastmod'], '2021-06-10T08:41:59-04:00')

    def test_parse_ignores_image_namespace(self):
        xml = (b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
               b'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
               b'<url><loc>https://www.foxnews.com/a</loc><lastmod>2021-01-01T00:00:00-05:00</lastmod>'
               b'<image:image><image:loc>https://x.example/y.jpg</image:loc></image:image></url></urlset>')
        entries = fna.parse_sitemap(xml)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['loc'], 'https://www.foxnews.com/a')


class TestWindowFiltering(unittest.TestCase):
    def test_in_window_inclusive(self):
        entries = fna.parse_sitemap(SITEMAP_PAGE_1)
        # NYT-style window: previous month first day .. as_of (inclusive)
        kept, dropped = fna.split_window_entries(
            entries, window_start='2021-05-01', as_of='2021-06-10T23:59:59-04:00')
        self.assertEqual(len(kept), 3)
        self.assertEqual(dropped, 0)
        entries[2]['lastmod'] = '2021-04-30T23:59:59-04:00'
        kept, dropped = fna.split_window_entries(
            entries, window_start='2021-05-01', as_of='2021-06-10T23:59:59-04:00')
        self.assertEqual(len(kept), 2)
        self.assertEqual(dropped, 1)


class TestKeywordRecall(unittest.TestCase):
    def setUp(self):
        self.rules = fna.load_recall_rules()

    def test_strong_term_hit(self):
        hits = fna.recall_text(self.rules, 'Inflation surges as gas prices soar', '')
        rules = {h['rule'] for h in hits}
        self.assertIn('direct_economic_terms', rules)

    def test_no_hit_for_culture_story(self):
        hits = fna.recall_text(self.rules, 'Celebrity wedding draws crowds', '')
        self.assertEqual(hits, [])

    def test_slug_recall_matches_hyphenated_slug(self):
        url = 'https://www.foxbusiness.com/economy/inflation-consumer-price-index-may-2021'
        self.assertTrue(fna.slug_recall(self.rules, url))
        self.assertFalse(fna.slug_recall(
            self.rules, 'https://www.foxnews.com/entertainment/celebrity-wedding-draws-crowds'))


class TestSceExclusion(unittest.TestCase):
    def test_sce_report_detected(self):
        self.assertTrue(fna.is_sce_report(
            'New York Fed survey of consumer expectations shows inflation outlook rise'))
        self.assertFalse(fna.is_sce_report('Consumer prices surge 5% annually'))


class TestHeuristicLabel(unittest.TestCase):
    def test_vocabulary_frozen(self):
        hits = fna.recall_text(fna.load_recall_rules(), 'Inflation surges as gas prices soar', '')
        label = fna.heuristic_label(hits, url='https://www.foxbusiness.com/economy/x')
        self.assertEqual(label['decision'], 'keep')
        self.assertIn('living_prices', label['topics'])
        self.assertIn(label['scope'], fna.SCOPES)

    def test_general_context_only_is_background(self):
        hits = fna.recall_text(fna.load_recall_rules(),
                               'Economy adds jobs as businesses ramp up spending', '')
        label = fna.heuristic_label(hits, url='https://www.foxnews.com/us/x')
        self.assertEqual(label['decision'], 'background')
        self.assertIn('economic_outlook', label['topics'] or ['economic_outlook'])

    def test_foreign_energy_is_global_scope(self):
        hits = fna.recall_text(
            fna.load_recall_rules(),
            'OPEC agrees output increase', 'Oil prices moved after the OPEC decision in Vienna.')
        label = fna.heuristic_label(hits, url='https://www.foxbusiness.com/markets/x')
        self.assertIn(label['scope'], ('global', 'us_and_global'))

    def test_no_hits_is_exclude(self):
        label = fna.heuristic_label([], url='https://www.foxnews.com/us/x')
        self.assertEqual(label['decision'], 'exclude')


class TestArticleParsing(unittest.TestCase):
    def test_json_ld(self):
        meta = fna.parse_article_html(ARTICLE_HTML,
                                      'https://www.foxbusiness.com/economy/inflation-consumer-price-index-may-2021')
        self.assertEqual(meta['title'],
                         'Consumer prices surge 5% annually, most since August 2008')
        self.assertEqual(meta['published_at'], '2021-06-10T08:41:59-04:00')
        self.assertIn('surged', meta['excerpt'])

    def test_meta_fallback(self):
        meta = fna.parse_article_html(ARTICLE_HTML_META_ONLY, 'https://www.foxnews.com/us/gas-prices')
        self.assertEqual(meta['title'], 'Gas prices keep climbing across the U.S.')
        self.assertEqual(meta['published_at'], '2021-06-08T10:00:00-04:00')


class TestWayback(unittest.TestCase):
    def test_cdx_parsing(self):
        captures = fna.parse_cdx_json(CDX_JSON)
        self.assertEqual(len(captures), 2)
        self.assertEqual(captures[0]['timestamp'], '20210610133944')
        self.assertEqual(captures[0]['statuscode'], '200')

    def test_verify_marks_archive_hit(self):
        fetcher = FakeFetcher({
            'https://web.archive.org/cdx/search/cdx?url=foxbusiness.com/economy/inflation-consumer-price-index-may-2021'
            '&output=json&limit=200&filter=statuscode:200': CDX_JSON})
        rec = fna.verify_wayback(
            fetcher, 'https://www.foxbusiness.com/economy/inflation-consumer-price-index-may-2021',
            published_at='2021-06-10T08:41:59-04:00')
        self.assertEqual(rec['status'], 'archive_verified')
        self.assertEqual(rec['capture_count'], 2)
        self.assertEqual(rec['earliest_capture'], '20210610133944')

    def test_verify_marks_unverified_on_error(self):
        fetcher = FakeFetcher({}, fail={'x': 'timeout'})
        rec = fna.verify_wayback(fetcher, 'x', published_at='2021-06-10T08:41:59-04:00')
        self.assertEqual(rec['status'], 'unverified')


class TestCollectMonthEndToEnd(unittest.TestCase):
    """Full pipeline on a fake month: sitemap -> recall -> fetch -> label."""

    def _mapping(self):
        sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.foxbusiness.com/economy/inflation-consumer-price-index-may-2021</loc><lastmod>2021-06-10T08:41:59-04:00</lastmod></url>
<url><loc>https://www.foxnews.com/us/new-york-fed-survey-consumer-expectations-inflation</loc><lastmod>2021-06-09T10:00:00-04:00</lastmod></url>
<url><loc>https://www.foxnews.com/entertainment/celebrity-wedding</loc><lastmod>2021-06-05T10:00:00-04:00</lastmod></url>
<url><loc>https://www.foxnews.com/us/gas-prices-old-story-updated-later</loc><lastmod>2021-06-01T10:00:00-04:00</lastmod></url>
</urlset>"""
        old_article = ARTICLE_HTML.replace(
            b'2021-06-10T08:41:59-04:00', b'2021-04-15T10:00:00-04:00')
        return {
            'https://www.foxbusiness.com/sitemap.xml?type=articles': sitemap,
            'https://www.foxbusiness.com/economy/inflation-consumer-price-index-may-2021': ARTICLE_HTML,
            'https://www.foxnews.com/us/new-york-fed-survey-consumer-expectations-inflation': SCE_ARTICLE_HTML,
            'https://www.foxnews.com/us/gas-prices-old-story-updated-later': old_article,
        }

    def _collect(self, tmp, fetcher):
        return fna.collect_month(
            fetcher=fetcher,
            out_dir=Path(tmp),
            month=202106,
            window_start='2021-05-01',
            as_of='2021-06-10T23:59:59-04:00',
            domains=('https://www.foxbusiness.com',),
            page_limit=50)

    def test_funnel(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetcher = PagedFakeFetcher(self._mapping())
            result = self._collect(tmp, fetcher)
            funnel = result['funnel']
            # 4 sitemap entries in window, 3 slug-recalled, 3 fetched,
            # 2 published in window (one lastmod-fresh but published 2021-04),
            # 1 SCE report excluded -> 1 eligible.
            self.assertEqual(funnel['sitemap_entries_in_window'], 4)
            self.assertEqual(funnel['slug_recalled'], 3)
            self.assertEqual(funnel['article_fetch_ok'], 3)
            self.assertEqual(funnel['published_in_window'], 2)
            self.assertEqual(funnel['excluded_sce_report'], 1)
            self.assertEqual(funnel['eligible'], 1)
            cand = result['candidates'][0]
            self.assertEqual(cand['source'], 'Fox Business')
            self.assertEqual(cand['label']['decision'], 'keep')
            self.assertIn('living_prices', cand['label']['topics'])
            self.assertTrue(cand['article_id'].startswith('external_'))
            self.assertEqual(len(cand['text_sha256']), 64)
            out = Path(tmp) / 'candidates.json'
            self.assertTrue(out.exists())
            saved = json.loads(out.read_text())
            self.assertEqual(saved['funnel']['eligible'], 1)

    def test_resume_skips_completed_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetcher = PagedFakeFetcher(self._mapping())
            first = self._collect(tmp, fetcher)
            fetcher2 = PagedFakeFetcher(self._mapping())
            second = self._collect(tmp, fetcher2)
            # No new sitemap or article fetches on the resumed run, and the
            # rebuilt candidate set is identical (no data loss on resume).
            self.assertEqual(fetcher2.calls, [])
            for k, v in first['funnel'].items():
                if k == 'sitemap_entries_seen':
                    continue  # below-window tail pages are not re-parsed on resume
                self.assertEqual(second['funnel'][k], v, k)
            self.assertEqual([c['article_id'] for c in second['candidates']],
                             [c['article_id'] for c in first['candidates']])

    def test_raw_responses_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetcher = PagedFakeFetcher(self._mapping())
            self._collect(tmp, fetcher)
            raw = Path(tmp) / 'raw'
            self.assertTrue((raw / 'http_log.jsonl').exists())
            sitemaps = list((raw / 'sitemaps').glob('*page-0001.xml.gz'))
            self.assertTrue(sitemaps)
            self.assertEqual(gzip.decompress(sitemaps[0].read_bytes()), self._mapping()[
                'https://www.foxbusiness.com/sitemap.xml?type=articles'])
            self.assertTrue(list((raw / 'articles').glob('*.html.gz')))


class TestExistingMonthsImport(unittest.TestCase):
    def test_fox_only_no_nypost(self):
        ext_dir = REPO_ROOT / 'outputs' / 'sce_media_mechanism_20261024_v1'
        if not ext_dir.exists():
            self.skipTest('existing external sample dir absent')
        windows = fna.import_existing_fox(ext_dir, months=(202106, 202206))
        for month, rows in windows.items():
            self.assertTrue(rows)
            for row in rows:
                self.assertTrue(row['source'].startswith('Fox'),
                                f'non-Fox source leaked: {row["source"]}')
            self.assertEqual(len({r['original_url'] for r in rows}), len(rows))
        if '202106' in windows:
            urls = [r['original_url'] for r in windows['202106']]
            self.assertFalse(any('nypost.com' in u for u in urls))


if __name__ == '__main__':
    unittest.main()
