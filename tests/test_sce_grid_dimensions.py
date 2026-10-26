"""Statistical invariants for the evaluation-only grid selection analysis."""
import numpy as np
import pandas as pd

from studies.sce_inflation_expectations.evaluation.grid_dimension_selection import (
    bootstrap_indices, domain_losses, ess, residualize, select_development,
    weighted_cramers_v,
)
from studies.sce_inflation_expectations.evaluation.grid_joint_holdout import empirical_joint_law


def test_cramers_v_ignores_survey_weight_scale():
    a = np.array(['a', 'a', 'b', 'b'])
    b = np.array(['c', 'd', 'c', 'd'])
    w = np.array([1., 2., 3., 7.])
    assert np.isclose(weighted_cramers_v(a, b, w), weighted_cramers_v(a, b, 100*w))


def test_cramers_v_known_independence_and_duplicate():
    a = np.array(['a', 'a', 'b', 'b']); w = np.ones(4)
    assert np.isclose(weighted_cramers_v(a, np.array(['c', 'd', 'c', 'd']), w), 0)
    assert np.isclose(weighted_cramers_v(a, a, w), 1)


def test_weighted_month_absorption():
    y = np.array([1., 5., 2., 9.]); w = np.array([2., 1., 1., 3.]); m = np.array([1, 1, 2, 2])
    r = residualize(y, w, m).ravel()
    for k in [1, 2]:
        assert np.isclose(np.sum(w[m == k]*r[m == k]), 0)


def test_within_month_score_does_not_claim_common_level_accuracy():
    y = np.array([[0., 1., 0., 0., 0.], [1., 2., 1., 1., 1.],
                  [2., 4., 1., 1., 1.], [3., 5., 0., 0., 1.]])
    # The distribution domain expects nine fixed CDF thresholds.
    y = np.column_stack([y[:, :3], np.tile(y[:, 3:4], (1, 9))])
    m = np.array([1, 1, 2, 2]); w = np.ones(4)
    _, a = domain_losses(y, y, w, m)
    _, b = domain_losses(y, y+100, w, m)
    assert np.allclose(a, 0)
    assert np.allclose(b, 0)


def test_ess_detects_weight_concentration():
    assert ess([1., 1., 1.]) == 3
    assert ess([1., 1., 100.]) < 1.05


def test_bootstrap_keeps_calendar_blocks_and_is_deterministic():
    a = bootstrap_indices(48, draws=2); b = bootstrap_indices(48, draws=2)
    for x, y in zip(a, b):
        assert np.array_equal(x, y)
        for block in x.reshape(-1, 6):
            assert np.array_equal(block, np.arange(block[0], block[0]+6))


def test_selection_prefers_small_grid_only_within_one_se_and_support():
    models = [{'name': 'small', 'role': 'candidate', 'fields': ['a', 'b', 'c'], 'cartesian_cells': 12},
              {'name': 'large', 'role': 'candidate', 'fields': ['a', 'b', 'c', 'd'], 'cartesian_cells': 36},
              {'name': 'sparse', 'role': 'candidate', 'fields': ['a', 'b', 'z'], 'cartesian_cells': 8}]
    monthly = np.repeat(np.linspace(.5, .9, 48)[:, None], 4, axis=1)
    cv = {k: {'composite_gain': v, 'monthly_domain_losses': monthly.tolist()}
          for k, v in [('small', .20), ('large', .201), ('sparse', .50)]}
    support = {k: {'development': {'mean_frame_supported_mass': v}}
               for k, v in [('small', .95), ('large', .95), ('sparse', .80)]}
    result = select_development(models, cv, support)
    assert result['recommended'] == 'small'
    assert result['best_predictive'] == 'large'


def test_selection_reports_no_supported_grid():
    models = [{'name': 'a', 'role': 'candidate', 'fields': ['x', 'y', 'z'], 'cartesian_cells': 18}]
    result = select_development(models, {}, {'a': {'development': {'mean_frame_supported_mass': .8}}})
    assert result['recommended'] is None


def test_joint_law_keeps_disjoint_parent_and_local_mass():
    p, atoms, missing, prior = empirical_joint_law(['a','a','b'], ['a'], [1,1,2], [1], tau=2)
    assert np.allclose(p, [[.25,.25,.5]])
    assert np.allclose(atoms,p[0])
    assert missing == 0
    assert prior == .5


def test_joint_law_falls_back_without_inventing_new_answer_atoms():
    p, atoms, missing, prior = empirical_joint_law(['a','b'], ['c'], [1,3], [2], tau=0)
    assert np.allclose(atoms,[.25,.75])
    assert missing == 1 and prior == 1


def test_joint_law_integral_matches_population_weighted_conditional_expectation():
    p, atoms, _, _ = empirical_joint_law(['a','a','b'], ['a','b','c'], [1,2,1], [2,1,3], tau=8)
    values=np.array([1.,5.,20.])
    assert np.isclose(atoms@values, np.average(p@values, weights=[2,1,3]))
    assert np.isclose(atoms.sum(),1)
