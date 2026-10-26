import numpy as np
import pytest
from studies.sce_inflation_expectations.evaluation.anomaly_year_calibration import eligible_training_indices,choose_before_2021


def test_calendar_earlier_but_not_yet_published_label_is_excluded():
    rows=[dict(month='202104',truth_published_date='2021-05-10'),
          dict(month='202105',truth_published_date='2021-06-14'),
          dict(month='202106',truth_published_date='2021-07-12')]
    target=dict(month='202106',as_of='2021-06-10T23:59:59-04:00')
    assert eligible_training_indices(rows,target).tolist()==[0]


def test_constant_new_regime_has_no_learned_effect_before_it_occurs():
    x=np.c_[np.arange(24.),np.zeros(24)]
    y=1+.2*x[:,0]
    fit=choose_before_2021(x,y,[0,1,10])
    assert fit['alpha']==0
    assert fit['coefficients'][1]==0
    with pytest.raises(ValueError):choose_before_2021(np.zeros((25,2)),np.zeros(25),[0])
