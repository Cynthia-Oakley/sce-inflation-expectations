"""Task A: descriptive update dynamics of the real SCE panel.

Everything here is computed on official Q9_mean (real->real metric); the
frozen scorer is used only in the LLM comparison module. All statistics are
descriptive; no significance tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..factual_mechanism_audit import audit_prior, correlation, wquantile
from .data import (
    EXPECTED_ADJACENT_PAIRS,
    EXPECTED_VALID_Q9_PAIRS,
    OVERLAP_NOTE,
    REFERENCE_SHA256,
    VALID_PAIR_DEFINITION,
    WEIGHT_SCOPE_NOTE,
    add_month_equal_weight,
    build_pairs,
    build_valid_pairs,
    load_reference_frame,
    month_index,
)
from .metrics import (
    mean_or_none,
    weighted_bin_index,
    weighted_ols_slope,
    weighted_pearson,
)

QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
GROUP_COLUMNS = ("_AGE_CAT", "_EDU_CAT", "_HH_INC_CAT", "_NUM_CAT")


def prepare_frame() -> pd.DataFrame:
    df = load_reference_frame()
    f = df.copy()
    for k in ["date", "userid", "weight", "Q9_mean", "Q9_iqr"]:
        f[k] = pd.to_numeric(f[k], errors="coerce")
    if f[["date", "userid"]].isna().any().any():
        raise ValueError("invalid panel key")
    f["date"] = f["date"].astype(int)
    return f


def check_acceptance(f: pd.DataFrame) -> dict:
    pairs = build_pairs(f)
    valid = build_valid_pairs(f)
    n_adjacent = len(pairs)
    n_valid = len(valid)
    result = {"adjacent_pairs": n_adjacent, "valid_q9_pairs": n_valid,
              "expected_adjacent_pairs": EXPECTED_ADJACENT_PAIRS,
              "expected_valid_q9_pairs": EXPECTED_VALID_Q9_PAIRS,
              "passed": (n_adjacent == EXPECTED_ADJACENT_PAIRS
                         and n_valid == EXPECTED_VALID_Q9_PAIRS)}
    if not result["passed"]:
        raise AssertionError(
            f"acceptance gate failed: adjacent {n_adjacent} (expected "
            f"{EXPECTED_ADJACENT_PAIRS}), valid {n_valid} (expected "
            f"{EXPECTED_VALID_Q9_PAIRS})")
    return result


def reconcile_with_reference_audit(f: pd.DataFrame) -> dict:
    """Recompute the published reference audit and diff against our monthly stats."""
    ref = audit_prior(f)
    pairs = add_month_equal_weight(build_valid_pairs(f))
    max_share_diff = 0.0
    max_mae_diff = 0.0
    for rec in ref["monthly"]:
        if not rec.get("valid_q9_pairs_n"):
            continue
        month = rec["month"]
        p = pairs[pairs["date"] == month]
        delta = (p["Q9_mean"] - p["previous_Q9_mean"]).to_numpy(float)
        w = p["weight"].to_numpy(float)
        share = float(np.average(np.abs(delta) <= 0.5, weights=w))
        mae = float(np.average(np.abs(delta), weights=w))
        max_share_diff = max(max_share_diff, abs(share - rec["share_absolute_change_at_most_0_5pp"]))
        max_mae_diff = max(max_mae_diff, abs(mae - rec["own_previous_mae_pp"]))
    out = {
        "reference_within_month_centered_q9_correlation": ref["within_month_centered_q9_correlation"],
        "reference_mean_monthly_unweighted_spearman": ref["mean_monthly_unweighted_spearman"],
        "reference_2021_own_previous_mae_month_equal":
            ref["yearly"]["2021"]["own_previous_mae_pp_month_equal"],
        "max_abs_diff_monthly_share_at_most_0_5pp": max_share_diff,
        "max_abs_diff_monthly_own_previous_mae_pp": max_mae_diff,
    }
    if max_share_diff > 1e-9:
        raise AssertionError(f"monthly share reconciliation failed: {max_share_diff}")
    return out


def weighted_quantiles(values, weights, quantiles=QUANTILES) -> dict:
    return {str(q): wquantile(values, weights, q) for q in quantiles}


def _weighted_spearman(x, y, w) -> float | None:
    """Weighted Pearson correlation of (unweighted) ranks."""
    xr = pd.Series(x).rank().to_numpy(float)
    yr = pd.Series(y).rank().to_numpy(float)
    return weighted_pearson(xr, yr, w)


def monthly_stats(pairs: pd.DataFrame) -> list[dict]:
    """Per-month update distribution, ordering and H1/H2 relationship stats."""
    records = []
    for month, p in pairs.groupby("date", sort=True):
        y_prev = p["previous_Q9_mean"].to_numpy(float)
        y_cur = p["Q9_mean"].to_numpy(float)
        w = p["weight"].to_numpy(float)
        delta = y_cur - y_prev
        rec = {
            "month": int(month),
            "n": len(p),
            "weighted_quantiles_delta": weighted_quantiles(delta, w),
            "mean_abs_delta_weighted": float(np.average(np.abs(delta), weights=w)),
            "mean_abs_delta_unweighted": float(np.mean(np.abs(delta))),
            "share_abs_le_0_5pp_weighted": float(np.average(np.abs(delta) <= 0.5, weights=w)),
            "share_delta_positive_weighted": float(np.average(delta > 0, weights=w)),
            "share_delta_negative_weighted": float(np.average(delta < 0, weights=w)),
            "spearman_unweighted": (float(pd.Series(y_prev).corr(pd.Series(y_cur), method="spearman"))
                                    if len(p) > 2 else None),
            "spearman_weighted_rank_pearson": _weighted_spearman(y_prev, y_cur, w),
            "h1": h1_stats_for_month(p),
            "h2": h2_stats_for_month(p),
        }
        records.append(rec)
    return records


def h1_stats_for_month(p: pd.DataFrame) -> dict:
    """d = y_{t-1} - weighted median(y_{t-1}); decile bins and OLS slope of delta ~ d."""
    y_prev = p["previous_Q9_mean"].to_numpy(float)
    w = p["weight"].to_numpy(float)
    delta = (p["Q9_mean"] - p["previous_Q9_mean"]).to_numpy(float)
    m_prev = wquantile(y_prev, w, 0.5)
    d = y_prev - m_prev
    cuts = [wquantile(d, w, q) for q in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)]
    bins = weighted_bin_index(d, w, cuts)
    per_bin = []
    for b in range(10):
        mask = bins == b
        if mask.any():
            per_bin.append({"n": int(mask.sum()),
                            "mean_delta_weighted": float(np.average(delta[mask], weights=w[mask])),
                            "mean_d_weighted": float(np.average(d[mask], weights=w[mask]))})
        else:
            per_bin.append({"n": 0, "mean_delta_weighted": None, "mean_d_weighted": None})
    return {
        "median_prev": m_prev,
        "decile_bins": per_bin,
        "ols_slope_weighted": weighted_ols_slope(d, delta, w),
        "ols_slope_unweighted": weighted_ols_slope(d, delta, None),
    }


def h1_pooled(pairs: pd.DataFrame) -> dict:
    """Month-equal aggregation of the per-month H1 decile curves and slopes."""
    monthly = [h1_stats_for_month(p) for _, p in pairs.groupby("date", sort=True)]
    bins = []
    for b in range(10):
        means = [m["decile_bins"][b]["mean_delta_weighted"] for m in monthly
                 if m["decile_bins"][b]["n"] > 0]
        ds = [m["decile_bins"][b]["mean_d_weighted"] for m in monthly
              if m["decile_bins"][b]["n"] > 0]
        bins.append({
            "bin": b + 1,
            "months_with_pairs": len(means),
            "mean_delta_month_equal": mean_or_none(means),
            "mean_d_month_equal": mean_or_none(ds),
        })
    return {
        "decile_bins_month_equal": bins,
        "mean_monthly_ols_slope_weighted": mean_or_none([m["ols_slope_weighted"] for m in monthly]),
        "mean_monthly_ols_slope_unweighted": mean_or_none([m["ols_slope_unweighted"] for m in monthly]),
        "n_months": len(monthly),
    }


def h2_stats_for_month(p: pd.DataFrame) -> dict:
    """Weighted quartile bins of previous Q9_iqr -> mean|delta| and mean delta."""
    iqr_prev = p["previous_Q9_iqr"].to_numpy(float)
    w = p["weight"].to_numpy(float)
    delta = (p["Q9_mean"] - p["previous_Q9_mean"]).to_numpy(float)
    ok = np.isfinite(iqr_prev)
    if ok.sum() < 4:
        return {"n_used": int(ok.sum()), "quartile_bins": []}
    iqr_prev, w, delta = iqr_prev[ok], w[ok], delta[ok]
    cuts = [wquantile(iqr_prev, w, q) for q in (0.25, 0.5, 0.75)]
    bins = weighted_bin_index(iqr_prev, w, cuts)
    per_bin = []
    for b in range(4):
        mask = bins == b
        per_bin.append({
            "n": int(mask.sum()),
            "mean_abs_delta_weighted": float(np.average(np.abs(delta[mask]), weights=w[mask])),
            "mean_delta_weighted": float(np.average(delta[mask], weights=w[mask])),
            "mean_iqr_prev_weighted": float(np.average(iqr_prev[mask], weights=w[mask])),
        })
    return {"n_used": int(ok.sum()), "quartile_bins": per_bin}


def h2_pooled(pairs: pd.DataFrame) -> dict:
    monthly = [h2_stats_for_month(p) for _, p in pairs.groupby("date", sort=True)]
    monthly = [m for m in monthly if len(m["quartile_bins"]) == 4]
    bins = []
    for b in range(4):
        abs_means = [m["quartile_bins"][b]["mean_abs_delta_weighted"] for m in monthly]
        means = [m["quartile_bins"][b]["mean_delta_weighted"] for m in monthly]
        iqrs = [m["quartile_bins"][b]["mean_iqr_prev_weighted"] for m in monthly]
        bins.append({
            "bin": b + 1,
            "mean_abs_delta_month_equal": mean_or_none(abs_means),
            "mean_delta_month_equal": mean_or_none(means),
            "mean_iqr_prev_month_equal": mean_or_none(iqrs),
            "n_months": len(monthly),
        })
    return {"quartile_bins_month_equal": bins, "n_months": len(monthly)}


def lag2_persistence(f: pd.DataFrame) -> dict:
    """Lag-2 centered correlation on respondents present in 3 consecutive months."""
    frame = f[np.isfinite(f["Q9_mean"]) & np.isfinite(f["weight"]) & (f["weight"] > 0)].copy()
    frame["mi"] = month_index(frame["date"])
    frame = frame.sort_values(["userid", "mi"])
    g = frame.groupby("userid", sort=False)
    frame["y_lag1"] = g["Q9_mean"].shift(1)
    frame["mi_lag1"] = g["mi"].shift(1)
    frame["y_lag2"] = g["Q9_mean"].shift(2)
    frame["mi_lag2"] = g["mi"].shift(2)
    frame["w_lag2"] = g["weight"].shift(2)
    trips = frame[(frame["mi"] - frame["mi_lag1"] == 1)
                  & (frame["mi_lag1"] - frame["mi_lag2"] == 1)
                  & np.isfinite(frame["y_lag2"]) & np.isfinite(frame["w_lag2"])].copy()
    if not len(trips):
        return {"n_triples": 0}
    trips["mw"] = trips["weight"] / trips.groupby("date")["weight"].transform("sum")
    x = trips["y_lag2"].copy()
    y = trips["Q9_mean"].copy()
    spearmans = []
    for month, p in trips.groupby("date"):
        x.loc[p.index] -= np.average(p["y_lag2"], weights=p["weight"])
        y.loc[p.index] -= np.average(p["Q9_mean"], weights=p["weight"])
        if len(p) > 2:
            spearmans.append(float(pd.Series(p["y_lag2"]).corr(p["Q9_mean"], method="spearman")))
    return {
        "n_triples": int(len(trips)),
        "n_months": int(trips["date"].nunique()),
        "within_month_centered_correlation_lag2": correlation(x, y, trips["mw"]),
        "mean_monthly_unweighted_spearman_lag2": mean_or_none(spearmans),
    }


def group_stats(pairs: pd.DataFrame) -> dict:
    """Descriptive update stats per preregistered demographic group."""
    out = {}

    def block(name: str, sub: pd.DataFrame) -> dict:
        if not len(sub):
            return {"n_pairs": 0}
        monthly = monthly_stats(sub)
        return {
            "n_pairs": int(len(sub)),
            "mean_abs_delta_weighted": float(
                np.average(np.abs(sub["Q9_mean"] - sub["previous_Q9_mean"]),
                           weights=sub["weight"])),
            "mean_monthly_spearman_unweighted":
                mean_or_none([m["spearman_unweighted"] for m in monthly]),
            "h1_mean_monthly_ols_slope_weighted":
                mean_or_none([m["h1"]["ols_slope_weighted"] for m in monthly]),
            "h2_quartile_mean_abs_delta_month_equal":
                [b["mean_abs_delta_month_equal"] for b in h2_pooled(sub)["quartile_bins_month_equal"]],
        }

    for label in ("Under 40", "40 to 60", "Over 60"):
        out.setdefault("age", {})[label] = block(f"age {label}", pairs[pairs["_AGE_CAT"] == label])
    edu = pairs["_EDU_CAT"].fillna("")
    out["education"] = {
        "College": block("College", pairs[edu == "College"]),
        "Non-college": block("Non-college", pairs[edu != "College"]),
    }
    for label in ("Under 50k", "50k to 100k", "Over 100k"):
        out.setdefault("income", {})[label] = block(f"income {label}", pairs[pairs["_HH_INC_CAT"] == label])
    for label in ("High", "Low"):
        out.setdefault("numeracy", {})[label] = block(f"numeracy {label}", pairs[pairs["_NUM_CAT"] == label])
    out["group_note"] = (
        "Groups use the current wave's demographic columns (time-invariant in this cache). "
        "Education bins are College vs all other recorded values (Some College / High School / "
        "blank). Missing demographic labels fall into Non-college and are not separately reported. "
        "All group statistics are descriptive; no significance tests were performed."
    )
    return out


def pooled_delta_stats(pairs: pd.DataFrame) -> dict:
    delta = (pairs["Q9_mean"] - pairs["previous_Q9_mean"]).to_numpy(float)
    w_raw = pairs["weight"].to_numpy(float)
    w_me = pairs["month_weight"].to_numpy(float)
    return {
        "quantiles_weighted": weighted_quantiles(delta, w_raw),
        "quantiles_month_equal_weight": weighted_quantiles(delta, w_me),
        "mean_abs_delta_weighted": float(np.average(np.abs(delta), weights=w_raw)),
        "mean_abs_delta_month_equal_weight": float(np.average(np.abs(delta), weights=w_me)),
        "share_abs_le_0_5pp_weighted": float(np.average(np.abs(delta) <= 0.5, weights=w_raw)),
        "share_delta_positive_weighted": float(np.average(delta > 0, weights=w_raw)),
        "share_delta_negative_weighted": float(np.average(delta < 0, weights=w_raw)),
    }


def run_analysis(output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    f = prepare_frame()
    acceptance = check_acceptance(f)
    reconciliation = reconcile_with_reference_audit(f)

    pairs = add_month_equal_weight(build_valid_pairs(f))
    monthly = monthly_stats(pairs)

    centered_pairs = pairs.copy()
    x = centered_pairs["previous_Q9_mean"].copy()
    y = centered_pairs["Q9_mean"].copy()
    spearman_w = []
    for month, p in centered_pairs.groupby("date"):
        x.loc[p.index] -= np.average(p["previous_Q9_mean"], weights=p["weight"])
        y.loc[p.index] -= np.average(p["Q9_mean"], weights=p["weight"])
    for month, p in pairs.groupby("date"):
        spearman_w.append(_weighted_spearman(p["previous_Q9_mean"], p["Q9_mean"], p["weight"]))

    all_pairs = build_pairs(f)
    coverage = all_pairs.groupby("date").size() / f.groupby("date").size()

    summary = {
        "line": "SCE belief dynamics (task A, zero-API)",
        "inputs": {
            "reference_private_parquet": str(load_reference_frame_path()),
            "reference_sha256": REFERENCE_SHA256,
            "rows": int(len(f)),
            "months": int(f["date"].nunique()),
            "unique_respondents": int(f["userid"].nunique()),
        },
        "acceptance": acceptance,
        "reconciliation": reconciliation,
        "pooled_delta": pooled_delta_stats(pairs),
        "monthly": monthly,
        "ordering": {
            "mean_monthly_spearman_unweighted":
                mean_or_none([m["spearman_unweighted"] for m in monthly]),
            "mean_monthly_spearman_weighted_rank_pearson":
                mean_or_none(spearman_w),
            "within_month_centered_q9_correlation":
                reconciliation["reference_within_month_centered_q9_correlation"],
            "lag2": lag2_persistence(f),
            "note": OVERLAP_NOTE,
        },
        "h1_mean_reversion": h1_pooled(pairs),
        "h2_uncertainty_adjustment": h2_pooled(pairs),
        "groups": group_stats(pairs),
        "coverage": {
            "adjacent_coverage_fraction_min": float(coverage.min()),
            "adjacent_coverage_fraction_max": float(coverage.max()),
        },
        "definitions": {
            "valid_pair_definition": VALID_PAIR_DEFINITION,
            "weight_scope_note": WEIGHT_SCOPE_NOTE,
            "overlap_note": OVERLAP_NOTE,
        },
        "interpretation": (
            "Descriptive update statistics on strict calendar-adjacent valid pairs. "
            "H1/H2 are month-equal pooled conditional means; slopes are monthly OLS "
            "averages. No causal or significance claims."),
    }

    summary_path = output_dir / "analysis_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    pairs_out = pairs[["userid", "date", "previous_Q9_mean", "Q9_mean", "previous_Q9_iqr",
                       "weight", "_AGE_CAT", "_EDU_CAT", "_HH_INC_CAT", "_NUM_CAT"]].copy()
    pairs_out = pairs_out.rename(columns={"previous_Q9_mean": "y_prev", "Q9_mean": "y_cur",
                                          "previous_Q9_iqr": "iqr_prev"})
    pairs_out["delta"] = pairs_out["y_cur"] - pairs_out["y_prev"]
    pairs_out.to_parquet(output_dir / "pairs_private.parquet", index=False)
    return summary


def load_reference_frame_path() -> Path:
    from .data import REFERENCE_PARQUET
    return REFERENCE_PARQUET
