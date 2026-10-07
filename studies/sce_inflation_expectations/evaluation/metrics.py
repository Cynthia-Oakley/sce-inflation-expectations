"""Common evaluation on weighted empirical distributions; values use percent units."""
from __future__ import annotations

import numpy as np


def empirical(values, weights=None):
    x = np.asarray(values, dtype=float)
    w = np.ones(len(x)) if weights is None else np.asarray(weights, dtype=float)
    if x.ndim != 1 or w.shape != x.shape:
        raise ValueError('Expected equally sized one-dimensional values and weights')
    if np.any(np.isfinite(w) & (w < 0)):
        raise ValueError('Negative survey weights are invalid')
    valid = np.isfinite(x) & np.isfinite(w) & (w > 0)
    if not valid.any():
        raise ValueError('No positive-weight finite observations')
    order = np.argsort(x[valid], kind='stable')
    return x[valid][order], w[valid][order], int((~valid).sum())


def quantile(values, weights, probability):
    if not 0 <= probability <= 1:
        raise ValueError('Quantile probability must lie in [0, 1]')
    x, w, _ = empirical(values, weights)
    index = np.searchsorted(np.cumsum(w), probability * w.sum(), side='left')
    return float(x[min(index, len(x) - 1)])


def distribution_summary(values, weights=None):
    x, w, excluded = empirical(values, weights)
    median = quantile(x, w, .5)
    q25, q75 = quantile(x, w, .25), quantile(x, w, .75)
    mean = float(np.average(x, weights=w))
    return dict(n_valid=len(x), n_excluded=excluded, weight_sum=float(w.sum()),
                ess=float(w.sum() ** 2 / (w @ w)), median_pp=median, mean_pp=mean,
                q25_pp=q25, q75_pp=q75, iqr_pp=q75 - q25,
                std_pp=float(np.sqrt(np.average((x - mean) ** 2, weights=w))),
                share_below_zero=float(w[x < 0].sum() / w.sum()),
                share_above_eight=float(w[x > 8].sum() / w.sum()))


def wasserstein1(left, left_weights, right, right_weights):
    """Exact integral of absolute empirical CDF difference; unequal n/weights allowed."""
    x, wx, _ = empirical(left, left_weights)
    y, wy, _ = empirical(right, right_weights)
    support = np.unique(np.concatenate((x, y)))
    cx = np.concatenate(([0.], np.cumsum(wx) / wx.sum()))
    cy = np.concatenate(([0.], np.cumsum(wy) / wy.sum()))
    ix = np.searchsorted(x, support[:-1], side='right')
    iy = np.searchsorted(y, support[:-1], side='right')
    return float(np.sum(np.abs(cx[ix] - cy[iy]) * np.diff(support)))


def compare_distributions(simulated, sim_weights, observed, obs_weights):
    sim = distribution_summary(simulated, sim_weights)
    obs = distribution_summary(observed, obs_weights)
    sx, sw, _ = empirical(simulated, sim_weights)
    ox, ow, _ = empirical(observed, obs_weights)
    return dict(simulated=sim, observed=obs,
                w1_pp=wasserstein1(sx, sw, ox, ow),
                centered_w1_pp=wasserstein1(sx - sim['median_pp'], sw,
                                           ox - obs['median_pp'], ow),
                median_bias_pp=sim['median_pp'] - obs['median_pp'],
                median_error_pp=abs(sim['median_pp'] - obs['median_pp']),
                iqr_error_pp=abs(sim['iqr_pp'] - obs['iqr_pp']))


def headline_errors(predicted, observed):
    p, y = np.asarray(predicted, float), np.asarray(observed, float)
    if p.shape != y.shape or p.ndim != 1 or not len(p):
        raise ValueError('Expected a nonempty matched monthly series')
    if not (np.isfinite(p).all() and np.isfinite(y).all()):
        raise ValueError('Missing forecasts must be reported, not silently excluded')
    error = p - y
    return dict(n_months=len(p), mae_pp=float(np.abs(error).mean()),
                rmse_pp=float(np.sqrt((error ** 2).mean())), bias_pp=float(error.mean()),
                max_absolute_error_pp=float(np.abs(error).max()))


def paired_month_mae_interval(model_errors, baseline_errors, *, block_length=6,
                             draws=2000, seed=42):
    """Approximate circular-block bootstrap; negative difference means improvement."""
    x, y = np.asarray(model_errors, float), np.asarray(baseline_errors, float)
    if x.shape != y.shape or x.ndim != 1 or not len(x):
        raise ValueError('Require matched monthly error arrays')
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValueError('Nonfinite monthly error')
    if not 1 <= block_length <= len(x) or draws < 1:
        raise ValueError('Invalid bootstrap configuration')
    delta = np.abs(x) - np.abs(y)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(x), size=(draws, int(np.ceil(len(x) / block_length))))
    indices = ((starts[..., None] + np.arange(block_length)) % len(x)).reshape(draws, -1)[:, :len(x)]
    samples = delta[indices].mean(axis=1)
    lo, hi = np.quantile(samples, [.025, .975])
    return dict(mae_difference_pp=float(delta.mean()), interval_95=[float(lo), float(hi)],
                block_length=block_length, draws=draws, seed=seed,
                interpretation='conditional retrospective uncertainty; not proof of future performance')
