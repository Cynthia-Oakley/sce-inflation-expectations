from copy import deepcopy
import numpy as np
import pytest
from studies.sce_inflation_expectations.experiments.frozen_batch import effective_temperature
from studies.sce_inflation_expectations.evaluation.temperature import variance_components


def test_old_protocol_temperature_unchanged():
    assert effective_temperature({'temperature': .5}, {'arm': 'anything'}) == .5


def test_temperature_arms_are_explicit_and_bounded():
    p = {'mechanism': 'temperature_sensitivity', 'arms': ['baseline', 'high'],
         'arm_temperatures': {'baseline': .5, 'high': 1.0}}
    assert effective_temperature(p, {'arm': 'high'}) == 1.0
    for value in [True, float('nan'), -1, 3]:
        q = deepcopy(p); q['arm_temperatures']['high'] = value
        with pytest.raises(ValueError): effective_temperature(q, {'arm': 'high'})
    q = deepcopy(p); q['mechanism'] = 'another_mechanism'
    with pytest.raises(ValueError): effective_temperature(q, {'arm': 'high'})


def test_repeat_noise_is_not_persistent_heterogeneity():
    same_person_means = np.array([[0, 2, 0, 2], [2, 0, 2, 0], [0, 2, 2, 0]])
    noise = variance_components(same_person_means)
    assert noise['pooled_population_variance_pp2'] > 0
    assert noise['between_person_repeat_mean_variance_pp2'] == 0
    assert noise['noise_adjusted_between_variance_pp2'] < 0  # Do not silently clip.
    stable = variance_components(np.array([[0]*4, [2]*4, [4]*4]))
    assert stable['within_person_repeat_variance_pp2'] == 0
    assert stable['noise_adjusted_between_variance_pp2'] > 0
    for result in [noise, stable]:
        assert result['pooled_population_variance_pp2'] == pytest.approx(
            result['between_means_population_variance_pp2']+result['within_person_population_variance_pp2'])
