"""Independent adapter checks: field origin, identity, mass and heldout evidence."""
import math
import pytest
from studies.sce_inflation_expectations.experiments.full_a_core_normal import (
    model_record, build_banks, holdout_split, holdout_weights,
)
from studies.sce_inflation_expectations.evaluation.metrics import quantile


def person(uid, age='under_40', weight=1.):
    return dict(id=uid, weight=weight, entry='returner', education='college',
                numeracy='High', age=age, income='under_50k')


def record(uid, value):
    return dict(id=uid, q9_bins=[0., 0., 0., 0., 100., 0., 0., 0., 0., 0.],
                q9_mean=value, q9_iqr=1., q8=value)


def test_prior_retained_and_unfit_fields_never_become_donors():
    action = dict(agent_id='a', field_updated={'q8': True, 'q9': False},
                  effective_q8=2., effective_q9_bins=None)
    row, q = model_record(action, {})
    assert row['q8'] == 2. and row['q9_mean'] is None
    assert q['q9_not_model_output'] == 1
    action.update(field_updated={'q8': True, 'q9': True}, effective_q9_bins=record('a', 2)['q9_bins'])
    row, q = model_record(action, {tuple(action['effective_q9_bins']): {'mean': None, 'iqr': None}})
    assert row['q9_bins'] == [] and row['q8'] == 2.
    assert q['q9_unfittable_model_output'] == 1
    with pytest.raises(ValueError, match='refitting is forbidden'):
        model_record(action, {})


def test_finite_mass_uses_raw_person_weight_not_design_weight_again():
    population = [person('a', weight=5), person('b', 'over_60', weight=1),
                  person('n1', weight=2), person('n2', 'over_60', weight=4)]
    selected = [dict(id='a', poststratified_weight=100), dict(id='b', poststratified_weight=100)]
    bank = build_banks(population, selected, [record('a', 2), record('b', 8)], 1)['q9']
    # Both cells have one local and one parent atom: each Normal splits 50/50.
    assert bank.atom_weights().tolist() == [8., 4.]
    assert quantile([2., 8.], bank.atom_weights(), .5) == 2.
    assert math.isclose(sum(bank.atom_weights()), 12.)


def test_population_outcome_and_extra_model_fields_are_rejected():
    people = [{**person('a'), 'truth': 3}]
    with pytest.raises(ValueError, match='whitelists'):
        build_banks(people, [{'id': 'a', 'poststratified_weight': 1}], [record('a', 2)], 0)
    with pytest.raises(ValueError, match='whitelists'):
        build_banks([person('a')], [{'id': 'a', 'poststratified_weight': 1}],
                    [{**record('a', 2), 'real_answer': 3}], 0)


def test_holdout_is_deterministic_disjoint_and_preserves_training_group_mass():
    people = [person(str(i), weight=i + 1) for i in range(10)] + [person('rare', 'over_60')]
    selected = [dict(id=r['id'], poststratified_weight=r['weight']) for r in people]
    answers = [record(r['id'], i + 1) for i, r in enumerate(people)]
    a, held = holdout_split(people, selected, answers, seed=7, month='202001', fraction=.2)
    b, held_again = holdout_split(people, selected, answers, seed=7, month='202001', fraction=.2)
    assert (a, held) == (b, held_again)
    assert len(held) == 2 and 'rare' not in held
    assert not set(held) & {r['id'] for r in a}
    assert math.isclose(sum(r['poststratified_weight'] for r in a if r['id'] != 'rare'), 55.)
    assert next(r['poststratified_weight'] for r in a if r['id'] == 'rare') == 1.
    bank = build_banks(people, a, [r for r in answers if r['id'] not in held], 8)['q9']
    assert not set(held) & set(bank.donor_ids)


def test_heldout_weights_restore_group_masses_not_unequal_holdout_fractions():
    people = [person(str(i)) for i in range(10)] + [person('b1', 'over_60'), person('b2', 'over_60')]
    selected = [{'id': r['id'], 'poststratified_weight':1.} for r in people]
    records = [record(r['id'], 2.) for r in people]
    w, coverage = holdout_weights(people, selected, records, ['0', '1', 'b1'])
    assert w == {'0': 5., '1': 5., 'b1': 2.}
    assert coverage['represented_valid_Core_mass_fraction'] == 1.


def test_invalid_q9_keeps_independent_q8_support():
    r = record('a', 2); r.update(q9_bins=[], q9_mean=None, q9_iqr=None)
    banks = build_banks([person('a'), person('b')],
                       [{'id':'a','poststratified_weight':1}, {'id':'b','poststratified_weight':1}],
                       [r, record('b', 8)], 24)
    assert len(banks['q9'].answers) == 1 and len(banks['q8'].answers) == 2
    assert sum(banks['q9'].atom_weights()) == 2.
