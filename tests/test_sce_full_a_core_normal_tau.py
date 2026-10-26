import numpy as np
import pytest

from studies.sce_inflation_expectations.evaluation.full_a_core_normal_tau import kernel, masses, medians, pick
from studies.sce_inflation_expectations.experiments.full_a_core_normal import build_banks


def fixture():
    people = [dict(id=str(i), weight=1+i/10, entry='returner', education='a' if i<3 else 'b',
                   numeracy='low', age='middle', income='middle') for i in range(6)]
    selected = [dict(id=str(i), poststratified_weight=2+i/10) for i in (0, 1, 3)]
    answers = [dict(id=str(i), q9_bins=[0]*5+[100]+[0]*4,
                    q9_mean=float(i), q9_iqr=1, q8=float(i)) for i in (0, 1, 3)]
    return dict(people=people, selected=selected, answers=answers)


def test_curve_matches_original_expansion_and_infinite_limit():
    payload = fixture(); curve = kernel(payload)
    taus = [0, .001, .5, 8, 24, 10000]
    for tau, mass in zip(taus, masses(curve, taus)):
        bank = build_banks(payload['people'], payload['selected'], payload['answers'], tau)['q9']
        assert np.allclose(mass, bank.atom_weights(), atol=1e-12)
    assert np.allclose(masses(curve, [np.inf]), masses(curve, [1e12]), atol=1e-10)


def test_known_weighted_median_and_smallest_training_tie():
    curve = dict(values=np.array([1., 2., 10.]), base=np.array([.3, .4, .3]),
                 delta=np.array([[.5, -.4, -.1]]), ess=np.array([2.]))
    assert medians(curve, [0, 8]).tolist() == [2., 1.]
    assert pick(np.array([8., 0., 24.]), np.array([.3, .3, .4])) == (0., .3)


@pytest.mark.parametrize('tau', [-1, np.nan, -np.inf])
def test_invalid_strength_is_rejected(tau):
    with pytest.raises(ValueError):
        masses(kernel(fixture()), [tau])
