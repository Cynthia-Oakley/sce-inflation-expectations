import numpy as np
import pandas as pd

from studies.sce_inflation_expectations.evaluation.retention_predictability import P_COLUMNS, STATE_COLUMNS
from studies.sce_inflation_expectations.evaluation.update_direction import (
    NUMERIC, classify, prepare_features, fit_change, fit_direction, direction_probabilities)


def fixture():
    return pd.DataFrame([{'userid':1,'date':201901+i,'mi':i,'weight':1.,'Q9_mean':mu,'Q9_iqr':2.,
        'panel_status':'entry_tenure_1' if i==0 else 'adjacent_returner',
        **{f'Q9_bin{j}':100. if j==4 else 0. for j in range(1,11)},
        **{c:'same' for c in P_COLUMNS+STATE_COLUMNS}} for i,mu in enumerate((2.,4.,5.,3.))])


def test_old_mean_excludes_prior_and_current_answers_do_not_enter_features():
    d=fixture(); a=prepare_features(d)
    assert np.isnan(a.older_gap_pp.iloc[1])
    assert abs(a.older_gap_pp.iloc[2]+2.)<1e-10
    d.loc[d.date>=201903,['Q9_mean','Q9_iqr']]=[99.,90.]
    b=prepare_features(d)
    pd.testing.assert_frame_equal(a.loc[a.month<=201903,list(NUMERIC)],b.loc[b.month<=201903,list(NUMERIC)])


def test_classification_preserves_boundary_and_missing():
    np.testing.assert_equal(classify([-.51,-.5,0.,.5,.51,np.nan]),[0.,1.,1.,1.,2.,np.nan])


def test_huber_reduces_influence_of_single_large_observation():
    x=np.ones((101,1)); y=np.r_[np.zeros(100),100.]; w=np.ones(101)
    assert abs(fit_change(x,y,w)[0]-100/101)<1e-9
    assert abs(fit_change(x,y,w,True)[0]-.01)<1e-5


def test_multinomial_probabilities_fit_known_order_and_sum_to_one():
    x=np.column_stack((np.ones(30),np.arange(30)/10-1.45)); y=np.repeat([0,1,2],10)
    b=fit_direction(x,y,np.ones(30)); p=direction_probabilities(x,b)
    np.testing.assert_allclose(p.sum(1),1.)
    assert p[0,0]>.8 and p[-1,2]>.8
