"""Small-sample tests for the SCE updating-facts module (F1-F6 helpers)."""
import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.belief_dynamics.updating_facts import (
    _excess_kurtosis,
    cg_regression,
    heaping_stats,
    inaction_stats,
    kmeans_fit,
    load_cpi_yoy,
    mean_reversion_stats,
    month_weighted_medians,
    shift_month,
    split_half,
    variance_decomposition,
)


def _toy_pairs() -> pd.DataFrame:
    """4 persons x 2 adjacent months, deltas 0, 0.1, -1.0, 2.0."""
    rows = []
    for uid, (y0, y1) in enumerate([(5.0, 5.0), (3.0, 3.1), (7.0, 6.0), (1.0, 3.0)]):
        rows.append({"userid": uid, "date": 202002, "previous_date": 202001,
                     "Q9_mean": y1, "previous_Q9_mean": y0, "weight": 1.0})
    return pd.DataFrame(rows)


def test_shift_month():
    assert shift_month(202002, 12) == 202102
    assert shift_month(202012, 1) == 202101
    assert shift_month(202001, -1) == 201912


def test_load_cpi_yoy_toy(tmp_path):
    p = tmp_path / "v.csv"
    p.write_text("observation_date,CPIAUCNS_20200101\n"
                 "2019-01-01,100.0\n2019-02-01,100.0\n"
                 "2020-01-01,102.0\n2020-02-01,103.0\n")
    yoy = load_cpi_yoy(p)
    assert yoy[202001] == pytest.approx(2.0)
    assert yoy[202002] == pytest.approx(3.0)
    assert 201902 not in yoy  # needs 2018-02 level


def test_load_cpi_yoy_bad_header(tmp_path):
    p = tmp_path / "v.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError):
        load_cpi_yoy(p)


def test_inaction_shares_toy():
    pairs = _toy_pairs()
    for i in range(1, 11):
        pairs[f"Q9_bin{i}"] = 10.0
        pairs[f"previous_Q9_bin{i}"] = 10.0
    pairs.loc[1, "Q9_bin1"] = 20.0  # person 1 changed a bin but mean moved 0.1
    out = inaction_stats(pairs)["overall"]
    assert out["share_exact_zero_delta_unweighted"] == pytest.approx(0.25)
    assert out["share_abs_delta_le_0.25pp_unweighted"] == pytest.approx(0.5)
    assert out["share_abs_delta_le_0.05pp_unweighted"] == pytest.approx(0.25)
    # bin vector of person 1 differs -> identical share = 3/4
    assert out["share_identical_bin_vector_unweighted"] == pytest.approx(0.75)


def test_excess_kurtosis_toy():
    rng = np.random.default_rng(7)
    normal = rng.normal(0, 1, 5000)
    assert abs(_excess_kurtosis(normal)) < 0.4
    heavy = np.r_[np.zeros(90), 10.0, -10.0, 8.0, -8.0, 6.0, -6.0, 5.0, -5.0, 4.0, -4.0]
    assert _excess_kurtosis(heavy) > 0


def test_cg_regression_exact_slope():
    # previous forecast constant at 4, current varies; realized t+12 = 2.
    # e = 2 - y1 = -1 - (y1 - 3); r = y1 - 4 -> after FE, slope = cov(r, e)/var(r)
    # = -1 exactly.
    n = 100
    y1 = np.linspace(1, 8, n)
    pairs = pd.DataFrame({
        "userid": np.arange(n),
        "date": np.repeat(202002, n),
        "previous_date": np.repeat(202001, n),
        "Q9_mean": y1,
        "previous_Q9_mean": np.full(n, 4.0),
        "weight": np.ones(n),
    })
    out = cg_regression(pairs, {shift_month(202002, 12): 2.0})
    assert out["n_pairs"] == n
    assert out["slope_pooled_month_fe_unweighted"] == pytest.approx(-1.0)


def test_heaping_stats_toy():
    frame = pd.DataFrame({
        "userid": [0, 1, 2],
        "date": [202001, 202001, 202001],
        "weight": [1.0, 1.0, 2.0],
        "Q9_mean": [0.0, 1.0, 2.0],
        **{f"Q9_bin{i}": v for i, v in
           enumerate([0, 0, 0, 0, 50, 50, 0, 0, 0, 0], start=1)},
    })
    # overwrite per-row bins
    frame.loc[1, [f"Q9_bin{i}" for i in range(1, 11)]] = [25, 25, 25, 25, 0, 0, 0, 0, 0, 0]
    frame.loc[2, [f"Q9_bin{i}" for i in range(1, 11)]] = [100, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    out = heaping_stats(frame)
    assert out["share_nonzero_divisible_by_5_unweighted"] == pytest.approx(1.0)
    # non-zero cells: row0 {50,50}, row1 {25x4}, row2 {100} -> 3 of 7 divisible by 10
    assert out["share_nonzero_divisible_by_10_unweighted"] == pytest.approx(3 / 7)
    top0 = out["top_vectors"][0]
    assert top0["vector"] == [0, 0, 0, 0, 50, 50, 0, 0, 0, 0]


def test_variance_decomposition_and_split_half():
    # person A always +5 above median, person B always -5 -> 100% between
    frame = pd.DataFrame({
        "userid": np.repeat([0, 1], 6),
        "date": np.tile([202001, 202002, 202003, 202004, 202005, 202006], 2),
        "Q9_mean": np.r_[np.repeat(5.0, 6), np.repeat(-5.0, 6)],
        "weight": np.ones(12),
    })
    medians = {m: 0.0 for m in frame["date"].unique()}
    vd = variance_decomposition(frame, medians, min_months=6)
    assert vd["between_share_unweighted"] == pytest.approx(1.0)
    # each person constant across waves -> odd mean == even mean per person
    sh = split_half(frame, medians, min_months=6)
    assert sh["correlation_odd_even_person_means"] == pytest.approx(1.0)
    # person0 high on odd waves / low on even, person1 the opposite -> -1
    frame2 = frame.copy()
    frame2.loc[frame2["userid"] == 0, "Q9_mean"] = [5, -5, 5, -5, 5, -5]
    frame2.loc[frame2["userid"] == 1, "Q9_mean"] = [-5, 5, -5, 5, -5, 5]
    sh2 = split_half(frame2, medians, min_months=6)
    assert sh2["correlation_odd_even_person_means"] == pytest.approx(-1.0)


def test_mean_reversion_toy():
    pairs = _toy_pairs()
    frame = pd.DataFrame({
        "userid": np.repeat([0, 1, 2, 3], 2),
        "date": [202001, 202002] * 4,
        "Q9_mean": [5.0, 5.0, 3.0, 3.1, 7.0, 6.0, 1.0, 3.0],
        "weight": np.ones(8),
    })
    medians = {202001: 0.0, 202002: 0.0}
    # previous means 5,3,7,1 -> deviations d = 5,3,7,1; deltas 0,0.1,-1,2
    out = mean_reversion_stats(pairs, medians, frame)
    # slope = cov(d, delta)/var(d) computed on 4 points
    d = np.array([5.0, 3.0, 7.0, 1.0])
    y = np.array([0.0, 0.1, -1.0, 2.0])
    expected = ((d - d.mean()) * (y - y.mean())).sum() / ((d - d.mean()) ** 2).sum()
    assert out["slope_unweighted"] == pytest.approx(expected)


def test_kmeans_recovers_separated_groups():
    rng = np.random.default_rng(1)
    a = rng.normal([0.1, 1.0, 2.0], 0.05, size=(50, 3))
    b = rng.normal([0.9, 4.0, 8.0], 0.05, size=(50, 3))
    X = np.vstack([a, b])
    labels, centers, inertia = kmeans_fit(X, 2, n_init=10, seed=0)
    assert len(set(labels.tolist())) == 2
    # groups should be cleanly separated: all of a share one label
    assert len(set(labels[:50].tolist())) == 1
    assert len(set(labels[50:].tolist())) == 1
    assert set(labels[:50].tolist()) != set(labels[50:].tolist())


def test_month_weighted_medians_toy():
    frame = pd.DataFrame({
        "userid": [0, 1, 2, 3],
        "date": [202001, 202001, 202001, 202002],
        "Q9_mean": [1.0, 2.0, 9.0, 5.0],
        "weight": [1.0, 1.0, 2.0, 1.0],
    })
    med = month_weighted_medians(frame)
    assert med[202001] == pytest.approx(2.0)  # weight 2 on 9.0 pulls ECDF
    assert med[202002] == 5.0
