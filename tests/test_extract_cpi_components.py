"""Tests for scripts/extract_cpi_components.py.

Unit tests feed synthetic sentences covering every phrasing variant seen in the
2020-2026 BLS releases; the archive regression test re-runs extraction over the
real PDFs and skips when the raw archive is absent (fresh checkout stays green).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import extract_cpi_components as ecc  # noqa: E402

ARCHIVE = REPO_ROOT / "data" / "raw" / "bls_initial_releases"


def hit(text: str, signal: str, ref: str = "2021-05"):
    return ecc._extract_from_text([text], signal, ref)


class TestTextPatterns(unittest.TestCase):
    def test_standard_over_the_last_12_months(self):
        h = hit("The energy index rose 24.5 percent over the last 12-months.",
                "cpi_energy_yoy")
        self.assertEqual(h["value"], 24.5)

    def test_combined_sentence_food(self):
        h = hit("The energy index rose 28.5 percent over the last 12-months, "
                "and the food index increased 2.2 percent.", "cpi_food_yoy")
        self.assertEqual(h["value"], 2.2)

    def test_over_that_period_food(self):
        h = hit("The energy index rose 24.8 percent over the last 12 months, "
                "and the food index increased 4.6 percent over that period.",
                "cpi_food_yoy")
        self.assertEqual(h["value"], 4.6)

    def test_for_the_12_months_ending(self):
        h = hit("The energy index increased 17.9 percent for the 12 months "
                "ending April.", "cpi_energy_yoy", "2026-04")
        self.assertEqual(h["value"], 17.9)

    def test_over_the_last_year_gasoline(self):
        h = hit("The gasoline index rose 42.1 percent over the last year.",
                "cpi_gasoline_yoy", "2021-09")
        self.assertEqual(h["value"], 42.1)

    def test_since_month_year_validated(self):
        h = hit("The gasoline index rose 56.2 percent since May 2020, when it "
                "was at its lowest level.", "cpi_gasoline_yoy", "2021-05")
        self.assertEqual(h["value"], 56.2)

    def test_since_month_year_wrong_offset_rejected(self):
        # "since March 2020" is 14 months before 2021-05: not a 12-month change
        h = hit("The gasoline index rose 56.2 percent since March 2020.",
                "cpi_gasoline_yoy", "2021-05")
        self.assertIsNone(h)

    def test_gasoline_after_energy_clause_2026(self):
        h = hit("The index for energy increased 23.5 percent over the past 12 "
                "months and the index for gasoline rose 40.5 percent.",
                "cpi_gasoline_yoy", "2026-05")
        self.assertEqual(h["value"], 40.5)

    def test_gasoline_participle_same_period(self):
        h = hit("The index for energy increased 16.3 percent over the past 12 "
                "months due in large part to the index for gasoline rising 27.4 "
                "percent over the same period.", "cpi_gasoline_yoy", "2026-08")
        self.assertEqual(h["value"], 27.4)

    def test_gasoline_energy_commodity_wrap_2020(self):
        h = hit("The energy index fell 9.4 percent over the past 12 months. "
                "Energy commodity indexes fell sharply over the period, with the "
                "fuel oil index declining 26.4 percent and the gasoline index "
                "decreasing 19.3 percent.", "cpi_gasoline_yoy", "2020-11")
        self.assertEqual(h["value"], -19.3)

    def test_shelter_parenthetical_signed(self):
        h = hit("... rose 1.6 percent over the past 12 months. Among the "
                "indexes rising more quickly were those for shelter "
                "(+1.7 percent), used cars and trucks (+9.4 percent), and "
                "medical care (+1.8 percent).", "cpi_shelter_yoy", "2021-03")
        self.assertEqual(h["value"], 1.7)

    def test_shelter_parenthetical_unsigned(self):
        h = hit("... over the last 12 months (its largest 12-month increase "
                "since the period ending May 1975). Indexes rising less than "
                "4.6 percent include shelter (3.5 percent) and medical care "
                "(1.3 percent).", "cpi_shelter_yoy", "2021-10")
        self.assertEqual(h["value"], 3.5)

    def test_food_at_home_12_months_ending(self):
        h = hit("The index for food at home rose 2.7 percent over the 12 "
                "months ending in May.", "cpi_food_at_home_yoy", "2026-05")
        self.assertEqual(h["value"], 2.7)


class TestArtifactFixes(unittest.TestCase):
    def test_split_letter_tokens_repaired(self):
        # exercise the fix table directly on a synthetic page text
        text = "Th e food at home index rose. The e nergy index rose. A ll items."
        for bad, good in ecc._ARTIFACT_FIXES:
            text = text.replace(bad, good)
        self.assertIn("The food at home index", text)
        self.assertIn("The energy index", text)
        self.assertIn("All items", text)


@unittest.skipUnless(ARCHIVE.is_dir() and list(ARCHIVE.glob("*/cpi_*.pdf")),
                     "raw BLS PDF archive not present")
class TestArchiveRegression(unittest.TestCase):
    def test_full_extraction_85_of_85(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out, hand = Path(td) / "out.jsonl", Path(td) / "hand.jsonl"
            ecc.main(["--archive", str(ARCHIVE), "--out", str(out),
                      "--handoff", str(hand)])
            records = [json.loads(l) for l in out.open()]
            handoff = [json.loads(l) for l in hand.open()]
        n_pdfs = len(list(ARCHIVE.glob("*/cpi_*.pdf")))
        self.assertEqual(len(records), n_pdfs * len(ecc.PATTERNS))
        self.assertEqual(handoff, [])
        # every value keeps its source quote, page and pdf hash
        for r in records:
            self.assertTrue(r["quote"])
            self.assertGreaterEqual(r["page"], 1)
            self.assertEqual(len(r["source_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
