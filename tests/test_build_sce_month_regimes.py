"""Offline tests for scripts/build_sce_month_regimes.py helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_sce_month_regimes import (  # noqa: E402
    REF_END, REF_START, classify, direction, latest_before, month_add)


class TestMonthMath(unittest.TestCase):
    def test_month_add(self):
        self.assertEqual(month_add("2019-01", -1), "2018-12")
        self.assertEqual(month_add("2019-01", -13), "2017-12")
        self.assertEqual(month_add("2026-09", 1), "2026-10")

    def test_reference_period_precedes_window(self):
        self.assertLess(REF_END, "2019-01")
        self.assertEqual(REF_START, "2013-06")


class TestClassification(unittest.TestCase):
    def test_direction_deadband(self):
        self.assertEqual(direction(0.5), "up")
        self.assertEqual(direction(-0.5), "down")
        self.assertEqual(direction(0.004), "flat")
        self.assertEqual(direction(-0.004), "flat")

    def test_magnitude_thresholds(self):
        self.assertEqual(classify(0.05, 0.074, 0.176), "small")
        self.assertEqual(classify(0.10, 0.074, 0.176), "medium")
        self.assertEqual(classify(0.20, 0.074, 0.176), "large")


class TestLatestBefore(unittest.TestCase):
    def test_picks_latest_eligible(self):
        recs = [{"published_at": "2019-06-12T08:30:00-04:00", "value": 1.8},
                {"published_at": "2019-05-10T08:30:00-04:00", "value": 2.0},
                {"published_at": "2019-07-11T08:30:00-04:00", "value": 9.9}]
        hit = latest_before(recs, "2019-06-30T23:59:59-04:00")
        self.assertEqual(hit["value"], 1.8)
        self.assertIsNone(latest_before(recs, "2019-05-01T00:00:00-04:00"))


if __name__ == "__main__":
    unittest.main()
