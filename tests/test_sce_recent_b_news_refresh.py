from copy import deepcopy
import unittest

from studies.sce_inflation_expectations.experiments.recent_b_news_refresh import (
    _news_pools, _topic_label, _validate_plan, _latest_cpi_release_day, replace_news_template,
)
from studies.sce_inflation_expectations.experiments.media_mechanism_trial import synthetic_news
from studies.sce_inflation_expectations.experiments.media_mechanism_v3 import four_tier_levels, draw_personal
from studies.sce_inflation_expectations.news_exposure_demo import render_news_input
from studies.sce_inflation_expectations.state_continuity_runtime import (
    STATE_TOKEN, TIMING_TOKEN, render_messages,
)


def story(aid, day, placement="other_recorded_page"):
    row = synthetic_news(aid, "Inflation and food prices " + aid)
    row.update(pub_date=f"2025-11-{day:02}T12:00:00-05:00", placement=placement)
    row["semantic_label"] = {"article_id": aid, "decision": "keep",
                             "topics": ["living_prices"], "scope": "us_national"}
    return row


def fixture():
    common = [story("g1", 1, "a1"), story("g2", 2, "a1"), story("g3", 3, "a1")]
    context = {"as_of": "2025-11-13T23:59:59-05:00", "common_news": common,
               "personal_news": [story("p1", 4)], "policy_published_at": "2025-10-29T23:59:59-04:00",
               "food_published_at": "2025-10-24T12:00:00-04:00"}
    state = {"fields": {"q8": {"value": 3, "source_period": 202510, "source_kind": "synthetic_donor"},
                         "q9": {"value": [10] * 10, "source_period": 202510, "source_kind": "synthetic_donor"}},
             "history_centers": [], "comparison_reference_day": "2025-10-31",
             "comparison_day_source": "synthetic_prior_reference_month_end"}
    text = ("FIXED PERSONA\nFIXED PRICE\n" + render_news_input(common, context["personal_news"]) +
            "\nPublic policy news brief (2025-10-29):\nFIXED POLICY\n" + TIMING_TOKEN + "\n\n" +
            STATE_TOKEN + "\n\nFIXED QUESTIONNAIRE AND FORMAT")
    template = [{"role": "user", "content": text}]
    return template, state, context


class RecentBNewsRefreshTests(unittest.TestCase):
    def test_refresh_updates_both_timing_lists_without_changing_other_inputs(self):
        template, state, old = fixture()
        new = {**old, "common_news": [story("n1", 5, "a1"), story("n2", 6, "a1"),
                                     {**story("n3", 7, "a1"), "pub_date": "2025-10-30T12:00:00-04:00"}],
               "personal_news": [story("q1", 8), story("q2", 9)]}
        state_before, template_before = deepcopy(state), deepcopy(template)
        old_render = render_messages(template, state, "202511", old)
        result, rendered = replace_news_template(template, old, new, state, old_render, "202511")
        text = rendered[0]["content"]
        self.assertIn("- General news, in the order listed above: later; later; earlier.", text)
        self.assertIn("- Other news, in the order listed above: later; later.", text)
        self.assertEqual(state, state_before)
        self.assertEqual(template, template_before)
        self.assertEqual(result[0]["content"].split("Public policy news brief (")[1],
                         template[0]["content"].split("Public policy news brief (")[1])
        self.assertTrue(text.startswith("FIXED PERSONA\nFIXED PRICE\n"))

    def test_cannot_change_global_b_cutoff_or_price_policy_dates(self):
        template, state, context = fixture()
        preview = render_messages(template, state, "202511", context)
        for key in ("as_of", "food_published_at", "policy_published_at"):
            new = {**context, key: "2025-11-14T12:00:00-05:00"}
            with self.assertRaises(ValueError):
                replace_news_template(template, context, new, state, preview, "202511")

    def test_original_prompt_must_reproduce_before_refresh(self):
        template, state, context = fixture()
        preview = render_messages(template, state, "202511", context)
        preview[0]["content"] += "changed"
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            replace_news_template(template, context, context, state, preview, "202511")

    def test_future_news_is_rejected_by_actual_render(self):
        template, state, context = fixture()
        new = {**context, "personal_news": [story("future", 14)]}
        with self.assertRaises(ValueError):
            replace_news_template(template, context, new, state,
                                  render_messages(template, state, "202511", context), "202511")

    def test_four_tiers_balanced_and_independent_of_input_order(self):
        ids = [f"proxy_{i:03}" for i in range(512)]
        tiers = four_tier_levels(ids, 202511)
        self.assertEqual(tiers, four_tier_levels(list(reversed(ids)), 202511))
        self.assertEqual({x: list(tiers.values()).count(x) for x in (4, 8, 16, 32)},
                         {4: 128, 8: 128, 16: 128, 32: 128})

    def test_news_pool_filters_sce_and_does_not_duplicate_common(self):
        rows = [story(f"x{i}", 1 + i % 12, "a1" if i < 3 else "other_recorded_page") for i in range(36)]
        for row in rows:
            row["new_hits"] = ["prices"]
        leakage = deepcopy(rows[-1]); leakage["article_id"] = "leak"
        leakage["headline"] = "Survey of Consumer Expectations releases a forecast"
        rows.append(leakage)
        labels = {r["article_id"]: r["semantic_label"] for r in rows}
        common, personal, audit = _news_pools(rows, labels, "2025-11-13T23:59:59-05:00", "2025-10-24")
        self.assertEqual(audit["sce_articles_excluded"], 1)
        self.assertEqual(len(common), 3)
        self.assertEqual(len(personal), 33)
        self.assertFalse({r["article_id"] for r in common} & {r["article_id"] for r in personal})
        self.assertNotIn("leak", {r["article_id"] for r in personal})

    def test_missing_topic_label_blocks_preparation(self):
        row = {**story("missing", 1), "new_hits": ["prices"]}
        with self.assertRaisesRegex(ValueError, "Missing base classification"):
            _news_pools([row], {}, "2025-11-13T23:59:59-05:00", "2025-10-24")

    def test_future_utc_timestamp_cannot_hide_behind_a_local_date(self):
        row = {**story("future", 13), "pub_date": "2025-11-14T05:00:00+00:00", "new_hits": []}
        with self.assertRaisesRegex(ValueError, "Future news"):
            _news_pools([row], {}, "2025-11-13T23:59:59-05:00", "2025-10-24")

    def test_cancelled_release_uses_actual_prior_cpi_day_not_asof(self):
        environment = {"provider_args": {"signals_by_step": {"0": [
            {"signal_id": "bls_cpi_u_all_items_yoy_nsa_september", "published_at": "2025-10-24T08:30:00-04:00"},
            {"signal_id": "bls_cpi_u_all_items_yoy_nsa_later", "published_at": "2025-12-18T08:30:00-05:00"},
            {"signal_id": "other_same_day", "published_at": "2025-11-13T08:30:00-05:00"}]}}}
        self.assertEqual(_latest_cpi_release_day(environment, "2025-11-13T23:59:59-05:00"), "2025-10-24")
        with self.assertRaises(ValueError):
            _latest_cpi_release_day(environment, "2025-10-23T23:59:59-04:00")

    def test_anchor_is_past_and_public_and_cutoff_stays_in_target(self):
        plan = {"month": "202511", "as_of": "2025-11-13T23:59:59-05:00",
                "last_public_national_anchor": {"reference_period": "2025-10", "published_date": "2025-11-10"}}
        _validate_plan(plan, "202511")
        for key, value in (("reference_period", "2025-11"), ("published_date", "2025-11-14")):
            bad = deepcopy(plan); bad["last_public_national_anchor"][key] = value
            with self.assertRaises(ValueError):
                _validate_plan(bad, "202511")

    def test_unused_tone_fields_cannot_change_personal_selection(self):
        rows = [story(f"s{i}", i + 1) for i in range(5)]
        plain = [_topic_label(r["semantic_label"]) for r in rows]
        annotated = [{**r, "semantic_label": {**label, "tone": "alarming", "persistence": "persistent"}}
                     for r, label in zip(rows, plain)]
        a = draw_personal(rows, [], 3, "fixed", {"food"}, alarming_boost=1.0, cpi_boost=1.5)
        b = draw_personal(annotated, [], 3, "fixed", {"food"}, alarming_boost=1.0, cpi_boost=1.5)
        self.assertEqual([r["article_id"] for r in a], [r["article_id"] for r in b])


if __name__ == "__main__":
    unittest.main()
