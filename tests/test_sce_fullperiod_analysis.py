import numpy as np
import pytest

from studies.sce_inflation_expectations.evaluation.fullperiod_analysis import variance_parts, wls, macro_scope, averages


def test_weighted_variance_between_within_identity_has_known_components():
    result=variance_parts([0,2,10,12],[1,1,1,1],['a','a','b','b'])
    assert result==dict(total_pp_squared=26.,between_pp_squared=25.,within_pp_squared=1.)
    weighted=variance_parts([0,2,10,12],[1,2,3,4],['a','a','b','b'])
    assert weighted['total_pp_squared']==pytest.approx(weighted['between_pp_squared']+weighted['within_pp_squared'])


def test_wls_matches_exact_linear_relationship_and_does_not_multiply_people():
    x=np.column_stack([np.ones(4),[0.,1.,2.,3.]])
    stats,b,residual=wls(x,np.array([1.,3.,5.,7.]),np.array([.1,.2,.3,.4]))
    assert b==pytest.approx([1.,2.]) and stats['r2']==pytest.approx(1.)
    assert np.max(abs(residual))<1e-12 and stats['rank']==2


def test_paired_macro_interval_uses_matched_errors_with_known_difference():
    rows=[dict(sim_pp=1.,truth_pp=0.,anchor_pp=2.),dict(sim_pp=-1.,truth_pp=0.,anchor_pp=-2.)]
    result=macro_scope(rows)
    assert result['model']['mae_pp']==1 and result['persistence']['mae_pp']==2
    assert result['model_win_months']==2
    assert result['paired_mae']['interval_95']==pytest.approx([-1.,-1.])


def test_sparse_means_never_replace_missing_metrics_with_zero():
    assert averages([dict(x=None),dict(x=2)],['x'])==dict(x=2.)
    assert averages([dict(x=None)],['x'])==dict(x=None)
