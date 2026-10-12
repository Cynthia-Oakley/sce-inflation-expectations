"""Mathematical checks for the offline probability-reporting sensitivity operator."""
import unittest

import numpy as np

from studies.sce_inflation_expectations.age_reporting_audit import round_distribution


class RoundingAuditChecks(unittest.TestCase):
    def test_exact_grids_are_unchanged_and_invalid_answers_are_not_repaired(self):
        p = [0, 0, 10, 30, 40, 15, 5, 0, 0, 0]
        self.assertEqual(round_distribution(p, 5), p)
        with self.assertRaises(ValueError):
            round_distribution([0, 0, 10, 30, 39, 15, 5, 0, 0, 0], 5)

    def test_mass_conservation_on_asymmetric_and_extreme_distributions(self):
        rng = np.random.default_rng(4711)
        vectors = [[100]+[0]*9, [0]*9+[100], [1, 3, 12, 34, 30, 12, 5, 2, 1, 0]]
        vectors += [v.tolist() for v in rng.dirichlet(np.ones(10), 50)*100]
        for p in vectors:
            for unit in (1, 5, 10):
                for random in (False, True):
                    q = np.asarray(round_distribution(p, unit, stochastic=random, rng=rng))
                    self.assertAlmostEqual(q.sum(), 100)
                    self.assertTrue(np.all((q >= 0) & (q <= 100)))
                    self.assertTrue(np.allclose(q/unit, np.rint(q/unit)))
                    self.assertTrue(np.all(np.abs(q-p) <= unit+1e-8))

    def test_balanced_random_rounding_has_the_analytical_expectation(self):
        # Only two outcomes are possible: [5,0,5,...,90] with probability .4,
        # or [0,5,5,...,90] with probability .6. Thus the mean is the original.
        p = [2, 3, 5, 0, 0, 90, 0, 0, 0, 0]
        rng = np.random.default_rng(104729)
        means = np.mean([round_distribution(p, 5, stochastic=True, rng=rng) for _ in range(6000)], axis=0)
        self.assertTrue(np.all(np.abs(means-p) < .08))

    def test_zero_average_errors_do_not_preserve_the_population_median(self):
        original = np.asarray([1., 2., 5.])
        error = np.asarray([-.1, -.1, .2])
        self.assertAlmostEqual(error.mean(), 0)
        self.assertAlmostEqual(float(np.median(original+error)-np.median(original)), -.1)


if __name__ == "__main__":
    unittest.main()
