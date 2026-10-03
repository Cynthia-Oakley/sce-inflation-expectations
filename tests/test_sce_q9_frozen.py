"""Tests for the frozen project Q9 scorer (scoring/sce_q9_frozen.py)."""

import sys
from pathlib import Path
import unittest

SCORING = Path(__file__).resolve().parents[1] / "studies/sce_inflation_expectations/scoring"
sys.path.insert(0, str(SCORING))
from sce_q9 import score_q9  # noqa: E402
from sce_q9_frozen import provenance, score_q9_frozen  # noqa: E402


class FrozenScorerTest(unittest.TestCase):
    def test_beta_branch_uses_candidate(self):
        import importlib.util
        diag_path = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_sce_beta.py"
        spec = importlib.util.spec_from_file_location("diagnose_sce_beta", diag_path)
        diag = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = diag
        spec.loader.exec_module(diag)

        bins = [5, 10, 30, 30, 15, 5, 3, 1, 1, 0]
        frozen = score_q9_frozen(bins)
        self.assertEqual((frozen.status, frozen.family), ("ok", "generalized_beta"))
        direct = diag.fit(bins, "relaxed_tail_skip_zero", tail_start=20.0)
        self.assertAlmostEqual(frozen.mean, direct["mean"], places=12)
        self.assertAlmostEqual(frozen.p50, direct["quartiles"][1], places=12)
        self.assertTrue(frozen.p25 <= frozen.p50 <= frozen.p75)
        self.assertAlmostEqual(frozen.iqr, frozen.p75 - frozen.p25, places=9)
        self.assertTrue(0.0 <= frozen.prob_deflation <= 1.0)

    def test_non_beta_branches_identical_to_original(self):
        cases = [
            [0, 0, 0, 100, 0, 0, 0, 0, 0, 0],      # uniform closed
            [100, 0, 0, 0, 0, 0, 0, 0, 0, 0],      # uniform open tail
            [0, 0, 0, 50, 50, 0, 0, 0, 0, 0],      # two adjacent bins
            [0, 0, 50, 0, 50, 0, 0, 0, 0, 0],      # two non-adjacent bins
            [0, 0, 0, 50, 40, 0, 0, 0, 0, 0],      # invalid sum
        ]
        for bins in cases:
            self.assertEqual(score_q9_frozen(bins), score_q9(bins), msg=str(bins))

    def test_provenance_live_matches_pinned(self):
        prov = provenance()
        self.assertTrue(prov["live_matches_pinned"])
        self.assertEqual(prov["variant"], "relaxed_tail_skip_zero")
        self.assertEqual(prov["tail_start"], 20.0)


if __name__ == "__main__":
    unittest.main()
