"""Tests for scripts/build_sce_environment_v2.py.

Integration tests need the raw archives (BLS PDFs, EIA CSV, NYT ledger);
they skip when inputs are absent so a fresh checkout stays green.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_sce_environment_v2 as v2  # noqa: E402

RAW_BLS = REPO_ROOT / "data" / "raw" / "bls_initial_releases"
INPUTS_PRESENT = (
    RAW_BLS.is_dir()
    and (RAW_BLS / "2019-12").is_dir()  # history extension fetched
    and v2.COMPONENTS_JSONL.is_file()
    and v2.GAS_WEEKLY_CSV.is_file()
    and v2.NYT_LEDGER.is_file()
)


class TestShiftMonth(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(v2.shift_month("2021-01", -1), "2020-12")
        self.assertEqual(v2.shift_month("2021-01", -13), "2019-12")
        self.assertEqual(v2.shift_month("2020-12", 2), "2021-02")


@unittest.skipUnless(INPUTS_PRESENT, "E v2 raw inputs not present")
class TestBuildWindowV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.targets = ["2021-05", "2021-06"]  # dev months
        cls.result = v2.build_window_v2(cls.targets, RAW_BLS, False, "")
        cls.records = cls.result["external_events"]["records_by_step"]
        cls.events = cls.result["external_events"]["events_by_step"]

    def test_record_composition(self):
        # 4 v1 headline + 5 components + 2 gasoline (latest)
        # + 6 history series x 11 refs (D049a/D051)
        for step in ("0", "1"):
            self.assertEqual(len(self.records[step]), 77)
        roles = [r["role"] for r in self.records["0"]]
        self.assertEqual(roles.count("latest_release"), 11)
        self.assertEqual(roles.count("history"), 66)

    def test_history_refs_contiguous_and_ordered(self):
        hist = [r for r in self.records["0"] if r["role"] == "history"]
        expected_refs = [v2.shift_month("2021-04", -k) for k in range(11, 0, -1)]
        series: dict[str, list[str]] = {}
        for r in hist:
            key = r["signal_id"].rsplit("_20", 1)[0]
            series.setdefault(key, []).append(r["reference_period"])
        self.assertEqual(len(series), 6)
        for key, refs in series.items():
            self.assertEqual(refs, expected_refs, key)

    def test_history_spot_values(self):
        # step 0 (target 2021-05, ref 2021-04): history refs 2020-05..2021-03
        hist = {(r["signal_id"].rsplit("_20", 1)[0], r["reference_period"]): r["value"]
                for r in self.records["0"] if r["role"] == "history"}
        # pandemic-era first releases (the values available at the time)
        self.assertEqual(hist[("bls_unemployment_rate_sa", "2020-05")], 13.3)
        self.assertEqual(hist[("bls_cpi_u_all_items_yoy_nsa", "2021-03")], 2.6)
        self.assertEqual(hist[("bls_cpi_energy_yoy_nsa", "2021-03")], 13.2)
        self.assertAlmostEqual(
            hist[("eia_gasoline_retail_regular_mean", "2021-03")], 2.81)

    def test_everything_published_before_as_of(self):
        for step, target in enumerate(self.targets):
            as_of = datetime.fromisoformat(
                self.result["external_events"]["as_of"][str(step)])
            for r in self.records[str(step)]:
                self.assertLess(datetime.fromisoformat(r["published_at"]), as_of,
                                r["signal_id"])
            for e in self.events[str(step)]:
                self.assertLessEqual(e["pub_date"], as_of.date().isoformat())

    def test_component_values_match_raw(self):
        comps = {r["signal_id"].split("_nsa_")[0]: r["value"]
                 for r in self.records["0"] if r["signal_id"].startswith("bls_cpi_")
                 and "component" not in r["signal_id"]
                 and r["role"] == "latest_release"}
        # 2021-04 ref (for target 2021-05): food 2.4, energy 25.1 (from archive)
        self.assertEqual(comps["bls_cpi_food_yoy"], 2.4)
        self.assertEqual(comps["bls_cpi_energy_yoy"], 25.1)

    def test_events_m_minus_1_through_as_of(self):
        # D050: events span month M-1 plus early M up to the as_of day (the
        # CPI release day inside M); all pub_dates are strictly before as_of.
        as_of = datetime.fromisoformat(
            self.result["external_events"]["as_of"]["0"])
        months = set()
        for e in self.events["0"]:
            months.add(e["pub_date"][:7])
            self.assertLessEqual(e["pub_date"], as_of.date().isoformat())
        self.assertEqual(months, {"2021-04", "2021-05"})

    def test_as_of_is_cpi_release_day(self):
        # step 0 (target 2021-05): as_of = the day the 2021-04 CPI was
        # released, 2021-05-12 23:59:59 ET (D050)
        as_of = self.result["external_events"]["as_of"]["0"]
        self.assertTrue(as_of.startswith("2021-05-12T23:59:59"), as_of)
        targets = self.result["bundle"]["provider_args"]["targets"]
        self.assertEqual(targets[0]["as_of"], as_of)

    def test_gasoline_present(self):
        gas = [r for r in self.records["0"]
               if r["signal_id"].startswith("eia_gasoline")
               and r["role"] == "latest_release"]
        self.assertEqual(len(gas), 2)
        level = next(r for r in gas if r["unit"] == "dollars_per_gallon")
        self.assertGreater(level["value"], 1.0)
        self.assertLess(level["value"], 6.0)


if __name__ == "__main__":
    unittest.main()
