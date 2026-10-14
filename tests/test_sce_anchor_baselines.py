"""Tests for the personal-anchor update rules (belief dynamics round 2)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.belief_dynamics.anchor import (
    HALFLIFE_MONTHS,
    MIN_HISTORY,
    attach_anchors,
    personal_anchors,
    predict_anchor,
)


def toy_answers() -> pd.DataFrame:
    # One person, four monthly answers; a second person with a single answer.
    return pd.DataFrame({
        "userid": [1, 1, 1, 1, 2],
        "date": [202101, 202102, 202103, 202104, 202103],
        "Q9_mean": [2.0, 4.0, 6.0, 8.0, 5.0],
    })


def test_anchor_is_strictly_prior_expanding_mean():
    anchors = personal_anchors(toy_answers(), mode="mean")
    a = anchors.set_index(["userid", "date"])["anchor"]
    assert np.isnan(a[(1, 202101)])                      # no history
    assert a[(1, 202102)] == pytest.approx(2.0)
    assert a[(1, 202103)] == pytest.approx(3.0)          # mean of 2, 4
    assert a[(1, 202104)] == pytest.approx(4.0)          # mean of 2, 4, 6
    assert anchors.set_index(["userid", "date"]).loc[(1, 202104), "history_count"] == 3


def test_anchor_has_no_lookahead():
    before = personal_anchors(toy_answers(), mode="mean")
    perturbed = toy_answers()
    perturbed.loc[perturbed["date"] == 202104, "Q9_mean"] = 99.0
    after = personal_anchors(perturbed, mode="mean")
    cols = ["anchor", "history_count"]
    merged = before.merge(after, on=["userid", "date"], suffixes=("_a", "_b"))
    assert np.allclose(merged["anchor_a"].fillna(-1), merged["anchor_b"].fillna(-1))


def test_anchor_decay_matches_manual_weights():
    anchors = personal_anchors(toy_answers(), mode="decay")
    a = anchors.set_index(["userid", "date"])["anchor"]
    # 202103: history months 202101 (2 months back), 202102 (1 month back)
    w1 = 0.5 ** (2 / HALFLIFE_MONTHS)
    w2 = 0.5 ** (1 / HALFLIFE_MONTHS)
    expected = (w1 * 2.0 + w2 * 4.0) / (w1 + w2)
    assert a[(1, 202103)] == pytest.approx(expected)
    assert a[(1, 202103)] > 3.0  # recent answer weighted above the flat mean


def test_anchor_median_mode():
    anchors = personal_anchors(toy_answers(), mode="median")
    a = anchors.set_index(["userid", "date"])["anchor"]
    assert a[(1, 202104)] == pytest.approx(4.0)          # median of 2, 4, 6


def test_anchor_unknown_mode_raises():
    with pytest.raises(ValueError):
        personal_anchors(toy_answers(), mode="bogus")


def toy_pairs() -> tuple[pd.DataFrame, dict]:
    pairs = pd.DataFrame({
        "userid": [1, 1, 1],
        "date": [202102, 202103, 202104],
        "previous_date": [202101, 202102, 202103],
        "Q9_mean": [4.0, 6.0, 8.0],
        "previous_Q9_mean": [2.0, 4.0, 6.0],
    })
    medians = {202101: 3.0, 202102: 3.0, 202103: 4.0, 202104: 4.0}
    return pairs, medians


def test_predict_anchor_zero_lambda_is_common_shift():
    pairs, medians = toy_pairs()
    fp = attach_anchors(pairs, personal_anchors(toy_answers()))
    pred = predict_anchor(fp, medians, lam=0.0)
    expected = pairs["previous_Q9_mean"] + (
        pairs["date"].map(medians) - pairs["previous_date"].map(medians))
    assert np.allclose(pred, expected.to_numpy())


def test_predict_anchor_full_lambda_hits_anchor_plus_shift():
    pairs, medians = toy_pairs()
    fp = attach_anchors(pairs, personal_anchors(toy_answers()))
    pred = predict_anchor(fp, medians, lam=1.0)
    # 202102: history_count=1 < MIN_HISTORY -> anchor term zero -> 2 + (3-3) = 2
    assert pred[0] == pytest.approx(2.0)
    # 202103: anchor = 3.0 -> 3.0 + (4-3) = 4.0
    assert pred[1] == pytest.approx(4.0)
    # 202104: anchor = 4.0 -> 4.0 + (4-4) = 4.0
    assert pred[2] == pytest.approx(4.0)


def test_predict_anchor_respects_min_history_fallback():
    pairs, medians = toy_pairs()
    fp = attach_anchors(pairs, personal_anchors(toy_answers()))
    pred = predict_anchor(fp, medians, lam=0.5)
    # 202102 has only the t-1 answer in history -> pure common shift, no pull.
    shift = medians[202102] - medians[202101]
    assert pred[0] == pytest.approx(2.0 + shift)
    # 202104 has 3 earlier answers -> pulled halfway toward anchor 4.0.
    assert pred[2] == pytest.approx(6.0 + 0.5 * (4.0 - 6.0) + (medians[202104] - medians[202103]))
    assert MIN_HISTORY == 2
