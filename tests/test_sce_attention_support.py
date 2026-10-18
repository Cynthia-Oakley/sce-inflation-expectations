import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.evaluation.attention_support import (
    harmonize, probability_scores, support_summary, fit_probabilities,
)


def test_probability_scores_use_order_and_known_values():
    perfect = probability_scores([0, 2], [[1, 0, 0], [0, 0, 1]], True)
    assert perfect == {'log_loss': 0., 'brier': 0., 'accuracy': 1., 'rps': 0.}
    near = probability_scores([0], [[0, 1, 0]], True)
    far = probability_scores([0], [[0, 0, 1]], True)
    assert near['brier'] == far['brier'] == 2.
    assert near['rps'] == .5 and far['rps'] == 1.
    with pytest.raises(ValueError):
        probability_scores([0], [[.2, .2]])


def test_mapping_preserves_boundaries_and_missing_income():
    frame = pd.DataFrame({'age': [39.5, 59.5, 69.5], 'education': [2, 4, 5],
                          'income': [37500, 87500, np.nan], 'region': [1, 2, 4]})
    mapped = harmonize(frame)
    assert mapped.age_group.tolist() == ['Under 40', '40 to 60', 'Over 60']
    assert mapped.education_group.tolist() == ['high_school', 'some_college', 'college']
    assert mapped.household_income_band.tolist() == ['under_50k', '50k_to_100k', 'missing']
    assert mapped.region.tolist() == ['Northeast', 'Midwest', 'West']


def test_support_does_not_invent_missing_donor_and_uses_weights():
    profile = dict(age_group='Under 40', education_group='college',
                   household_income_band='missing', region='West')
    donors = pd.DataFrame([profile]*12)
    result = support_summary(donors, [profile, {**profile, 'region': 'South'}], [1, 3])
    assert result['weighted_share_no_donor'] == .75
    assert result['weighted_share_fewer_than_10_donors'] == .75


def test_intercept_only_fit_recovers_training_prevalence():
    train = pd.DataFrame(index=range(10))
    p = fit_probabilities(train, pd.DataFrame(index=range(2)), np.array([0]*7+[1]*3), 2, [])
    assert np.allclose(p, [[.7, .3]]*2, atol=1e-6)
