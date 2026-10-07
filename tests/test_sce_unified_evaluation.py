from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from scipy.stats import wasserstein_distance

from scripts.evaluate_sce_outputs import evaluate_bundles  # installs the standalone evaluation package path
from evaluation.metrics import (
    compare_distributions, headline_errors, paired_month_mae_interval, quantile, wasserstein1,
)
from evaluation.baselines import ar1_forecast, conditional_donor_distribution
from evaluation.benchmark import available_rows, reconstruction_benchmarks


def test_weighted_w1_matches_independent_scipy_with_unequal_sample_sizes():
    x, y, wx, wy = [0, 4, 10], [-1, 2], [1, 8, 1], [3, 7]
    assert wasserstein1(x, wx, y, wy) == pytest.approx(wasserstein_distance(x, y, wx, wy))


def test_same_median_does_not_hide_disagreement():
    result = compare_distributions([4, 4, 4], [1, 1, 1], [2, 4, 6], [1, 1, 1])
    assert result['median_error_pp'] == 0
    assert result['w1_pp'] == pytest.approx(4 / 3)
    assert result['iqr_error_pp'] == 4


def test_centered_distance_does_not_reward_known_level_constraint():
    result = compare_distributions([3, 4, 5], [1, 1, 1], [1, 2, 3], [1, 1, 1])
    assert result['w1_pp'] == 2
    assert result['centered_w1_pp'] == 0


def test_quantile_and_negative_weights():
    assert quantile([1, 3], [1, 3], .5) == 3
    with pytest.raises(ValueError):
        quantile([1, 3], [-1, 3], .5)


def test_forecast_statistics_and_missing_forecast_rejection():
    metrics = headline_errors([2, 5], [3, 3])
    assert metrics['mae_pp'] == 1.5
    assert metrics['bias_pp'] == .5
    assert metrics['rmse_pp'] == pytest.approx(np.sqrt(2.5))
    with pytest.raises(ValueError):
        headline_errors([2, np.nan], [3, 3])


def test_release_date_excludes_may_sce_from_june10_input():
    rows = [{'reference_period': '2021-04', 'published_date': '2021-05-10', 'value_pp': 3.4},
            {'reference_period': '2021-05', 'published_date': '2021-06-14', 'value_pp': 4.0}]
    cutoff = datetime(2021, 6, 10, 23, 59, 59, tzinfo=ZoneInfo('America/New_York'))
    assert available_rows(rows, cutoff) == rows[:1]
    mutated = deepcopy(rows)
    mutated[1]['value_pp'] = 99
    assert available_rows(mutated, cutoff) == rows[:1]


def test_date_only_availability_is_conservative_same_day():
    row = [{'reference_period': '2021-04', 'published_date': '2021-05-10'}]
    assert not available_rows(row, datetime(2021, 5, 10, 12, tzinfo=ZoneInfo('America/New_York')))
    assert available_rows(row, datetime(2021, 5, 10, 23, 59, 59, tzinfo=ZoneInfo('America/New_York'))) == row


def test_ar1_recurses_for_publication_lag():
    prediction, _ = ar1_forecast(np.arange(1, 14), 2)
    assert prediction == pytest.approx(15)


def test_conditional_mixture_uses_population_mass_not_equal_groups():
    x, w, _, _ = conditional_donor_distribution([1, 7], [1, 1], ['a', 'b'],
                                               ['a', 'b'], [9, 1], minimum_donors=1)
    assert np.average(x, weights=w) == pytest.approx(1.6)
    assert quantile(x, w, .5) == 1


def test_identical_forecasts_have_zero_paired_interval():
    result = paired_month_mae_interval([1, -2, 1, 2], [1, -2, 1, 2], block_length=2, draws=30)
    assert result['mae_difference_pp'] == 0
    assert result['interval_95'] == [0, 0]


def test_unified_population_rejects_scoring_mismatch_and_marks_constraints():
    common = {'kind': 'population', 'truth_series_id': 'test', 'scoring_version': 'same',
              'records': [{'target_month': '2021-05', 'mean_pp': 4, 'weight': 1}]}
    sim = deepcopy(common)
    sim['constraints'] = ['national_median']
    result = evaluate_bundles(sim, common)
    assert result['primary_metric'] == 'centered_w1_pp'
    assert result['national_median_role'] == 'constraint_satisfaction_only'
    sim['scoring_version'] = 'different'
    with pytest.raises(ValueError):
        evaluate_bundles(sim, common)


def test_unified_evaluation_rejects_missing_months():
    real = {'kind': 'headline', 'truth_series_id': 'first', 'records': [
        {'target_month': '2020-01', 'value_pp': 3}, {'target_month': '2020-02', 'value_pp': 4}]}
    sim = deepcopy(real)
    sim['records'] = sim['records'][:1]
    with pytest.raises(ValueError):
        evaluate_bundles(sim, real)


def test_real_text_categories_preserve_conditional_population_mass():
    import pandas as pd
    def rows(month, count, age, mean):
        return [{'date': month, 'weight': 1, 'Q9_mean': mean, 'Q9_iqr': 2,
                 '_AGE_CAT': age, '_EDU_CAT': 'College'} for _ in range(count)]
    frame = pd.DataFrame(rows(201912, 20, 'Under 40', 0) + rows(201912, 20, 'Over 60', 10)
                         + rows(202001, 180, 'Under 40', 1) + rows(202001, 20, 'Over 60', 9))
    protocol = {'evaluation_start': '2020-01', 'evaluation_end': '2020-01',
                'reconstruction_conditional_fields': ['_AGE_CAT', '_EDU_CAT'],
                'reconstruction_minimum_donor_count': 20}
    result, _ = reconstruction_benchmarks(frame, protocol)
    conditional = next(r for r in result if r['method'] == 'population_conditional')
    pooled = next(r for r in result if r['method'] == 'prior_distribution')
    assert conditional['simulated']['mean_pp'] == pytest.approx(1)
    assert pooled['simulated']['mean_pp'] == pytest.approx(5)
    assert conditional['group_median_error_pp'] == pytest.approx(1)


def test_individual_pairing_requires_explicit_observed_linkage():
    common = {'kind': 'population', 'truth_series_id': 'test', 'scoring_version': 'same',
              'group_fields': ['age'], 'minimum_group_count': 1,
              'records': [{'target_month': '2021-05', 'person_id': 'one', 'mean_pp': 4, 'weight': 3, 'age': 'Under40'}]}
    sim = deepcopy(common)
    sim['records'][0]['mean_pp'] = 6
    assert evaluate_bundles(sim, common)['monthly'][0]['paired'] is None
    sim['pairing'] = 'same_observed_person'
    result = evaluate_bundles(sim, common)['monthly'][0]
    assert result['paired']['weighted_mae_pp'] == 2
    assert result['groups'][0]['median_error_pp'] == 2


def test_future_target_and_macro_values_cannot_change_current_forecasts():
    from evaluation.benchmark import forecast_benchmarks
    releases = [{'reference_period': f'2019-{m:02d}', 'published_date': f'2019-{m+1:02d}-07',
                 'value_pp': 3., 'chart_snapshot_value_pp': 3.} for m in range(1,12)]
    releases += [{'reference_period':'2018-12','published_date':'2019-01-07','value_pp':3.,'chart_snapshot_value_pp':3.},
                 {'reference_period':'2019-12','published_date':'2020-01-07','value_pp':3.,'chart_snapshot_value_pp':3.},
                 {'reference_period':'2020-01','published_date':'2020-02-07','value_pp':4.,'chart_snapshot_value_pp':4.}]
    inputs={'headline_releases':releases,'cpi_calendar':[{'target_month':'2020-01','published_date':'2020-01-13'}],
            'cpi_first_releases':[{'reference_period':'2019-12','published_date':'2020-01-13','value':2.},
                                  {'reference_period':'2020-01','published_date':'2020-02-13','value':99.}]}
    protocol={'evaluation_start':'2020-01','evaluation_end':'2020-01','forecast_cutoffs':['current_month_cpi_release_day_end'],
              'minimum_training_observations':12,'rolling_mean_months':12,'sticky_agent_update_probabilities':[.25],
              'simple_agent_n':30,'seed':42}
    original,_=forecast_benchmarks(inputs,protocol)
    changed=deepcopy(inputs)
    changed['headline_releases'][-1]['value_pp']=90
    changed['cpi_first_releases'][-1]['value']=100
    mutated,_=forecast_benchmarks(changed,protocol)
    assert [(r['method'],r['prediction_pp']) for r in original]==[(r['method'],r['prediction_pp']) for r in mutated]


def test_missing_cpi_release_day_is_reported_and_never_invented():
    from evaluation.benchmark import forecast_benchmarks, macro_feature
    inputs = {'headline_releases': [{'reference_period': '2025-11', 'published_date': '2025-12-08',
                'value_pp': 3.2, 'chart_snapshot_value_pp': 3.2}],
              'cpi_calendar': [], 'cpi_first_releases': []}
    protocol = {'evaluation_start': '2025-11', 'evaluation_end': '2025-11',
                'forecast_cutoffs': ['current_month_cpi_release_day_end'],
                'missing_current_cpi_cutoff_rule': 'exclude_and_report',
                'headline_baselines': ['persistence'], 'macro_extensions': ['arx_sce_cpi']}
    rows, skipped = forecast_benchmarks(inputs, protocol)
    assert not rows
    assert len(skipped) == 2
    assert {r['reason'] for r in skipped} == {'no_actual_current_month_cpi_release_day'}
    assert macro_feature('2025-11', 'current_month_cpi_release_day_end', inputs) is None
    protocol.pop('missing_current_cpi_cutoff_rule')
    with pytest.raises(ValueError):
        forecast_benchmarks(inputs, protocol)
