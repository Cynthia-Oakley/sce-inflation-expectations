"""Offline reference models; forecast functions receive released history only."""
from __future__ import annotations

import numpy as np

from .metrics import empirical, quantile


def ar1_forecast(history, horizon):
    y = np.asarray(history, float)
    if len(y) < 12 or horizon < 1 or not np.isfinite(y).all():
        raise ValueError('AR(1) requires at least 12 observations and positive horizon')
    design = np.column_stack((np.ones(len(y) - 1), y[:-1]))
    intercept, phi = np.linalg.lstsq(design, y[1:], rcond=None)[0]
    prediction = float(y[-1])
    for _ in range(horizon):
        prediction = float(intercept + phi * prediction)
    return prediction, {'intercept': float(intercept), 'phi': float(phi), 'n_pairs': len(y) - 1}


def arx_direct_forecast(training_features, training_targets, feature):
    x, y = np.asarray(training_features, float), np.asarray(training_targets, float)
    if len(y) < 12 or x.shape != (len(y), 2) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('ARX requires 12 released target/feature pairs')
    design = np.column_stack((np.ones(len(x)), x))
    coef = np.linalg.lstsq(design, y, rcond=None)[0]
    return float(np.r_[1., feature] @ coef), {'coefficients': coef.tolist(), 'n_pairs': len(y)}


def sticky_information_agent(history, *, update_probability=.25, n_agents=1300, seed=42):
    """Carroll-inspired structure, with SCE public signal rather than professional forecasts.

    Each release triggers an independent update for each archetype. All initialize
    at the first released headline. This is a reference assumption, not an estimate
    of actual household updating or a replication of Carroll's quarterly model.
    """
    y = np.asarray(history, float)
    if not len(y) or not np.isfinite(y).all() or not 0 <= update_probability <= 1 or n_agents < 1:
        raise ValueError('Invalid agent history/configuration')
    rng = np.random.default_rng(seed)
    beliefs = np.full(n_agents, y[0], dtype=float)
    for signal in y[1:]:
        update = rng.random(n_agents) < update_probability
        beliefs[update] = signal
    return quantile(beliefs, np.ones(n_agents), .5)


def conditional_donor_distribution(prior_values, prior_weights, prior_cells, target_cells,
                                   target_weights, *, minimum_donors=20):
    """Exact historical-donor mixture using current A-line population cell masses.

    Generates a distribution of means, not a full questionnaire or paired answers.
    Returns cell distributions for conditional evaluation. No target answers used.
    """
    values = np.asarray(prior_values, float)
    weights = np.asarray(prior_weights, float)
    cells = list(prior_cells)
    target = list(target_cells)
    tw = np.asarray(target_weights, float)
    if len(values) != len(weights) or len(values) != len(cells) or len(target) != len(tw):
        raise ValueError('Donor/population lengths differ')
    if not np.isfinite(tw).all() or np.any(tw <= 0):
        raise ValueError('Target population requires finite positive weights')
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    pooled_x, pooled_w, _ = empirical(values, weights)
    result_x, result_w, by_cell, fallbacks = [], [], {}, []
    for cell in sorted(set(target), key=str):
        mass = float(tw[np.array([c == cell for c in target])].sum() / tw.sum())
        mask = valid & np.array([c == cell for c in cells])
        if mask.sum() < minimum_donors:
            x, w = pooled_x, pooled_w
            fallbacks.append(cell)
        else:
            x, w = values[mask], weights[mask]
        normalized = w / w.sum()
        result_x.extend(x)
        result_w.extend(normalized * mass)
        by_cell[cell] = (x, normalized)
    return np.asarray(result_x), np.asarray(result_w), by_cell, fallbacks
