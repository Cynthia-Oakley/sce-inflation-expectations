import unittest

from studies.sce_inflation_expectations.experiments.full_a_personal_inputs import (
    _calibrate_remaining_weights,
    _select_common,
    _without_tone,
)
from studies.sce_inflation_expectations.experiments.media_mechanism_v3 import draw_personal
from studies.sce_inflation_expectations.experiments.media_timing_inputs import cutoff_for_response


def _weight_frame():
    rows = {}
    cells = [
        f"{education}|{numeracy}|{age}|{income}"
        for education in ("high_school", "some_college", "college")
        for numeracy in ("High", "Low")
        for age in ("under_40", "40_60", "over_60")
        for income in ("under_50k", "50k_100k", "over_100k")
    ]
    for i in range(512):
        cell = cells[i % len(cells)]
        rows[f"aid_{i:03d}"] = {
            "raw_survey_weight": 1.0 + i / 1000,
            "analysis_weight": 1.0 + i / 1000,
            "design_weight": 1.0 + i / 1000,
            "poststratified_weight": 1.0 + i / 1000,
            "weight_valid": True,
            "inclusion_probability": 1.0,
            "stratum": cell,
            "grid_version": "education_numeracy_age_income_54_v1",
            "profile_cell": cell,
        }
    return rows


class FullAPersonalInputsTests(unittest.TestCase):
    def test_cutoff_is_previous_calendar_day_new_york_end(self):
        self.assertEqual(cutoff_for_response("2021-06-17", "202106"), "2021-06-16T23:59:59-04:00")
        self.assertEqual(cutoff_for_response("2021-01-17", "202101"), "2021-01-16T23:59:59-05:00")
        with self.assertRaises(ValueError):
            cutoff_for_response("2021-07-01", "202106")

    def test_exclusion_calibration_restores_each_original_cell_mass(self):
        weights = _weight_frame()
        eligible = set(weights) - {"aid_000", "aid_054"}
        adjusted, receipt, original_zero_cells = _calibrate_remaining_weights(weights, eligible, "201901")
        self.assertEqual(len(receipt), 54)
        self.assertEqual(original_zero_cells, [])
        self.assertEqual(set(adjusted), eligible)
        for cell, audit in receipt.items():
            self.assertAlmostEqual(audit["retained_calibrated_mass"], audit["original_poststratified_mass"])
            actual = sum(r["analysis_weight"] for r in adjusted.values() if r["profile_cell"] == cell)
            self.assertAlmostEqual(actual, audit["original_poststratified_mass"])
            self.assertAlmostEqual(actual, sum(
                r["poststratified_weight"] for r in weights.values() if r["profile_cell"] == cell))

    def test_empty_original_cell_is_named_as_error(self):
        weights = _weight_frame()
        empty_cell = weights["aid_000"]["profile_cell"]
        eligible = {aid for aid, row in weights.items() if row["profile_cell"] != empty_cell}
        with self.assertRaisesRegex(ValueError, empty_cell):
            _calibrate_remaining_weights(weights, eligible, "201901")

    def test_alarm_one_personal_selection_is_invariant_to_tone(self):
        rows = [
            {"article_id": "a", "headline": "Inflation and prices", "abstract": "", "snippet": "",
             "pub_date": "2021-06-01T12:00:00-04:00", "routing_tags": ["food"],
             "semantic_label": {"topics": ["living_prices"]}},
            {"article_id": "b", "headline": "Jobs update", "abstract": "", "snippet": "",
             "pub_date": "2021-06-02T12:00:00-04:00", "routing_tags": [],
             "semantic_label": {"topics": ["labor_income"]}},
            {"article_id": "c", "headline": "CPI changes", "abstract": "", "snippet": "",
             "pub_date": "2021-06-03T12:00:00-04:00", "routing_tags": ["road_fuel"],
             "semantic_label": {"topics": ["living_prices"]}},
        ]
        with_tone = [{**row, "semantic_label": {**row["semantic_label"], "tone": "alarming"}}
                     for row in rows]
        plain = draw_personal(rows, [], 2, "seed", {"food"}, alarming_boost=1.0, cpi_boost=1.5)
        annotated = draw_personal(with_tone, [], 2, "seed", {"food"}, alarming_boost=1.0, cpi_boost=1.5)
        self.assertEqual([r["article_id"] for r in plain], [r["article_id"] for r in annotated])

    def test_tone_projection_does_not_fill_missing_values(self):
        projected = _without_tone({"article_id": "a", "decision": "keep", "topics": [], "scope": "us_national",
                                   "tone": None, "persistence": None})
        self.assertEqual(projected, {"article_id": "a", "decision": "keep", "topics": [], "scope": "us_national"})

    def test_common_three_fills_from_eligible_pool_when_a1_is_short(self):
        pool = [
            {"article_id": "a1", "headline": "Local story one", "abstract": "", "snippet": "",
             "pub_date": "2024-03-01T12:00:00-05:00", "placement": "a1", "routing_tags": [],
             "semantic_label": {"scope": "us_local", "topics": ["other_economic"]}},
            {"article_id": "a2", "headline": "Local story two", "abstract": "", "snippet": "",
             "pub_date": "2024-03-02T12:00:00-05:00", "placement": "a1", "routing_tags": ["food"],
             "semantic_label": {"scope": "us_local", "topics": ["living_prices"]}},
            {"article_id": "b1", "headline": "Consumer inflation pressures families", "abstract": "",
             "snippet": "", "pub_date": "2024-03-03T12:00:00-05:00", "placement": "other_recorded_page",
             "routing_tags": ["food"], "semantic_label": {"scope": "us_national", "topics": ["living_prices"]}},
            {"article_id": "b2", "headline": "A sports story", "abstract": "", "snippet": "",
             "pub_date": "2024-03-04T12:00:00-05:00", "placement": "other_recorded_page",
             "routing_tags": [], "semantic_label": {"scope": "us_local", "topics": ["other_economic"]}},
        ]
        common, receipt = _select_common(pool, "2024-03-15")
        self.assertEqual(len(common), 3)
        self.assertEqual({row["article_id"] for row in common}, {"a1", "a2", "b1"})
        self.assertEqual(receipt, {
            "rule": "a1_first_then_eligible_pool_salience", "a1_available": 2, "fallback_n": 1
        })


if __name__ == "__main__":
    unittest.main()
