"""Tests for the preregistered empirical update baselines (B0-B4)."""
import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.belief_dynamics.baselines import (
    common_medians,
    evaluate,
    fit_param,
    predict,
)
from studies.sce_inflation_expectations.belief_dynamics.data import (
    build_valid_pairs,
)
from studies.sce_inflation_expectations.belief_dynamics.dynamics import prepare_frame


def synthetic_pairs():
    """Two respondents, three months, hand-set values, legal uniform bins."""
    rows = []
    for userid, base in [(1, 2.0), (2, 4.0)]:
        for date in (202001, 202002, 202003):
            row = {"userid": userid, "date": date, "weight": 1.0,
                   "Q9_mean": base + 0.1 * (date % 100), "Q9_iqr": 2.0}
            for i in range(1, 11):
                row[f"Q9_bin{i}"] = 10.0
            rows.append(row)
    f = pd.DataFrame(rows)
    return f


@pytest.fixture(scope="module")
def synth():
    f = synthetic_pairs()
    return f, common_medians(f)


def test_b2_lambda_zero_equals_b0(synth):
    f, medians = synth
    pairs = build_valid_pairs(f)
    yhat_b0 = predict(pairs, medians, "B0")
    yhat_b2 = predict(pairs, medians, "B2", lam=0.0)
    np.testing.assert_allclose(yhat_b2, yhat_b0)


def test_b3_rho_one_equals_b1(synth):
    f, medians = synth
    pairs = build_valid_pairs(f)
    yhat_b1 = predict(pairs, medians, "B1")
    yhat_b3 = predict(pairs, medians, "B3", rho=1.0)
    np.testing.assert_allclose(yhat_b3, yhat_b1)


def test_b0_delta_w1_equals_weighted_mean_abs_delta():
    frame = prepare_frame()
    medians = common_medians(frame)
    pairs = build_valid_pairs(frame)
    for month in (202003, 202112, 202310):
        sub = pairs[pairs["date"] == month]
        res = evaluate(sub, medians, "B0")
        delta = (sub["Q9_mean"] - sub["previous_Q9_mean"]).to_numpy(float)
        w = sub["weight"].to_numpy(float)
        assert res["n_months"] == 1
        assert res["delta_w1_month_equal"] == pytest.approx(
            np.average(np.abs(delta), weights=w), rel=1e-12)


def test_fit_param_selects_grid_point():
    frame = prepare_frame()
    medians = common_medians(frame)
    pairs = build_valid_pairs(frame)
    train = pairs[(pairs["date"] >= 201702) & (pairs["date"] <= 202112)]
    grid = np.round(np.arange(0.0, 1.0 + 1e-9, 0.02), 2)
    lam, obj = fit_param(train, medians, "B2", grid)
    assert lam in grid
    assert 0.0 <= lam <= 1.0
    assert obj > 0
    # Refit objective reproduces the reported train MAE.
    res = evaluate(train, medians, "B2", lam=lam)
    assert res["mae_pp_month_equal_auxiliary"] == pytest.approx(obj, rel=1e-12)
