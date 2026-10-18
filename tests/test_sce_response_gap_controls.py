import numpy as np
import pytest

from studies.sce_inflation_expectations.evaluation.response_gap_controls import probability_features, regression, q8_crosscheck


def test_probability_shape_degenerate_and_equal_mass():
    one = probability_features([0, 0, 0, 100, 0, 0, 0, 0, 0, 0])
    assert one['zero_deflation'] == 1 and one['nonzero_bins'] == 1
    assert one['entropy_bits'] == 0 and one['maximum_bin_pct'] == 100
    uniform = probability_features([10]*10)
    assert uniform['deflation_probability_pct'] == 50
    assert uniform['entropy_bits'] == pytest.approx(np.log2(10))


def test_no_repair_of_invalid_probability():
    with pytest.raises(ValueError):
        probability_features([0]*10)


def test_conditional_gap_coefficients_are_model_minus_real():
    x = np.column_stack([np.ones(5), np.arange(5)])
    yreal = 1+2*np.arange(5)
    ysim = 3+.5*np.arange(5)
    _, coefficient = regression(x, ysim-yreal, np.array([1, 2, 3, 4, 5]), ['constant', 'prior'])
    assert coefficient == pytest.approx([2, -1.5])


def test_q8_is_separate_weighted_support_and_median():
    rows = []
    for real, weight, prior in [(1., 3., 1.), (3., 1., 3.), (None, 4., 1.)]:
        reply = {'real': {'q8_point': real}, 'arms': {'reference': {'point': 2.}}}
        rows.append({'month': 202003, 'weight': weight, 'prior_q8': prior,
                     'records': [reply, reply]})
    result = q8_crosscheck(rows)
    assert result['n_person_months'] == 2
    assert result['cells'][0]['excluded_from_q9_common_support_n'] == 1
    assert result['all_months_equal_weight']['model']['center_mae_pp'] == pytest.approx(1.)
    assert result['all_months_equal_weight']['truth']['cross_person_iqr_pp'] == pytest.approx(0.)
    assert result['all_months_equal_weight']['copy_previous']['person_mae_pp'] == 0
    assert result['mean_of_monthly_slopes_on_prior'] == pytest.approx({'truth': 1, 'model': 0})
