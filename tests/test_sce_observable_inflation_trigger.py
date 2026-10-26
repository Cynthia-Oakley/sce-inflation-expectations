import numpy as np
from studies.sce_inflation_expectations.evaluation.observable_inflation_trigger import constrained_fit,signal_features,training_threshold,complete_differences
import pytest


def row(dc,ds):
    return dict(baseline_pp=3,cpi_yoy_pp=2,cpi_change_pp=dc,expanded_model_pp=3,
                lag_y_change=.1,sim_change=ds)


def test_trigger_is_observable_and_strictly_uses_price_change():
    f=signal_features(row(.5,.1),.2)
    assert f['trigger']==1 and np.isclose(f['underreaction'],.4)
    assert signal_features(row(.2,-.1),.2)['trigger']==0
    assert signal_features(row(-.1,-.5),.2)['underreaction']==0


def test_sign_bound_prevents_upward_channel_from_learning_a_negative_slope():
    x=np.arange(10.)[:,None];y=-2*x[:,0]
    fit=constrained_fit(x,y,0,[0])
    assert fit['coefficients'][0]>=0 and fit['coefficients'][0]<1e-8
    positive=constrained_fit(x,-y,0,[0])
    assert np.isclose(positive['coefficients'][0],2)


def test_unobserved_constant_trigger_gets_no_invented_coefficient():
    x=np.c_[np.arange(10.),np.zeros(10)];y=1+x[:,0]
    fit=constrained_fit(x,y,0,[1])
    assert fit['coefficients'][1]==0 and fit['constant_columns_unlearned']==[1]


def test_threshold_is_derived_only_from_supplied_training_predictors():
    rows=[row(v,0) for v in [-.2,0,.1,.3]]
    assert np.isclose(training_threshold(rows),.15)


def test_true_differences_use_adjacent_public_anchor_and_previous_simulation():
    first=dict(month='202012',truth_pp=3,baseline_pp=2.8,expanded_model_pp=2.9,
               cpi_yoy_pp=1.2,cpi_change_pp=.1,truth_published_date='2021-01-11',as_of='2020-12-31')
    second=dict(first,month='202101',truth_pp=3.2,baseline_pp=3,expanded_model_pp=3.3,
                truth_published_date='2021-02-08',as_of='2021-01-31')
    r=complete_differences([first,second])[0]
    assert np.isclose(r['lag_y_change'],.2) and np.isclose(r['sim_change'],.4)
    with pytest.raises(ValueError,match='not adjacent'):
        complete_differences([first,dict(second,baseline_pp=2.8)])
    with pytest.raises(ValueError,match='Unavailable lagged'):
        complete_differences([dict(first,truth_published_date='2021-02-01'),second])
