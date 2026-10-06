import unittest
from studies.sce_inflation_expectations.household_state_analysis import density, paired_metrics


class AnalysisTest(unittest.TestCase):
    def test_frozen_uniform_hand_computed_and_invalid_probability(self):
        bins = [0.] * 10
        bins[3] = 100.
        result = density(bins)
        # Fourth official bin is inflation between 2 and 4 percent.
        self.assertEqual(result["mean"], 3.)
        self.assertEqual(result["iqr"], 1.)
        self.assertEqual(density([10.] * 9 + [None])["status"], "invalid_bins")
        self.assertEqual(density([9.] * 10)["status"], "invalid_bins")

    def test_paired_errors_group_gap_and_common_case_missingness(self):
        rows = [{"Q1": c, "real": 6.-c, "baseline": 2., "q1_state": 6.-c} for c in range(1, 6)]
        rows.append({"Q1": 1, "real": 100., "baseline": 0., "q1_state": None})
        result = paired_metrics(rows)
        self.assertEqual(result["n_complete_pairs"], 5)
        self.assertEqual(result["n_excluded"], 1)
        self.assertAlmostEqual(result["arms"]["baseline"]["MAE_pp"], 1.4)
        self.assertEqual(result["arms"]["q1_state"]["MAE_pp"], 0.)
        self.assertEqual(result["arms"]["baseline"]["group_gap_absolute_error_pp"], 2.)
        self.assertTrue(result["development_signal_both_primary_and_group_improve"])

    def test_wider_answers_without_fit_improvement_are_not_success(self):
        rows = [{"Q1": c, "real": 2., "baseline": 2., "q1_state": float(c)} for c in range(1, 6)]
        result = paired_metrics(rows)
        self.assertFalse(result["development_signal_both_primary_and_group_improve"])
        self.assertGreater(result["arms"]["q1_state"]["distribution"]["iqr"], 0.)


if __name__ == "__main__":
    unittest.main()
