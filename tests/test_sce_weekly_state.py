import json

import pytest

from studies.sce_inflation_expectations.experiments.weekly_state import (
    advance_state,
    initialize_state,
    render_state,
    reset_state,
)


def joint_fields(q8=3.1, q9=None, *, source_period=202510, source_kind="synthetic_donor"):
    bins = [10.0] * 10 if q9 is None else q9
    return {
        "q8": {"value": q8, "source_period": source_period, "source_kind": source_kind},
        "q9": {"value": bins, "source_period": source_period, "source_kind": source_kind},
    }


def response(*, point=3.4, bins=None):
    vals = [10.0] * 10 if bins is None else bins
    return json.dumps({"point_pct": point, "q9": {f"bin{i}": v for i, v in enumerate(vals, 1)}})


def test_initial_joint_pair_accepts_period_provenance_and_same_month_weekly_cutoffs():
    state = initialize_state(
        "household-1", "2025-10|2025-11-07", "2025-11-08T00:00:00-05:00",
        joint_fields(q9=[4.0] * 10), center=2.8,
    )
    assert state["fields"]["q9"]["value"] == pytest.approx([10.0] * 10)
    assert state["fields"]["q9"]["source_period"] == 202510
    assert state["last_cutoff"] is None
    assert "Earlier belief state" in render_state(state, "2025-11-08T00:00:00-05:00")
    rendered = render_state(state, "2025-11-14T23:59:59-05:00")
    assert "source period 202510" in rendered
    assert '"q9"' in rendered


def test_advance_uses_full_aware_instant_and_rejects_duplicate_or_backward_cutoff():
    state = initialize_state("h1", "cycle-a", "2025-11-08T00:00:00-05:00", joint_fields(), center=3.0)
    first = advance_state(state, response(), "2025-11-14T23:59:59-05:00", center=3.4)
    second = advance_state(first, response(point=3.5), "2025-11-21T23:59:59-05:00", center=3.6)
    assert first["last_cutoff"] == "2025-11-15T04:59:59Z"
    assert second["fields"]["q8"]["source_at"] == "2025-11-22T04:59:59Z"
    assert len(second["steps"]) == 2
    assert len(second["history_centers"]) == 3  # joint origin plus two weekly answers
    with pytest.raises(ValueError, match="strictly later"):
        advance_state(first, response(), "2025-11-14T17:59:59-11:00", center=3.4)
    with pytest.raises(ValueError, match="follow"):
        render_state(second, "2025-11-21T23:59:59-05:00")
    assert "Across 3 earlier states" in render_state(second, "2025-11-28T23:59:59-05:00")


def test_q8_q9_failures_retain_each_field_independently_and_history_appends_once():
    state = initialize_state("h2", "cycle-a", "2025-11-08T00:00:00-05:00", joint_fields(), center=3.0)
    q8_failed = advance_state(
        state,
        json.dumps({"point_pct": 1000, "q9": {f"bin{i}": 2 for i in range(1, 11)}}),
        "2025-11-14T23:59:59-05:00", center=4.25,
    )
    assert q8_failed["fields"]["q8"] == state["fields"]["q8"]
    assert q8_failed["fields"]["q9"]["value"] == pytest.approx([10.0] * 10)
    assert q8_failed["steps"][-1]["field_retained_as_explicit_fallback"] == {"q8": True, "q9": False}
    assert q8_failed["steps"][-1]["q9_proportional_normalization"] is True
    assert len(q8_failed["history_centers"]) == 2

    q9_failed = advance_state(
        q8_failed,
        json.dumps({"point_pct": 3.8, "q9": {"bin1": -1}}),
        "2025-11-21T23:59:59-05:00", center=99.0,
    )
    assert q9_failed["fields"]["q8"]["value"] == 3.8
    assert q9_failed["fields"]["q9"] == q8_failed["fields"]["q9"]
    assert len(q9_failed["history_centers"]) == 2
    assert q9_failed["steps"][-1]["field_retained_as_explicit_fallback"] == {"q8": False, "q9": True}

    final_failure = advance_state(
        q9_failed, None, "2025-11-28T23:59:59-05:00", technical_failure=True,
    )
    assert final_failure["fields"] == q9_failed["fields"]
    assert final_failure["history_centers"] == q9_failed["history_centers"]
    assert final_failure["steps"][-1]["technical_failure"] is True
    with pytest.raises(ValueError, match="strictly later"):
        advance_state(final_failure, response(), "2025-11-28T23:59:59-05:00")


def test_new_public_cycle_archives_old_history_preserves_memory_and_keeps_clock_monotone():
    memory = {"seen_article_ids": ["a", "b"], "monthly_budget_remaining": 4}
    state = initialize_state("h3", "cycle-a", "2025-11-08T00:00:00-05:00", joint_fields(),
                             center=3.0, news_memory=memory)
    state = advance_state(state, response(), "2025-11-14T23:59:59-05:00", center=3.3)
    state = advance_state(state, response(point=3.6), "2025-11-21T23:59:59-05:00", center=3.7)
    old_history = list(state["history_centers"])
    old_steps = list(state["steps"])

    refreshed = reset_state(
        state, "cycle-b", "2025-12-09T00:00:00-05:00",
        joint_fields(q8=3.2, q9=[1.0] * 10, source_period=202511), center=3.1,
    )
    assert refreshed["cycle_key"] == "cycle-b"
    assert refreshed["cycle_started_at"] == "2025-12-09T05:00:00Z"
    assert refreshed["last_cutoff"] == state["last_cutoff"]  # no backward/reset of weekly clock
    assert refreshed["news_memory"] == memory
    assert refreshed["history_centers"] == [
        {"source_at": "2025-12-09T05:00:00Z", "center": 3.1,
         "source_kind": "cycle_start_joint_prior"}
    ]
    assert len(refreshed["cycle_archives"]) == 1
    archive = refreshed["cycle_archives"][0]
    assert archive["cycle_key"] == "cycle-a"
    assert archive["history_centers"] == old_history
    assert archive["steps"] == old_steps
    rendered = render_state(refreshed, "2025-12-12T23:59:59-05:00")
    assert "Across" not in rendered  # old cycle summary did not leak across the reset

    continued = advance_state(refreshed, response(point=3.2),
                              "2025-12-12T23:59:59-05:00", center=3.2)
    assert len(continued["history_centers"]) == 2
    assert "Across 2 earlier states" in render_state(continued, "2025-12-19T23:59:59-05:00")


def test_joint_origin_cycle_and_timezone_guards():
    fields = joint_fields()
    fields["q8"]["source_period"] = 202509
    with pytest.raises(ValueError, match="same source period"):
        initialize_state("h4", "cycle-a", "2025-11-08T00:00:00-05:00", fields, center=3.0)
    with pytest.raises(ValueError, match="Timezone-aware"):
        initialize_state("h4", "cycle-a", "2025-11-08T00:00:00", joint_fields(), center=3.0)

    state = initialize_state("h4", "cycle-a", "2025-11-08T00:00:00-05:00", joint_fields(), center=3.0)
    with pytest.raises(ValueError, match="complete joint"):
        reset_state(state, "cycle-b", "2025-11-09T00:00:00-05:00", {"q8": fields["q8"]})
    with pytest.raises(ValueError, match="changed cycle"):
        reset_state(state, "cycle-a", "2025-11-09T00:00:00-05:00", joint_fields(), center=3.0)
    with pytest.raises(ValueError, match="Timezone-aware"):
        advance_state(state, response(), "2025-11-14T23:59:59")


def test_q9_initial_probability_validation_uses_shared_normalizer():
    state = initialize_state(
        "h5", "cycle-a", "2025-11-08T00:00:00-05:00",
        joint_fields(q9=[1.0] * 10), center=3.0,
    )
    assert state["fields"]["q9"]["value"] == pytest.approx([10.0] * 10)
    with pytest.raises(ValueError, match="nonnegative"):
        initialize_state("h5", "cycle-a", "2025-11-08T00:00:00-05:00",
                         joint_fields(q9=[-1.0] + [10.0] * 9), center=3.0)
