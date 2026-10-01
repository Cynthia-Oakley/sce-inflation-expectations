"""Independent analytic checks for the SCE Q9 scorer."""

import sys
from pathlib import Path
import unittest


SCORING = Path(__file__).resolve().parents[1] / "studies/sce_inflation_expectations/scoring"
sys.path.insert(0, str(SCORING))
from sce_q9 import score_q9, weighted_empirical_quantile  # noqa: E402


class Q9ScoringTest(unittest.TestCase):
    def test_uniform_closed_and_open(self):
        closed = score_q9([0, 0, 0, 100, 0, 0, 0, 0, 0, 0])
        self.assertEqual((closed.status, closed.family, closed.mean, closed.iqr), ("ok", "uniform", 3, 1))
        open_tail = score_q9([100, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual((open_tail.mean, open_tail.iqr), (25, 13))

    def test_two_adjacent_bins_triangle(self):
        equal = score_q9([0, 0, 0, 50, 50, 0, 0, 0, 0, 0])
        self.assertAlmostEqual(equal.mean, 2)
        self.assertAlmostEqual(equal.iqr, 4 * (1 - 1 / 2**0.5))
        unequal = score_q9([0, 0, 0, 70, 30, 0, 0, 0, 0, 0])
        self.assertAlmostEqual(unequal.mean, 2.367884312210892, places=8)

    def test_beta_two_two_recovered_from_bin_cdf(self):
        # Exact Beta(2,2) on [-2,4]: CDF at 0 and 2 is 7/27 and 20/27.
        bins = [0, 0, 0, 700 / 27, 1300 / 27, 700 / 27, 0, 0, 0, 0]
        score = score_q9(bins)
        self.assertEqual((score.status, score.family), ("ok", "generalized_beta"))
        self.assertAlmostEqual(score.mean, 1, places=7)
        self.assertAlmostEqual(score.prob_deflation, 7 / 27, places=7)
        self.assertLess(score.fit_loss, 1e-12)

    def test_invalid_not_repaired(self):
        self.assertEqual(score_q9([0] * 10).status, "invalid_probability_sum")
        self.assertEqual(score_q9([0, 0, 0, 70, 0, 30, 0, 0, 0, 0]).status, "two_nonadjacent")

    def test_weighted_step_median(self):
        self.assertEqual(weighted_empirical_quantile([1, 2, 3], [1, 3, 1]), 2)
        self.assertEqual(weighted_empirical_quantile([1, 2, 3], [3, 1, 1]), 1)


if __name__ == "__main__":
    unittest.main()
