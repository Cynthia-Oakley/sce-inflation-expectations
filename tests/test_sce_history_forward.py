"""Known solutions for the new offline rule; no frozen scorer or API calls."""
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation'))
from history_forward import convex_weights, quantile


def test_known_interior_mixture():
    prior = np.array([1., 2., 3., 4.]); older = np.array([4., 1., 5., 2.]); sim = np.array([2., 6., 1., 3.])
    target = .3*prior+.3*older+.4*sim
    assert np.allclose(convex_weights(target, prior, older, sim, np.ones(4)), [.3, .4], atol=1e-10)


def test_no_useful_history_and_copy_solution():
    prior = np.array([1., 2., 4.]); sim = prior+1
    assert np.allclose(convex_weights(prior, prior, prior, sim, np.ones(3)), [0, 0])


def test_simplex_boundary_against_independent_optimizer():
    rng = np.random.default_rng(42)
    for _ in range(5):
        prior, older, sim, y = rng.normal(size=(4, 20)); w = rng.uniform(.1, 2, 20)
        x = np.column_stack((older-prior, sim-prior))
        loss = lambda c: np.dot(w, (y-prior-x@c)**2)
        actual = convex_weights(y, prior, older, sim, w)
        check = minimize(loss, [.2, .2], bounds=((0, 1), (0, 1)),
                         constraints={'type': 'ineq', 'fun': lambda c: 1-sum(c)},
                         method='SLSQP', options={'ftol': 1e-12})
        assert check.success and abs(loss(actual)-loss(check.x)) < 1e-8


def test_quantile_left_inverse_convention():
    assert quantile([0., 10.], [.5, .5], .5) == 0.
    assert quantile([8., 3., 5.], [.2, .6, .2], .5) == 3.
