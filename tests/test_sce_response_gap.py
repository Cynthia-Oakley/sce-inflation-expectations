"""Independent small-number checks for offline response gap diagnostics."""
from copy import deepcopy

import pytest

from studies.sce_inflation_expectations.evaluation import response_gap as gap


def case(uid, repeat, prior=2., truth=2., model=2., weight=1.):
    return {'month': 202003, 'userid': uid, 'agent_id': f'test_{uid}', 'repeat': repeat,
            'profile': {'age_group': 'young'}, 'stratum': 'young',
            'survey_weight': weight, 'inclusion_probability': .5, 'design_survey_weight': 2 * weight,
            'real': {'q9_mean': truth, 'q9_iqr': 1., 'previous_q9_mean': prior},
            'baselines': {'copy_previous': prior},
            'arms': {'reference': {'mean': model, 'iqr': 1., 'validation_status': 'valid', 'scorer_status': 'ok'}}}


def test_weighted_median_and_w1_have_hand_computed_expectations():
    # CDF puts 20%, then 60%, then 100% at 0/10/20. Median is 10,
    # even though the unweighted median of the repeated support differs.
    assert gap.quantile([0., 10., 20.], [1., 2., 2.], .5) == 10.
    assert gap.quantile([1., 9.], [1., 1.], .5) == 1.  # Left-CDF boundary.
    # Translating every mass by 3 gives an exact W1 of 3.
    assert gap.wasserstein1([0, 10], [1, 3], [3, 13], [1, 3]) == pytest.approx(3.)
    assert gap.ess([1., 2., 2.]) == pytest.approx(25 / 9)


@pytest.mark.parametrize('change,threshold,expected', [
    (-.5, .5, 'stable'), (.5, .5, 'stable'), (0., .25, 'stable'),
    (-.50001, .5, 'down'), (.50001, .5, 'up'), (.75, 1., 'stable')])
def test_stability_and_direction_boundaries(change, threshold, expected):
    assert gap.direction(change, threshold) == expected


def test_weighted_mse_identity_is_not_absolute_error_decomposition():
    # Errors 1 and -3 with weights 3:1: bias 0, MSE=variance=3.
    result = gap.mse_identity([3., -1.], [2., 2.], [3., 1.])
    assert result['individual_mean_mse_pp2'] == pytest.approx(3.)
    assert result['mean_error_squared_pp2'] == pytest.approx(0.)
    assert result['centered_error_variance_pp2'] == pytest.approx(3.)
    assert result['mse_identity_residual_pp2'] == pytest.approx(0.)
    # Errors 1 and 3, weights 1:3: E[e]=2.5, E[e²]=7, Var(e)=.75.
    other = gap.mse_identity([1., 3.], [0., 0.], [1., 3.])
    assert other['individual_mean_mse_pp2'] == pytest.approx(7.)
    assert other['mean_error_squared_pp2'] == pytest.approx(6.25)
    assert other['centered_error_variance_pp2'] == pytest.approx(.75)


def test_person_pair_normalization_missingness_and_duplicate_rejection():
    cases = [case(uid, rep, weight=uid) for uid in (1, 2) for rep in (1, 2)]
    rows = gap.prepare_pairs(cases)
    assert len(rows) == 2
    assert [r['normalized_month_weight'] for r in rows] == pytest.approx([1 / 3, 2 / 3])
    bad = deepcopy(cases)
    bad[3]['arms']['reference']['iqr'] = None
    rows = gap.prepare_pairs(bad)
    assert rows[0]['normalized_month_weight'] == 1.
    assert not rows[1]['paired_eligible'] and rows[1]['invalid_model_repeats'] == [2]
    with pytest.raises(ValueError, match='Duplicate person-month-repeat'):
        gap.prepare_pairs(cases + [cases[0]])
    with pytest.raises(ValueError, match='exactly two'):
        gap.prepare_pairs(cases[:-1])
    bad = deepcopy(cases)
    bad[1]['real']['q9_mean'] = 9.
    with pytest.raises(ValueError, match='Inconsistent paired'):
        gap.prepare_pairs(bad)


def test_primary_repeat_mae_is_not_mae_of_averaged_prediction():
    # Each person has model 0/4 around truth 2; each repeat MAE=2.
    cases = [case(uid, rep, model=0. if rep == 1 else 4.) for uid in range(10) for rep in (1, 2)]
    rows = gap.prepare_pairs(cases)
    summary = gap.summarize_slice(rows)
    assert summary['n'] == 10
    assert summary['model_average_of_repeat_metrics']['q9_center_mae_pp'] == 2.
    assert summary['model_average_of_repeat_metrics']['individual_density_mean_mae_pp'] == 2.
    assert summary['copy_previous']['individual_density_mean_mae_pp'] == 0.
    assert gap.summarize_slice(rows[:9]) == {'n_assigned': 9, 'n': 9, 'ess': pytest.approx(9.), 'suppressed': True}


def test_update_rates_and_copy_errors_have_independent_count_answers():
    # 10 equal-weight cases: 4 stable truth / 3 up / 3 down.
    # Model: first 4 move up 2, next 3 reverse down 2, final 3 copy (stable).
    pairs = []
    for uid in range(10):
        dy = 0. if uid < 4 else 1. if uid < 7 else -1.
        dm = 2. if uid < 4 else -2. if uid < 7 else 0.
        pairs.extend(case(uid, rep, truth=2. + dy, model=2. + dm) for rep in (1, 2))
    result = gap.update_cell(gap.prepare_pairs(pairs), .5)['average_of_repeat_metrics']
    assert result['model_stable_share'] == pytest.approx(.3)
    assert result['model_reverse_direction_share'] == pytest.approx(.3)
    assert result['model_excessive_movement_share'] == pytest.approx(.7)
    assert result['model_moves_while_truth_stable_share'] == pytest.approx(.4)
    assert result['copy_person_mae_pp'] == pytest.approx(.6)
    assert result['model_person_mae_pp'] == pytest.approx(2.)  # .4*2+.3*3+.3*1
    assert result['model_worse_than_copy_share'] == pytest.approx(.7)
    assert result['model_ties_copy_share'] == pytest.approx(.3)
    assert sum(v for k, v in result.items() if k.startswith('truth_') and '__model_' in k) == pytest.approx(1.)


def test_prior_band_boundaries():
    assert [gap.prior_band(v) for v in (1.99, 2., 3.99, 4., 7.99, 8.)] == [
        'below_2', '2_to_below_4', '2_to_below_4', '4_to_below_8', '4_to_below_8', '8_or_above']


def test_month_demeaned_regression_uses_person_average_only_here():
    cases = []
    # prior=[1,3], truth=[5,9] gives slope2; repeat means give [10,11], slope.5.
    for uid, prior, truth, model in ((1, 1., 5., 10.), (2, 3., 9., 11.)):
        cases.extend(case(uid, rep, prior=prior, truth=truth, model=model + (-2. if rep == 1 else 2.)) for rep in (1, 2))
    result = gap._regression_cell(gap.prepare_pairs(cases))
    assert result['truth_current_on_prior_slope'] == pytest.approx(2.)
    assert result['model_two_repeat_mean_current_on_prior_slope'] == pytest.approx(.5)
    assert result['truth_delta_on_prior_slope'] == pytest.approx(1.)
    assert result['model_to_truth_person_sd_ratio'] == pytest.approx(.25)


def test_low_ess_is_warned_without_replacing_n_suppression():
    # n=10 with one large weight has ESS near 1 and remains reportable.
    cases = [case(uid, rep, weight=100. if uid == 0 else 1.) for uid in range(10) for rep in (1, 2)]
    cell = gap.summarize_slice(gap.prepare_pairs(cases))
    assert cell['n'] == 10 and cell['ess'] < 10 and not cell['suppressed']
    fake = {'monthly': [dict(month=202003, **cell)], 'demographics': {'monthly': {}},
            'prior_levels': {'monthly': {}}, 'updates': {'by_threshold': {}}, 'regressions': {'monthly': []}}
    audit = gap.support_audit(fake)
    assert audit['n_weak_support_cells_with_reported_metrics'] == 1
    assert audit['cells'][0]['weak_support_ess_below_10']
    assert not audit['cells'][0]['metrics_suppressed_n_below_10']
