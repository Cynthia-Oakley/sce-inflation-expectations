"""Sampling mass and identity guarantees for the opt-in fine-grid adapter."""
from collections import defaultdict
import math

import pytest

from studies.sce_inflation_expectations.population.grid_sampling import plan_core, draw_core


def frame():
    return ([{'id': f'a{i}', 'cell': 'common', 'weight': float(i+1)} for i in range(20)]
            + [{'id': f'b{i}', 'cell': 'rare', 'weight': 1.} for i in range(3)])


def test_long_tail_is_oversampled_without_duplicate_people():
    rows = frame(); p = plan_core(rows, 10, minimum=3)
    pick = draw_core(rows, p, seed=42, month=202501)
    assert p['cells']['rare']['selected_n'] == 3
    assert p['cells']['rare']['inclusion_probability'] == 1
    assert len(pick) == len({r['id'] for r in pick}) == 10


def test_exact_population_cell_mass_despite_oversampling_and_unequal_weights():
    rows = frame(); p = plan_core(rows, 10, minimum=3)
    pick = draw_core(rows, p, seed=42, month=202501)
    mass = defaultdict(float)
    for r in pick:
        mass[r['cell']] += r['poststratified_weight']
        assert math.isclose(r['design_weight'], r['weight']/r['inclusion_probability'])
    assert math.isclose(mass['common'], 210.)
    assert math.isclose(mass['rare'], 3.)
    # One rare group response must not receive its 30% Core headcount share.
    assert math.isclose(mass['rare']/sum(mass.values()), 3/213)


def test_draw_is_reproducible_and_month_seed_changes_common_members():
    rows = frame(); p = plan_core(rows, 10, minimum=3)
    a = draw_core(rows, p, seed=42, month=202501)
    assert a == draw_core(rows, p, seed=42, month=202501)
    assert {r['id'] for r in a} != {r['id'] for r in draw_core(rows, p, seed=43, month=202501)}


def test_infeasible_floors_fail_instead_of_dropping_rare_cells():
    with pytest.raises(ValueError, match='minimums'):
        plan_core(frame(), 4, minimum=3)


def test_missing_weights_are_not_replaced_by_one():
    with pytest.raises(ValueError, match='weights'):
        plan_core([{'id': 'x', 'cell': 'unknown', 'weight': None}], 1, minimum=1)


def test_duplicate_or_changed_frame_is_rejected():
    rows = frame()
    with pytest.raises(ValueError, match='Duplicate'):
        plan_core(rows+[rows[0]], 10, minimum=3)
    p = plan_core(rows, 10, minimum=3)
    changed = [dict(r) for r in rows]; changed[0]['weight'] += 1
    with pytest.raises(ValueError, match='counts or population weights'):
        draw_core(changed, p, seed=42, month=202501)


def test_unknown_cell_is_kept_and_census_draw_restores_every_original_weight():
    rows = frame()+[{'id': 'u', 'cell': 'unknown', 'weight': 5.}]
    p = plan_core(rows, len(rows), minimum=3)
    pick = draw_core(rows, p, seed=42, month=202501)
    assert 'unknown' in p['cells']
    assert all(r['inclusion_probability'] == 1 and r['poststratified_weight'] == r['weight'] for r in pick)


def test_modified_plan_cannot_silently_exceed_budget():
    p = plan_core(frame(), 10, minimum=3); p['budget'] = 9
    with pytest.raises(ValueError, match='budget'):
        draw_core(frame(), p, seed=42, month=202501)
