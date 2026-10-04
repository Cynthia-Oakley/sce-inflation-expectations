"""Tests for scripts/fetch_eia_gasoline.py (pure aggregation logic only;
no network access)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import fetch_eia_gasoline as feg  # noqa: E402


class TestAggregateMonthly(unittest.TestCase):
    WEEKLY = [
        ("2020-01-06", 2.0), ("2020-01-13", 3.0),  # Jan 2020 mean 2.5
        ("2021-01-04", 5.0), ("2021-01-11", 5.0),
        ("2021-01-18", 5.0), ("2021-01-25", 5.0),  # Jan 2021 mean 5.0
        ("2021-02-01", 4.0),                        # Feb 2021, no prior year
    ]

    def test_monthly_mean_and_week_count(self):
        rows = {r["month"]: r for r in feg.aggregate_monthly(self.WEEKLY)}
        self.assertEqual(rows["2020-01"]["price_mean"], 2.5)
        self.assertEqual(rows["2020-01"]["n_weeks"], 2)
        self.assertEqual(rows["2021-02"]["n_weeks"], 1)

    def test_yoy_computed_only_with_prior_year(self):
        rows = {r["month"]: r for r in feg.aggregate_monthly(self.WEEKLY)}
        self.assertNotIn("yoy_pct", rows["2020-01"])
        self.assertEqual(rows["2021-01"]["yoy_pct"], 100.0)  # 2.5 -> 5.0
        self.assertNotIn("yoy_pct", rows["2021-02"])

    def test_output_sorted_by_month(self):
        months = [r["month"] for r in feg.aggregate_monthly(self.WEEKLY)]
        self.assertEqual(months, sorted(months))


if __name__ == "__main__":
    unittest.main()
