import unittest
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

from studies.sce_inflation_expectations.information_exposure import (
    route_channel, shuffled_channels, build_exposure_view, build_exposure_messages, validate_bundle, SCHEMA,
)
from studies.sce_inflation_expectations.price_experience import profile_hash
from studies.sce_inflation_expectations.information_exposure_analysis import paired_metrics


class ExposureTest(unittest.TestCase):
    def setUp(self):
        self.profile = {"age_group": "under 40", "housing_tenure": "rent"}
        self.shares = {"food": .4, "gasoline": 0., "shelter": 0., "other": .6}
        self.bundle = {"schema_version": SCHEMA, "research_line": "A_historical_reconstruction",
                       "target_month": "2021-05", "arm": "matched", "news_policy": "off_all_arms",
                       "routing_rule": "conditional_ce_share_draw_seed42_v1", "rows": {"a": {
                           "agent_id": "a", "profile_sha256": profile_hash(self.profile), "spending_shares": self.shares,
                           "intended_channel": "food", "delivered_channel": "food"}}}
        self.info = {"target_month": "2021-05", "as_of": "2021-05-12T23:59:59-04:00",
                     "signals": [{"signal_id": name, "published_at": "2021-05-12T08:30:00-04:00",
                                  "reference_period": "2021-04", "measure": label, "unit": "percent", "value": value}
                                 for name, label, value in (("bls_cpi_food_yoy_nsa_apr", "food YoY", 2.4),
                                     ("bls_cpi_u_all_items_yoy_nsa_apr", "all-items YoY", 4.2))],
                     "events": [{"event_id": "news1", "pub_date": "2021-05-12", "headline": "Total CPI 4.2%"}],
                     "broadcasts": [{"content": "Total CPI 4.2%"}]}

    def test_zero_share_categories_not_selected(self):
        for i in range(100):
            self.assertEqual(route_channel(str(i), self.shares), "food")
        with self.assertRaises(ValueError):
            route_channel("a", {"food": 0, "gasoline": 0, "shelter": 0, "other": 1})

    def test_shuffle_preserves_packages_and_deranges_people(self):
        ids = list("abcdef")
        ch = dict(zip(ids, ["food", "food", "gasoline", "gasoline", "shelter", "shelter"]))
        shuffled, donors = shuffled_channels(ids, ch)
        self.assertEqual(Counter(shuffled.values()), Counter(ch.values()))
        self.assertTrue(all(a != b for a, b in donors.items()))
        self.assertEqual(shuffled_channels(list(reversed(ids)), ch)[0], shuffled)

    def test_future_fact_and_profile_mismatch_rejected(self):
        bad = deepcopy(self.info)
        bad["signals"][0]["published_at"] = "2021-05-13T08:30:00-04:00"
        with self.assertRaises(ValueError):
            build_exposure_view(self.profile, bad, self.bundle, "a")
        with self.assertRaises(ValueError):
            build_exposure_view({"age_group": "over 60"}, self.info, self.bundle, "a")

    def test_mask_removes_headline_news_and_broadcast_without_mutating_ledger(self):
        original = deepcopy(self.info)
        view, state = build_exposure_view(self.profile, self.info, self.bundle, "a")
        self.assertEqual(view["signals"][0]["value"], 2.4)
        self.assertEqual(len(view["signals"]), 1)
        self.assertEqual(view["events"], [])
        self.assertEqual(view["broadcasts"], [])
        self.assertEqual(self.info, original)
        self.assertEqual(len(state["source_signal_ids"]), 2)
        self.assertEqual(state["excluded_event_ids"], ["news1"])

    def test_answer_field_not_accepted(self):
        personas = [SimpleNamespace(agent_id="a", attributes=self.profile)]
        validate_bundle(self.bundle, personas, "2021-05")
        self.bundle["rows"]["a"]["Q9_mean"] = 5
        with self.assertRaises(ValueError):
            validate_bundle(self.bundle, personas, "2021-05")

    def test_questionnaire_and_actual_masked_prompt(self):
        view, state = build_exposure_view(self.profile, self.info, self.bundle, "a")
        ob = SimpleNamespace(macro_information=view, local_information={"information_exposure": state})
        base = [{"role": "user", "content": "Persona.\n\nYou are answering a survey. You only know information available by May 12.\n\nTotal CPI 4.2%.\n\nQuestion 1 (point estimate): ORIGINAL QUESTIONNAIRE"}]
        text = build_exposure_messages(ob, base)[0]["content"]
        self.assertIn("2021-04: 2.4", text)
        self.assertNotIn("4.2", text)
        self.assertEqual(text.split("Question 1 (point estimate):")[1], " ORIGINAL QUESTIONNAIRE")

    def test_metric_does_not_confuse_distribution_fit_with_individual_fit(self):
        rows = [{"real": 0., "shared": 1., "shuffled": 1., "matched": 2., "channel": "food"},
                {"real": 2., "shared": 1., "shuffled": 1., "matched": 0., "channel": "gasoline"}]
        m = paired_metrics(rows)
        self.assertEqual(m["arms"]["matched"]["distribution_W1_pp"], 0)
        self.assertEqual(m["arms"]["matched"]["MAE_pp"], 2)
        self.assertFalse(m["development_screen_passed"])


if __name__ == "__main__":
    unittest.main()
