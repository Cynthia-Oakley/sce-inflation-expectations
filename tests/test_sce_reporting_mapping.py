import numpy as np
import pandas as pd
import pytest
from scipy.stats import wasserstein_distance

from studies.sce_inflation_expectations.reporting_behavior.mapping import (
    map_probabilities, history_profiles, assign_styles, permute_styles, cell_metrics,
)


def test_independent_rounding_examples_and_conservation():
    p = [23, 47, 30] + [0] * 7
    np.testing.assert_array_equal(map_probabilities(p, 1), [25, 45, 30] + [0] * 7)
    np.testing.assert_array_equal(map_probabilities(p, 2), [20, 50, 30] + [0] * 7)
    np.testing.assert_array_equal(map_probabilities(p, 0), p)
    rng = np.random.default_rng(23)
    for probability in rng.dirichlet(np.ones(10), size=100) * 100:
        for style, grid in ((1, 5), (2, 10)):
            answer = map_probabilities(probability, style)
            assert answer.sum() == 100
            assert (answer % grid == 0).all()
            assert (answer >= 0).all()
    with pytest.raises(ValueError):
        map_probabilities([23, 47, 29] + [0] * 7, 1)


def test_fractional_tie_has_declared_bin_order():
    np.testing.assert_array_equal(map_probabilities([25, 25, 25, 25] + [0] * 6, 2),
                                  [30, 30, 20, 20] + [0] * 6)


def test_current_future_and_other_person_truth_cannot_change_style():
    rows = []
    for uid in (1, 2):
        for date in (201701, 201702, 202203, 202204):
            row = {"userid": uid, "date": date, "weight": 1, "Q9_iqr": 2}
            row.update({f"Q9_bin{i}": v for i, v in enumerate([5, 95] + [0] * 8, 1)})
            rows.append(row)
    data = pd.DataFrame(rows)
    tables = {"population": [.2, .3, .5], "state": {},
              "cuts": {"previous_Q9_iqr": [1, 2, 3], "previous_max_mass": [25, 50, 75]}}
    subjects = [{"userid": 1, "month": 202203}]
    original = history_profiles(data, subjects, tables)
    altered = data.copy()
    mask = (altered.date >= 202203) | (altered.userid == 2)
    altered.loc[mask, [f"Q9_bin{i}" for i in range(1, 11)]] = np.nan
    changed = history_profiles(altered, subjects, tables)
    assert original == changed
    np.testing.assert_allclose(original[0]["class_probabilities"], [.12, .58, .30])
    assert original[0]["past_n"] == 2
    assert original[0]["previous_valid_date"] == 201702


def test_no_history_uses_training_reference():
    data = pd.DataFrame(columns=["userid", "date", "weight", "Q9_iqr"] + [f"Q9_bin{i}" for i in range(1, 11)])
    tables = {"population": [.2, .3, .5], "state": {},
              "cuts": {"previous_Q9_iqr": [1, 2, 3], "previous_max_mass": [25, 50, 75]}}
    result = history_profiles(data, [{"userid": 1, "month": 202203}], tables)
    np.testing.assert_allclose(result[0]["class_probabilities"], tables["population"])
    assert result[0]["past_n"] == 0


def test_assignments_ignore_input_order_and_permutations_preserve_month_counts():
    profiles = [{"userid": i + 1, "month": 202203 if i < 5 else 202209,
                 "class_probabilities": [.2, .3, .5]} for i in range(10)]
    styles = assign_styles(profiles, 42)
    np.testing.assert_array_equal(assign_styles(profiles[::-1], 42)[::-1], styles)
    permutation = permute_styles(profiles, styles, 10, 1)
    for row in permutation:
        for idx in (slice(0, 5), slice(5, 10)):
            np.testing.assert_array_equal(np.bincount(row[idx], minlength=3),
                                          np.bincount(styles[idx], minlength=3))
    np.testing.assert_array_equal(permutation, permute_styles(profiles, styles, 10, 1))


def test_vectorized_w1_against_independent_scipy_and_empirical_quantiles():
    predicted = np.array([1., 2., 2., 7.])
    real = np.array([0., 3., 4., 8.])
    previous = np.array([2., 1., 5., 7.])
    weights = np.array([[1, 1, 1, 1], [0, 3, 1, 2], [2, 0, 2, 0]], float)
    result = cell_metrics(predicted, real, previous, weights)
    for i, w in enumerate(weights):
        assert result["cross_section_w1_pp"][i] == pytest.approx(wasserstein_distance(predicted, real, w, w))
        assert result["delta_w1_pp"][i] == pytest.approx(wasserstein_distance(predicted - previous, real - previous, w, w))
    assert result["sample_center_mae_pp"][0] == 1
    assert result["cross_person_iqr_pp"][0] == 1
    assert result["real_cross_person_iqr_pp"][0] == 4
