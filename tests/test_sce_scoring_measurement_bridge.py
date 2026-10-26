import numpy as np
import pytest
from studies.sce_inflation_expectations.evaluation.scoring_measurement_bridge import midcdf_quantile,signed_decomposition


def test_midcdf_groups_ties_and_is_invariant_to_split_rows():
    assert midcdf_quantile([0,10],[2,2],.5)==5
    assert midcdf_quantile([0,0,10],[1,1,2],.5)==5
    assert midcdf_quantile([0,10],[2,2],0)==0
    assert midcdf_quantile([0,10],[2,2],1)==10


def test_known_official_appendix_midpoint_interpolation():
    # mid-CDF at x=0 is .2 and at x=10 is .7, so p=.5 is 6.
    assert np.isclose(midcdf_quantile([0,10],[.4,.6],.5),6)
    with pytest.raises(ValueError):midcdf_quantile([1],[1],1.1)


def test_error_identity_allows_measurement_to_reduce_absolute_error():
    r=signed_decomposition([4,4],[5,5],[4.5,4.5])
    assert r['total']['mae_pp']==.5
    assert r['common_score_target']['mae_pp']==1
    assert r['net_mae_change_when_using_official_target_pp']==-.5
    assert abs(r['mse_identity']['identity_residual'])<1e-12
