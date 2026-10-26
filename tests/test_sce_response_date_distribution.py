import numpy as np
import pytest
from studies.sce_inflation_expectations.evaluation.response_date_distribution import rebin,distance,candidate,shifted


def test_uniform_rescaling_preserves_uniformity_and_total_mass():
    for a,b in [(31,30),(28,29),(29,28),(30,31)]:
        p=rebin(np.ones(a)/a,b)
        assert np.allclose(p,np.ones(b)/b) and p.sum()==pytest.approx(1)


def test_date_distance_has_days_not_inflation_units():
    r=distance([1,0,0],[0,0,1])
    assert r==dict(tvd=1,maximum_cdf_gap=1,w1_days=2)


def test_previous_year_source_is_time_eligible_and_future_wave_is_not_used():
    hist={202409:np.ones(30)/30,202501:np.ones(31)/31,202509:np.r_[1.,np.zeros(29)]}
    _,refs=candidate(hist,202509,'previous_year_same_month')
    assert refs==[202409]
    _,refs=candidate(hist,202509,'last6_available_months')
    assert refs==[202409]


def test_leap_and_year_boundaries():
    assert shifted(202601,-12)==202501 and shifted(202601,-1)==202512
    p=np.r_[np.zeros(28),1.]
    q=rebin(p,28)
    assert q.sum()==pytest.approx(1) and np.argmax(q)==27
