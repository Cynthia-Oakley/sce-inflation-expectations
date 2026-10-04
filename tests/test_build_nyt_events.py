"""Tests for scripts/build_nyt_events.py (pure selection logic; no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_nyt_events as bne  # noqa: E402


def doc(**kw):
    base = {
        "document_type": "article",
        "web_url": "https://www.nytimes.com/2021/06/10/x.html",
        "pub_date": "2021-06-10T09:00:00+0000",
        "headline": {"main": "Some headline"},
        "abstract": "An abstract.",
        "snippet": "",
        "section_name": "Business",
        "news_desk": "Business",
    }
    base.update(kw)
    return base


class TestParseMonths(unittest.TestCase):
    def test_range_within_year(self):
        self.assertEqual(bne.parse_months("2021-01..2021-03"),
                         ["2021-01", "2021-02", "2021-03"])

    def test_range_crossing_year(self):
        self.assertEqual(bne.parse_months("2020-11..2021-02"),
                         ["2020-11", "2020-12", "2021-01", "2021-02"])


class TestClassifyDoc(unittest.TestCase):
    def test_front_page_wins_without_keywords(self):
        d = doc(print_section="A", print_page="1",
                headline={"main": "Local team wins championship"})
        self.assertEqual(bne.classify_doc(d), ("front_page", []))

    def test_keyword_without_front_page(self):
        d = doc(headline={"main": "Gasoline Prices Jump Again"},
                abstract="Drivers feel the pinch as inflation builds.")
        tier, matched = bne.classify_doc(d)
        self.assertEqual(tier, "strong_keyword")
        self.assertIn("gasoline", matched)
        self.assertIn("inflation", matched)

    def test_no_match(self):
        d = doc(headline={"main": "Opera season opens"}, section_name="Arts")
        self.assertEqual(bne.classify_doc(d), (None, []))

    def test_front_page_requires_a1(self):
        d = doc(print_section="B", print_page="1",
                headline={"main": "Metro brief"})
        self.assertEqual(bne.classify_doc(d), (None, []))

    def test_broad_only_off_front_page_dropped(self):
        # Covid human-interest noise: broad keyword, no front page -> excluded
        d = doc(headline={"main": "A family reunites after the pandemic"},
                abstract="Covid kept them apart for a year.")
        self.assertEqual(bne.classify_doc(d), (None, []))

    def test_front_page_broad_only(self):
        d = doc(print_section="A", print_page="1",
                headline={"main": "Vaccine Drive Accelerates"},
                abstract="The coronavirus campaign expands.")
        tier, matched = bne.classify_doc(d)
        self.assertEqual(tier, "front_page+broad")
        self.assertIn("vaccine", matched)

    def test_front_page_plus_strong(self):
        d = doc(print_section="A", print_page="1",
                headline={"main": "Inflation Surges"})
        self.assertEqual(bne.classify_doc(d),
                         ("front_page+strong", ["inflation"]))

    def test_substring_false_positives_blocked(self):
        # "apparently" contains rent; "waging" contains wage's stem prefix;
        # neither may count as a keyword hit
        d = doc(print_section="A", print_page="1",
                headline={"main": "Gunman Kills 9 at Rail Yard"},
                abstract="The attacker was apparently waging a personal feud.")
        self.assertEqual(bne.classify_doc(d), ("front_page", []))

    def test_inflections_still_match(self):
        d = doc(headline={"main": "Rents Rise as Gas Prices Follow"})
        tier, matched = bne.classify_doc(d)
        self.assertEqual(tier, "strong_keyword")
        self.assertIn("rent", matched)
        self.assertIn("gas price", matched)


class TestSelectEvents(unittest.TestCase):
    def test_dedupe_sort_cap(self):
        fp = doc(print_section="A", print_page="1", pub_date="2021-06-05T00:00:00+0000",
                 headline={"main": "Front page story"},
                 web_url="https://x/1")
        kw_old = doc(headline={"main": "Inflation rises"},
                     pub_date="2021-06-02T00:00:00+0000", web_url="https://x/2")
        kw_new = doc(headline={"main": "Supply chain snarls"},
                     pub_date="2021-06-20T00:00:00+0000", web_url="https://x/3")
        dup = dict(fp)  # same url as fp
        non_article = doc(print_section="A", print_page="1",
                          document_type="multimedia", web_url="https://x/4")
        out = bne.select_events([kw_new, fp, kw_old, dup, non_article],
                                "2021-06", "sha", max_per_month=10)
        self.assertEqual(len(out), 3)  # dup and multimedia dropped
        # final output is chronological regardless of tier
        self.assertEqual([e["headline"] for e in out],
                         ["Inflation rises", "Front page story",
                          "Supply chain snarls"])

    def test_front_page_keyword_combo_ranked_first(self):
        combo = doc(print_section="A", print_page="1",
                    headline={"main": "Inflation Surges as Economy Reopens"},
                    pub_date="2021-06-15T00:00:00+0000", web_url="https://x/9")
        fp_plain = [doc(print_section="A", print_page="1",
                        pub_date=f"2021-06-{d:02d}T00:00:00+0000",
                        web_url=f"https://x/fp{d}") for d in range(1, 6)]
        out = bne.select_events(fp_plain + [combo], "2021-06", "sha",
                                max_per_month=3)
        # combo (rank 0) survives the cap; fp-only overflow keeps most recent
        tiers = [e["tier"] for e in out]
        self.assertEqual(tiers.count("front_page+strong"), 1)
        self.assertEqual([e["pub_date"][:10] for e in out if e["tier"] == "front_page"],
                         ["2021-06-04", "2021-06-05"])

    def test_strong_off_front_page_outranks_broad_on_front_page(self):
        strong = doc(headline={"main": "Used Car Prices Soar"},
                     pub_date="2021-06-03T00:00:00+0000", web_url="https://x/s")
        broad_fp = doc(print_section="A", print_page="1",
                       headline={"main": "Delta Variant Spreads"},
                       pub_date="2021-06-10T00:00:00+0000",
                       web_url="https://x/b")
        fp_plain = [doc(print_section="A", print_page="1",
                        pub_date=f"2021-06-{d:02d}T00:00:00+0000",
                        web_url=f"https://x/fp{d}") for d in range(20, 23)]
        out = bne.select_events([strong, broad_fp] + fp_plain,
                                "2021-06", "sha", max_per_month=2)
        self.assertEqual([e["tier"] for e in out],
                         ["strong_keyword", "front_page+broad"])

    def test_overflow_keeps_most_recent(self):
        docs = [doc(headline={"main": f"Inflation story {d}"},
                    pub_date=f"2021-06-{d:02d}T00:00:00+0000",
                    web_url=f"https://x/{d}") for d in range(1, 8)]
        out = bne.select_events(docs, "2021-06", "sha", max_per_month=3)
        self.assertEqual([e["pub_date"][:10] for e in out],
                         ["2021-06-05", "2021-06-06", "2021-06-07"])

    def test_cap_applies(self):
        docs = [doc(print_section="A", print_page="1",
                    pub_date=f"2021-06-{d:02d}T00:00:00+0000",
                    web_url=f"https://x/{d}") for d in range(1, 8)]
        out = bne.select_events(docs, "2021-06", "sha", max_per_month=3)
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
