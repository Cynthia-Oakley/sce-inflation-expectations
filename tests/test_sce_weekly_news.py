from copy import deepcopy

from studies.sce_inflation_expectations.experiments.weekly_news import (
    advance_weekly_news,
    monthly_quota_at_cutoff,
)


def article(identity, published, *, placement="external_online", decision="keep", headline=None):
    return {
        "article_id": identity,
        "headline": headline or f"Consumer prices and inflation report {identity}",
        "abstract": "A short report about household prices.",
        "snippet": "",
        "pub_date": published,
        "placement": placement,
        "routing_tags": ["food"],
        "semantic_label": {
            "decision": decision,
            "topics": ["living_prices"],
            "scope": "us_national",
            "tone": "neutral",
        },
    }


def common_rows(published="2025-11-03T10:00:00-05:00", prefix="c"):
    return [article(f"{prefix}{i}", published, placement="a1") for i in range(1, 4)]


def run(pool, common, cutoff, tier=8, state=None, aid="household-1", seed="test-seed"):
    return advance_weekly_news(
        candidate_pool=pool,
        common_candidates=common,
        cutoff=cutoff,
        household_id=aid,
        attention_tier=tier,
        interests={"food"},
        state=state,
        seed=seed,
    )


def test_hand_calculated_cumulative_floors_for_all_four_tiers():
    cutoffs = [f"2025-11-{day:02d}T23:59:59-05:00" for day in (7, 14, 21, 28)]
    expected = {
        4: [0, 1, 2, 3],
        8: [1, 3, 5, 7],
        16: [3, 7, 11, 14],
        32: [7, 14, 22, 29],
    }
    for tier, values in expected.items():
        assert [monthly_quota_at_cutoff(tier, cutoff)["monthly_target"] for cutoff in cutoffs] == values


def test_three_available_articles_in_low_tier_underfill_hand_calculation():
    shared = common_rows()
    result = run(shared, shared, "2025-11-30T23:59:59-05:00", tier=4)

    assert result["new_article_ids"] == ["c1", "c2", "c3"]
    assert result["common_news"] == shared
    assert result["personal_news"] == []
    assert result["unfilled_count"] == 1  # monthly cap 4 minus 3 available unique articles
    assert result["cumulative_count"]["monthly_contact_count"] == 3
    assert result["cumulative_count"]["monthly_common_count"] == 3
    assert result["memory_after"]["seen_article_ids"] == ["c1", "c2", "c3"]


def test_low_tier_first_week_does_not_receive_unaccrued_news():
    shared = common_rows()
    result = run(shared, shared, "2025-11-07T23:59:59-05:00", tier=4)

    assert result["new_articles"] == []
    assert result["unfilled_count"] == 0
    assert result["cumulative_count"]["monthly_target"] == 0
    assert result["audit"]["bootstrap_background_count"] == 0


def test_shared_quota_caps_at_three_and_late_a1_keep_can_be_personal():
    first_shared = common_rows("2025-11-02T10:00:00-05:00", "early")
    late_a1 = common_rows("2025-11-20T10:00:00-05:00", "late")
    first = run(first_shared, first_shared, "2025-11-07T23:59:59-05:00", tier=8)
    second = run(first_shared, first_shared, "2025-11-14T23:59:59-05:00", tier=8,
                 state=first["memory_after"])
    assert len(first["common_news"]) == 1
    assert len(second["common_news"]) == 2
    assert second["cumulative_count"]["monthly_common_count"] == 3

    third = run(first_shared + late_a1, late_a1, "2025-11-21T23:59:59-05:00", tier=8,
                state=second["memory_after"])
    assert third["common_news"] == []
    assert len(third["personal_news"]) == 2
    assert set(third["new_article_ids"]) <= {row["article_id"] for row in late_a1}
    assert third["cumulative_count"]["monthly_common_count"] == 3
    assert len(third["memory_after"]["seen_article_ids"]) == 5


def test_cutoff_filters_future_articles_before_common_and_personal_selection():
    eligible_common = common_rows("2025-11-06T10:00:00-05:00")
    future = article("future", "2025-11-21T10:00:00-05:00", placement="a1",
                     headline="CPI inflation surges to a record high")
    eligible_personal = article("p1", "2025-11-06T11:00:00-05:00")
    result = run(eligible_common + [eligible_personal, future],
                 eligible_common + [future], "2025-11-07T23:59:59-05:00", tier=8)

    assert "future" not in result["new_article_ids"]
    assert result["audit"]["future_candidate_count_excluded"] == 1
    assert result["audit"]["future_common_count_excluded"] == 1
    assert all(row["article_id"] != "future" for row in result["common_news"] + result["personal_news"])


def test_article_memory_survives_calibration_boundary_and_month_change():
    shared = common_rows("2025-11-02T10:00:00-05:00")
    first = run(shared, shared, "2025-11-14T23:59:59-05:00", tier=8)
    # A publication-time belief recalibration occurs outside this news module;
    # passing the saved news state forward must retain every previously seen ID.
    second = run(shared, shared, "2025-11-21T23:59:59-05:00", tier=8,
                 state=first["memory_after"])
    assert set(first["new_article_ids"]).isdisjoint(second["new_article_ids"])
    assert set(first["new_article_ids"]) <= set(second["memory_after"]["seen_article_ids"])

    december_new = [article("dec-p1", "2025-12-03T10:00:00-05:00")]
    dec_pool = shared + december_new
    december = run(dec_pool, [], "2025-12-05T23:59:59-05:00", tier=8,
                   state=second["memory_after"])
    assert "dec-p1" in december["new_article_ids"]
    assert not (set(shared[i]["article_id"] for i in range(3)) & set(december["new_article_ids"]))
    assert set(first["new_article_ids"]) <= set(december["memory_after"]["seen_article_ids"])
    assert december["cumulative_count"]["month"] == "2025-12"
    assert december["cumulative_count"]["monthly_contact_count"] == 1


def test_same_state_replay_is_deterministic_and_applied_replay_is_noop():
    shared = common_rows()
    personal = [article(f"p{i}", f"2025-11-{i + 2:02d}T10:00:00-05:00") for i in range(1, 5)]
    pool = shared + personal
    cutoff = "2025-11-14T23:59:59-05:00"
    before = {"unmodified": True}
    a = run(pool, shared, cutoff, tier=8)
    b = run(pool, shared, cutoff, tier=8)
    assert a == b
    assert before == {"unmodified": True}

    replay = run(pool, shared, cutoff, tier=8, state=a["memory_after"])
    assert replay["new_articles"] == []
    assert replay["memory_after"] == a["memory_after"]
    assert replay["cumulative_count"] == a["cumulative_count"]


def test_input_state_is_not_mutated_and_late_month_residual_is_audited():
    shared = common_rows()
    original_state = {
        "schema_version": 1,
        "attention_tier": 4,
        "seen_article_ids": [],
        "month": None,
        "month_article_ids": [],
        "month_common_article_ids": [],
        "last_cutoff": None,
    }
    frozen = deepcopy(original_state)
    result = run(shared, shared, "2026-01-23T23:59:59-05:00", tier=4, state=original_state)

    assert original_state == frozen
    assert result["cumulative_count"]["is_last_friday_of_month"] is False
    assert result["cumulative_count"]["monthly_target"] == 2
    assert result["cumulative_count"]["after_last_friday_unissued_quota"] is None
    assert "not carried" in result["audit"]["quota_note"]


def test_last_friday_reports_unissued_fractional_month_end_quota():
    shared = common_rows("2026-01-02T10:00:00-05:00")
    result = run(shared, shared, "2026-01-30T23:59:59-05:00", tier=4)

    assert result["cumulative_count"]["is_last_friday_of_month"] is True
    assert result["cumulative_count"]["monthly_target"] == 3
    assert result["cumulative_count"]["after_last_friday_unissued_quota"] == 1
