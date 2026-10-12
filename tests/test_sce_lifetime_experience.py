"""Independent numerical and information-boundary checks for the new sidecar."""
from copy import deepcopy
import unittest

from studies.sce_inflation_expectations.lifetime_experience import (
    MARKER, age_text, annual_inflation, event_matches, insert_block, period_stats, stage_summaries,
)


def year_rows(year, values):
    return [{"observation_date": f"{year}-{m:02d}-01", "index": str(value)}
            for m, value in enumerate(values, 1)]


class LifetimeChecks(unittest.TestCase):
    def test_annual_average_change_is_not_december_change(self):
        # Dec/Dec is 20%; annual average is 110 vs 100, so change is 10%.
        rows = year_rows(2000, [100]*12) + year_rows(2001, [100]*6+[120]*6)
        annual = annual_inflation(rows, "index", 2001)
        self.assertAlmostEqual(annual[2001]["annual_average_yoy_pct"], 10.)

    def test_incomplete_and_future_years_are_not_used(self):
        rows = year_rows(2000, [100]*12) + year_rows(2001, [110]*12)
        rows += year_rows(2002, [121]*11) + year_rows(2003, [130]*12)
        self.assertEqual(set(annual_inflation(rows, "index", 2001)), {2001})
        # Complete 2003 cannot get a rate from incomplete 2002.
        self.assertEqual(set(annual_inflation(rows, "index", 2003)), {2001})

    def test_duplicate_and_nonpositive_months_rejected(self):
        for rows in (year_rows(2000, [100]*12)+year_rows(2000, [100]),
                     year_rows(2000, [0]*12), year_rows(2000, [float("nan")]*12)):
            with self.assertRaises(ValueError):
                annual_inflation(rows, "index", 2000)

    def test_missing_history_period_is_not_silently_filled(self):
        annual = {2001: {"annual_average_yoy_pct": 3.}, 2003: {"annual_average_yoy_pct": 5.}}
        with self.assertRaises(ValueError):
            period_stats(annual, 2001, 2003)

    def test_birth_year_and_start_age_boundaries(self):
        annual = {y: {"annual_average_yoy_pct": float(y-1990)} for y in range(1990, 2020)}
        child_and_adult = stage_summaries(annual, 1990, 6, 2019)
        adult = stage_summaries(annual, 1990, 18, 2019)
        self.assertEqual(child_and_adult[0]["first_year"], 1996)
        self.assertEqual(child_and_adult[0]["last_year"], 2007)
        self.assertEqual(adult[0]["first_year"], 2008)
        self.assertEqual(adult[0]["last_year"], 2019)

    def test_event_overlap_does_not_invent_unborn_experience(self):
        events = [{"id": "old", "start_year": 1975, "end_year": 1982}]
        self.assertEqual(event_matches(events, [1985, 1986], 6, 2021), [])
        matches = event_matches(events, [1976, 1977], 6, 2021)
        self.assertEqual(matches[0]["overlap_status"], "some_birth_year_candidates")
        self.assertEqual(matches[0]["age_during_overlap_range"], [6, 6])
        self.assertEqual(event_matches(events, [1960], 6, 1981), [])

    def test_insert_preserves_old_PE_and_instrument(self):
        original = [{"role": "user", "content": "Old profile and environment.\n\n"+MARKER+" Q8. Q9. Output JSON."}]
        baseline = deepcopy(original)
        changed = insert_block(original, "A neutral historical block.")
        self.assertEqual(original, baseline)
        self.assertEqual(changed[0]["content"].replace("A neutral historical block.\n\n", "", 1), original[0]["content"])
        self.assertEqual(changed[0]["content"].split(MARKER)[1], original[0]["content"].split(MARKER)[1])

    def test_changed_message_shape_or_multiple_questions_rejected(self):
        for content in ("No marker", MARKER+MARKER):
            with self.assertRaises(ValueError):
                insert_block([{"role": "user", "content": content}], "Extra")

    def test_self_report_at_60_does_not_invent_an_older_age(self):
        text = age_text({"target_month_age_conservative_range": [60, 60], "source_age_group": "Over 60"})
        self.assertIn("approximately 60 years", text)
        self.assertIn("category also includes age 60", text)


if __name__ == "__main__":
    unittest.main()
