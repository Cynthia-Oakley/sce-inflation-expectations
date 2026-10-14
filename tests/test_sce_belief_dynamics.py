"""Tests for the SCE belief-dynamics line (task A facts + shared metrics)."""
import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.belief_dynamics.data import (
    build_valid_pairs,
    previous_calendar_month,
)
from studies.sce_inflation_expectations.belief_dynamics.dynamics import (
    prepare_frame,
)
from studies.sce_inflation_expectations.belief_dynamics.metrics import (
    weighted_bin_index,
    weighted_ols_slope,
    weighted_w1,
)
from studies.sce_inflation_expectations.factual_mechanism_audit import wquantile
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import (
    provenance,
    score_q9_frozen,
)


@pytest.fixture(scope="module")
def frame():
    return prepare_frame()


@pytest.fixture(scope="module")
def valid_pairs(frame):
    return build_valid_pairs(frame)


def test_adjacent_and_valid_pair_counts_reproduce(valid_pairs):
    # Recompute adjacent count independently via the acceptance path.
    from studies.sce_inflation_expectations.belief_dynamics.data import build_pairs
    f = valid_pairs  # only to keep fixture usage explicit; counts come from frame below
    frame = prepare_frame()
    pairs = build_pairs(frame)
    assert len(pairs) == 106351
    assert len(valid_pairs) == 103630


def test_previous_calendar_month():
    assert previous_calendar_month(202203) == 202202
    assert previous_calendar_month(202301) == 202212
    assert previous_calendar_month(201702) == 201701


def test_b0_2021_own_previous_mae_month_equal(valid_pairs):
    year = valid_pairs[valid_pairs["date"].floordiv(100) == 2021]
    monthly_mae = []
    for _, p in year.groupby("date"):
        delta = (p["Q9_mean"] - p["previous_Q9_mean"]).to_numpy(float)
        w = p["weight"].to_numpy(float)
        monthly_mae.append(np.average(np.abs(delta), weights=w))
    assert len(monthly_mae) == 12
    assert abs(np.mean(monthly_mae) - 2.9236997163903147) < 1e-9


def test_weighted_w1_small_examples():
    # Point mass at 0 vs values -> weighted mean |value|.
    assert weighted_w1([0, 0, 0], [1.0, -2.0, 3.0]) == pytest.approx(2.0)
    assert weighted_w1([0, 0], [1.0, 3.0], [2.0, 1.0]) == pytest.approx(2.0)
    assert weighted_w1([0, 0], [1.0, 3.0], [2.0, 1.0], [1.0, 3.0]) == pytest.approx(2.5)
    # Identical distributions -> 0.
    assert weighted_w1([1, 2, 3], [1, 2, 3], [1, 2, 3], [1, 2, 3]) == 0.0
    # Pure shift of all mass by 1 -> W1 = 1.
    assert weighted_w1([0, 2], [1, 3], [1, 1], [1, 1]) == pytest.approx(1.0)


def test_wquantile_matches_definitions():
    x = [1.0, 2.0, 3.0, 4.0]
    assert wquantile(x, [1, 1, 1, 1], 0.5) == 2.0
    assert wquantile(x, [1, 1, 1, 1], 0.0) == 1.0
    # Reference implementation uses a left-continuous weighted ECDF:
    # cumulative mass reaches exactly 0.5 at x=1.
    assert wquantile(x, [1, 0, 0, 1], 0.5) == 1.0
    assert wquantile(x, [1, 0, 0, 1], 0.75) == 4.0
    assert wquantile([], [1], 0.5) is None


def test_weighted_bin_index_small_example():
    cutpoints = [1.0, 2.0]
    bins = weighted_bin_index([0.5, 1.0, 1.5, 2.5, 3.0], [1, 1, 1, 1, 1], cutpoints)
    assert bins.tolist() == [0, 0, 1, 2, 2]  # value == cutpoint falls in lower bin


def test_weighted_ols_slope_small_example():
    # y = 2x exactly -> slope 2 (weights irrelevant).
    assert weighted_ols_slope([1, 2, 3], [2, 4, 6], [1, 2, 3]) == pytest.approx(2.0)
    # Perfect negative relation.
    assert weighted_ols_slope([1, 2, 3], [6, 4, 2], [1, 1, 1]) == pytest.approx(-2.0)
    # Constant x -> undefined.
    assert weighted_ols_slope([1, 1, 1], [1, 2, 3], [1, 1, 1]) is None


def test_frozen_scorer_provenance_and_symmetric_bins():
    prov = provenance()
    assert prov["live_matches_pinned"] is True
    score = score_q9_frozen([0, 0, 0, 25, 25, 25, 25, 0, 0, 0])
    assert score.status == "ok"
    # Symmetric bins 4-7 (bins 3-6 zero-based) straddle 0 -> center near 0.
    assert abs(score.mean) < 1e-6
    assert score.iqr > 0


def test_frozen_scorer_prior_match_flag_counts():
    # The LLM comparison asserts supplied own-previous priors against the real
    # previous-month bins at tolerance 1e-9; the run reports 0 mismatches.
    from studies.sce_inflation_expectations.belief_dynamics.llm_compare import (
        build_person_month_table,
    )
    from studies.sce_inflation_expectations.belief_dynamics.data import load_reference_frame
    _, note = build_person_month_table(load_reference_frame())
    assert note["n_q9_records"] == 96
    assert note["n_prior_mismatch_vs_real_prev_bins"] == 0
