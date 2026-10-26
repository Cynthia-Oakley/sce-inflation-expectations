import pytest
from scripts.read_sce_post2025_validation import national_cells


def test_national_comparison_uses_predicted_weighted_center_directly():
    r={'cells':[dict(month=202504,repeat=1,n=2,ess=1.2,
        arms={'model':dict(predicted_center_pp=5.,truth_center_pp=4.)})]}
    truth=[dict(month=202504,official_national=dict(q9_headline_pp=3.,center_mae_pp=.1),
        full_wave=dict(frozen_score_median_pp=3.5))]
    row=national_cells(r,truth,'model')[0]
    assert row['model_center_pp']==5.
    assert row['model_national_abs_error_pp']==pytest.approx(2.)
    assert row['model_full_wave_abs_error_pp']==pytest.approx(1.5)
