"""Small metric helpers shared by the belief-dynamics analyses."""
from __future__ import annotations

import numpy as np

from ..factual_mechanism_audit import wquantile


def _weighted_cdf_support(values, weights):
    """Unique sorted values and normalized cumulative weights (right-continuous CDF)."""
    v, w = np.asarray(values, float), np.asarray(weights, float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[ok], w[ok]
    if not len(v):
        raise ValueError("weighted_w1: empty distribution")
    order = np.argsort(v, kind="stable")
    v, w = v[order], w[order]
    uniq, first = np.unique(v, return_index=True)
    last = np.r_[first[1:] - 1, len(v) - 1]  # CDF at x includes all mass at x
    total = w.sum()
    cum = np.cumsum(w)[last] / total
    return uniq, cum


def weighted_w1(values_a, values_b, weights_a=None, weights_b=None) -> float:
    """Weighted 1-Wasserstein distance between two empirical 1-D distributions.

    CDF integration on the union of supports; robust to duplicated values and
    differing weights (scipy.stats.wasserstein_distance is not, for duplicated
    inputs with unequal weights).
    """
    a = np.asarray(values_a, float)
    b = np.asarray(values_b, float)
    if weights_a is None:
        weights_a = np.ones(len(a))
    if weights_b is None:
        weights_b = np.ones(len(b))
    x_a, f_a = _weighted_cdf_support(a, weights_a)
    x_b, f_b = _weighted_cdf_support(b, weights_b)
    points = np.unique(np.concatenate([x_a, x_b]))

    def cdf_at(x_vals, f_vals):
        # Right-continuous F(point): 0 below the first support point.
        idx = np.searchsorted(x_vals, points, side="right")
        return np.where(idx > 0, f_vals[np.clip(idx - 1, 0, len(x_vals) - 1)], 0.0)

    fa, fb = cdf_at(x_a, f_a), cdf_at(x_b, f_b)
    gaps = np.diff(points)
    return float(np.sum(np.abs(fa[:-1] - fb[:-1]) * gaps))


def weighted_ols_slope(x, y, w=None) -> float | None:
    """Weighted least-squares slope of y ~ x (single regressor, intercept)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if w is None:
        w = np.ones(len(x))
    w = np.asarray(w, float)
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    x, y, w = x[ok], y[ok], w[ok]
    if len(x) < 3:
        return None
    xm = np.average(x, weights=w)
    ym = np.average(y, weights=w)
    var = np.average((x - xm) ** 2, weights=w)
    if var <= 0:
        return None
    return float(np.average((x - xm) * (y - ym), weights=w) / var)


def weighted_pearson(x, y, w=None) -> float | None:
    from ..factual_mechanism_audit import correlation
    if w is None:
        w = np.ones(len(x))
    return correlation(x, y, w)


def weighted_bin_index(values, weights, cutpoints):
    """Bin index (0..len(cutpoints)) per row; values equal to a cutpoint fall
    into the lower bin (np.searchsorted side='left')."""
    v = np.asarray(values, float)
    return np.clip(np.searchsorted(np.asarray(cutpoints, float), v), 0, len(cutpoints))


def mean_or_none(values):
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else None


def iqr(values) -> float:
    """Unweighted interquartile range (linear interpolation)."""
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if not len(v):
        return float("nan")
    return float(np.percentile(v, 75) - np.percentile(v, 25))


def weighted_median(values, weights) -> float | None:
    return wquantile(values, weights, 0.5)
