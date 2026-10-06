"""Evaluation-only common-case diagnostics; no import from simulation code."""
import math
import numpy as np
from .household_state_analysis import distribution
from .information_exposure import ARMS


def paired_metrics(rows):
    keys = ("real",) + ARMS
    common = [r for r in rows if all(type(r[k]) in (int, float) and math.isfinite(r[k]) for k in keys)]
    out = {"n_selected": len(rows), "n_common": len(common), "n_excluded": len(rows) - len(common),
           "estimand": "equal-channel diagnostic sample; not nationally representative", "arms": {}}
    real = np.asarray([r["real"] for r in common], float)
    out["matched_real"] = distribution(real)
    for arm in ARMS:
        pred = np.asarray([r[arm] for r in common], float)
        summary = distribution(pred)
        out["arms"][arm] = {"distribution": summary,
            "MAE_pp": float(np.mean(abs(pred - real))) if len(real) else None,
            "MedAE_pp": float(np.median(abs(pred - real))) if len(real) else None,
            "bias_pp": float(np.mean(pred - real)) if len(real) else None,
            "distribution_W1_pp": float(np.mean(abs(np.sort(pred) - np.sort(real)))) if len(real) else None,
            "IQR_absolute_gap_pp": abs(summary["iqr"] - out["matched_real"]["iqr"]) if len(real) else None,
            "intended_channel_groups": {ch: {"real": distribution([r["real"] for r in common if r["channel"] == ch]),
                "simulated": distribution([r[arm] for r in common if r["channel"] == ch])} for ch in ("food", "gasoline", "shelter")}}
    changes = [abs(r["matched"] - r["real"]) - abs(r["shuffled"] - r["real"]) for r in common]
    out["paired_absolute_error_change_matched_minus_shuffled_pp"] = distribution(changes)
    if changes:
        rng = np.random.default_rng(42)
        bs = np.mean(rng.choice(np.asarray(changes), size=(2000, len(changes)), replace=True), axis=1)
        out["paired_mean_error_change_bootstrap_95_interval_pp"] = np.quantile(bs, [.025, .975]).tolist()
    else:
        out["paired_mean_error_change_bootstrap_95_interval_pp"] = None
    # This is a screening rule, not a statistical-power or causal assertion.
    out["development_screen_passed"] = bool(common and all(
        out["arms"]["matched"][metric] < out["arms"][control][metric]
        for metric in ("MAE_pp", "distribution_W1_pp") for control in ("shared", "shuffled")) and
        out["arms"]["matched"]["IQR_absolute_gap_pp"] <= out["arms"]["shared"]["IQR_absolute_gap_pp"])
    return out
