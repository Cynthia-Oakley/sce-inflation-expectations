from copy import deepcopy
import unittest

from studies.sce_inflation_expectations.experiments.state_continuity import (
    build_dependency_plan, legal_prior_fields, select_frame,
)


def belief(period, q8=3):
    return {"source_kind": "observed_previous", "source_period": period,
            "q8_q9": {"q8_point_pct": q8, "q9_bins": [10] * 10}}


class StateContinuityTests(unittest.TestCase):
    def test_q8_survives_missing_q9_and_probability_mass_is_not_invented(self):
        prior = {"q8_point_pct": -1, "q9_bins": [None] * 10}
        self.assertEqual(legal_prior_fields(prior), {"q8": True, "q9": False})
        self.assertFalse(legal_prior_fields({"q9_bins": [-1] + [101 / 9] * 9})["q9"])

    def test_selection_uses_priority_not_outcome_or_weight_and_neutralizes_model_weight(self):
        p = {"personas": [{"agent_id": "a", "weight": 100, "attributes": {}},
                          {"agent_id": "b", "weight": 1, "attributes": {}}]}
        side = {"persons": [{"agent_id": "a", "stable_priority": 9, "survey_weight": 100},
                            {"agent_id": "b", "stable_priority": 1, "survey_weight": 2}]}
        before = deepcopy(p)
        rows = select_frame(p, side, 1)
        self.assertEqual(rows[0]["persona"]["agent_id"], "b")
        self.assertEqual(rows[0]["inclusion_probability"], .5)
        self.assertEqual(rows[0]["analysis_weight_as_delivered"], 4)
        self.assertEqual(p, before)

    def fixture(self):
        months = ["202505", "202506", "202507"]
        names = [["a", "b"], ["a", "c"], ["a", "b"]]
        selected = {m: [{"persona": {"agent_id": a}} for a in aa] for m, aa in zip(months, names)}
        priors = {m: {a: belief(int(m) - 1) for a in aa} for m, aa in zip(months, names)}
        entries = {m: {a: {"survey_entry_status": "returning"} for a in aa} for m, aa in zip(months, names)}
        return months, selected, priors, entries

    def test_recursive_dependency_does_not_refresh_from_new_true_belief(self):
        months, selected, priors, entries = self.fixture()
        priors["202506"]["a"]["q8_q9"]["q8_point_pct"] = 99
        nodes, summary = build_dependency_plan(selected, priors, entries, months=months)
        r = next(v for v in nodes if v["month"] == "202506" and v["agent_id"] == "a"
                 and v["arm"] == "simulated_history" and v["repeat"] == 1)
        self.assertIsNone(r["initial_belief"])
        self.assertEqual(r["dependency"]["month"], "202505")
        self.assertEqual(r["dependency"]["repeat"], 1)
        self.assertEqual(summary["person_months"], 6)
        self.assertEqual(summary["distinct_people"], 3)
        self.assertEqual(summary["logical_positions"], 24)
        self.assertEqual(summary["potential_unique_calls_before_prompt_hash"], 18)

    def test_core_gap_is_a_simulated_older_state_and_not_a_new_survey_entrant(self):
        months, selected, priors, entries = self.fixture()
        nodes, _ = build_dependency_plan(selected, priors, entries, months=months)
        r = next(v for v in nodes if v["month"] == "202507" and v["agent_id"] == "b"
                 and v["arm"] == "simulated_history")
        self.assertEqual(r["source_kind"], "simulated_older")
        self.assertEqual(r["survey_entry_status"], "returning")
        self.assertEqual(r["core_entry_status"], "core_gap_return")

    def test_initial_state_is_shared_between_arms_but_never_across_repeats(self):
        months, selected, priors, entries = self.fixture()
        nodes, _ = build_dependency_plan(selected, priors, entries, months=months)
        first = [r for r in nodes if r["month"] == "202505" and r["agent_id"] == "a"]
        self.assertEqual(len({r["logical_reuse_key"] for r in first}), 2)

    def test_current_belief_or_nonconsecutive_calendar_is_rejected(self):
        months, selected, priors, entries = self.fixture()
        priors["202505"]["a"]["source_period"] = 202505
        with self.assertRaises(ValueError):
            build_dependency_plan(selected, priors, entries, months=months)
        with self.assertRaises(ValueError):
            build_dependency_plan(selected, priors, entries, months=["202505", "202507"])
