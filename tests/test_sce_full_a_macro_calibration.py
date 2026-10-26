import numpy as np
import pytest
from studies.sce_inflation_expectations.evaluation.full_a_macro_calibration import fit_ridge,predict,train_only_fit,cpi_features


def test_unpenalized_linear_fit_has_known_raw_coefficient():
    x=np.arange(10.)[:,None];y=3+2*x[:,0]
    fit=fit_ridge(x,y,0)
    assert np.isclose(fit['intercept'],3)
    assert np.allclose(fit['coefficients'],[2])
    assert np.allclose(predict(x,fit),y)


def test_constant_predictor_is_safe_and_penalty_shrinks():
    x=np.c_[np.arange(48.),np.ones(48)];y=np.arange(48.)*.2
    a=fit_ridge(x,y,0);b=fit_ridge(x,y,100)
    assert abs(b['coefficients'][0])<abs(a['coefficients'][0])
    assert np.isfinite(predict(x,b)).all()


def test_training_selection_rejects_later_targets():
    x=np.arange(82.)[:,None];y=np.arange(82.)*.1
    with pytest.raises(ValueError):train_only_fit(x,y,[0,1])
    fit=train_only_fit(x[:48],y[:48],[0,1])
    assert fit['alpha']==0


def test_future_cpi_is_excluded_and_missing_history_not_filled():
    records=[dict(signal_id='bls_cpi_u_all_items_yoy_'+m,reference_period=m,published_at=d,value=v)
             for m,d,v in [('2021-04','2021-05-12T08:30:00-04:00',4.2),
                           ('2021-03','2021-04-13T08:30:00-04:00',2.6),
                           ('2021-05','2021-06-10T08:30:00-04:00',5)]]
    env=dict(provider_args=dict(targets=[dict(as_of='2021-06-01T23:59:59-04:00')],signals_by_step={'0':records}))
    result=cpi_features(env)
    assert result['cpi_yoy_pp']==4.2
    assert np.isclose(result['cpi_change_pp'],1.6)
    env['provider_args']['targets'][0]['as_of']='2021-05-01T23:59:59-04:00'
    with pytest.raises(ValueError):cpi_features(env)
