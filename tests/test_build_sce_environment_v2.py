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
        # 4 v1 headline + 5 components + 11 history + 2 gasoline
        for step in ("0", "1"):
            self.assertEqual(len(self.records[step]), 22)
        roles = [r["role"] for r in self.records["0"]]
        self.assertEqual(roles.count("latest_release"), 11)
        self.assertEqual(roles.count("history"), 11)

    def test_history_refs_contiguous_and_ordered(self):
        hist = [r for r in self.records["0"] if r["role"] == "history"]
        refs = [r["reference_period"] for r in hist]
        self.assertEqual(refs, [v2.shift_month("2021-03", -k)
                                for k in range(11, 0, -1)])

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
                 and "component" not in r["signal_id"]}
        # 2021-03 ref (for target 2021-05): food 3.5, energy 13.2 (from archive)
        self.assertEqual(comps["bls_cpi_food_yoy"], 3.5)
        self.assertEqual(comps["bls_cpi_energy_yoy"], 13.2)

    def test_events_from_m_minus_1(self):
        for e in self.events["0"]:
            self.assertEqual(e["month"] if "month" in e else
                             e["pub_date"][:7], "2021-04")

    def test_gasoline_present(self):
        gas = [r for r in self.records["0"]
               if r["signal_id"].startswith("eia_gasoline")]
        self.assertEqual(len(gas), 2)
        level = next(r for r in gas if r["unit"] == "dollars_per_gallon")
        self.assertGreater(level["value"], 1.0)
        self.assertLess(level["value"], 6.0)


if __name__ == "__main__":
    unittest.main()
