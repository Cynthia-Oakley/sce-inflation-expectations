from copy import deepcopy
import unittest

from studies.sce_inflation_expectations.experiments.recent_b_continuity_pe import (
    checked_months, dependency_plan, fixed_population, resolve_prior,
    validate_dependencies, validate_public_environment,
)


def initial_state():
    return {"fields": {"q8": {"value": -2.0, "source_period": 202510, "source_kind": "synthetic_donor"},
                       "q9": {"value": [10] * 10, "source_period": 202510, "source_kind": "synthetic_donor"}},
            "history_centers": [], "comparison_reference_day": "2025-10-31",
            "comparison_day_source": "synthetic_prior_reference_month_end"}


def environment():
    return {"scheduled_events": [], "information_program": {"broadcasts": []},
            "provider_args": {"targets": [{"as_of": "2025-11-13T23:59:59-05:00"}],
                              "events_by_step": {"0": []}, "signals_by_step": {"0": [
                                  {"signal_id": "bls_cpi_price", "published_at": "2025-10-24T08:30:00-04:00"}]}}}


class RecentBContinuityPETests(unittest.TestCase):
    def test_fixed_roster_has_one_root_and_a_complete_consecutive_chain_per_person(self):
        months = ("202511", "202512", "202601")
        nodes = dependency_plan(["b", "a"], months)
        result = validate_dependencies(nodes, ["a", "b"], months)
        self.assertEqual((result["positions"], result["roots"], result["edges"]), (6, 2, 4))
        self.assertEqual(sum(n["initial_state_source"] is not None for n in nodes), 2)
        self.assertEqual(nodes[-2]["dependency"], {"month": "202512", "agent_id": "a"})

    def test_gap_reordering_duplicate_and_out_of_scope_months_are_rejected(self):
        for months in (("202511", "202601"), ("202512", "202511"), ("202511", "202511"),
                       ("202510", "202511"), ("202512", "202601")):
            with self.assertRaises(ValueError):
                checked_months(months)

    def test_no_entry_exit_or_later_root_can_hide_in_dependency_plan(self):
        months = ("202511", "202512")
        nodes = dependency_plan(["a", "b"], months)
        changed = deepcopy(nodes); changed[-1]["dependency"] = None
        with self.assertRaises(ValueError):
            validate_dependencies(changed, ["a", "b"], months)
        with self.assertRaises(ValueError):
            validate_dependencies(nodes[:-1], ["a", "b"], months)

    def test_first_state_is_copied_and_signed_q8_remains_legal(self):
        initial = {"a": initial_state()}
        node = dependency_plan(["a"], ("202511", "202512"))[0]
        state = resolve_prior(node, initial, {})
        self.assertEqual(state["fields"]["q8"]["value"], -2.0)
        state["fields"]["q8"]["value"] = 7
        self.assertEqual(initial["a"]["fields"]["q8"]["value"], -2.0)

    def test_root_cannot_accept_real_personal_or_pre_simulated_answers(self):
        node = dependency_plan(["a"], ("202511", "202512"))[0]
        for kind in ("own_observed", "simulated"):
            state = initial_state(); state["fields"]["q8"]["source_kind"] = kind
            with self.assertRaisesRegex(ValueError, "synthetic initial seed"):
                resolve_prior(node, {"a": state}, {})

    def test_later_synthetic_state_cannot_secretly_swap_a_new_donor(self):
        node = dependency_plan(["a"], ("202511", "202512"))[1]
        state = initial_state(); state["fields"]["q8"]["value"] = 9.0
        saved = {("202511", "a"): {"month": "202511", "agent_id": "a", "state": state}}
        with self.assertRaisesRegex(ValueError, "original seed"):
            resolve_prior(node, {"a": initial_state()}, saved)

    def test_missing_predecessor_blocks_instead_of_monthly_donor_refresh(self):
        node = dependency_plan(["a"], ("202511", "202512"))[1]
        with self.assertRaisesRegex(ValueError, "Previous simulated state is unavailable"):
            resolve_prior(node, {"a": initial_state()}, {})

    def test_saved_state_cannot_be_taken_from_another_person_or_month(self):
        node = dependency_plan(["a"], ("202511", "202512"))[1]
        saved = {("202511", "a"): {"month": "202511", "agent_id": "b", "state": initial_state()}}
        with self.assertRaisesRegex(ValueError, "identity/month differs"):
            resolve_prior(node, {"a": initial_state()}, saved)
        swapped = deepcopy(node); swapped["dependency"]["agent_id"] = "b"
        with self.assertRaises(ValueError):
            resolve_prior(swapped, {"a": initial_state()}, saved)

    def test_true_personal_refresh_and_target_period_states_are_rejected(self):
        node = dependency_plan(["a"], ("202511", "202512"))[1]
        state = initial_state(); state["fields"]["q8"]["source_kind"] = "own_observed"
        saved = {("202511", "a"): {"month": "202511", "agent_id": "a", "state": state}}
        with self.assertRaisesRegex(ValueError, "true personal answers"):
            resolve_prior(node, {"a": initial_state()}, saved)
        state["fields"]["q8"].update(source_kind="simulated", source_period=202512)
        with self.assertRaises(ValueError):
            resolve_prior(node, {"a": initial_state()}, saved)

    def test_recorded_failed_fields_can_retain_their_own_earlier_state(self):
        node = dependency_plan(["a"], ("202511", "202512"))[1]
        state = initial_state()
        saved = {("202511", "a"): {"month": "202511", "agent_id": "a", "state": state}}
        result = resolve_prior(node, {"a": initial_state()}, saved)
        self.assertEqual(result, state)
        self.assertIsNot(result, state)

    def test_population_keeps_baseline_attributes_id_and_weights(self):
        base = {"materialized_count": 1, "provider_args": {"source_reference_period": "202501"},
                "personas": [{"agent_id": "a", "attributes": {"employment_status": "employed"},
                              "weight": 1.0, "init_state": {}}]}
        original = deepcopy(base)
        updated = fixed_population(base, "202609", "2026-09-11T23:59:59-04:00", "202501")
        self.assertEqual(updated["personas"], base["personas"])
        self.assertEqual(updated["provider_args"]["source_reference_period"], "202501")
        self.assertEqual(updated["provider_args"]["target_month"], "2026-09")
        self.assertEqual(base, original)

    def test_analysis_weights_cannot_enter_population_model_weights(self):
        base = {"materialized_count": 1, "provider_args": {},
                "personas": [{"agent_id": "a", "attributes": {}, "weight": 3.5}]}
        with self.assertRaises(ValueError):
            fixed_population(base, "202511", "2025-11-13T23:59:59-05:00", "202501")

    def test_environment_rejects_future_signal_by_absolute_time(self):
        env = environment()
        validate_public_environment(env, "2025-11-13T23:59:59-05:00")
        env["provider_args"]["signals_by_step"]["0"][0]["published_at"] = "2025-11-14T05:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "Future/undated"):
            validate_public_environment(env, "2025-11-13T23:59:59-05:00")

    def test_unregistered_sce_anchor_broadcast_or_deadline_change_is_rejected(self):
        env = environment()
        env["provider_args"]["signals_by_step"]["0"][0]["signal_id"] = "nyfed_sce_last_public"
        with self.assertRaisesRegex(ValueError, "separately declared"):
            validate_public_environment(env, "2025-11-13T23:59:59-05:00")
        env = environment(); env["information_program"]["broadcasts"] = [{"text": "extra"}]
        with self.assertRaises(ValueError):
            validate_public_environment(env, "2025-11-13T23:59:59-05:00")
        with self.assertRaises(ValueError):
            validate_public_environment(environment(), "2025-11-14T23:59:59-05:00")


if __name__ == "__main__":
    unittest.main()
