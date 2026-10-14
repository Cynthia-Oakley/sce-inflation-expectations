"""Personal-anchor update rules (second preregistered round).

Design frozen in docs/workstreams/20261013_behavior/kimi_anchor_prereg.md
before any outcome was computed. Single change versus the first round: the
adjustment anchor is the respondent's own trailing history, not the common
current-wave median.

C1 (main):  yhat = y_{t-1} + lam * (a_{i,t-1} - y_{t-1}) + (m_t - m_{t-1})
C2:         same, anchor = exponentially decayed personal mean (half-life 12m)
C3:         same, anchor = personal running median

a_{i,t-1} uses all of the person's valid answers strictly earlier than t
(including t-1 itself). With fewer than MIN_HISTORY earlier valid answers the
anchor term is zero and the rule degenerates to the B1 common shift.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .baselines import TRAIN_RANGE, VAL_RANGE, common_medians, evaluate_predictions
from .data import (
    WEIGHT_SCOPE_NOTE,
    add_month_equal_weight,
    build_valid_pairs,
    legal_bins_mask,
    month_index,
)
from .dynamics import prepare_frame

PREREGISTRATION = "docs/workstreams/20261013_behavior/kimi_anchor_prereg.md (2026-10-13)"
MIN_HISTORY = 2
HALFLIFE_MONTHS = 12.0
LAMBDA_GRID = np.round(np.arange(0.0, 1.0 + 1e-9, 0.02), 2)

C1 = ("C1 personal-anchor partial adjustment: yhat = y_{t-1} + lam (a_i - y_{t-1}) "
      "+ (m_t - m_{t-1}); a_i = expanding mean of own earlier valid answers")
C2 = "C2 sensitivity: same rule, anchor = own decayed mean (half-life 12 months)"
C3 = "C3 sensitivity: same rule, anchor = own running median"


def valid_answer_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows usable as outcomes and as anchor history: bins legal, Q9_mean finite."""
    ok = legal_bins_mask(frame) & np.isfinite(frame["Q9_mean"].to_numpy(float))
    f = frame[ok.to_numpy()].copy()
    if f.duplicated(["userid", "date"]).any():
        raise ValueError("non-unique person-month in reference frame")
    return f.sort_values(["userid", "date"], kind="stable").reset_index(drop=True)


def personal_anchors(answers: pd.DataFrame, mode: str = "mean") -> pd.DataFrame:
    """Anchor per (userid, date) from answers strictly earlier than date.

    Returns columns userid/date/anchor/history_count, one row per input row.
    """
    frames = []
    for _, g in answers.groupby("userid", sort=False):
        y = g["Q9_mean"].to_numpy(float)
        months = np.array([month_index(d) for d in g["date"]], dtype=float)
        n = len(g)
        anchor = np.full(n, np.nan)
        if mode == "mean":
            cum = np.cumsum(y)
            anchor[1:] = cum[:-1] / np.arange(1, n)
        elif mode == "decay":
            for i in range(1, n):
                w = 0.5 ** ((months[i] - months[:i]) / HALFLIFE_MONTHS)
                anchor[i] = float(np.sum(w * y[:i]) / np.sum(w))
        elif mode == "median":
            for i in range(1, n):
                anchor[i] = float(np.median(y[:i]))
        else:
            raise ValueError(mode)
        frames.append(pd.DataFrame({
            "userid": g["userid"].to_numpy(),
            "date": g["date"].to_numpy(),
            "anchor": anchor,
            "history_count": np.arange(n),
        }))
    out = pd.concat(frames, ignore_index=True)
    return out


def attach_anchors(pairs: pd.DataFrame, anchors: pd.DataFrame) -> pd.DataFrame:
    merged = pairs.merge(anchors, on=["userid", "date"], how="left", validate="many_to_one")
    # Every pair's current row is itself a valid answer row, so the merge must
    # always hit; anchor is NaN exactly when history_count == 0 (first answer).
    if merged["history_count"].isna().any():
        raise ValueError("pair current row missing from the valid-answer frame")
    return merged


def predict_anchor(fp: pd.DataFrame, medians: dict, lam: float) -> np.ndarray:
    """C1-family prediction; anchor term drops out below MIN_HISTORY."""
    y_prev = fp["previous_Q9_mean"].to_numpy(float)
    m_t = fp["date"].map(medians).to_numpy(float)
    m_prev = fp["previous_date"].map(medians).to_numpy(float)
    has_anchor = fp["history_count"].to_numpy() >= MIN_HISTORY
    anchor = fp["anchor"].to_numpy(float)
    adj = np.where(has_anchor, lam * (anchor - y_prev), 0.0)
    return y_prev + adj + (m_t - m_prev)


def fit_lambda(fp: pd.DataFrame, medians: dict) -> tuple[float, float]:
    best_lam, best_obj = None, np.inf
    for lam in LAMBDA_GRID:
        obj = evaluate_predictions(fp, predict_anchor(fp, medians, lam))[
            "mae_pp_month_equal_auxiliary"]
        if obj < best_obj:
            best_obj, best_lam = obj, float(lam)
    return best_lam, best_obj


def anchor_spread(anchors: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    """Cross-person dispersion of personal anchors on validation pair months."""
    merged = pairs[(pairs["date"] >= VAL_RANGE[0]) & (pairs["date"] <= VAL_RANGE[1])]
    merged = merged.merge(anchors, on=["userid", "date"], how="left", validate="many_to_one")
    ok = merged[np.isfinite(merged["anchor"])]
    per_month = ok.groupby("date")["anchor"].agg(
        lambda s: float(np.percentile(s, 75) - np.percentile(s, 25)))
    return {"val_anchor_iqr_month_equal": float(per_month.mean()),
            "val_anchor_iqr_min": float(per_month.min()),
            "val_anchor_iqr_max": float(per_month.max()),
            "note": "unweighted cross-person IQR of the personal anchor within month"}


def run_anchor_baselines(output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    frame = prepare_frame()
    answers = valid_answer_frame(frame)
    medians = common_medians(frame)
    pairs = add_month_equal_weight(build_valid_pairs(frame))

    variants = {"C1": ("mean", C1), "C2": ("decay", C2), "C3": ("median", C3)}
    results = {}
    for name, (mode, desc) in variants.items():
        anchors = personal_anchors(answers, mode=mode)
        fp = attach_anchors(pairs, anchors)
        train = fp[(fp["date"] >= TRAIN_RANGE[0]) & (fp["date"] <= TRAIN_RANGE[1])]
        val = fp[(fp["date"] >= VAL_RANGE[0]) & (fp["date"] <= VAL_RANGE[1])]
        lam, obj = fit_lambda(train, medians)
        results[name] = {
            "description": desc,
            "anchor_mode": mode,
            "selected_lambda": lam,
            "train_objective": obj,
            "anchor_coverage_val": float((val["history_count"] >= MIN_HISTORY).mean()),
            "train": evaluate_predictions(train, predict_anchor(train, medians, lam)),
            "val": evaluate_predictions(val, predict_anchor(val, medians, lam)),
        }
        if name == "C1":
            results[name]["anchor_spread"] = anchor_spread(anchors, pairs)

    summary = {
        "line": "SCE preregistered personal-anchor update rule (task B round 2)",
        "preregistration_reference": PREREGISTRATION,
        "data": {
            "metric": "official Q9_mean (real -> real, consistent口径)",
            "valid_pairs": int(len(pairs)),
            "train_months": f"{TRAIN_RANGE[0]}..{TRAIN_RANGE[1]}",
            "val_months": f"{VAL_RANGE[0]}..{VAL_RANGE[1]}",
            "train_pairs": int(len(pairs[(pairs['date'] >= TRAIN_RANGE[0])
                                         & (pairs['date'] <= TRAIN_RANGE[1])])),
            "val_pairs": int(len(pairs[(pairs['date'] >= VAL_RANGE[0])
                                       & (pairs['date'] <= VAL_RANGE[1])])),
            "anchor_definition": ("expanding mean of own valid answers strictly before t "
                                  "(C1); decay half-life 12m (C2); running median (C3). "
                                  f"Anchor term zero when earlier valid history < {MIN_HISTORY}."),
            "weight_scope_note": WEIGHT_SCOPE_NOTE,
            "interpretation_boundary": ("A-line diagnostic: the common-shift term uses "
                                        "current-wave common statistics; not a PIT-B forecast."),
            "exposure": ("Validation split used once before (B0-B4). This second use evaluates "
                         "a rule form fixed by the first round's failure mode; development "
                         "diagnostic, not a final test."),
        },
        "grid": {"lambda": "0.00-1.00 step 0.02",
                 "objective": "month-equal mean of monthly weighted MAE(ŷ, y_t) on train"},
        "success_criteria": {
            "preserve_cross_section": "val cross_section_w1_month_equal <= 0.60",
            "respond_to_information": "val delta_w1_month_equal <= 2.0",
            "rule": "both must hold simultaneously (single-metric success not allowed)",
        },
        "variants": results,
    }
    (output_dir / "anchor_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
