"""Numerical checks independent of model calls or graphical implementation."""
import numpy as np
from studies.sce_inflation_expectations.pe_diagnostic import remembered_point, probability_diagnostic, prev_month, monthly_groups


def test_last_month_memory_not_just_prior_keyword():
    text='Last month you gave a point estimate of 2.0% for the then-current period.'
    assert 'prior' not in text and 'previous' not in text
    assert remembered_point(text)==2.
    assert remembered_point('Question about future inflation only') is None
    assert remembered_point('Last month you gave a point estimate of -1.5%')==-1.5
    assert prev_month(202101)==202012


def test_bin_direction_and_tail_sensitivity():
    x=probability_diagnostic([0,0,0,0,60,40,0,0,0,0])
    assert x['deflation_mass_pct']==40
    assert x['positive_bin_count']==2
    assert np.isclose(x['midpoint_mean_tail16_pp'],.2)
    assert probability_diagnostic([0]*10) is None
    y=probability_diagnostic([10,0,0,0,90,0,0,0,0,0])
    assert y['symmetric_tail12_20_mean_range_pp']==[2.1,2.9]


def test_monthly_q8_and_q9_have_independent_masks():
    base={'month':202101,'deflation_mass_pct':0.,'midpoint_mean_tail16_pp':1.,'positive_bin_count':1}
    rows=[{**base,'point':2.,'density':1.,'real_point':4.,'real_density':3.},
          {**base,'point':4.,'density':2.,'real_point':8.,'real_density':None}]
    x=monthly_groups(rows)['202101']
    assert x['point']['simulated']['n']==2 and x['point']['simulated']['median']==3
    assert x['density']['simulated']['n']==1 and x['density']['matched_real']['median']==3
