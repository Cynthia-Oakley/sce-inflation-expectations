import math
import unittest

from studies.sce_inflation_expectations.submission_tools.release_evidence import (
    check_downstream, load_case, metrics,
)


class ReleaseEvidenceTests(unittest.TestCase):
    def sample(self):
        predictions = []
        expected = []
        for model, values in (("official_sce", [0, 4]), ("simulated_sce", [1, 3])):
            for date, value, actual in zip(("2025-01", "2025-02"), values, (1, 3)):
                predictions.append(dict(outcome="credit", horizon="1", scope="A", evaluation="rolling",
                    date=date, target_date=date, model=model, n_train="36", prediction=value,
                    actual=actual, error=value-actual))
            expected.append(dict(outcome="credit", horizon="1", scope="A", evaluation="rolling", model=model,
                n="2", mae=1 if model == "official_sce" else 0,
                rmse=1 if model == "official_sce" else 0, bias=0))
        contrasts = [dict(outcome="credit", horizon="1", scope="A", evaluation="rolling",
            reference="official_sce", candidate="simulated_sce", n="2", reference_mae=1,
            candidate_mae=0, reference_rmse=1, candidate_rmse=0, mae_improvement=1, rmse_improvement=1)]
        return predictions, expected, contrasts

    def test_recomputes_known_errors_and_perfect_candidate_without_refitting(self):
        result = check_downstream(*self.sample())
        self.assertEqual(result["model_metrics_verified"], 2)
        self.assertEqual(result["paired_contrasts_verified"], 1)
        self.assertFalse(result["regressions_refitted"])
        result = metrics([0, 6], [1, 4])
        self.assertEqual(result["mae_pp"], 1.5)
        self.assertAlmostEqual(result["rmse_pp"], math.sqrt(2.5))

    def test_equal_scores_cannot_hide_different_pairing_or_changed_error(self):
        predictions, expected, contrasts = self.sample()
        predictions[-1]["date"] = "2025-03"
        with self.assertRaisesRegex(ValueError, "identical"):
            check_downstream(predictions, expected, contrasts)
        predictions, expected, contrasts = self.sample()
        predictions[-1]["error"] = 2
        with self.assertRaisesRegex(ValueError, "stored error"):
            check_downstream(predictions, expected, contrasts)

    def test_expected_results_are_checked_not_merely_copied(self):
        predictions, expected, contrasts = self.sample()
        expected[0]["rmse"] = 7
        with self.assertRaisesRegex(ValueError, "mismatch"):
            check_downstream(predictions, expected, contrasts)

    def test_invalid_missing_or_duplicate_months_fail_closed(self):
        for rows in ([dict(month="202501", truth_pp=3, raw=float("nan"))],
                     [dict(month="202502", truth_pp=3, raw=3), dict(month="202501", truth_pp=3, raw=3)],
                     [dict(month="202501", truth_pp=3, raw=3)] * 2):
            with self.assertRaises(ValueError):
                load_case(rows, ["raw"])


if __name__ == "__main__":
    unittest.main()
