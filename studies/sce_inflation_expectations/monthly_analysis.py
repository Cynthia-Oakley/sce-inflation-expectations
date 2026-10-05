"""Evaluation helpers: weights and survey dates are never model inputs."""
from datetime import datetime

import numpy as np


def date_group(survey_date, as_of):
    """Date-level grouping; same-day times are unknown, not guessed."""
    if not survey_date:
        return "unknown_date"
    try:
        day = datetime.fromisoformat(str(survey_date)).date()
    except ValueError:
        return "unknown_date"
    cutoff = datetime.fromisoformat(as_of).date()
    return "before_cutoff" if day < cutoff else "after_cutoff" if day > cutoff else "same_day_time_unknown"


def weighted_summary(values, weights, *, interpolate_median=False):
    x, w = np.asarray(values, float), np.asarray(weights, float)
    if len(x) != len(w):
        raise ValueError("values/weights lengths differ")
    valid = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x, w = x[valid], w[valid]
    if not len(x):
        return {"n_valid": 0, "weighted_median_pp": None, "weighted_mean_pp": None, "weighted_std_pp": None}
    order = np.argsort(x, kind="stable")
    x, w = x[order], w[order]
    if interpolate_median:
        # Collapse ties before mid-distribution interpolation, matching our Q8 contract.
        unique, inverse = np.unique(x, return_inverse=True)
        mass = np.bincount(inverse, weights=w)
        centers = (np.cumsum(mass) - .5 * mass) / mass.sum()
        median = float(np.interp(.5, centers, unique))
    else:
        median = float(x[min(np.searchsorted(np.cumsum(w), .5 * w.sum(), side="left"), len(x) - 1)])
    mean = float(x @ w / w.sum())
    return {"n_valid": len(x), "weighted_median_pp": median, "weighted_mean_pp": mean,
            "weighted_std_pp": float(np.sqrt(((x - mean) ** 2) @ w / w.sum())),
            "effective_sample_size": float(w.sum() ** 2 / (w @ w))}


def paired_metrics(simulated, observed, weights, *, point_prediction=False):
    """Same-person comparisons, with an independent mask for each question."""
    sim, real, w = np.asarray(simulated, float), np.asarray(observed, float), np.asarray(weights, float)
    if not len(sim) == len(real) == len(w):
        raise ValueError("paired inputs must have equal lengths")
    valid = np.isfinite(sim) & np.isfinite(real) & np.isfinite(w) & (w > 0)
    sim, real, w = sim[valid], real[valid], w[valid]
    if not len(w):
        return {"n_pairs": 0, "weighted_mae_pp": None, "weighted_bias_pp": None,
                "weighted_median_absolute_error_pp": None}
    error = sim - real
    return {"n_pairs": len(w), "weighted_mae_pp": float(np.abs(error) @ w / w.sum()),
            "weighted_bias_pp": float(error @ w / w.sum()),
            "weighted_median_absolute_error_pp": weighted_summary(np.abs(error), w)["weighted_median_pp"],
            "simulated": weighted_summary(sim, w, interpolate_median=point_prediction),
            "observed": weighted_summary(real, w, interpolate_median=point_prediction)}
