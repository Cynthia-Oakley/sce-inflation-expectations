"""Offline contract across weekly release clocks and household state transitions.

Release values below are synthetic fixtures, never SCE target observations.
"""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from studies.sce_inflation_expectations.experiments.weekly_release_protocol import (
    evaluate_frozen_points,
    schedule,
    score_cutoffs,
)
from studies.sce_inflation_expectations.experiments.weekly_state import (
    advance_state,
    initialize_state,
    render_state,
    reset_state,
)


NY = ZoneInfo("America/New_York")


def _next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _synthetic_releases():
    """Date-only public metadata and fabricated levels for tests only."""
    rows = []
    year, month = 2025, 9
    for index in range(13):  # targets/anchors 2025-09 through 2026-09
        period = f"{year:04}-{month:02}"
        pub_year, pub_month = _next_month(year, month)
        rows.append({
            "reference_period": period,
            "published_date": f"{pub_year:04}-{pub_month:02}-07",
            "value_pp": 2.5 + index * 0.01,  # fixture only, not a target value
        })
        year, month = _next_month(year, month)
    return rows


def _friday_cutoffs():
    first = date(2025, 11, 7)
    return [datetime.combine(first + timedelta(days=7 * i), time(23, 59, 59), NY).isoformat()
            for i in range(47)]


def _canonical_utc(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _joint_donor_fields(point):
    source_period = int(point["anchor_reference_period"].replace("-", ""))
    # Synthetic complete Q8/Q9 donor pair; this is unrelated to release values.
    return {
        "q8": {"value": 3.0, "source_period": source_period, "source_kind": "synthetic_donor"},
        "q9": {"value": [10.0] * 10, "source_period": source_period,
               "source_kind": "synthetic_donor"},
    }


def _answer(*, point=3.2, bins=None):
    bins = [10.0] * 10 if bins is None else bins
    return json.dumps({"point_pct": point,
                       "q9": {f"bin{i}": value for i, value in enumerate(bins, 1)}})


def test_47_week_state_replay_respects_public_cycles_and_score_target_isolation():
    releases = _synthetic_releases()
    points = schedule(_friday_cutoffs(), releases)
    assert len(points) == 47
    assert len({row["target_reference_period"] for row in points}) == 11
    assert sum(row["reset_required"] for row in points) == 12  # includes the initial cycle
    assert all(row["anchor_reference_period"] < row["target_reference_period"] for row in points)

    # Date-only October release is not available on the first Friday itself;
    # after the conservative next-day boundary it may anchor November forecasts.
    assert points[0]["target_reference_period"] == "2025-11"
    assert points[0]["anchor_reference_period"] == "2025-09"
    assert points[1]["target_reference_period"] == "2025-11"
    assert points[1]["anchor_reference_period"] == "2025-10"
    assert points[0]["anchor_reference_period"] != "2025-11"

    # The cycle changes inside December while the forecast target is still December.
    dec_5 = next(row for row in points if row["cutoff"].startswith("2025-12-05"))
    dec_12 = next(row for row in points if row["cutoff"].startswith("2025-12-12"))
    assert dec_5["target_reference_period"] == dec_12["target_reference_period"] == "2025-12"
    assert dec_5["anchor_reference_period"] == "2025-10"
    assert dec_12["anchor_reference_period"] == "2025-11"
    assert dec_12["reset_required"] is True

    # Crossing a calendar month without a new public anchor is not a reset.
    dec_26 = next(row for row in points if row["cutoff"].startswith("2025-12-26"))
    jan_2 = next(row for row in points if row["cutoff"].startswith("2026-01-02"))
    assert dec_26["cycle_key"] == jan_2["cycle_key"]
    assert jan_2["reset_required"] is False

    state = None
    forecasts = []
    archived_history_centers = 0
    archived_steps = 0
    q9_failure_cutoff = points[1]["cutoff"]
    q9_before_failure = None
    history_count_before_failure = None
    history_count_after_recovery = None

    for index, point in enumerate(points):
        fields = _joint_donor_fields(point)
        if state is None:
            state = initialize_state(
                "private-household-test-id", point["cycle_key"], point["anchor_known_from"],
                fields, center=3.0,
                news_memory={"seen_article_ids": ["fixture-news-1"]},
            )
        elif point["reset_required"]:
            previous_cutoff = state["last_cutoff"]
            archived_before = len(state["cycle_archives"])
            old_history = deepcopy(state["history_centers"])
            old_steps = deepcopy(state["steps"])
            state = reset_state(state, point["cycle_key"], point["anchor_known_from"],
                                fields, center=3.0 + index / 1000)
            assert state["last_cutoff"] == previous_cutoff
            assert len(state["cycle_archives"]) == archived_before + 1
            archive = state["cycle_archives"][-1]
            assert archive["history_centers"] == old_history
            assert archive["steps"] == old_steps
            assert len(state["history_centers"]) == 1
            assert state["history_centers"][0]["source_kind"] == "cycle_start_joint_prior"
            assert state["news_memory"] == {"seen_article_ids": ["fixture-news-1"]}
            archived_history_centers += len(old_history)
            archived_steps += len(old_steps)
            # Old-cycle summaries never enter the new current-cycle render.
            assert "Across" not in render_state(state, point["cutoff"])

        prompt_state = render_state(state, point["cutoff"])
        assert state["agent_id"] not in prompt_state
        assert point["anchor_reference_period"] < point["target_reference_period"]

        if index == 1:
            # Q8 succeeds, Q9 fails: keep the household's prior Q9 exactly once.
            q9_before_failure = deepcopy(state["fields"]["q9"])
            history_count_before_failure = len(state["history_centers"])
            raw = _answer(point=3.6, bins=[-1.0] + [10.0] * 9)
            state = advance_state(state, raw, point["cutoff"], center=3.6)
            assert state["fields"]["q8"]["value"] == pytest.approx(3.6)
            assert state["fields"]["q9"] == q9_before_failure
            assert len(state["history_centers"]) == history_count_before_failure
            assert state["steps"][-1]["field_retained_as_explicit_fallback"] == {
                "q8": False, "q9": True,
            }
        else:
            history_before = len(state["history_centers"])
            state = advance_state(state, _answer(point=3.1 + index / 100), point["cutoff"],
                                  center=3.1 + index / 100)
            assert state["last_cutoff"] == _canonical_utc(point["cutoff"])
            if index == 2:
                assert state["fields"]["q9"]["source_at"] != q9_before_failure["source_at"]
                history_count_after_recovery = len(state["history_centers"])
            # A successful Q9 answer contributes one summary center at this cutoff.
            assert len(state["history_centers"]) == history_before + 1

        forecasts.append({
            "cutoff": point["cutoff"],
            "target_reference_period": point["target_reference_period"],
            "anchor_reference_period": point["anchor_reference_period"],
            "anchor_pp": point["anchor_pp"],
            "forecast_pp": 3.15,  # synthetic forecast fixture
            "forecast_kind": "raw_model_pre_reset",
        })

    assert history_count_after_recovery == history_count_before_failure + 1
    assert len(state["cycle_archives"]) == 11
    assert archived_steps + len(state["steps"]) == 47
    assert archived_history_centers + len(state["history_centers"]) == 12 + 46

    selections = score_cutoffs(points, releases)
    primary = [row for row in selections if row["panel"] == "last_week_in_month"]
    assert len(primary) == 11
    releases_by_period = {row["reference_period"]: row for row in releases}
    for selection in primary:
        assert selection["cutoff"] is not None
        assert selection["cutoff"][:10] < selection["target_published_date"]
        assert selection["anchor_reference_period"] < selection["target_reference_period"]
        assert selection["target_reference_period"] in releases_by_period

    # The evaluator accepts only pre-reset raw forecast rows and selects one
    # eligible point per target month; all fixture levels remain synthetic.
    evaluated = evaluate_frozen_points(forecasts, releases)
    assert evaluated["n_distinct_target_months"] == 11
    assert evaluated["panels"]["last_week_in_month"]["n_target_months"] == 11
    assert evaluated["new_API_calls"] == 0
    scored = evaluated["panels"]["last_week_in_month"]["rows"]
    assert {row["target_reference_period"] for row in scored} == {
        row["target_reference_period"] for row in primary
    }
    assert all(row["cutoff"][:10] < row["target_published_date"] for row in scored)

    post_reset = dict(forecasts[0], forecast_kind="post_reset_calibrated")
    with pytest.raises(ValueError, match="Post-reset"):
        evaluate_frozen_points([post_reset], releases)
