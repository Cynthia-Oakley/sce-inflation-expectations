from studies.sce_inflation_expectations.evaluation.dynamic_fair_benchmark import month_end,public_anchor
import pytest


def test_new_york_month_end_handles_leap_and_daylight_saving():
    assert month_end('202002')=='2020-02-29T23:59:59-05:00'
    assert month_end('202106')=='2021-06-30T23:59:59-04:00'


def test_month_end_control_may_use_a_release_unavailable_at_old_shared_cutoff():
    releases=[dict(reference_period='2021-04',published_date='2021-05-10',value_pp=3.4),
              dict(reference_period='2021-05',published_date='2021-06-14',value_pp=4.),
              dict(reference_period='2021-06',published_date='2021-07-12',value_pp=4.8)]
    assert public_anchor(releases,'202106','2021-06-10T23:59:59-04:00')['value_pp']==3.4
    assert public_anchor(releases,'202106',month_end('202106'))['value_pp']==4.
    with pytest.raises(ValueError):public_anchor(releases,'202106','2021-05-01')
