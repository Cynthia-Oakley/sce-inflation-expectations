"""Checks for selection independence and unequal inclusion-weight correction."""
import unittest
import numpy as np
from scripts.check_sce_population_precision import allocate, draw_sample, quantile


class PopulationPrecisionTest(unittest.TestCase):
    def test_sparse_cells_have_coverage_and_bounded_allocation(self):
        np.testing.assert_array_equal(allocate([90, 9, 1], 10), [8, 1, 1])
        with self.assertRaises(ValueError):
            allocate([5, 5, 1], 2)

    def test_design_correction_recovers_known_cell_population(self):
        cells = np.array(["a"] * 90 + ["b"] * 9 + ["c"])
        ix, multiplier = draw_sample(cells, 10, np.random.default_rng(42), True)
        for name, total in [("a", 90), ("b", 9), ("c", 1)]:
            self.assertAlmostEqual(multiplier[cells[ix] == name].sum(), total)
        self.assertEqual(len(set(ix)), 10)

    def test_census_and_fixed_seed(self):
        cells = np.array(["a", "a", "b", "b"])
        ix, mult = draw_sample(cells, 4, np.random.default_rng(42), True)
        np.testing.assert_array_equal(np.sort(ix), np.arange(4))
        np.testing.assert_array_equal(mult, np.ones(4))
        first = draw_sample(cells, 2, np.random.default_rng(42), True)
        second = draw_sample(cells, 2, np.random.default_rng(42), True)
        np.testing.assert_array_equal(first[0], second[0])

    def test_weighted_median_uses_mass_and_ignores_missing_answer(self):
        self.assertEqual(quantile(np.array([1., 3., 9., np.nan]), np.array([1., 1., 8., 100.]), .5), 9.)


if __name__ == "__main__":
    unittest.main()
