import pytest
from studies.sce_inflation_expectations.model_comparison_analysis import comparison_metrics


def test_paired_common_mask_and_error_direction():
    rows=[{'real':1.,'deepseek_reference':0.,'llama':1.},
          {'real':3.,'deepseek_reference':1.,'llama':5.},
          {'real':100.,'deepseek_reference':None,'llama':100.}]
    r=comparison_metrics(rows,['deepseek_reference','llama'])
    assert r['n_common']==2 and r['n_excluded']==1
    assert r['matched_real']['median']==2
    assert r['arms']['deepseek_reference']['individual_mae_pp']==1.5
    assert r['arms']['llama']['individual_mae_pp']==1
    assert r['paired_mae_changes_vs_deepseek_pp']['llama']==-.5
    assert r['arms']['llama']['mean_bias_pp']==1
    assert r['arms']['llama']['distribution']['iqr']==2
    assert r['arms']['llama']['wasserstein_1_pp']==1


def test_no_finite_common_cases_is_not_success():
    with pytest.raises(ValueError,match='no common'):
        comparison_metrics([{'real':float('nan'),'model':1.}],['model'])
