"""Offline tests for scripts/build_sce_fullperiod_batch_population.py."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_sce_fullperiod_batch_population import (  # noqa: E402
    PRIORITY, SAMPLE_MONTHS)


class TestPriorityMonths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cov = json.loads(
            (REPO_ROOT / "outputs/sce_fullperiod_data_20261021_v1/coverage.json")
            .read_text())
        cls.by_month = {m["target_month"].replace("-", ""): m
                        for m in cov["months"]}

    def test_priority_in_coverage_with_micro(self):
        for t in PRIORITY:
            self.assertIn(t, self.by_month)
            self.assertTrue(self.by_month[t]["micro_truth_available"], t)

    def test_priority_never_touches_frozen_samples(self):
        self.assertFalse(set(PRIORITY) & SAMPLE_MONTHS)

    def test_continuity_acceptance_window_complete(self):
        # Codex: continuity acceptance needs 2025-05..07 consecutive
        for t in ("202505", "202506", "202507"):
            self.assertIn(t, PRIORITY)


if __name__ == "__main__":
    unittest.main()
