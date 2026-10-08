"""Independent known answers for the offline evaluation, no network."""
import numpy as np
import pandas as pd

from studies.sce_inflation_expectations.numeracy_audit import shift_month, add_benchmarks, adjusted_associations
from studies.sce_inflation_expectations.household_state_audit import classify_numeracy, summary


def test_calendar_horizon_and_not_current_error():
    assert shift_month(202012, 1) == 202101
    assert shift_month(202001, -1) == 201912
    f = pd.DataFrame({'date': [202105, 202106], 'point': [5., 5.], 'density_mean': [4., 4.]})
    g = add_benchmarks(f, {202105: 5., 202205: 8.6})
    assert g.point_current_distance.iloc[0] == 0
    assert np.isclose(g.point_future_error.iloc[0], 3.6)
    assert np.isnan(g.point_future_error.iloc[1])  # unknown realized value stays missing


def test_official_numeracy_threshold_and_incomplete_policy():
    d = pd.DataFrame({'QNUM1': [150, 150, 150, None], 'QNUM2': [242, 242, 240, 242],
                      'QNUM3': [10, 10, 9, 10], 'QNUM5': [100, 100, 100, 100],
                      'QNUM6': [5, 4, 5, 5]})
    labels, complete = classify_numeracy(d)
    assert labels.iloc[:3].tolist() == ['High', 'High', 'Low']
    assert not complete.iloc[3] and pd.isna(labels.iloc[3])


def test_weighted_location_and_missing_values():
    s = summary([1, 9, np.nan, 999], [3, 1, 9, 0])
    assert s['valid_n'] == 2 and s['weighted_mean_pp'] == 3
    assert s['weighted_median_pp'] == 1


def test_known_adjusted_gap_in_balanced_cells():
    rows = []
    for month in [202101, 202102]:
        for age in ['a', 'b']:
            for num in ['High', 'Low']:
                y = 3 + (num == 'Low') * 2 + (age == 'b') + (month == 202102) * 5
                rows.append({'date': month, '_AGE_CAT': age, '_EDU_CAT': 'x', '_HH_INC_CAT': 'x',
                             '_REGION_CAT': 'x', '_NUM_CAT': num, 'weight': 1,
                             'point': y, 'density_mean': y, 'uncertainty': y, 'point_future_error': y, 'density_future_error': y})
    r = adjusted_associations(pd.DataFrame(rows), 'weight')
    assert all(np.isclose(v['low_minus_high_coefficient_pp'], 2.) for v in r['outcomes'].values())
