"""Task B: preregistered low-parameter empirical update baselines.

Design frozen in docs/workstreams/20261013_behavior/kimi_progress.md section 5;
implemented without looking at outcomes first. Predicts the current Q9 center
of a returning respondent using only (a) own previous center and previous
uncertainty, and (b) current/previous full-wave common statistics (A-line
diagnostic quantities, NOT PIT-B forecasts). No injected noise.

Real -> real on official Q9_mean; train 201702-202112, validation 202201-202510.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..factual_mechanism_audit import wquantile
from .data import WEIGHT_SCOPE_NOTE, add_month_equal_weight, build_valid_pairs
from .dynamics import h2_pooled, prepare_frame
from .metrics import weighted_w1

TRAIN_RANGE = (201702, 202112)
VAL_RANGE = (202201, 202510)
PREREGISTRATION = "docs/workstreams/20261013_behavior/kimi_progress.md section 5 (2026-10-13)"

B0 = "B0 persistence: yhat = y_{t-1}"
B1 = "B1 common shift: yhat = y_{t-1} + (m_t - m_{t-1})"
B2 = "B2 partial adjustment: yhat = (1-lambda) y_{t-1} + lambda m_t"
B3 = "B3 decentered rebound: yhat = m_t + rho (y_{t-1} - m_{t-1})"
B4 = ("B4 uncertainty-gated rebound: yhat = m_t + rho0 exp(-rho1 IQR_{t-1}) "
      "(y_{t-1} - m_{t-1}); estimated only if the training-period H2 ordering "
      "(mean|delta| strictly increasing across previous-Q9_iqr quartiles) holds")


def common_medians(frame: pd.DataFrame) -> dict:
    """m~_t: weighted median of legal official Q9_mean over the full wave t."""
    ok = frame[np.isfinite(frame["Q9_mean"]) & np.isfinite(frame["weight"]) & (frame["weight"] > 0)]
    return {int(m): wquantile(g["Q9_mean"], g["weight"], 0.5)
            for m, g in ok.groupby("date")}


def predict(frame_pairs: pd.DataFrame, medians: dict, kind: str,
            lam: float | None = None, rho: float | None = None,
            rho0: float | None = None, rho1: float | None = None) -> np.ndarray:
    y_prev = frame_pairs["previous_Q9_mean"].to_numpy(float)
    m_t = frame_pairs["date"].map(medians).to_numpy(float)
    m_prev = frame_pairs["previous_date"].map(medians).to_numpy(float)
    if kind == "B0":
        return y_prev
    if kind == "B1":
        return y_prev + (m_t - m_prev)
    if kind == "B2":
        return (1 - lam) * y_prev + lam * m_t
    if kind == "B3":
        return m_t + rho * (y_prev - m_prev)
    if kind == "B4":
        iqr_prev = frame_pairs["previous_Q9_iqr"].to_numpy(float)
        shrink = rho0 * np.exp(-rho1 * iqr_prev)
        return m_t + shrink * (y_prev - m_prev)
    raise ValueError(kind)


def evaluate_predictions(frame_pairs: pd.DataFrame, y_hat: np.ndarray,
                         mask: np.ndarray | None = None) -> dict:
    """Preregistered metrics for an externally supplied prediction (month-equal means)."""
    fp = frame_pairs.reset_index(drop=True)
    y_hat = np.asarray(y_hat, float)
    y_real = fp["Q9_mean"].to_numpy(float)
    real_delta = y_real - fp["previous_Q9_mean"].to_numpy(float)
    pred_delta = y_hat - fp["previous_Q9_mean"].to_numpy(float)
    w = fp["weight"].to_numpy(float)
    sel = np.ones(len(fp), bool) if mask is None else np.asarray(mask, bool)
    monthly = []
    for month, p in fp.groupby("date"):
        idx = p.index.to_numpy()
        idx = idx[sel[idx]]
        rec = {"month": int(month), "n": int(len(idx))}
        if not len(idx):
            monthly.append(rec)
            continue
        rec["delta_w1"] = weighted_w1(pred_delta[idx], real_delta[idx], w[idx], w[idx])
        rec["cross_section_w1"] = weighted_w1(y_hat[idx], y_real[idx], w[idx], w[idx])
        yh, yr = y_hat[idx], y_real[idx]
        if len(np.unique(yh)) > 1 and len(np.unique(yr)) > 1 and len(idx) > 2:
            rec["spearman"] = float(pd.Series(yh).corr(pd.Series(yr), method="spearman"))
        else:
            rec["spearman"] = None
        rec["median_abs_error_pp"] = abs(wquantile(y_hat[idx], w[idx], 0.5)
                                         - wquantile(y_real[idx], w[idx], 0.5))
        rec["mae_pp"] = float(np.average(np.abs(y_hat[idx] - y_real[idx]), weights=w[idx]))
        monthly.append(rec)
    usable = [r for r in monthly if "mae_pp" in r]

    def mmean(key):
        vals = [r[key] for r in usable
                if r.get(key) is not None and np.isfinite(r.get(key))]
        return float(np.mean(vals)) if vals else None

    return {
        "n_months": len(usable),
        "delta_w1_month_equal": mmean("delta_w1"),
        "cross_section_w1_month_equal": mmean("cross_section_w1"),
        "spearman_month_equal": mmean("spearman"),
        "median_abs_error_pp_month_equal": mmean("median_abs_error_pp"),
        "mae_pp_month_equal_auxiliary": mmean("mae_pp"),
        "monthly": monthly,
    }


def evaluate(frame_pairs: pd.DataFrame, medians: dict, kind: str, **params) -> dict:
    """Preregistered metrics for one baseline on one split (month-equal means)."""
    fp = frame_pairs.reset_index(drop=True)
    y_hat = predict(fp, medians, kind, **params)
    if kind == "B4":
        mask = np.isfinite(fp["previous_Q9_iqr"].to_numpy(float))
    else:
        mask = None
    return evaluate_predictions(fp, y_hat, mask)


def fit_param(frame_pairs: pd.DataFrame, medians: dict, kind: str,
              grid: np.ndarray) -> tuple[float, float]:
    """Select the parameter minimizing mean monthly weighted MAE on train."""
    best_lam, best_obj = None, np.inf
    for lam in grid:
        obj = evaluate(frame_pairs, medians, kind, lam=lam, rho=lam)["mae_pp_month_equal_auxiliary"]
        if obj < best_obj:
            best_obj, best_lam = obj, float(lam)
    return best_lam, best_obj


def run_baselines(output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    frame = prepare_frame()
    medians = common_medians(frame)
    pairs = add_month_equal_weight(build_valid_pairs(frame))

    train = pairs[(pairs["date"] >= TRAIN_RANGE[0]) & (pairs["date"] <= TRAIN_RANGE[1])]
    val = pairs[(pairs["date"] >= VAL_RANGE[0]) & (pairs["date"] <= VAL_RANGE[1])]
    grid = np.round(np.arange(0.0, 1.0 + 1e-9, 0.02), 2)

    results = {"B0": {"description": B0}, "B1": {"description": B1},
               "B2": {"description": B2}, "B3": {"description": B3},
               "B4": {"description": B4}}

    results["B0"]["train"] = evaluate(train, medians, "B0")
    results["B0"]["val"] = evaluate(val, medians, "B0")
    results["B1"]["train"] = evaluate(train, medians, "B1")
    results["B1"]["val"] = evaluate(val, medians, "B1")

    lam, obj = fit_param(train, medians, "B2", grid)
    results["B2"]["selected_lambda"] = lam
    results["B2"]["train_objective"] = obj
    results["B2"]["train"] = evaluate(train, medians, "B2", lam=lam)
    results["B2"]["val"] = evaluate(val, medians, "B2", lam=lam)

    rho, obj = fit_param(train, medians, "B3", grid)
    results["B3"]["selected_rho"] = rho
    results["B3"]["train_objective"] = obj
    results["B3"]["train"] = evaluate(train, medians, "B3", rho=rho)
    results["B3"]["val"] = evaluate(val, medians, "B3", rho=rho)

    # B4 gate: training-period H2 ordering must be strictly increasing.
    h2_train = h2_pooled(train)
    bins = [b["mean_abs_delta_month_equal"] for b in h2_train["quartile_bins_month_equal"]]
    triggered = all(bins[i] is not None and bins[i + 1] is not None and bins[i + 1] > bins[i]
                    for i in range(len(bins) - 1)) and len(bins) == 4
    results["B4"]["gate"] = {
        "triggered": bool(triggered),
        "train_h2_quartile_mean_abs_delta_month_equal": bins,
        "rule": "estimate only if mean|delta| strictly increases across previous-Q9_iqr quartiles on train",
    }
    if triggered:
        rho0_grid = np.round(np.arange(0.0, 1.0 + 1e-9, 0.05), 2)
        rho1_grid = np.array([0.0, 0.05, 0.1, 0.2, 0.4])
        best = (None, None, np.inf)
        for rho0 in rho0_grid:
            for rho1 in rho1_grid:
                obj = evaluate(train, medians, "B4", rho0=rho0, rho1=rho1)["mae_pp_month_equal_auxiliary"]
                if obj < best[2]:
                    best = (float(rho0), float(rho1), obj)
        results["B4"]["selected_rho0"] = best[0]
        results["B4"]["selected_rho1"] = best[1]
        results["B4"]["train_objective"] = best[2]
        results["B4"]["train"] = evaluate(train, medians, "B4", rho0=best[0], rho1=best[1])
        results["B4"]["val"] = evaluate(val, medians, "B4", rho0=best[0], rho1=best[1])
    else:
        results["B4"]["skipped_reason"] = (
            "Training-period H2 ordering not strictly increasing; B4 not estimated "
            "per preregistration.")

    summary = {
        "line": "SCE preregistered empirical update baselines (task B)",
        "preregistration_reference": PREREGISTRATION,
        "data": {
            "metric": "official Q9_mean (real -> real, consistent口径)",
            "valid_pairs": int(len(pairs)),
            "train_months": f"{TRAIN_RANGE[0]}..{TRAIN_RANGE[1]} ({train['date'].nunique()})",
            "val_months": f"{VAL_RANGE[0]}..{VAL_RANGE[1]} ({val['date'].nunique()})",
            "train_pairs": int(len(train)),
            "val_pairs": int(len(val)),
            "m_tilde_definition": ("weighted median of legal official Q9_mean over the full "
                                   "wave t cross-section (not restricted to pair sample)"),
            "weight_scope_note": WEIGHT_SCOPE_NOTE,
            "interpretation_boundary": ("A-line baselines condition on current-wave common "
                                        "statistics m~_t; they measure the personal update rule "
                                        "given the common level, not PIT-B forecasting ability."),
        },
        "grid": {"lam/rho": "0.00-1.00 step 0.02",
                 "B4_rho0": "0.00-1.00 step 0.05", "B4_rho1": [0.0, 0.05, 0.1, 0.2, 0.4],
                 "objective": "month-equal mean of monthly weighted MAE(ŷ, y_t) on train"},
        "baselines": results,
    }
    (output_dir / "baseline_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
