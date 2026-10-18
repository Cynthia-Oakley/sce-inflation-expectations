"""Only new past-feature and probability-estimator risks; no old scorer reruns."""
import numpy as np
import pandas as pd

from studies.sce_inflation_expectations.evaluation.retention_predictability import (
    NUMERIC, P_COLUMNS, STATE_COLUMNS, auc, build_features, fit_logistic, probability_metrics)


def fixture():
    rows = []
    for month, mean, bins in [(201901, 2., [0, 0, 0, 100, 0, 0, 0, 0, 0, 0]),
                              (201902, 2., [0, 0, 0, 100, 0, 0, 0, 0, 0, 0]),
                              (201903, 5., [0, 0, 100, 0, 0, 0, 0, 0, 0, 0]),
                              (201904, 5., [0, 0, 100, 0, 0, 0, 0, 0, 0, 0])]:
        rows.append({'userid': 101, 'date': month, 'mi': month % 100, 'weight': 1.,
                     'Q9_mean': mean, 'Q9_iqr': 2., 'panel_status': 'adjacent_returner' if month > 201901 else 'entry_tenure_1',
                     **{f'Q9_bin{i+1}': v for i, v in enumerate(bins)},
                     **{c: 'same' for c in P_COLUMNS+STATE_COLUMNS}})
    return pd.DataFrame(rows)


def test_current_answers_and_current_P_cannot_change_current_features():
    original = fixture(); modified = original.copy()
    modified.loc[modified.date >= 201903, ['Q9_mean', 'Q9_iqr']] = [99., 80.]
    modified.loc[modified.date >= 201903, ['Q9_bin3', 'Q9_bin4']] = [50., 50.]
    modified.loc[modified.date >= 201903, 'financial_change'] = 'changed'
    a, b = build_features(original), build_features(modified)
    columns = list(NUMERIC)+['past_'+c for c in P_COLUMNS+STATE_COLUMNS]
    pd.testing.assert_frame_equal(a.loc[a.month <= 201903, columns], b.loc[b.month <= 201903, columns])


def test_history_counts_and_short_history_are_past_only():
    d = build_features(fixture())
    assert d.past_transition_n.tolist() == [0., 0., 1., 2.]
    assert d.past_stable_count.tolist() == [0., 0., 1., 1.]
    assert np.isnan(d.past_stable_rate.iloc[0])
    assert d.past_stable_rate.iloc[-1] == .5


def test_calendar_gap_is_not_a_monthly_stability_label():
    d = fixture().drop(index=1)
    result = build_features(d)
    assert np.isnan(result.loc[result.month == 201903, 'label_stable'].iloc[0])


def test_weighted_auc_ties_and_perfect_order():
    y = np.array([0., 1., 0., 1.]); w = np.array([1., 3., 2., 1.])
    assert auc(y, np.ones(4)*.3, w) == .5
    assert auc(y, y, w) == 1.
    assert auc(y, 1-y, w) == 0.


def test_regularized_logistic_finds_known_signal():
    x = np.column_stack((np.ones(10), np.arange(10)-4.5))
    y = np.r_[np.zeros(5), np.ones(5)]
    b, result = fit_logistic(x, y, np.ones(10))
    assert result['converged'] and b[1] > 1.
    assert abs(b[0]) < 1e-5


def test_calibration_boundary_belongs_to_one_bin_only():
    rows = pd.DataFrame({'month': [202001]*20, 'weight': [1.]*20,
                         'label_stable': [0., 1.]*10})
    result = probability_metrics(rows, np.full(20, .3))
    assert len(result['calibration']) == 1
    assert result['calibration'][0]['n'] == 20
