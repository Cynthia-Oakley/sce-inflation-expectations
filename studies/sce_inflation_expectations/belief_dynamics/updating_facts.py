"""Six micro facts about how real SCE respondents update inflation expectations.

Zero-API, zero-network descriptive analysis on the audited private reference
cache. Reuses the loading/pairing logic from ``data.py``/``dynamics.py``; the
only new external input is a local ALFRED CPIAUCNS vintage CSV (final-vintage
CPI-U NSA levels) used as the ex-post realized inflation for the
Coibion-Gorodnichenko-style regression (F3a).

All statistics are descriptive. Confidence intervals are clustered by userid
where stated; no causal claims.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..factual_mechanism_audit import correlation, wquantile
from .data import (
    Q9_BIN_COLUMNS,
    REFERENCE_SHA256,
    REPO_ROOT,
    build_valid_pairs,
    legal_bins_mask,
    month_index,
)
from .dynamics import check_acceptance, prepare_frame
from .metrics import weighted_ols_slope

CPI_VINTAGE_CSV = (REPO_ROOT / "data" / "raw" / "lifetime_experience" / "20261012_v1"
                   / "cpi_nsa_vintage_2024-03-12.csv")
CPI_VINTAGE_NOTE = (
    "Local final-vintage CPI-U NSA levels, ALFRED vintage dated 2024-03-12 "
    "(file data/raw/lifetime_experience/20261012_v1/cpi_nsa_vintage_2024-03-12.csv). "
    "Levels run 1913-01..2024-02, so the 12-month YoY is available through 2024-02; "
    "an expectation formed in month t needs YoY(t+12), hence only forecast months "
    "t <= 2023-02 are covered. 2023-03..2025-10 expectations have no local ex-post "
    "realization and are excluded from F3a."
)

INACTION_THRESHOLDS_PP = (0.0, 0.05, 0.1, 0.25)
LUMPY_CUTS_PP = (0.5, 1.0, 2.0)


# ---------------------------------------------------------------------------
# data assembly
# ---------------------------------------------------------------------------

def load_cpi_yoy(path: Path | None = None) -> dict[int, float]:
    """Parse a local ALFRED CPIAUCNS vintage CSV -> {YYYYMM: 12m YoY in %}.

    The CSV has columns observation_date (YYYY-MM-DD) and one value column
    whose name must contain the vintage date (e.g. CPIAUCNS_20240312).
    """
    path = Path(path) if path is not None else CPI_VINTAGE_CSV
    with open(path, newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if len(header) != 2 or not header[1].startswith("CPIAUCNS_"):
            raise ValueError(f"unexpected CPI vintage CSV header: {header}")
        levels: dict[int, float] = {}
        for row in reader:
            if not row or not row[0]:
                continue
            yyyymm = int(row[0][:4]) * 100 + int(row[0][5:7])
            value = row[1].strip()
            if value in ("", "."):
                continue
            levels[yyyymm] = float(value)
    yoy: dict[int, float] = {}
    for m, level in levels.items():
        mi = month_index(m)
        prev_key = (mi - 12 - 1) // 12 * 100 + (mi - 12 - 1) % 12 + 1
        prev = levels.get(prev_key)
        if prev:
            yoy[m] = 100.0 * (level / prev - 1.0)
    return yoy


def shift_month(yyyymm: int, n: int) -> int:
    mi = month_index(int(yyyymm)) + n
    return (mi - 1) // 12 * 100 + (mi - 1) % 12 + 1


def pairs_with_bins(frame: pd.DataFrame) -> pd.DataFrame:
    """Valid adjacent pairs with the ten Q9 bins for both waves attached."""
    valid = build_valid_pairs(frame).copy()
    prev = frame[["userid", "date"] + list(Q9_BIN_COLUMNS)].rename(
        columns={"date": "previous_date"})
    prev.columns = (["userid", "previous_date"]
                    + [f"previous_{c}" for c in Q9_BIN_COLUMNS])
    out = valid.merge(prev, on=["userid", "previous_date"], how="left", validate="m:1")
    prev_cols = [f"previous_{c}" for c in Q9_BIN_COLUMNS]
    if out[prev_cols].isna().any().any():
        raise AssertionError("previous-bin merge produced missing values")
    return out


def month_weighted_medians(frame: pd.DataFrame) -> dict[int, float]:
    """Weighted median Q9_mean per calendar month (finite mean, weight>0)."""
    f = frame[np.isfinite(frame["Q9_mean"]) & np.isfinite(frame["weight"])
              & (frame["weight"] > 0)]
    out = {}
    for month, g in f.groupby("date", sort=True):
        out[int(month)] = float(wquantile(g["Q9_mean"].to_numpy(float),
                                          g["weight"].to_numpy(float), 0.5))
    return out


def _share(mask: np.ndarray, w: np.ndarray | None) -> float:
    mask = np.asarray(mask, bool)
    if w is None:
        return float(mask.mean())
    w = np.asarray(w, float)
    return float(np.average(mask, weights=w))


def _excess_kurtosis(x) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    m2 = np.mean((x - x.mean()) ** 2)
    m4 = np.mean((x - x.mean()) ** 4)
    return float(m4 / m2 ** 2 - 3.0)


# ---------------------------------------------------------------------------
# F1 inaction
# ---------------------------------------------------------------------------

def inaction_stats(pairs: pd.DataFrame) -> dict:
    """Shares of near-zero revisions among valid adjacent pairs, overall and
    by calendar year; includes exact bin-vector equality."""
    delta = (pairs["Q9_mean"] - pairs["previous_Q9_mean"]).to_numpy(float)
    w = pairs["weight"].to_numpy(float)
    cur_bins = pairs[list(Q9_BIN_COLUMNS)].to_numpy(float)
    prev_bins = pairs[[f"previous_{c}" for c in Q9_BIN_COLUMNS]].to_numpy(float)
    identical = (cur_bins == prev_bins).all(axis=1)

    overall = {
        "n_pairs": int(len(pairs)),
        **{f"share_abs_delta_le_{thr:g}pp_unweighted": _share(np.abs(delta) <= thr, None)
           for thr in INACTION_THRESHOLDS_PP},
        **{f"share_abs_delta_le_{thr:g}pp_weighted": _share(np.abs(delta) <= thr, w)
           for thr in INACTION_THRESHOLDS_PP},
        "share_exact_zero_delta_unweighted": _share(delta == 0.0, None),
        "share_exact_zero_delta_weighted": _share(delta == 0.0, w),
        "share_identical_bin_vector_unweighted": _share(identical, None),
        "share_identical_bin_vector_weighted": _share(identical, w),
    }
    by_year = {}
    year = pairs["date"].floordiv(100)
    for yr, g in pairs.groupby(year, sort=True):
        gd = (g["Q9_mean"] - g["previous_Q9_mean"]).to_numpy(float)
        gw = g["weight"].to_numpy(float)
        gb_cur = g[list(Q9_BIN_COLUMNS)].to_numpy(float)
        gb_prev = g[[f"previous_{c}" for c in Q9_BIN_COLUMNS]].to_numpy(float)
        by_year[str(int(yr))] = {
            "n_pairs": int(len(g)),
            "share_exact_zero_delta_unweighted": _share(gd == 0.0, None),
            "share_exact_zero_delta_weighted": _share(gd == 0.0, gw),
            "share_abs_delta_le_0.25pp_unweighted": _share(np.abs(gd) <= 0.25, None),
            "share_abs_delta_le_0.25pp_weighted": _share(np.abs(gd) <= 0.25, gw),
            "share_identical_bin_vector_unweighted": _share((gb_cur == gb_prev).all(axis=1), None),
        }
    return {"overall": overall, "by_year": by_year}


# ---------------------------------------------------------------------------
# F2 lumpy revisions
# ---------------------------------------------------------------------------

def lumpy_stats(pairs: pd.DataFrame) -> dict:
    """Distribution of revisions among movers (|delta|>0) and tail shares."""
    delta = (pairs["Q9_mean"] - pairs["previous_Q9_mean"]).to_numpy(float)
    w = pairs["weight"].to_numpy(float)
    moved = np.abs(delta) > 0.0
    dm, wm = delta[moved], w[moved]

    def wq(x, ww, q):
        return float(wquantile(x, ww, q))

    out = {
        "n_pairs": int(len(pairs)),
        "n_movers": int(moved.sum()),
        "mover_quantiles_weighted": {str(q): wq(dm, wm, q) for q in (0.05, 0.25, 0.5, 0.75, 0.95)},
        "mover_quantiles_unweighted": {str(q): float(np.quantile(dm, q))
                                       for q in (0.05, 0.25, 0.5, 0.75, 0.95)},
        "excess_kurtosis_all_delta": _excess_kurtosis(delta),
        "excess_kurtosis_abs_delta_movers": _excess_kurtosis(np.abs(dm)),
        "mean_abs_delta_movers_weighted": float(np.average(np.abs(dm), weights=wm)),
        "mean_abs_delta_movers_unweighted": float(np.mean(np.abs(dm))),
    }
    for cut in LUMPY_CUTS_PP:
        out[f"share_abs_delta_gt_{cut:g}pp_unweighted"] = _share(np.abs(delta) > cut, None)
        out[f"share_abs_delta_gt_{cut:g}pp_weighted"] = _share(np.abs(delta) > cut, w)
    return out


# ---------------------------------------------------------------------------
# F3a Coibion-Gorodnichenko-style ex-post error on revision
# ---------------------------------------------------------------------------

def _month_demean(values, dates) -> np.ndarray:
    s = pd.Series(np.asarray(values, float), index=np.asarray(dates))
    return (s - s.groupby(level=0).transform("mean")).to_numpy(float)


def _cluster_slope_se(x: np.ndarray, resid: np.ndarray, clusters: np.ndarray,
                      n_params: int) -> tuple[float, float]:
    """Slope-only OLS SE clustered on `clusters` (one regressor, no intercept;
    x must already be demeaned within cluster FE)."""
    x = np.asarray(x, float)
    r = np.asarray(resid, float)
    xx = float(x @ x)
    slope_var_scale = 1.0 / xx
    meat = 0.0
    for g in np.unique(clusters):
        s = x[clusters == g] @ r[clusters == g]
        meat += s * s
    n = len(x)
    g_n = len(np.unique(clusters))
    corr = (g_n / (g_n - 1.0)) * ((n - 1.0) / (n - n_params))
    var = corr * meat * slope_var_scale ** 2
    return slope_var_scale, float(np.sqrt(max(var, 0.0)))


def cg_regression(pairs: pd.DataFrame, cpi_yoy: dict[int, float]) -> dict:
    """e_{i,t} = pi(t+12) - Q9_mean_{i,t} on r_{i,t} = Q9_mean_{i,t} - Q9_mean_{i,t-1},
    pooled with calendar-month fixed effects, clustered by userid.

    Positive slope => average revisions under-react to future inflation
    surprises (information rigidity, CG 2015 interpretation).
    """
    dates = pairs["date"].to_numpy(int)
    realized = np.array([cpi_yoy.get(shift_month(d, 12), np.nan) for d in dates], float)
    ok = np.isfinite(realized)
    sub = pairs[ok].copy()
    realized = realized[ok]
    e = realized - sub["Q9_mean"].to_numpy(float)
    r = (sub["Q9_mean"] - sub["previous_Q9_mean"]).to_numpy(float)
    dates_sub = sub["date"]
    x = _month_demean(pd.Series(r), dates_sub)
    y = _month_demean(pd.Series(e), dates_sub)
    ok2 = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok2], y[ok2]
    sub = sub[ok2]
    xx = float(x @ x)
    slope = float(x @ y / xx)
    resid = y - slope * x
    r2 = float(1.0 - (resid @ resid) / (y @ y))
    n_months = int(sub["date"].nunique())
    clusters = sub["userid"].to_numpy()
    _, se = _cluster_slope_se(x, resid, clusters, n_months + 1)
    # month-equal weighted variant (weighted slope on month-demeaned data)
    sub_w = sub.copy()
    sub_w["_x"] = r[ok2]
    sub_w["_y"] = e[ok2]
    xw, yw = [], []
    for _, g in sub_w.groupby("date"):
        ww = g["weight"].to_numpy(float)
        xw.append(g["_x"].to_numpy(float) - np.average(g["_x"], weights=ww))
        yw.append(g["_y"].to_numpy(float) - np.average(g["_y"], weights=ww))
    xw = np.concatenate(xw)
    yw = np.concatenate(yw)
    slope_weighted = float((xw @ yw) / (xw @ xw)) if (xw @ xw) > 0 else None

    by_year = {}
    for yr, g in sub.groupby(sub["date"].floordiv(100), sort=True):
        gx = _month_demean(
            pd.Series((g["Q9_mean"] - g["previous_Q9_mean"]).to_numpy(float),
                      index=g.index), g["date"])
        gy = _month_demean(pd.Series(
            [cpi_yoy[shift_month(int(d), 12)] - m for d, m in
             zip(g["date"], g["Q9_mean"])], index=g.index), g["date"])
        okk = np.isfinite(gx) & np.isfinite(gy)
        if okk.sum() > 10 and (gx[okk] @ gx[okk]) > 0:
            by_year[str(int(yr))] = {
                "n_pairs": int(okk.sum()),
                "slope_unweighted_month_fe": float(gx[okk] @ gy[okk] / (gx[okk] @ gx[okk])),
            }
    return {
        "n_pairs": int(len(sub)),
        "n_months": n_months,
        "first_forecast_month": int(sub["date"].min()),
        "last_forecast_month": int(sub["date"].max()),
        "slope_pooled_month_fe_unweighted": slope,
        "se_clustered_by_userid": se,
        "ci95_clustered": [slope - 1.96 * se, slope + 1.96 * se],
        "r_squared": r2,
        "slope_pooled_month_demeaned_weighted": slope_weighted,
        "by_year": by_year,
        "definition_note": ("e_{i,t}=realized CPI-U NSA 12m YoY at t+12 minus Q9_mean_{i,t}; "
                            "r_{i,t}=Q9_mean_{i,t}-Q9_mean_{i,t-1}; both demeaned by calendar "
                            "month; SE clustered by userid (person-level)."),
        "coverage_note": CPI_VINTAGE_NOTE,
    }


# ---------------------------------------------------------------------------
# F3b mean reversion with attenuation caveats
# ---------------------------------------------------------------------------

def mean_reversion_stats(pairs: pd.DataFrame, medians: dict[int, float],
                         frame: pd.DataFrame) -> dict:
    """delta_{i,t} on d_{i,t-1} = Q9_mean_{i,t-1} - median_t (month FE built in
    via the median regressor; month-demeaned slope also reported). Robustness:
    (i) IV using the t-2 deviation, (ii) movers with |d|>1pp."""
    d_prev = (pairs["previous_Q9_mean"]
              - pairs["date"].map(medians)).to_numpy(float)
    delta = (pairs["Q9_mean"] - pairs["previous_Q9_mean"]).to_numpy(float)
    w = pairs["weight"].to_numpy(float)
    ok = np.isfinite(d_prev) & np.isfinite(delta)
    d_prev, delta, w = d_prev[ok], delta[ok], w[ok]
    slope_u = weighted_ols_slope(d_prev, delta, None)
    slope_w = weighted_ols_slope(d_prev, delta, w)

    # month-demeaned unweighted slope (month FE explicit)
    p = pairs[ok].copy()
    p["_d"] = d_prev
    p["_y"] = delta
    x = _month_demean(p["_d"], p["date"])
    y = _month_demean(p["_y"], p["date"])
    slope_fe = float(x @ y / (x @ x))

    # IV: z = deviation of the person's own t-2 wave (vs the t-2 month median),
    # built from strict consecutive triples.
    fw = frame[np.isfinite(frame["Q9_mean"]) & np.isfinite(frame["weight"])
               & (frame["weight"] > 0)][["userid", "date", "Q9_mean"]].copy()
    fw["dev"] = fw["Q9_mean"] - fw["date"].map(medians)
    fw = fw[np.isfinite(fw["dev"])].sort_values(["userid", "date"])
    fw["mi"] = month_index(fw["date"].to_numpy(int))
    g = fw.groupby("userid", sort=False)
    fw["y_lag1"] = g["Q9_mean"].shift(1)
    fw["mi_lag1"] = g["mi"].shift(1)
    fw["dev_lag1"] = g["dev"].shift(1)
    fw["dev_lag2"] = g["dev"].shift(2)
    tri = fw[(fw["mi"] - fw["mi_lag1"] == 1)
             & (fw["mi_lag1"] - g["mi"].shift(2) == 1)
             & np.isfinite(fw["dev_lag2"])]
    z = tri["dev_lag2"].to_numpy(float)
    xm = tri["dev_lag1"].to_numpy(float)
    ym = (tri["Q9_mean"] - tri["y_lag1"]).to_numpy(float)
    okm = np.isfinite(z) & np.isfinite(xm) & np.isfinite(ym)
    z, xm, ym = z[okm], xm[okm], ym[okm]
    first_stage = weighted_ols_slope(z, xm, None)
    beta_iv = float((z @ ym) / (z @ xm)) if (z @ xm) != 0 else None

    big = np.abs(d_prev) > 1.0
    slope_big = weighted_ols_slope(d_prev[big], delta[big], None)
    return {
        "n_pairs": int(len(d_prev)),
        "slope_unweighted": slope_u,
        "slope_weighted": slope_w,
        "slope_month_fe_unweighted": slope_fe,
        "iv_tminus2_deviation": {
            "n_triples": int(okm.sum()),
            "first_stage_slope_z_on_x": first_stage,
            "beta_iv": beta_iv,
        },
        "subsample_abs_dev_gt_1pp": {
            "n_pairs": int(big.sum()),
            "slope_unweighted": slope_big,
        },
        "caveat": (
            "OLS slope suffers classical attenuation: Q9_mean is a noisy proxy "
            "for the latent belief, so the true mean-reversion rate is less "
            "negative (closer to 0) than the OLS estimate; the IV/t-2 and "
            "large-deviation variants bound the attenuation but the t-2 "
            "instrument is weakly correlated with the t-1 deviation and the "
            "large-deviation subset is selected. Consistent with the -0.44 "
            "caveat in docs/workstreams/20261013_behavior/codex_results.md."),
    }


# ---------------------------------------------------------------------------
# F4 heaping
# ---------------------------------------------------------------------------

def heaping_stats(frame: pd.DataFrame) -> dict:
    """Rounding structure of the raw ten-bin probability answers."""
    ok = (legal_bins_mask(frame) & np.isfinite(frame["Q9_mean"])
          & np.isfinite(frame["weight"]) & (frame["weight"] > 0))
    f = frame[ok]
    bins = np.round(f[list(Q9_BIN_COLUMNS)].to_numpy(float), 6)
    w = f["weight"].to_numpy(float)
    nz = bins[bins > 0]
    nz_w = np.repeat(w, (bins > 0).sum(axis=1))
    nz_int = np.round(nz)
    n_nonzero_cells = int((bins > 0).sum())
    out = {
        "n_person_months": int(len(f)),
        "n_nonzero_cells": n_nonzero_cells,
        "share_nonzero_divisible_by_5_unweighted": float(np.mean(nz_int % 5 == 0)),
        "share_nonzero_divisible_by_5_weighted": float(np.average(nz_int % 5 == 0, weights=nz_w)),
        "share_nonzero_divisible_by_10_unweighted": float(np.mean(nz_int % 10 == 0)),
        "share_nonzero_divisible_by_10_weighted": float(np.average(nz_int % 10 == 0, weights=nz_w)),
        "nonzero_count_distribution": {},
    }
    counts = (bins > 0).sum(axis=1)
    for k in range(1, 11):
        out["nonzero_count_distribution"][str(k)] = {
            "share_person_months_unweighted": float(np.mean(counts == k)),
            "share_person_months_weighted": _share(counts == k, w),
        }
    vec = [tuple(int(v) for v in row) for row in bins]
    vc = pd.Series(vec).value_counts()
    out["top_vectors"] = [
        {"vector": list(idx), "count": int(c),
         "share_person_months": float(c / len(f))}
        for idx, c in vc.head(10).items()
    ]
    out["note"] = ("Divisibility is evaluated on rounded non-zero cell values; "
                   "cells are percentages summing to 100.")
    return out


# ---------------------------------------------------------------------------
# F5 stable interpersonal differences
# ---------------------------------------------------------------------------

def _valid_person_months(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[np.isfinite(frame["Q9_mean"]) & np.isfinite(frame["weight"])
                 & (frame["weight"] > 0)][["userid", "date", "Q9_mean", "weight"]].copy()


def variance_decomposition(frame: pd.DataFrame, medians: dict[int, float],
                           min_months: int = 6) -> dict:
    """Between-person share of the variance of deviations from the monthly
    weighted median, restricted to persons with >= min_months valid waves."""
    f = _valid_person_months(frame)
    f["dev"] = f["Q9_mean"] - f["date"].map(medians)
    f = f[np.isfinite(f["dev"])]
    keep = f.groupby("userid")["dev"].size()
    keep = keep[keep >= min_months].index
    f = f[f["userid"].isin(keep)]
    gm = f["dev"].mean()
    pm = f.groupby("userid")["dev"].mean()
    sizes = f.groupby("userid")["dev"].size()
    total_ss = float(((f["dev"] - gm) ** 2).sum())
    between_ss = float((sizes * (pm - gm) ** 2).sum())
    # weighted variant: weight person-months by their sampling weight
    fw = f.copy()
    gmw = np.average(fw["dev"], weights=fw["weight"])
    between_w = 0.0
    total_w = float((fw["weight"] * (fw["dev"] - gmw) ** 2).sum())
    for uid, g in fw.groupby("userid"):
        pmw = np.average(g["dev"], weights=g["weight"])
        between_w += float(g["weight"].sum() * (pmw - gmw) ** 2)
    return {
        "min_months": int(min_months),
        "n_person_months": int(len(f)),
        "n_persons": int(f["userid"].nunique()),
        "between_share_unweighted": between_ss / total_ss,
        "between_share_weighted": between_w / total_w,
        "mean_person_months": float(sizes.mean()),
        "definition": ("dev_{i,t}=Q9_mean_{i,t}-weighted monthly median; "
                       "between share = sum_i n_i*(mean_i-mean)^2 / total SS."),
    }


def persistence_regression(pairs: pd.DataFrame, medians: dict[int, float]) -> dict:
    """dev_{i,t} on dev_{i,t-1} (both vs own-month weighted median)."""
    x = (pairs["previous_Q9_mean"] - pairs["date"].map(medians)).to_numpy(float)
    y = (pairs["Q9_mean"] - pairs["date"].map(medians)).to_numpy(float)
    w = pairs["weight"].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y, w = x[ok], y[ok], w[ok]
    slope_u = weighted_ols_slope(x, y, None)
    xm = x - x.mean()
    ym = y - y.mean()
    r2 = float(1 - ((ym - slope_u * xm) ** 2).sum() / (ym ** 2).sum())
    return {
        "n_pairs": int(len(x)),
        "slope_unweighted": slope_u,
        "slope_weighted": weighted_ols_slope(x, y, w),
        "r_squared_unweighted": r2,
        "note": ("Overlapping 12-month forecast windows mechanically inflate the "
                 "lag-1 persistence; see OVERLAP_NOTE in data.py."),
    }


def split_half(frame: pd.DataFrame, medians: dict[int, float],
               min_months: int = 6) -> dict:
    """Correlation between odd-wave and even-wave person means of the
    month-median deviation (trait stability check)."""
    f = _valid_person_months(frame)
    f["dev"] = f["Q9_mean"] - f["date"].map(medians)
    f = f[np.isfinite(f["dev"])].sort_values(["userid", "date"])
    f["wave_idx"] = f.groupby("userid").cumcount()
    keep = f.groupby("userid")["dev"].size()
    keep = keep[keep >= min_months].index
    f = f[f["userid"].isin(keep)]
    odd = f[f["wave_idx"] % 2 == 1].groupby("userid")["dev"].mean()
    even = f[f["wave_idx"] % 2 == 0].groupby("userid")["dev"].mean()
    both = pd.concat([odd.rename("odd"), even.rename("even")], axis=1).dropna()
    r = float(both["odd"].corr(both["even"]))
    return {
        "min_months": int(min_months),
        "n_persons": int(len(both)),
        "correlation_odd_even_person_means": r,
        "definition": ("waves counted per person in chronological order starting "
                       "at 0; odd index = 1st,3rd,... valid wave."),
    }


# ---------------------------------------------------------------------------
# F6 update-type distribution
# ---------------------------------------------------------------------------

def person_type_frame(pairs: pd.DataFrame, frame: pd.DataFrame,
                      min_pairs: int = 8) -> pd.DataFrame:
    """Per-person update primitives: p_i = share of |delta|>0.05pp,
    m_i = mean |delta| among movers, l_i = long-run mean level."""
    delta = (pairs["Q9_mean"] - pairs["previous_Q9_mean"]).to_numpy(float)
    movers = np.abs(delta) > 0.05
    recs = []
    pm = pairs[["userid", "date"]].copy()
    pm["abs_delta"] = np.abs(delta)
    pm["mover"] = movers
    for uid, g in pm.groupby("userid"):
        if len(g) < min_pairs:
            continue
        m_i = float(g.loc[g["mover"], "abs_delta"].mean()) if g["mover"].any() else 0.0
        recs.append({"userid": int(uid), "n_pairs": int(len(g)),
                     "p_update": float(g["mover"].mean()), "m_size_pp": m_i})
    pf = pd.DataFrame(recs)
    levels = (_valid_person_months(frame).groupby("userid")["Q9_mean"].mean()
              .rename("level_pp").reset_index())
    pf = pf.merge(levels, on="userid", how="left")
    return pf


def kmeans_fit(X: np.ndarray, k: int, n_init: int = 50,
               seed: int = 20261019) -> tuple[np.ndarray, np.ndarray, float]:
    """Hand-written Lloyd k-means on standardized columns; best of n_init runs."""
    X = np.asarray(X, float)
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_init):
        centers = Z[rng.choice(len(Z), size=k, replace=False)].copy()
        labels = np.zeros(len(Z), int)
        for _ in range(200):
            dist = ((Z[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            new_labels = dist.argmin(axis=1)
            if (new_labels == labels).all() and _ > 0:
                break
            labels = new_labels
            for j in range(k):
                mask = labels == j
                if mask.any():
                    centers[j] = Z[mask].mean(axis=0)
        inertia = float(((Z - centers[labels]) ** 2).sum())
        if best is None or inertia < best[2]:
            best = (labels.copy(), centers.copy(), inertia)
    return best


def type_classification(pf: pd.DataFrame, k: int) -> dict:
    X = pf[["p_update", "m_size_pp", "level_pp"]].to_numpy(float)
    labels, _, inertia = kmeans_fit(X, k)
    pf = pf.copy()
    pf["cluster"] = labels
    clusters = []
    for j in range(k):
        g = pf[pf["cluster"] == j]
        clusters.append({
            "cluster": j,
            "n_persons": int(len(g)),
            "share_persons": float(len(g) / len(pf)),
            "p_update_mean": float(g["p_update"].mean()),
            "p_update_median": float(g["p_update"].median()),
            "m_size_pp_mean": float(g["m_size_pp"].mean()),
            "m_size_pp_median": float(g["m_size_pp"].median()),
            "level_pp_mean": float(g["level_pp"].mean()),
            "level_pp_median": float(g["level_pp"].median()),
        })
    clusters.sort(key=lambda c: c["p_update_mean"])
    return {"k": k, "inertia_standardized": inertia, "clusters": clusters,
            "n_persons": int(len(pf))}


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def run_analysis(output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir()

    f = prepare_frame()
    acceptance = check_acceptance(f)
    medians = month_weighted_medians(f)
    pairs = pairs_with_bins(f)
    cpi_yoy = load_cpi_yoy()

    f1 = inaction_stats(pairs)
    f2 = lumpy_stats(pairs)
    f3a = cg_regression(pairs, cpi_yoy)
    f3b = mean_reversion_stats(pairs, medians, f)
    f4 = heaping_stats(f)
    f5a = variance_decomposition(f, medians)
    f5b = persistence_regression(pairs, medians)
    f5c = split_half(f, medians)
    pf = person_type_frame(pairs, f)
    f6_3 = type_classification(pf, 3)
    f6_4 = type_classification(pf, 4)
    pf.to_parquet(output_dir / "persons_private.parquet", index=False)

    summary = {
        "line": "SCE updating micro facts F1-F6 (zero-API)",
        "inputs": {
            "reference_private_parquet": "outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet",
            "reference_sha256": REFERENCE_SHA256,
            "rows": int(len(f)),
            "months": int(f["date"].nunique()),
            "unique_respondents": int(f["userid"].nunique()),
            "cpi_vintage_csv": str(CPI_VINTAGE_CSV),
        },
        "acceptance": acceptance,
        "F1_inaction": f1,
        "F2_lumpy_revisions": f2,
        "F3a_cg_rigidity": f3a,
        "F3b_mean_reversion": f3b,
        "F4_heaping": f4,
        "F5a_variance_decomposition": f5a,
        "F5b_persistence": f5b,
        "F5c_split_half": f5c,
        "F6_update_types": {"min_pairs": 8, "k3": f6_3, "k4": f6_4},
        "interpretation": (
            "Descriptive micro facts on the 103,630 strict calendar-adjacent valid "
            "pairs. Weighted = current-wave sampling weights (cross-sectional scope); "
            "month-equal weighting noted per statistic. No causal claims."),
    }
    (output_dir / "analysis_summary.json").write_text(json.dumps(summary, indent=2))

    fig_data = {
        "delta": (pairs["Q9_mean"] - pairs["previous_Q9_mean"]).to_numpy(float),
        "d_prev": (pairs["previous_Q9_mean"] - pairs["date"].map(medians)).to_numpy(float),
        "pairs": pairs,
    }
    _write_figures(f1, f2, f3a, f3b, f4, f5a, f5c, pf, f6_4, fig_data, figures_dir)
    return summary


def _save(fig, figures_dir: Path, name: str) -> None:
    fig.tight_layout()
    fig.savefig(figures_dir / f"{name}.png", dpi=150)
    fig.savefig(figures_dir / f"{name}.svg")
    import matplotlib.pyplot as plt
    plt.close(fig)


def _write_figures(f1, f2, f3a, f3b, f4, f5a, f5c, pf, f6_4, fig_data,
                   figures_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # F1: inaction shares by year
    years = sorted(f1["by_year"])
    zero_w = [f1["by_year"][y]["share_exact_zero_delta_weighted"] for y in years]
    q25_w = [f1["by_year"][y]["share_abs_delta_le_0.25pp_weighted"] for y in years]
    zero_u = [f1["by_year"][y]["share_exact_zero_delta_unweighted"] for y in years]
    q25_u = [f1["by_year"][y]["share_abs_delta_le_0.25pp_unweighted"] for y in years]
    xpos = np.arange(len(years))
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(xpos, zero_w, "o-", label="exact 0 (weighted)")
    ax.plot(xpos, q25_w, "s-", label="|delta|<=0.25pp (weighted)")
    ax.plot(xpos, zero_u, "o--", color="0.6", label="exact 0 (unweighted)")
    ax.plot(xpos, q25_u, "s--", color="0.8", label="|delta|<=0.25pp (unweighted)")
    ax.set_xticks(xpos)
    ax.set_xticklabels(years, rotation=45)
    ax.set_ylabel("share of adjacent pairs")
    ax.set_title("F1 inaction: share of near-zero revisions by year")
    ax.legend()
    ax.grid(alpha=0.3)
    _save(fig, figures_dir, "f1_inaction_by_year")

    # F2: delta histogram, full range and zoom on the 0 spike
    delta = fig_data["delta"]
    delta = delta[np.isfinite(delta)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].hist(delta, bins=np.linspace(-25, 25, 101), color="steelblue")
    axes[0].set_title("revision delta = Q9_mean_t - Q9_mean_t-1 (pp)")
    axes[0].set_xlabel("delta (pp)")
    axes[0].set_ylabel("pairs")
    axes[1].hist(delta, bins=np.linspace(-3, 3, 121), color="darkorange")
    axes[1].set_title("zoom [-3, +3] pp: spike at 0")
    axes[1].set_xlabel("delta (pp)")
    axes[1].set_ylabel("pairs")
    _save(fig, figures_dir, "f2_delta_histogram")

    # F3: CG slope by year + mean-reversion summary bar
    yrs = sorted(f3a["by_year"])
    slopes = [f3a["by_year"][y]["slope_unweighted_month_fe"] for y in yrs]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].bar(yrs, slopes, color="seagreen")
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].axhline(f3a["slope_pooled_month_fe_unweighted"], color="red", ls="--",
                    label=f"pooled {f3a['slope_pooled_month_fe_unweighted']:.3f}")
    axes[0].set_title("F3a CG slope by forecast year (e on r, month FE)")
    axes[0].set_ylabel("slope")
    axes[0].legend()
    axes[0].tick_params(axis="x", rotation=45)
    labels = ["OLS", "OLS |d|>1pp", "IV (t-2 dev)"]
    vals = [f3b["slope_unweighted"], f3b["subsample_abs_dev_gt_1pp"]["slope_unweighted"],
            f3b["iv_tminus2_deviation"]["beta_iv"]]
    axes[1].bar(labels, vals, color=["steelblue", "darkorange", "purple"])
    axes[1].axhline(0, color="k", lw=0.8)
    axes[1].set_title("F3b mean-reversion slope robustness")
    axes[1].set_ylabel("slope of delta on deviation")
    _save(fig, figures_dir, "f3_rigidity_and_mean_reversion")

    # F4: nonzero-bin count distribution + top vectors
    ks = list(range(1, 11))
    cnt_u = [f4["nonzero_count_distribution"][str(k)]["share_person_months_unweighted"]
             for k in ks]
    cnt_w = [f4["nonzero_count_distribution"][str(k)]["share_person_months_weighted"]
             for k in ks]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    axes[0].bar([str(k) for k in ks], cnt_u, color="steelblue", label="unweighted")
    axes[0].plot([str(k) for k in ks], cnt_w, "o-", color="darkorange", label="weighted")
    axes[0].set_title("F4 number of non-zero bins per person-wave")
    axes[0].set_xlabel("non-zero bins (of 10)")
    axes[0].set_ylabel("share of person-months")
    axes[0].legend()
    top = f4["top_vectors"]
    names = ["/".join(str(v) for v in t["vector"]) for t in top]
    shares = [t["share_person_months"] for t in top]
    axes[1].barh(range(len(top)), shares, color="seagreen")
    axes[1].set_yticks(range(len(top)))
    axes[1].set_yticklabels(names, fontsize=7)
    axes[1].invert_yaxis()
    axes[1].set_title("top-10 most common bin vectors")
    axes[1].set_xlabel("share of person-months")
    _save(fig, figures_dir, "f4_heaping")

    # F5: trait stability
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].bar(["between share\n(unweighted)", "between share\n(weighted)"],
                [f5a["between_share_unweighted"], f5a["between_share_weighted"]],
                color=["steelblue", "darkorange"])
    axes[0].set_ylim(0, 1)
    axes[0].set_title("F5a between-person variance share of deviations")
    axes[0].set_ylabel("share of total variance")
    axes[1].axis("off")
    axes[1].text(0.1, 0.6, f"split-half (odd vs even waves)\n"
                 f"person-mean correlation = {f5c['correlation_odd_even_person_means']:.3f}\n"
                 f"n persons = {f5c['n_persons']}", fontsize=12)
    axes[1].set_title("F5c trait stability")
    _save(fig, figures_dir, "f5_trait_stability")

    # F6: p x m scatter colored by cluster (k=4)
    X = pf[["p_update", "m_size_pp", "level_pp"]].to_numpy(float)
    labels, _, _ = kmeans_fit(X, f6_4["k"])
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    ax.scatter(pf["p_update"], pf["m_size_pp"], c=labels, cmap="tab10", s=8, alpha=0.5)
    ax.set_xlabel("p_i = share of revisions with |delta|>0.05pp")
    ax.set_ylabel("m_i = mean |delta| among movers (pp)")
    ax.set_title("F6 update types (k-means k=4 on p, m, level)")
    _save(fig, figures_dir, "f6_update_types")
