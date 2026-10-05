import unittest

from studies.sce_inflation_expectations.monthly_analysis import date_group, paired_metrics, weighted_summary


class MonthlyAnalysisTest(unittest.TestCase):
    def test_same_day_not_assumed_to_be_after_release(self):
        cutoff = "2021-05-12T23:59:59-04:00"
        self.assertEqual(date_group("2021-05-11 00:00:00", cutoff), "before_cutoff")
        self.assertEqual(date_group("2021-05-12 00:00:00", cutoff), "same_day_time_unknown")
        self.assertEqual(date_group("2021-05-13 00:00:00", cutoff), "after_cutoff")
        self.assertEqual(date_group(None, cutoff), "unknown_date")

    def test_weighted_mean_std_and_quantile_contracts(self):
        empirical = weighted_summary([1, 3], [1, 3])
        interp = weighted_summary([1, 3], [1, 3], interpolate_median=True)
        self.assertEqual(empirical["weighted_median_pp"], 3)
        self.assertEqual(interp["weighted_median_pp"], 2.5)
        self.assertEqual(empirical["weighted_mean_pp"], 2.5)
        self.assertAlmostEqual(empirical["weighted_std_pp"], .75 ** .5)

    def test_ties_collapsed_before_interpolation(self):
        result = weighted_summary([1, 1, 3], [1, 1, 2], interpolate_median=True)
        self.assertEqual(result["weighted_median_pp"], 2)

    def test_missing_answers_removed_without_dropping_other_rows(self):
        result = weighted_summary([None, 4], [10, 1])
        self.assertEqual(result["n_valid"], 1)
        self.assertEqual(result["weighted_mean_pp"], 4)

    def test_paired_errors_weighted_and_separate_question_masks(self):
        q8 = paired_metrics([3, 5], [2, 2], [1, 3], point_prediction=True)
        self.assertEqual(q8["weighted_mae_pp"], 2.5)
        self.assertEqual(q8["weighted_bias_pp"], 2.5)
        self.assertEqual(q8["weighted_median_absolute_error_pp"], 3)
        self.assertEqual(paired_metrics([3], [None], [1])["n_pairs"], 0)
        self.assertEqual(paired_metrics([3], [1], [1])["n_pairs"], 1)


if __name__ == "__main__":
    unittest.main()
