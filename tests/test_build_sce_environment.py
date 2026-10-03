"""Round-trip tests for scripts/build_sce_environment.py.

Requires the archived BLS initial releases under data/raw/bls_initial_releases/
(gitignored raw data); every test skips when the archive is absent so a fresh
checkout without raw data stays green.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_sce_environment as bse  # noqa: E402

RAW_ROOT = REPO_ROOT / "data" / "raw" / "bls_initial_releases"

MAIN_TARGETS = bse.parse_targets("2021-01..2021-12")
FWD_TARGETS = bse.parse_targets("2026-06..2026-10")

SIGNAL_FIELDS = {
    "signal_id", "measure", "value", "unit", "reference_period",
    "published_at", "source_version", "source_url", "eligibility",
}

ARCHIVE_AVAILABLE = (RAW_ROOT / "2020-11").is_dir() and \
    any((RAW_ROOT / "2020-11").glob("cpi_*.pdf")) and \
    (RAW_ROOT / "2026-04").is_dir() and \
    any((RAW_ROOT / "2026-04").glob("empsit_*.pdf"))

needs_archive = unittest.skipUnless(
    ARCHIVE_AVAILABLE, "data/raw/bls_initial_releases archive missing")


def _built(targets):
    return bse.build_window(list(targets), RAW_ROOT, fetch=False, proxy="")


def _validate(bundle, sim):
    bse.validate_with_official_schemas(bundle, sim)


class TestCalendar(unittest.TestCase):
    def test_reference_period_is_m_minus_2(self):
        self.assertEqual(bse.reference_period("2021-01"), "2020-11")
        self.assertEqual(bse.reference_period("2021-12"), "2021-10")
        self.assertEqual(bse.reference_period("2026-06"), "2026-04")
        self.assertEqual(bse.reference_period("2021-02"), "2020-12")

    def test_as_of_dst_offsets(self):
        # EST (-05:00) outside DST, EDT (-04:00) inside DST (2021: 03-14..11-07)
        self.assertEqual(bse.as_of_for("2021-01"), "2020-12-31T23:59:59-05:00")
        self.assertEqual(bse.as_of_for("2021-06"), "2021-05-31T23:59:59-04:00")
        self.assertTrue(bse.as_of_for("2021-03").endswith("-05:00"))  # Feb end
        self.assertTrue(bse.as_of_for("2021-07").endswith("-04:00"))
        # 2026 DST: 03-08..11-01; forward window as_of are all -04:00
        for t in FWD_TARGETS:
            self.assertTrue(bse.as_of_for(t).endswith("-04:00"), t)

    def test_parse_targets_range(self):
        self.assertEqual(len(MAIN_TARGETS), 12)
        self.assertEqual(MAIN_TARGETS[0], "2021-01")
        self.assertEqual(MAIN_TARGETS[-1], "2021-12")
        self.assertEqual(bse.parse_targets("2026-06..2026-10"),
                         ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"])


@needs_archive
class TestMainWindow2021(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = _built(MAIN_TARGETS)
        cls.bundle = cls.result["bundle"]
        _validate(cls.bundle, bse.simulation_config(MAIN_TARGETS))

    def test_step_count_and_structure(self):
        self.assertEqual(len(self.bundle["provider_args"]["targets"]), 12)
        sbs = self.bundle["provider_args"]["signals_by_step"]
        self.assertEqual(sorted(sbs.keys(), key=int), [str(i) for i in range(12)])
        bcasts = self.bundle["information_program"]["broadcasts"]
        self.assertEqual(len(bcasts), 12)
        for i, b in enumerate(bcasts):
            self.assertEqual(b["at_step"], i)
            self.assertEqual(b["ttl"], 1)
            self.assertEqual(b["channel"], "official_bls_release")

    def test_targets_match_as_of(self):
        targets = self.bundle["provider_args"]["targets"]
        for i, t in enumerate(targets):
            self.assertEqual(t["target_month"], MAIN_TARGETS[i])
            self.assertEqual(t["as_of"], bse.as_of_for(MAIN_TARGETS[i]))

    def test_each_step_has_four_eligible_signals(self):
        sbs = self.bundle["provider_args"]["signals_by_step"]
        for step, signals in sbs.items():
            self.assertEqual(len(signals), 4, f"step {step}")
            for s in signals:
                self.assertEqual(set(s.keys()), SIGNAL_FIELDS)
                self.assertEqual(s["eligibility"], "eligible")
                self.assertTrue(s["signal_id"].endswith("_initial"))
                self.assertTrue(s["source_url"].startswith(
                    "https://www.bls.gov/news.release/archives/"))
                self.assertTrue(s["source_version"].startswith("USDL-"))
                self.assertEqual(s["reference_period"],
                                 bse.reference_period(
                                     MAIN_TARGETS[int(step)]))
                pub = datetime.fromisoformat(s["published_at"])
                as_of = datetime.fromisoformat(
                    self.bundle["provider_args"]["targets"][int(step)]["as_of"])
                self.assertLess(pub, as_of, s["signal_id"])
                self.assertIn(s["published_at"][-6:], ("-04:00", "-05:00"))

    def test_no_runtime_injected_keys(self):
        pa = self.bundle["provider_args"]
        for banned in ("persona_by_id", "audit_dir", "run_id"):
            self.assertNotIn(banned, pa)
        self.assertEqual(pa["evidence_class"],
                         "historical_official_release_evidence")
        self.assertEqual(pa["excluded_sources"], ["fred", "nyfed_sce",
                                                  "nyt_archive"])

    def test_signals_equal_external_events(self):
        self.assertEqual(
            self.result["external_events"]["records_by_step"],
            self.bundle["provider_args"]["signals_by_step"])
        self.assertEqual(self.result["external_events"]["as_of"],
                         {str(i): bse.as_of_for(t)
                          for i, t in enumerate(MAIN_TARGETS)})

    def test_dev_window_reference_values_unchanged(self):
        # 2021-03/2021-04 reference months overlap the dev window exemplar:
        # yoy/mom/unemployment must match environment.json exactly.
        dev = json.loads((REPO_ROOT / "studies" / "sce_inflation_expectations"
                          / "environment" / "environment.json").read_text())
        dev_signals = {s["signal_id"]: s for sigs in
                       dev["provider_args"]["signals_by_step"].values()
                       for s in sigs}
        sbs = self.bundle["provider_args"]["signals_by_step"]
        for step in (4, 5):  # targets 2021-05, 2021-06 -> refs 2021-03, 2021-04
            for s in sbs[str(step)]:
                old = dev_signals.get(s["signal_id"])
                if old is None:
                    continue  # nonfarm is new in the main window
                self.assertEqual(s["value"], old["value"], s["signal_id"])
                self.assertEqual(s["source_version"], old["source_version"])
                self.assertEqual(s["published_at"], old["published_at"])


@needs_archive
class TestForwardWindow2026(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = _built(FWD_TARGETS)
        cls.bundle = cls.result["bundle"]
        _validate(cls.bundle, bse.simulation_config(FWD_TARGETS))

    def test_step_count(self):
        self.assertEqual(len(self.bundle["provider_args"]["targets"]), 5)
        sbs = self.bundle["provider_args"]["signals_by_step"]
        self.assertEqual(sorted(sbs.keys(), key=int), [str(i) for i in range(5)])
        self.assertEqual(len(self.bundle["information_program"]
                             ["broadcasts"]), 5)

    def test_reference_periods_m_minus_2(self):
        sbs = self.bundle["provider_args"]["signals_by_step"]
        for step, signals in sbs.items():
            for s in signals:
                self.assertEqual(s["reference_period"],
                                 bse.reference_period(
                                     FWD_TARGETS[int(step)]), s["signal_id"])
                pub = datetime.fromisoformat(s["published_at"])
                as_of = datetime.fromisoformat(
                    self.bundle["provider_args"]["targets"][int(step)]["as_of"])
                self.assertLess(pub, as_of, s["signal_id"])

    def test_targets_are_2026_06_to_10(self):
        targets = self.bundle["provider_args"]["targets"]
        self.assertEqual([t["target_month"] for t in targets],
                         ["2026-06", "2026-07", "2026-08", "2026-09",
                          "2026-10"])
        self.assertEqual([bse.reference_period(t) for t in FWD_TARGETS],
                         ["2026-04", "2026-05", "2026-06", "2026-07",
                          "2026-08"])


if __name__ == "__main__":
    unittest.main()
