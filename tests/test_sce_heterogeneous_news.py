"""Meaningful boundaries for allocation without questionnaire answers."""
import numpy as np
import pytest

from studies.sce_inflation_expectations.evaluation.heterogeneous_news import allocate, level_arm, stable_uniform


def test_quota_average_and_ordering_from_known_attention():
    people = [str(i) for i in range(96)]
    p = np.zeros((96, 6))
    p[:48, 0] = 1
    p[48:76, 2] = 1
    p[76:, 5] = 1
    result = allocate(people, p, 123)
    assert all(result[str(i)] == 3 for i in range(48))
    assert all(result[str(i)] == 8 for i in range(48, 76))
    assert all(result[str(i)] == 20 for i in range(76, 96))
    assert sum(result.values())/96 == 8


def test_stable_person_draw_and_source_order_invariance():
    people = [str(i) for i in range(96)]
    p = np.full((96, 6), 1/6)
    assert allocate(people, p, 19) == allocate(people[::-1], p[::-1], 19)
    assert stable_uniform(19, '7', 'class') == stable_uniform(19, '7', 'class')
    assert 0 <= stable_uniform(19, '7', 'class') < 1
    with pytest.raises(ValueError):
        allocate(people, p*2, 19)
    with pytest.raises(ValueError):
        level_arm(40, 'complete')
