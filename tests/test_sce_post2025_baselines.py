import json
import numpy as np
import pytest
from studies.sce_inflation_expectations.evaluation.post2025_baselines import public_bins, baseline_metrics


def test_missing_truth_is_null_without_inventing_probabilities():
    row={f'Q9_bin{i}':float('nan') for i in range(1,11)}
    bins=public_bins(row)
    assert bins==[None]*10
    json.dumps(bins,allow_nan=False)


def test_baselines_use_matching_scorable_people():
    rows=[dict(real={'q9_mean':y},carry=x,design_survey_weight=1.) for y,x in [(1.,1.),(3.,2.),(None,50.)]]
    result=baseline_metrics(rows,'carry')
    assert result['person_months']==2
    assert result['personal_mae_pp']==pytest.approx(.5)
    assert result['w1_pp']==pytest.approx(.5)
