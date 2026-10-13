"""Public-codebook-driven MIDUS summaries. No individual exports or networking.

Real MIDUS data must be processed by the user outside the AI workspace.
This module is tested only with invented records; it does not modify the simulator.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRAIT_RANGES = {
    "RA1SNEURO": (1.0, 4.0),
    "RA1SEXTRA": (1.0, 4.0),
    "RA1SOPEN": (1.0, 4.0),
    "RA1SCONS2": (1.0, 4.0),
    "RA1SAGREE": (1.0, 4.0),
    "RA1SORIEN": (6.0, 30.0),
}
TRAITS = list(TRAIT_RANGES)
WEIGHTS = {"RA1SWGHT6", "RA1SWGHT7", "RA1SWGHT8"}
MIN_DISCLOSURE_CELL = 11


def weighted_moments(values: np.ndarray, weights: np.ndarray):
    """Descriptive weighted population moments, not design-based standard errors."""
    weights = np.asarray(weights, dtype=float)
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or len(values) != len(weights) or not len(weights):
        raise ValueError("Incompatible nonempty arrays required")
    if not np.isfinite(values).all() or not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("Finite values and positive weights required")
    normalized = weights / weights.sum()
    mean = normalized @ values
    centered = values - mean
    covariance = (centered * normalized[:, None]).T @ centered
    return mean, covariance


def _tertile_cuts(values, weights):
    order = np.argsort(values, kind="stable")
    v, w = np.asarray(values)[order], np.asarray(weights)[order]
    cdf = np.cumsum(w) / np.sum(w)
    return v[np.searchsorted(cdf, [1 / 3, 2 / 3], side="left")]


def joint_bins(values, weights, cuts):
    """Release the whole 3x3 table only if every cell has at least 11 people.

    Suppressing the whole table avoids reconstruction of a small missing cell
    from a released total. Zero/tied bins also cause the whole table to be omitted.
    """
    buckets = np.column_stack([
        np.searchsorted(cuts[k], values[:, k], side="left") for k in range(2)
    ])
    counts = np.zeros((3, 3), dtype=int)
    masses = np.zeros((3, 3), dtype=float)
    for i, j, w in zip(buckets[:, 0], buckets[:, 1], weights):
        counts[i, j] += 1
        masses[i, j] += w
    if (counts < MIN_DISCLOSURE_CELL).any():
        return None
    return {
        "variables": ["RA1SNEURO", "RA1SORIEN"],
        "probabilities": (masses / masses.sum()).round(4).tolist(),
        "rounding_note": "Four decimal places; the rounded sum can differ from one.",
    }


def _support_band(n):
    if n < 100:
        return "60-99"
    if n < 200:
        return "100-199"
    if n < 500:
        return "200-499"
    if n < 1000:
        return "500-999"
    return "1000+"


def summarize_frame(frame: pd.DataFrame, weight_column="RA1SWGHT6"):
    """Summarize current MR1 data; no IDs, raw values, exact small counts or donors.

    Complete-case, age 25-74 restriction is an explicit first-stage choice. The
    current codebook records computed ages 23-76; their extremes are not extrapolated.
    """
    if weight_column not in WEIGHTS:
        raise ValueError("Only documented SAQ post-stratification weights are supported")
    fields = ["RA1PRAGE", "RA1PB1", weight_column, *TRAITS]
    missing = set(fields) - set(frame.columns)
    if missing:
        raise ValueError("Required codebook columns are missing: " + ", ".join(sorted(missing)))
    data = frame.loc[:, fields].apply(pd.to_numeric, errors="coerce")
    valid = data["RA1PRAGE"].between(25, 74) & data["RA1PB1"].isin(range(1, 13))
    valid &= np.isfinite(data[weight_column]) & data[weight_column].gt(0)
    valid &= data[weight_column].ne(99)  # official no-SAQ sentinel
    for field, (lo, hi) in TRAIT_RANGES.items():
        valid &= np.isfinite(data[field]) & data[field].between(lo, hi)
    data = data.loc[valid].copy()
    result = {
        "schema": "midus_mr1_group_summary_v1",
        "data_version": "MR1_P1_SURVEY_N3577_20250407",
        "source_wave": "2011-2014; current revised release",
        "weight": weight_column,
        "traits": TRAITS,
        "selection": "Complete cases; age 25-74; valid education; valid SAQ weight",
        "minimum_group": 60,
        "minimum_histogram_cell": MIN_DISCLOSURE_CELL,
        "groups": [],
        "cautions": [
            "Descriptive moments, not causal effects or population design-based uncertainty.",
            "Complete-case selection and cross-survey transport still need examination.",
            "Current 2025 weights are not certified for a 2021 point-in-time forecast.",
            "No SCE identities or answers linked; not permission to send data to an AI service.",
        ],
    }
    if len(data) < 60:
        return result
    cuts = [
        _tertile_cuts(data[field].to_numpy(), data[weight_column].to_numpy())
        for field in ["RA1SNEURO", "RA1SORIEN"]
    ]
    # Cutpoints are released only with a supported histogram, not separately.
    age_specs = [(25, 39, "25-39"), (40, 59, "40-59"), (60, 74, "60-74")]
    edu_specs = [(1, 5, "high_school_or_less"), (6, 8, "some_college_or_associate"),
                 (9, 12, "bachelor_or_more")]
    for age_lo, age_hi, age_label in age_specs:
        for edu_lo, edu_hi, edu_label in edu_specs:
            group = data.loc[data["RA1PRAGE"].between(age_lo, age_hi)
                             & data["RA1PB1"].between(edu_lo, edu_hi)]
            if len(group) < 60:
                continue
            values = group[TRAITS].to_numpy()
            weights = group[weight_column].to_numpy()
            mean, cov = weighted_moments(values, weights)
            entry = {
                "age": age_label, "education": edu_label,
                "sample_support_band": _support_band(len(group)),
                "mean": mean.round(4).tolist(),
                "covariance": cov.round(4).tolist(),
                "covariance_definition": "sum(normalized_weight * centered_outer_product)",
            }
            hist = joint_bins(group[["RA1SNEURO", "RA1SORIEN"]].to_numpy(), weights, cuts)
            if hist is not None:
                hist["pooled_weighted_tertile_cuts"] = [x.round(4).tolist() for x in cuts]
                entry["neuroticism_optimism_joint"] = hist
            result["groups"].append(entry)
    return result
