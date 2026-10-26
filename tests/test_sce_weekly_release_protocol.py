from copy import deepcopy

import pytest

from studies.sce_inflation_expectations.experiments.weekly_release_protocol import (
    known_from,schedule,score_cutoffs,direction,evaluate_frozen_points,
)


def releases():
    return [dict(reference_period='2025-10',published_date='2025-11-07',value_pp=3.2),
            dict(reference_period='2025-11',published_date='2025-12-08',value_pp=3.2),
            dict(reference_period='2025-12',published_date='2026-01-08',value_pp=3.4),
            dict(reference_period='2026-01',published_date='2026-02-09',value_pp=3.1)]


def dates():
    return ['2025-12-05T23:59:59-05:00','2025-12-12T23:59:59-05:00',
            '2025-12-19T23:59:59-05:00','2025-12-26T23:59:59-05:00',
            '2026-01-02T23:59:59-05:00','2026-01-09T23:59:59-05:00',
            '2026-01-16T23:59:59-05:00','2026-01-23T23:59:59-05:00','2026-01-30T23:59:59-05:00']


def test_calendar_month_change_does_not_reset_without_new_release():
    rows=schedule(dates(),releases())
    assert rows[3]['cycle_key']==rows[4]['cycle_key']
    assert rows[4]['reset_required'] is False
    assert rows[5]['reset_required'] is True
    assert rows[4]['anchor_reference_period']=='2025-11'
    assert rows[5]['anchor_reference_period']=='2025-12'


def test_release_day_without_timestamp_is_not_silently_available_in_morning():
    r=releases()[2]
    assert known_from(r).isoformat()=='2026-01-09T00:00:00-05:00'
    points=schedule(['2026-01-08T15:00:00-05:00','2026-01-09T15:00:00-05:00'],releases())
    assert points[0]['anchor_reference_period']=='2025-11'
    assert points[1]['anchor_reference_period']=='2025-12'


def test_verified_timestamp_can_be_used_only_after_publication():
    rs=releases();rs[2]['verified_published_at']='2026-01-08T11:00:00-05:00'
    p=schedule(['2026-01-08T10:00:00-05:00','2026-01-08T12:00:00-05:00'],rs)
    assert p[0]['reset_required'] and p[1]['reset_required']
    assert p[1]['anchor_reference_period']=='2025-12'


def test_each_horizon_uses_one_latest_eligible_forecast_per_month():
    points=schedule(dates(),releases());selected=score_cutoffs(points,releases(),(7,14,21))
    main=[r for r in selected if r['panel']=='last_week_in_month']
    assert len(main)==2 and [r['cutoff'][:10] for r in main]==['2025-12-26','2026-01-30']
    h14=[r for r in selected if r['panel']=='at_least_14_days_before_release']
    assert [r['cutoff'][:10] for r in h14]==['2025-12-19','2026-01-23']


def test_manual_expected_level_skill_and_direction_with_false_alarm():
    rows=schedule(dates(),releases())
    # Month-end predictions 3.3 and 3.0: each misses by .1; persistence
    # errors .2 and .3, so MAE .1 vs .25 and relative reduction .6.
    forecasts=[dict(**r,forecast_pp=3.3 if r['target_reference_period']=='2025-12' else 3.0,
                    forecast_kind='raw_model_pre_reset') for r in rows]
    out=evaluate_frozen_points(forecasts,releases());p=out['panels']['last_week_in_month']
    assert p['raw']['mae_pp']==pytest.approx(.1)
    assert p['persistence']['mae_pp']==pytest.approx(.25)
    assert p['relative_MAE_reduction']==pytest.approx(.6)
    assert p['n_target_months']==2 and out['n_distinct_target_months']==2
    assert out['new_API_calls']==0 and p['rows'][1]['evaluation_only_anomaly'] is True


def test_post_reset_state_cannot_masquerade_as_pre_release_prediction():
    r=dict(**schedule(dates()[:1],releases())[0],forecast_pp=3.2,forecast_kind='post_reset_calibrated')
    with pytest.raises(ValueError,match='Post-reset'):evaluate_frozen_points([r],releases())


def test_baseline_cannot_use_a_national_value_not_yet_public():
    r=dict(**schedule(dates()[4:5],releases())[0],forecast_pp=3.2,forecast_kind='raw_model_pre_reset')
    r['anchor_reference_period']='2025-12';r['anchor_pp']=3.4
    with pytest.raises(ValueError,match='metadata mismatch'):evaluate_frozen_points([r],releases())


def test_deadband_avoids_rounding_error_turning_point_one_into_trend():
    assert direction(3.4-3.3,.1)=='flat'
    assert direction(.2,.1)=='up'
    assert direction(-.2,.1)=='down'


def test_duplicate_or_naive_weekly_clocks_rejected():
    with pytest.raises(ValueError,match='Unique'):schedule([dates()[0],dates()[0]],releases())
    with pytest.raises(ValueError,match='Timezone'):schedule(['2026-01-02T12:00:00'],releases())
