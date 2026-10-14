import numpy as np
import pytest
import pandas as pd
from scipy.stats import wasserstein_distance
from studies.sce_inflation_expectations.evaluation.expansion_diagnostic import covariance_parts, sample_metrics_sorted, valid_population_pools


def test_common_answer_cancels_person_variance():
    p=np.array([1.,3.,5.,9.])
    r=covariance_parts(p,np.full(4,4.))
    assert r['current_variance']==0
    assert r['descriptive_retention_slope']==0
    assert r['update_variance']==r['previous_variance']
    assert r['twice_previous_update_covariance']==-2*r['previous_variance']
    assert abs(r['identity_error'])<1e-12


def test_projection_identity_for_nontrivial_updates():
    r=covariance_parts([1,2,4,8],[2,3,9,6])
    assert abs(r['identity_error'])<1e-12
    assert abs(r['projection_identity_error'])<1e-12


def test_previous_weight_does_not_delete_valid_past_answer():
    rows=[]
    for date,weight in [(202101,0.),(202102,2.)]:
        rows.append(dict(userid=1,date=date,weight=weight,Q9_mean=3.,
            **{f'Q9_bin{i}':100. if i==4 else 0. for i in range(1,11)}))
    full,pool=valid_population_pools(pd.DataFrame(rows))
    assert len(full)==1 and len(pool)==1
    assert int(pool.iloc[0].previous_date)==202101


@pytest.mark.parametrize('weighted',[False,True])
def test_sampling_w1_matches_independent_scipy_with_ties(weighted):
    x=np.array([-2.,0.,0.,3.,7.]); w=np.array([1.,2.,5.,1.,3.]); ix=np.array([0,2,4])
    r=sample_metrics_sorted(x,w,ix,weighted)
    ww=w if weighted else np.ones(5)
    assert r['w1_pp']==pytest.approx(wasserstein_distance(x[ix],x,ww[ix],ww))
    whole=sample_metrics_sorted(x,w,np.arange(5),weighted)
    assert all(v==0 for v in whole.values())
