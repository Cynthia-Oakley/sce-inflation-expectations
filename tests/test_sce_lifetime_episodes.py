"""Numerical trajectory, clipping and recalled-history boundaries."""
import unittest

from studies.sce_inflation_expectations.lifetime_episodes import (
    monthly_changes, select_landmarks, history_duration, make_cards, render_cards, trend_sentence, prepare,
)


class EpisodeTests(unittest.TestCase):
    def test_missing_main_age_cannot_silently_create_only_a_baseline(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root/"outputs/invalid"
            with self.assertRaisesRegex(ValueError, "main start age"):
                prepare(root, out, (10, 12), main_start_age=6)
            self.assertFalse(out.exists())

    def test_monthly_yoy_is_not_monthly_or_annualized_growth(self):
        rows = [{"observation_date": "2000-01-01", "x": "100"},
                {"observation_date": "2000-12-01", "x": "109"},
                {"observation_date": "2001-01-01", "x": "110"},
                {"observation_date": "2002-01-01", "x": "121"}]
        result = monthly_changes(rows, "x", 2001)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["cpi_yoy_pct"], 10.)
        self.assertEqual(result[0]["month"], "2001-01")

    def test_missing_annual_lag_not_interpolated_and_duplicate_rejected(self):
        rows = [{"observation_date": "2001-01-01", "x": "110"}]
        self.assertEqual(monthly_changes(rows, "x", 2001), [])
        with self.assertRaises(ValueError):
            monthly_changes(rows+rows, "x", 2001)

    def test_landmarks_preserve_multiple_peaks_and_a_reversal(self):
        path = [{"month": f"{1970+i}-12", "cpi_yoy_pct": v} for i, v in enumerate((1, 3, 9, 4, 12, 6))]
        selected = select_landmarks(path, 5)
        self.assertEqual([x["cpi_yoy_pct"] for x in selected], [1, 9, 4, 12, 6])

    def test_recovery_duration_is_historical_and_censored_when_unseen(self):
        history = [{"month": f"2008-{m:02d}", "cpi_yoy_pct": v} for m, v in zip((7, 8, 9, 10), (8, 7, 6, 4))]
        result = history_duration(history[:2], history[0], history, 5.)
        self.assertEqual(result["months_from_peak_to_below_threshold"], 3)
        self.assertEqual(result["longest_consecutive_months_shown_at_or_above_threshold"], 2)
        self.assertEqual(result["continuous_high_inflation_spell_around_peak"]["known_months"], 3)
        self.assertTrue(result["continuous_high_inflation_spell_around_peak"]["left_censored"])
        short = history_duration(history[:2], history[0], history[:3], 5.)
        self.assertIsNone(short["months_from_peak_to_below_threshold"])
        self.assertTrue(short["no_subsequent_fall_observed_by_history_end"])

    def test_birth_uncertainty_and_future_context_are_clipped(self):
        history = [{"month": f"{y}-{m:02d}", "cpi_yoy_pct": 2.} for y in range(2004, 2009) for m in range(1, 13)]
        catalogue = {"landmark_cap_per_era": 8, "duration_threshold_pct": 5.,
            "sources": {"past": {"review_date": "2009-01-01"}, "future": {"review_date": "2025-01-01"}},
            "eras": [{"id": "era", "start_year": 2004, "end_year": 2024, "label": "Example era", "facts": [
                {"id": "before_person", "event_start": "2005-01", "event_end": "2005-12", "source_id": "past", "text": "Before the eligible window."},
                {"id": "eligible", "event_start": "2008-01", "event_end": "2008-06", "source_id": "past", "text": "A past fact."},
                {"id": "future", "event_start": "2008-01", "event_end": "2008-06", "source_id": "future", "text": "A future source."}]}]}
        cards = make_cards(history, catalogue, [2000, 2001], 6, "2022-03-10T23:59:59-05:00")
        self.assertEqual(cards[0]["covered_start"], "2008-01")
        self.assertEqual(cards[0]["covered_end"], "2008-12")
        self.assertEqual([f["id"] for f in cards[0]["context_facts"]], ["eligible"])
        self.assertEqual(cards[0]["age_range_approximate"], [6, 8])
        text = render_cards(cards, "Past price history.")
        self.assertNotIn("this peak", text)
        self.assertNotIn("2024", text)
        self.assertNotIn("Before the eligible", text)
        self.assertNotIn("family shopping", text)
        self.assertIn("family shopping", render_cards(cards, "Past price history.", involvement=True))

    def test_missing_month_cannot_be_hidden_as_a_complete_episode(self):
        history = [{"month": "2008-01", "cpi_yoy_pct": 2.}, {"month": "2008-03", "cpi_yoy_pct": 3.}]
        with self.assertRaises(ValueError):
            make_cards(history, {"eras": []}, [2000], 6, "2022-03-10T23:59:59-05:00")

    def test_generated_words_distinguish_slowing_inflation_from_falling_prices(self):
        points = lambda values: [{"cpi_yoy_pct": v} for v in values]
        self.assertEqual(trend_sentence(points((8, 6, 3))), "Inflation eased.")
        self.assertNotIn("prices fell", trend_sentence(points((8, 6, 3))))
        self.assertIn("turned negative", trend_sentence(points((2, 6, -2, 3))))
        self.assertEqual(trend_sentence(points((1, 12, 5, 15))), "Inflation rose, then eased, then rose.")

    def test_cutoff_high_is_not_called_a_confirmed_peak_or_counted_twice(self):
        from copy import deepcopy
        path = [{"month": "2021-11", "cpi_yoy_pct": 6.5}, {"month": "2021-12", "cpi_yoy_pct": 7.}]
        card = {"covered_start": "2021-11", "covered_end": "2021-12", "label": "Recent prices",
                "age_range_approximate": None, "life_stages": [], "context_facts": [], "landmarks": path,
                "duration": history_duration(path, path[-1], path, 5.)}
        text = render_cards([card, deepcopy(card)], "Past prices.")
        self.assertEqual(text.count("The stretch at/above"), 1)
        self.assertEqual(text.count("No later fall"), 1)
        self.assertNotIn("peak", text)


if __name__ == "__main__":
    unittest.main()
