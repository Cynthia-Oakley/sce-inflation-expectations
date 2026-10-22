"""Offline unit tests for scripts/build_sce_population_grid.py (synthetic data).

Covers the ESS formula, the education/employment cell mapping (including the
unknown pool), the floor + largest-remainder allocation with its fallback
rules, and count conservation. No micro files, no network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_sce_population_grid as g  # noqa: E402


class TestESS(unittest.TestCase):
    def test_equal_weights(self):
        self.assertAlmostEqual(g.effective_sample_size([1.0] * 20), 20.0)

    def test_empty_and_invalid(self):
        self.assertEqual(g.effective_sample_size([]), 0.0)
        self.assertEqual(g.effective_sample_size([None, float("nan"), 0.0]), 0.0)

    def test_known_values(self):
        # (sum w)^2 / sum w^2 = 16 / 10 = 1.6
        self.assertAlmostEqual(g.effective_sample_size([3.0, 1.0]), 1.6)
        # one dominant weight drives ESS towards 1
        ess = g.effective_sample_size([100.0, 1.0, 1.0, 1.0])
        self.assertAlmostEqual(ess, 103.0 ** 2 / 10003.0)


class TestCellMapping(unittest.TestCase):
    def test_attached(self):
        self.assertEqual(g.assign_cell("College", "employed"),
                         ("college|attached", ""))
        self.assertEqual(g.assign_cell("High School", "on_leave"),
                         ("high_school|attached", ""))

    def test_not_attached_keeps_label(self):
        cell, reason = g.assign_cell("Some College", "retired")
        self.assertEqual((cell, reason), ("some_college|not_attached", ""))
        cell, _ = g.assign_cell("Some College", "unemployed")
        self.assertEqual(cell, "some_college|not_attached")
        # mapping collapses the grid cell only; the label itself is preserved
        self.assertNotEqual(g.classify_employment({"Q10_7": 1}),
                            g.classify_employment({"Q10_3": 1}))

    def test_unknown_pool(self):
        self.assertEqual(g.assign_cell(None, "employed"),
                         (g.UNKNOWN_CELL, "education_missing"))
        self.assertEqual(g.assign_cell("College", None),
                         (g.UNKNOWN_CELL, "employment_unclassified"))
        self.assertEqual(g.assign_cell(None, None),
                         (g.UNKNOWN_CELL, "both"))
        self.assertEqual(g.assign_cell("PhD", "employed"),
                         (g.UNKNOWN_CELL, "education_missing"))

    def test_q10_priority(self):
        # priority: 3 (unemployed) beats 9 (homemaker); 1 beats 3
        self.assertEqual(g.classify_employment(
            {"Q10_3": 1, "Q10_9": 1}), "unemployed")
        self.assertEqual(g.classify_employment(
            {"Q10_1": 1, "Q10_3": 1}), "employed")
        self.assertEqual(g.classify_employment({f"Q10_{i}": 0 for i in range(1, 11)}),
                         None)


class TestAllocateCore(unittest.TestCase):
    CELLS = g.PRIMARY_CELLS + [g.UNKNOWN_CELL]

    def _counts(self, **kw):
        return {c: kw.get(c, 100) for c in self.CELLS}

    def test_conservation_and_floor(self):
        counts = self._counts()
        masses = {c: 100.0 for c in self.CELLS}
        alloc = g.allocate_core(counts, masses, 512, floor=24)
        self.assertEqual(sum(alloc.values()), 512)
        for c in g.PRIMARY_CELLS:
            self.assertGreaterEqual(alloc[c], 24)

    def test_proportional_remainder(self):
        counts = self._counts()
        masses = {c: 1.0 for c in self.CELLS}
        masses["college|attached"] = 100.0
        alloc = g.allocate_core(counts, masses, 512, floor=24)
        self.assertEqual(sum(alloc.values()), 512)
        # the heavy cell should receive the largest share of the remainder
        self.assertGreater(alloc["college|attached"], alloc["high_school|attached"])

    def test_tiny_cell_fallback(self):
        counts = self._counts(**{"high_school|not_attached": 5})
        masses = {c: 1.0 for c in self.CELLS}
        alloc = g.allocate_core(counts, masses, 512, floor=24)
        self.assertEqual(alloc["high_school|not_attached"], 5)
        self.assertEqual(sum(alloc.values()), 512)  # slots flow back to others

    def test_empty_cell(self):
        counts = self._counts(**{"high_school|not_attached": 0})
        masses = {c: (0.0 if c == "high_school|not_attached" else 1.0)
                  for c in self.CELLS}
        alloc = g.allocate_core(counts, masses, 512, floor=24)
        self.assertEqual(alloc["high_school|not_attached"], 0)
        self.assertEqual(sum(alloc.values()), 512)

    def test_unknown_capped(self):
        counts = self._counts(**{g.UNKNOWN_CELL: 3})
        masses = {c: 1.0 for c in self.CELLS}
        alloc = g.allocate_core(counts, masses, 512, floor=24)
        self.assertEqual(alloc[g.UNKNOWN_CELL], 3)  # full inclusion when small

    def test_never_above_frame(self):
        import random
        rng = random.Random(7)
        for _ in range(50):
            counts = {c: rng.randint(0, 600) for c in self.CELLS}
            masses = {c: (rng.random() * counts[c]) for c in self.CELLS}
            alloc = g.allocate_core(counts, masses, 512, floor=24)
            self.assertEqual(sum(alloc.values()),
                             min(512, sum(counts.values())))
            for c in self.CELLS:
                self.assertLessEqual(alloc[c], counts[c])

    def test_frame_smaller_than_total(self):
        counts = {c: 10 for c in self.CELLS}
        masses = {c: 1.0 for c in self.CELLS}
        alloc = g.allocate_core(counts, masses, 512, floor=24)
        self.assertEqual(sum(alloc.values()), 70)  # whole frame taken, honest

    def test_infeasible_floor_raises(self):
        counts = {c: 100 for c in self.CELLS}
        masses = {c: 1.0 for c in self.CELLS}
        with self.assertRaises(ValueError):
            g.allocate_core(counts, masses, 100, floor=24)  # base 168 > 100

    def test_validation(self):
        with self.assertRaises(ValueError):
            g.allocate_core({"a": 1}, {"a": 1.0, "b": 1.0}, 10)
        with self.assertRaises(ValueError):
            g.allocate_core({"a": -1}, {"a": 1.0}, 10)
        with self.assertRaises(ValueError):
            g.allocate_core({"a": 5}, {"a": -1.0}, 10)


if __name__ == "__main__":
    unittest.main()
