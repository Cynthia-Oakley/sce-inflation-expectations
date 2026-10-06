"""Evaluation-only paired diagnostics, never imported by the decision provider."""
import math
import numpy as np
from .scoring.sce_q9_frozen import score_q9_frozen


def density(bins):
    if len(bins) != 10 or any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 100 for x in bins):
        return {"mean": None, "iqr": None, "status": "invalid_bins"}
    if abs(sum(bins) - 100) > .5:
        return {"mean": None, "iqr": None, "status": "invalid_bins"}
    score = score_q9_frozen(bins)
    return {"mean": score.mean if score.mean is not None and math.isfinite(score.mean) else None,
            "iqr": score.iqr if score.iqr is not None and math.isfinite(score.iqr) else None, "status": score.status}


def distribution(values):
    arr = np.asarray(values, float)
    if not len(arr) or not np.isfinite(arr).all():
        return {"n": 0, "median": None, "mean": None, "iqr": None}
    lo, med, hi = np.quantile(arr, [.25, .50, .75])
    return {"n": len(arr), "median": float(med), "mean": float(arr.mean()), "iqr": float(hi - lo)}


def paired_metrics(rows):
    """Common-case sample for every comparison; group assignment fixed upfront."""
    eligible = [r for r in rows if all(r[k] is not None and math.isfinite(r[k]) for k in ("real", "baseline", "q1_state"))]
    out = {"n_selected": len(rows), "n_complete_pairs": len(eligible), "n_excluded": len(rows) - len(eligible),
           "population_estimand": "Q1-balanced diagnostic sample only; not nationally representative", "arms": {}}
    real = distribution([r["real"] for r in eligible])
    out["matched_real"] = real
    for arm in ("baseline", "q1_state"):
        pred = distribution([r[arm] for r in eligible])
        errs = [abs(r[arm] - r["real"]) for r in eligible]
        out["arms"][arm] = {"distribution": pred, "MAE_pp": float(np.mean(errs)) if errs else None,
                            "IQR_absolute_gap_pp": abs(pred["iqr"] - real["iqr"]) if errs else None,
                            "Q1_groups": {str(c): {"simulated": distribution([r[arm] for r in eligible if r["Q1"] == c]),
                                "real": distribution([r["real"] for r in eligible if r["Q1"] == c])} for c in range(1, 6)}}
        g = out["arms"][arm]["Q1_groups"]
        vals = [g[str(c)][k]["median"] for c in (1, 3) for k in ("simulated", "real")]
        if all(x is not None for x in vals):
            simgap, realgap = vals[0] - vals[2], vals[1] - vals[3]
            out["arms"][arm].update(worse_minus_same_gap_pp=simgap,
                                    matched_real_worse_minus_same_gap_pp=realgap,
                                    group_gap_absolute_error_pp=abs(simgap - realgap))
        else:
            out["arms"][arm]["group_gap_absolute_error_pp"] = None
    differences = [abs(r["q1_state"] - r["real"]) - abs(r["baseline"] - r["real"]) for r in eligible]
    out["paired_error_change_q1_minus_baseline_pp"] = distribution(differences)
    base, trial = out["arms"]["baseline"], out["arms"]["q1_state"]
    out["development_signal_both_primary_and_group_improve"] = bool(eligible and
        trial["MAE_pp"] < base["MAE_pp"] and trial["group_gap_absolute_error_pp"] is not None and
        trial["group_gap_absolute_error_pp"] < base["group_gap_absolute_error_pp"])
    return out
