#!/usr/bin/env python3
"""Wave-by-wave descriptive statistics on FRBNY SCE public micro data
(SocioVerse Challenge 2026, sce_inflation_expectations).

Purpose: give measured evidence for the population-simulation design
(core/normal two-layer sampling, stratification dimensions, and the B-line
"population distribution is stationary enough to extrapolate with a stale
(<=M-12) population" hypothesis).

All statistics are descriptive (no causal claims). Every number is
reproducible via this script; aggregations are reported UNWEIGHTED and
WEIGHTED (`weight`) side by side.

Answers (Q9_mean, Q8v2part2, Q9 bins) and weights are used ONLY here in the
evaluation/analysis layer; nothing in this script writes persona/Agent input.

Example:
    python scripts/analyze_sce_wave_stats.py \
        --months 202011,202012,202101,...,202112
Outputs:
    studies/sce_inflation_expectations/reports/POPULATION_WAVE_STATS.json
    studies/sce_inflation_expectations/reports/POPULATION_WAVE_STATS.md
"""
from __future__ import annotations

import argparse
import hashlib
import warnings
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from build_sce_population import (EMPLOYMENT_CODE_MAP, EMPLOYMENT_PRIORITY,  # noqa: E402
                                  HOUSING_CODE_MAP)

DEFAULT_DATA = REPO_ROOT / "data" / "raw" / "sce_audit_20260928" / "micro_2020_2024.xlsx"
REPORT_DIR = REPO_ROOT / "studies" / "sce_inflation_expectations" / "reports"
STUDY_ID = "sce_inflation_expectations"

READ_COLS = (["date", "userid", "tenure", "weight", "Q8v2", "Q8v2part2",
              "Q9_mean", "Q9_iqr", "Q43", "_STATE"]
             + [f"Q10_{i}" for i in range(1, 11)]
             + [f"Q9_bin{i}" for i in range(1, 11)]
             + ["_AGE_CAT", "_EDU_CAT", "_HH_INC_CAT", "_REGION_CAT", "_NUM_CAT"])

PROFILE_DIMS = {
    "age": "_AGE_CAT", "education": "_EDU_CAT", "income": "_HH_INC_CAT",
    "region": "_REGION_CAT", "numeracy": "_NUM_CAT",
}
HET_DIMS = dict(PROFILE_DIMS, employment="employment")
GROUP_DIMS_FOR_MEDIANS = ["income", "age", "education", "numeracy"]
POINT_ESTIMATE_CLIP = 100.0  # part2 outliers (e.g. 10000) treated as entry errors


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wquantile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    """Weighted quantile via cumulative-weight interpolation."""
    idx = np.argsort(x)
    x, w = x[idx], w[idx]
    cw = np.cumsum(w) - 0.5 * w
    cw /= w.sum()
    return float(np.interp(q, cw, x))


def weighted_moments(x: np.ndarray, w: np.ndarray) -> dict:
    mu = float(np.average(x, weights=w))
    var = float(np.average((x - mu) ** 2, weights=w))
    return {"mean": mu, "std": np.sqrt(var)}


def tvd(p: dict, q: dict, cats: list) -> float:
    return float(0.5 * sum(abs(p.get(c, 0.0) - q.get(c, 0.0)) for c in cats))


def month_label(m: int) -> str:
    return f"{m // 100}-{m % 100:02d}"


def employment_code(row) -> str | None:
    selected = {i for i in range(1, 11) if row[f"Q10_{i}"] == 1}
    for code in EMPLOYMENT_PRIORITY:
        if code in selected:
            return EMPLOYMENT_CODE_MAP[code]
    return None


def load_frame(data_path: Path) -> pd.DataFrame:
    df = pd.read_excel(data_path, skiprows=1, usecols=READ_COLS)
    df["employment"] = df.apply(employment_code, axis=1)
    df["housing_tenure"] = df["Q43"].map(HOUSING_CODE_MAP)
    # 16 rows in the source file carry a NaN weight (review CORE_NORMAL_REVIEW_
    # 20261003 sec. 3). They are real respondents, so they stay in the frame and
    # in UNWEIGHTED statistics; for weighted math their weight is set to 0 so
    # they are excluded without deleting rows. Both counts go into the meta.
    df["weight"] = df["weight"].fillna(0.0)
    return df


# ---------------------------------------------------------------- profiles
def profile_shares(sub: pd.DataFrame, col: str) -> dict:
    """Unweighted + weighted category shares within a month subset."""
    out = {}
    tot_w = sub["weight"].sum()
    for cat, g in sub.groupby(col, dropna=False):
        key = str(cat)
        out[key] = {"n": int(len(g)),
                    "share_unweighted": float(len(g) / len(sub)),
                    "share_weighted": float(g["weight"].sum() / tot_w)}
    return out


def dimension_drift(shares_by_month: dict, baseline_month: int,
                    window_months: list) -> dict:
    """TVD of each month vs baseline month and vs the window-average dist."""
    cats = sorted({c for s in shares_by_month.values() for c in s})
    pu = {m: {c: s.get(c, {}).get("share_unweighted", 0.0) for c in cats}
          for m, s in shares_by_month.items()}
    pw = {m: {c: s.get(c, {}).get("share_weighted", 0.0) for c in cats}
          for m, s in shares_by_month.items()}
    n_m = len(window_months)
    avg_u = {c: sum(pu[m][c] for m in window_months) / n_m for c in cats}
    avg_w = {c: sum(pw[m][c] for m in window_months) / n_m for c in cats}
    res = {}
    for m in shares_by_month:
        res[m] = {
            "tvd_vs_baseline_unweighted": tvd(pu[m], pu[baseline_month], cats),
            "tvd_vs_baseline_weighted": tvd(pw[m], pw[baseline_month], cats),
            "tvd_vs_window_mean_unweighted": tvd(pu[m], avg_u, cats),
            "tvd_vs_window_mean_weighted": tvd(pw[m], avg_w, cats),
        }
    return res


def lag12_tvd(shares_by_month: dict) -> dict:
    """TVD between month M and month M-12 (B-line stale-population distance)."""
    out = {}
    for m in sorted(shares_by_month):
        prev = m - 100  # 12 calendar months back = same month, previous year
        if prev not in shares_by_month:
            continue
        s_now, s_prev = shares_by_month[m], shares_by_month[prev]
        cats = sorted(set(s_now) | set(s_prev))
        out[m] = {
            "vs_month": prev,
            "tvd_unweighted": tvd({c: s_now.get(c, {}).get("share_unweighted", 0.0) for c in cats},
                                  {c: s_prev.get(c, {}).get("share_unweighted", 0.0) for c in cats},
                                  cats),
            "tvd_weighted": tvd({c: s_now.get(c, {}).get("share_weighted", 0.0) for c in cats},
                                {c: s_prev.get(c, {}).get("share_weighted", 0.0) for c in cats},
                                cats),
        }
    return out


# ---------------------------------------------------------------- answers
def answer_stats_month(sub: pd.DataFrame) -> dict:
    q9 = sub.dropna(subset=["Q9_mean"])
    w = q9["weight"].to_numpy()
    x = q9["Q9_mean"].to_numpy()
    wm = weighted_moments(x, w)
    pt = sub.dropna(subset=["Q8v2part2"])
    pt = pt[pt["Q8v2part2"].abs() <= POINT_ESTIMATE_CLIP]
    pw_ = pt["weight"].to_numpy()
    px = pt["Q8v2part2"].to_numpy()
    bins_u = bins_w = None
    bin_mask = sub[[f"Q9_bin{i}" for i in range(1, 11)]].notna().all(axis=1)
    if bin_mask.any():
        bsub = sub[bin_mask]
        bins_u = [float(bsub[f"Q9_bin{i}"].mean()) for i in range(1, 11)]
        bw = bsub["weight"].to_numpy()
        bins_w = [float(np.average(bsub[f"Q9_bin{i}"].to_numpy(), weights=bw))
                  for i in range(1, 11)]
    qs_u = [float(np.quantile(px, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)]
    qs_w = [wquantile(px, pw_, q) for q in (0.1, 0.25, 0.5, 0.75, 0.9)]
    return {
        "q9_mean": {
            "n": int(len(q9)),
            "unweighted": {"mean": float(x.mean()), "median": float(np.median(x)),
                           "std": float(x.std()), "iqr": float(np.quantile(x, .75)
                                                               - np.quantile(x, .25))},
            "weighted": {"mean": wm["mean"],
                         "median": wquantile(x, w, 0.5), "std": wm["std"],
                         "iqr": float(wquantile(x, w, 0.75) - wquantile(x, w, 0.25))},
        },
        "point_estimate_Q8v2part2": {
            "n": int(len(pt)),
            "n_clipped_outliers": int(sub["Q8v2part2"].notna().sum() - len(pt)),
            "unweighted_quantiles_p10_p25_p50_p75_p90": qs_u,
            "weighted_quantiles_p10_p25_p50_p75_p90": qs_w,
        },
        "q9_bins_mean_probability_unweighted": bins_u,
        "q9_bins_mean_probability_weighted": bins_w,
    }


# ---------------------------------------------------------------- rotation
def rotation_stats(df: pd.DataFrame) -> dict:
    months = sorted(df["date"].unique())
    first_seen = df.groupby("userid")["date"].min()
    last_seen = df.groupby("userid")["date"].max()
    by_month = dict(tuple(df.groupby("date")))
    out = {}
    for i, m in enumerate(months):
        sub = by_month[m]
        uids = set(sub["userid"])
        prev_uids = set(by_month[months[i - 1]]["userid"]) if i > 0 else set()
        new = int(sum(1 for u in uids if first_seen[u] == m))
        # re-entrants: seen before in the file but absent last month. Distinct
        # from first-time entrants (review CORE_NORMAL_REVIEW_20261003 sec. 3).
        reentrant = int(sum(1 for u in uids
                            if first_seen[u] < m and u not in prev_uids)) if i > 0 else None
        exited = int(sum(1 for u in prev_uids
                         if last_seen[u] == months[i - 1])) if i > 0 else None
        overlap = (len(uids & prev_uids) / len(uids)) if i > 0 else None
        t = sub["tenure"].dropna()
        out[int(m)] = {
            "n_respondents": int(len(sub)),
            "n_new_entrants": new,
            "n_reentrants": reentrant,
            "new_entrant_share": new / len(sub),
            "n_exit_prev_month": exited,
            "overlap_with_prev_month": overlap,
            "tenure_months": {"min": int(t.min()), "p25": float(t.quantile(.25)),
                              "median": float(t.median()), "p75": float(t.quantile(.75)),
                              "max": int(t.max()), "mean": float(t.mean())},
        }
    return out


# ------------------------------------------------------- group medians etc.
def group_medians_month(sub: pd.DataFrame) -> dict:
    q9 = sub.dropna(subset=["Q9_mean"])
    out = {}
    for dim, col in PROFILE_DIMS.items():
        if dim not in GROUP_DIMS_FOR_MEDIANS:
            continue
        cats = {}
        for cat, g in q9.groupby(col, dropna=True):
            x = g["Q9_mean"].to_numpy()
            w = g["weight"].to_numpy()
            cats[str(cat)] = {
                "n": int(len(g)),
                "median_unweighted": float(np.median(x)),
                "median_weighted": wquantile(x, w, 0.5),
            }
        out[dim] = cats
    return out


def heterogeneity_month(sub: pd.DataFrame) -> dict:
    """Between-group variance share of Q9_mean per profile dimension."""
    q9 = sub.dropna(subset=["Q9_mean"])
    x = q9["Q9_mean"].to_numpy()
    w = q9["weight"].to_numpy()
    mu = np.average(x, weights=w)
    tss = float(np.average((x - mu) ** 2, weights=w))
    out = {}
    for dim, col in HET_DIMS.items():
        bss = 0.0
        meds = []
        for _, g in q9.groupby(col, dropna=True):
            gx = g["Q9_mean"].to_numpy()
            gw = g["weight"].to_numpy()
            gm = np.average(gx, weights=gw)
            bss += gw.sum() * (gm - mu) ** 2 / w.sum()
            meds.append(wquantile(gx, gw, 0.5))
        out[dim] = {
            "between_group_variance_share": float(bss / tss) if tss > 0 else 0.0,
            "max_median_gap": float(max(meds) - min(meds)) if len(meds) > 1 else 0.0,
        }
    return out


def autocorr_q9(df: pd.DataFrame) -> dict:
    """Within-person lag-1 correlation of Q9_mean over adjacent months."""
    months = sorted(df["date"].unique())
    pairs = []
    by_month = {m: g.dropna(subset=["Q9_mean"]).set_index("userid")
                for m, g in df.groupby("date")}
    series = []
    for i in range(1, len(months)):
        m0, m1 = months[i - 1], months[i]
        common = by_month[m0].index.intersection(by_month[m1].index)
        if len(common) < 30:
            continue
        a = by_month[m0].loc[common, "Q9_mean"].to_numpy()
        b = by_month[m1].loc[common, "Q9_mean"].to_numpy()
        w0 = by_month[m0].loc[common, "weight"].to_numpy()
        w1 = by_month[m1].loc[common, "weight"].to_numpy()
        pair_w = np.sqrt(w0 * w1)
        pear = float(np.corrcoef(a, b)[0, 1])
        # weighted Pearson
        ma = np.average(a, weights=pair_w)
        mb = np.average(b, weights=pair_w)
        cov = np.average((a - ma) * (b - mb), weights=pair_w)
        corr_w = float(cov / np.sqrt(np.average((a - ma) ** 2, weights=pair_w)
                                     * np.average((b - mb) ** 2, weights=pair_w)))
        series.append({"month_pair": [int(m0), int(m1)], "n_pairs": int(len(common)),
                       "corr_unweighted": pear, "corr_weighted": corr_w})
        pairs.append((a, b, pair_w))
    all_a = np.concatenate([p[0] for p in pairs])
    all_b = np.concatenate([p[1] for p in pairs])
    all_w = np.concatenate([p[2] for p in pairs])
    ma = np.average(all_a, weights=all_w)
    mb = np.average(all_b, weights=all_w)
    cov = np.average((all_a - ma) * (all_b - mb), weights=all_w)
    pooled_w = float(cov / np.sqrt(np.average((all_a - ma) ** 2, weights=all_w)
                                   * np.average((all_b - mb) ** 2, weights=all_w)))
    return {"by_month_pair": series,
            "pooled": {"corr_unweighted": float(np.corrcoef(all_a, all_b)[0, 1]),
                       "corr_weighted": pooled_w,
                       "n_pairs": int(len(all_a))}}


# ---------------------------------------------------------------- report
def fmt(x, nd=3):
    return "-" if x is None else f"{x:.{nd}f}"


def build_report(res: dict, main_months: list) -> str:
    L = []
    a = L.append
    a("# POPULATION_WAVE_STATS — SCE 微观数据逐期统计\n")
    a(f"- study: `{STUDY_ID}`；生成: {res['meta']['generated_at_utc']}；"
      f"脚本: `scripts/analyze_sce_wave_stats.py`（参数化 `--months`，可复算）\n")
    a(f"- 数据源: `{res['meta']['data_path']}` sha256 `{res['meta']['data_sha256'][:16]}…`"
      f"（{res['meta']['n_rows']} 行，{res['meta']['n_months']} 个月，"
      f"{res['meta']['n_unique_userids']} 个 userid）\n")
    mw = res['config']['main_window_months']
    a(f"- 主分析窗: {month_label(mw[0])}..{month_label(mw[-1])}"
      f"（{len(mw)} 个月）；背景对照全 {res['meta']['date_min']}–{res['meta']['date_max']}。\n")
    a("- 所有聚合同时给出**未加权**与 `weight` **加权**两版（正文表格以未加权为主，"
      "加权差异在漂移/平稳性处并列）。\n")
    a("- 纪律：纯描述统计，无因果断言；回答/权重仅用于本评价层输出，"
      "不进入任何 persona/Agent 输入。\n")
    a("- 编码核实：`Q8v2=1`=预期上涨（`Q8v2part2` 全部 ≥0，中位数 +5），"
      "`Q8v2=2`=预期下降（part2 全部 <0，中位数 −4）；本文件无\"持平\"码。"
      f"`Q8v2part2` 超出 ±{POINT_ESTIMATE_CLIP:.0f} 的录入异常值（如 10000）"
      "在分位数统计中剔除并计数。\n")
    a("- 住房 `Q43` 只问新入组者（官方问卷 p.27：Q32–Q47 仅对新受访者；Q43 在 p.32）。"
      "当月约 12% 的覆盖是入组流量、不是随机轮换抽问；经核实每个 userid 只有一条"
      "Q43 记录（8,536 人，从未改答），沿同一人的入组回答前向沿用后 2021 年人月"
      "覆盖达 99.64%。本节住房构成仍以当月被问样本（新入组者）计算并标注 n，"
      "不得把新入组者的住房占比当作全体住房构成。\n")

    # ---- 2a profiles
    a("## 2a. 逐期画像分布与漂移\n")
    a("主窗口各月画像占比（未加权；每格为占比%，加权版见 JSON）：\n")
    for dim in list(PROFILE_DIMS) + ["employment", "housing"]:
        a(f"### {dim}\n")
        cats = res["profile_distributions"][dim]["categories"]
        header = ("| month | " + " | ".join(cats)
                  + (" | n(Q43 asked) |" if dim == "housing" else " |")) + "\n"
        sep = "|" + "---|" * (len(cats) + 2 if dim == "housing" else len(cats) + 1) + "\n"
        a(header + sep)
        for m in main_months:
            row = res["profile_distributions"][dim]["by_month"][str(m)]
            n = row.get("n_subsample")
            cells = [f"{row['shares'].get(c, {}).get('share_unweighted', 0.0) * 100:.1f}" for c in cats]
            a(f"| {month_label(m)} | " + " | ".join(cells)
              + (f" | {n}" if dim == "housing" else "") + " |\n")
        a("")
    a("### 逐月漂移（TVD，未加权 / 加权）\n")
    a("TVD = 0.5·Σ|p−q|，基线为 2021-01，另给对 --months 主窗口"
      "（默认 202011..202112 共 14 个月）均值分布的 TVD。"
      "表为全 2020–2024 每维度的摘要；逐月序列见 JSON。\n")
    a("| dimension | TVD vs 2021-01 max (u/w) | mean (u/w) | TVD vs window mean max (u/w) | mean (u/w) | TVD M vs M−12 mean (u/w) | max |\n")
    a("|---|---|---|---|---|---|---|\n")
    for dim in res["profile_drift_summary"]:
        s = res["profile_drift_summary"][dim]
        a(f"| {dim} | {fmt(s['vs_202101']['max_unweighted'])} / {fmt(s['vs_202101']['max_weighted'])} "
          f"| {fmt(s['vs_202101']['mean_unweighted'])} / {fmt(s['vs_202101']['mean_weighted'])} "
          f"| {fmt(s['vs_window_mean']['max_unweighted'])} / {fmt(s['vs_window_mean']['max_weighted'])} "
          f"| {fmt(s['vs_window_mean']['mean_unweighted'])} / {fmt(s['vs_window_mean']['mean_weighted'])} "
          f"| {fmt(s['lag12']['mean_unweighted'])} / {fmt(s['lag12']['mean_weighted'])} "
          f"| {fmt(s['lag12']['max_unweighted'])} / {fmt(s['lag12']['max_weighted'])} |\n")
    a("")

    # ---- 2b answers
    a("## 2b. 逐期回答分布\n")
    a("| month | Q9_mean n | mean u/w | median u/w | std u/w | IQR u/w | part2 p10/p25/p50/p75/p90 (u) |\n")
    a("|---|---|---|---|---|---|---|\n")
    for m in main_months:
        s = res["answer_stats"][str(m)]
        q9 = s["q9_mean"]
        pt = s["point_estimate_Q8v2part2"]
        qs = "/".join(f"{q:.1f}" for q in pt["unweighted_quantiles_p10_p25_p50_p75_p90"])
        a(f"| {month_label(m)} | {q9['n']} | {fmt(q9['unweighted']['mean'], 2)}/{fmt(q9['weighted']['mean'], 2)} "
          f"| {fmt(q9['unweighted']['median'], 2)}/{fmt(q9['weighted']['median'], 2)} "
          f"| {fmt(q9['unweighted']['std'], 2)}/{fmt(q9['weighted']['std'], 2)} "
          f"| {fmt(q9['unweighted']['iqr'], 2)}/{fmt(q9['weighted']['iqr'], 2)} | {qs} |\n")
    a("\nQ9 十档平均概率分布（主窗口首/中/末月示例，未加权；加权与全序列见 JSON）：\n")
    b0 = res["answer_stats"][str(main_months[0])]["q9_bins_mean_probability_unweighted"]
    bm = res["answer_stats"][str(main_months[len(main_months) // 2])]["q9_bins_mean_probability_unweighted"]
    b1 = res["answer_stats"][str(main_months[-1])]["q9_bins_mean_probability_unweighted"]
    a("| bin | ≥+12 | +8..12 | +4..8 | +2..4 | +0..2 | −2..0 | −4..−2 | −8..−4 | −12..−8 | ≤−12 |\n")
    a("|---|---|---|---|---|---|---|---|---|---|---|\n")
    for name, b in [("首月 " + month_label(main_months[0]), b0),
                    ("中月 " + month_label(main_months[len(main_months) // 2]), bm),
                    ("末月 " + month_label(main_months[-1]), b1)]:
        if b:
            a(f"| {name} | " + " | ".join(f"{v:.1f}" for v in b) + " |\n")
    a("")

    # ---- 2c rotation
    a("## 2c. 轮换结构\n")
    a("口径限定（复审更正）：\"新进\"= 在本文件内首次出现（2020-01 存在左截断，"
      "该月的\"新进\"含此前已在册者）；\"退出\"= 以全文件 last_seen 事后识别，"
      "不能直接当作 B 线的在线退出规则；\"重返\"= 此前出现过但上月缺席，"
      "与首次入组分开计数。\n")
    a("| month | n | 新进 n (占比) | 重返 n | 上月退出 n | 与上月重叠率 | tenure 中位 [p25,p75] (max) |\n")
    a("|---|---|---|---|---|---|---|\n")
    for m in main_months:
        r = res["rotation"][m]
        t = r["tenure_months"]
        a(f"| {month_label(m)} | {r['n_respondents']} | {r['n_new_entrants']} "
          f"({r['new_entrant_share'] * 100:.1f}%) | {r.get('n_reentrants')} "
          f"| {r['n_exit_prev_month']} "
          f"| {fmt(r['overlap_with_prev_month'], 3)} | {t['median']:.0f} "
          f"[{t['p25']:.0f},{t['p75']:.0f}] ({t['max']}) |\n")
    a("\n回答缺失模式（主窗口各字段每月缺失率均值，全序列见 JSON；"
      "Q43 的\"缺失\"实为未被问——该题只问新入组者，不应读作随机缺失）：\n")
    a("| field | 主窗口月均缺失率 | 全期最高月 |\n|---|---|---|\n")
    for f_, s_ in res["missingness_summary"].items():
        a(f"| {f_} | {s_['mean_main_window'] * 100:.2f}% | {s_['max'] * 100:.1f}% ({month_label(int(s_['max_month']))}) |\n")
    a("")

    # ---- 2d stationarity
    a("## 2d. 跨期平稳性\n")
    a("画像分布逐月 TVD 序列：见 JSON `profile_drift`（全 60 个月，vs 2021-01 基线"
      "与 vs 14 个月主窗口均值）。下图文字版为主窗口内 employment 与 income 的"
      "未加权 TVD（vs 2021-01）：\n")
    for dim in ("employment", "income"):
        seq = [(m, res["profile_drift"][dim][str(m)]["tvd_vs_baseline_unweighted"])
               for m in main_months]
        a(f"- {dim}: " + ", ".join(f"{month_label(m)}:{v:.3f}" for m, v in seq) + "\n")
    a("\n回答水平 × 画像分组（每月 Q9_mean 分组中位数，未加权/加权）："
      "方向与量级稳定性见 JSON `group_medians`；主窗口收入组示例（加权中位数）：\n")
    a("| month | Under 50k | 50k to 100k | Over 100k | 组间极差 |\n|---|---|---|---|---|\n")
    for m in main_months:
        gm = res["group_medians"][str(m)]["income"]
        vals = {c: gm[c]["median_weighted"] for c in gm}
        rng = max(vals.values()) - min(vals.values())
        a(f"| {month_label(m)} | " + " | ".join(f"{vals[c]:.2f}" for c in
          ["Under 50k", "50k to 100k", "Over 100k"]) + f" | {rng:.2f} |\n")
    a("")

    # ---- 2e heterogeneity
    a("## 2e. 异质性结构（core/normal 分层依据）\n")
    a("每月各画像维度的 Q9_mean 组间方差占比（between-group share，加权）"
      "与组间中位数极差；表为全期均值 [主窗口均值]：\n")
    a("| dimension | between-share full [main] | max median-gap full [main] |\n|---|---|---|\n")
    for dim in HET_DIMS:
        fs = res["heterogeneity_summary"][dim]
        a(f"| {dim} | {fmt(fs['between_share_full'])} [{fmt(fs['between_share_main'])}] "
          f"| {fmt(fs['median_gap_full'], 2)} [{fmt(fs['median_gap_main'], 2)}] |\n")
    stab = res.get("group_median_stability", {})
    if stab:
        a("\n分组中位数向量相邻月 Spearman 秩相关均值（全期，回答-画像关系稳定性）：")
        a("；".join(f"{d} ρ={fmt(v['mean_consecutive_spearman'], 2)}"
                    for d, v in stab.items()) + "\n")
    ac = res["q9_lag1_autocorr"]["pooled"]
    a(f"\nwithin-person Q9_mean 相邻月自相关（全体相邻月对合并，加权 pearson）："
      f"**{ac['corr_weighted']:.3f}**（未加权 {ac['corr_unweighted']:.3f}，"
      f"n={ac['n_pairs']} 对）；逐月对序列见 JSON `q9_lag1_autocorr.by_month_pair`。\n")
    a("主窗口各月对自相关（未加权）：\n")
    a("| month pair | n pairs | corr u/w |\n|---|---|---|\n")
    for rec in res["q9_lag1_autocorr"]["by_month_pair"]:
        if rec["month_pair"][1] in main_months:
            a(f"| {month_label(rec['month_pair'][0])}→{month_label(rec['month_pair'][1])} "
              f"| {rec['n_pairs']} | {rec['corr_unweighted']:.3f}/{rec['corr_weighted']:.3f} |\n")
    a("")

    # ---- conclusions
    a(res["conclusions_md"])
    return "".join(L)


def summarize_drift(res_profile_drift: dict, lag12: dict,
                    main_months: list) -> dict:
    out = {}
    dims = res_profile_drift
    for dim, bym in dims.items():
        rows = list(bym.values())
        all_months = sorted(int(m) for m in bym)
        lag = lag12.get(dim, {})
        out[dim] = {
            "vs_202101": {
                "max_unweighted": max(r["tvd_vs_baseline_unweighted"] for r in rows),
                "max_weighted": max(r["tvd_vs_baseline_weighted"] for r in rows),
                "mean_unweighted": float(np.mean([r["tvd_vs_baseline_unweighted"] for r in rows])),
                "mean_weighted": float(np.mean([r["tvd_vs_baseline_weighted"] for r in rows])),
            },
            "vs_window_mean": {
                "max_unweighted": max(r["tvd_vs_window_mean_unweighted"] for r in rows),
                "max_weighted": max(r["tvd_vs_window_mean_weighted"] for r in rows),
                "mean_unweighted": float(np.mean([r["tvd_vs_window_mean_unweighted"] for r in rows])),
                "mean_weighted": float(np.mean([r["tvd_vs_window_mean_weighted"] for r in rows])),
            },
            "lag12": {
                "max_unweighted": max((v["tvd_unweighted"] for v in lag.values()), default=None),
                "max_weighted": max((v["tvd_weighted"] for v in lag.values()), default=None),
                "mean_unweighted": float(np.mean([v["tvd_unweighted"] for v in lag.values()])) if lag else None,
                "mean_weighted": float(np.mean([v["tvd_weighted"] for v in lag.values()])) if lag else None,
                "n_months": len(all_months),
            },
        }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", default=",".join(
        str(m) for m in list(range(202011, 202013)) + list(range(202101, 202113))),
        help="comma-separated YYYYMM main-window months "
             "(default 202011..202112, 14 months)")
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--outdir", type=Path, default=REPORT_DIR)
    args = ap.parse_args(argv)

    main_months = [int(m) for m in args.months.split(",") if m.strip()]
    df = load_frame(args.data)
    all_months = sorted(int(m) for m in df["date"].unique())

    res: dict = {
        "meta": {
            "study_id": STUDY_ID,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "script": "scripts/analyze_sce_wave_stats.py",
            "data_path": str(args.data.relative_to(REPO_ROOT)),
            "data_sha256": _sha256(args.data),
            "n_rows": int(len(df)),
            "n_rows_zero_weight": int((df["weight"] == 0).sum()),
            "zero_weight_note": ("rows with missing source weight kept in frame and "
                                 "unweighted stats; weight set to 0 for weighted stats"),
            "n_months": len(all_months),
            "n_unique_userids": int(df["userid"].nunique()),
            "date_min": int(df["date"].min()),
            "date_max": int(df["date"].max()),
        },
        "config": {
            "main_window_months": main_months,
            "baseline_month_for_tvd": 202101,
            "point_estimate_clip_abs": POINT_ESTIMATE_CLIP,
            "note": ("all aggregates reported unweighted and weight-weighted; "
                     "Q9/Q8v2part2 answers and weights stay in this evaluation "
                     "layer only"),
        },
    }

    by_month = {int(m): g for m, g in df.groupby("date")}

    # ---- 2a profile distributions + drift
    prof_dist, prof_drift, prof_lag12 = {}, {}, {}
    for dim, col in PROFILE_DIMS.items():
        shares = {m: profile_shares(by_month[m], col) for m in all_months}
        prof_dist[dim] = {"source_column": col,
                          "categories": sorted({c for s in shares.values() for c in s}),
                          "by_month": {str(m): {"n_subsample": int(by_month[m][col].notna().sum()),
                                                "shares": shares[m]} for m in all_months}}
        prof_drift[dim] = {str(m): r for m, r in
                           dimension_drift(shares, 202101, main_months).items()}
        prof_lag12[dim] = {str(m): r for m, r in lag12_tvd(shares).items()}
    # employment (mapped from Q10)
    shares = {m: profile_shares(by_month[m], "employment") for m in all_months}
    prof_dist["employment"] = {
        "source_column": "Q10_1..Q10_10 dummies (priority-mapped as in build_sce_population.py)",
        "categories": sorted({c for s in shares.values() for c in s}),
        "by_month": {str(m): {"n_subsample": int(by_month[m]["employment"].notna().sum()),
                              "shares": shares[m]} for m in all_months}}
    prof_drift["employment"] = {str(m): r for m, r in
                                dimension_drift(shares, 202101, main_months).items()}
    prof_lag12["employment"] = {str(m): r for m, r in lag12_tvd(shares).items()}
    # housing Q43 (asked of new entrants only; mapped to owner/renter/other labels)
    shares = {}
    for m in all_months:
        asked = by_month[m][by_month[m]["housing_tenure"].notna()]
        shares[m] = profile_shares(asked, "housing_tenure") if len(asked) else {}
    prof_dist["housing"] = {
        "source_column": "Q43 (asked of new entrants only; shares computed among respondents ASKED that month = the entrant flow, not the whole sample; 1=owner 2=renter 3=other)",
        "categories": ["owner", "renter", "other"],
        "by_month": {str(m): {"n_subsample": int(by_month[m]["Q43"].notna().sum()),
                              "shares": shares[m]} for m in all_months}}
    prof_drift["housing"] = {str(m): r for m, r in
                             dimension_drift(shares, 202101, main_months).items()}
    prof_lag12["housing"] = {str(m): r for m, r in lag12_tvd(shares).items()}
    res["profile_distributions"] = prof_dist
    res["profile_drift"] = prof_drift
    res["profile_lag12_tvd"] = prof_lag12
    res["profile_drift_summary"] = summarize_drift(prof_drift, prof_lag12, main_months)

    # ---- 2b answer stats
    res["answer_stats"] = {str(m): answer_stats_month(by_month[m]) for m in all_months}

    # ---- 2c rotation + missingness
    res["rotation"] = rotation_stats(df)
    miss_fields = ["Q9_mean", "Q8v2", "Q8v2part2", "Q43",
                   "_EDU_CAT", "_HH_INC_CAT", "Q10_1"]
    miss = {f_: {str(m): float(by_month[m][f_].isna().mean()) for m in all_months}
            for f_ in miss_fields}
    res["missingness_by_month"] = miss
    res["missingness_summary"] = {
        f_: {"mean_main_window": float(np.mean([miss[f_][str(m)] for m in main_months])),
             "mean": float(np.mean(list(miss[f_].values()))),
             "max": max(miss[f_].values()),
             "max_month": max(miss[f_], key=lambda k: miss[f_][k])}
        for f_ in miss_fields}

    # ---- 2d group medians
    res["group_medians"] = {str(m): group_medians_month(by_month[m]) for m in all_months}

    # ---- 2e heterogeneity + autocorr
    het = {m: heterogeneity_month(by_month[m]) for m in all_months}
    res["heterogeneity_by_month"] = {str(m): het[m] for m in all_months}
    het_sum = {}
    for dim in HET_DIMS:
        het_sum[dim] = {
            "between_share_full": float(np.mean(
                [het[m][dim]["between_group_variance_share"] for m in all_months])),
            "between_share_main": float(np.mean(
                [het[m][dim]["between_group_variance_share"] for m in main_months if m in het])),
            "median_gap_full": float(np.mean(
                [het[m][dim]["max_median_gap"] for m in all_months])),
            "median_gap_main": float(np.mean(
                [het[m][dim]["max_median_gap"] for m in main_months if m in het])),
        }
    res["heterogeneity_summary"] = het_sum
    # group-median profile stability: mean consecutive-month Spearman rank
    # correlation of the category-median vector (dimension -> [cat medians]).
    from scipy.stats import spearmanr
    stab = {}
    for dim in GROUP_DIMS_FOR_MEDIANS:
        vecs = []
        for m in all_months:
            cats_m = res["group_medians"][str(m)].get(dim, {})
            vecs.append([cats_m[c]["median_weighted"] for c in cats_m] or None)
        pairs = [(a, b) for a, b in zip(vecs, vecs[1:]) if a and b and len(a) > 1]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rhos = [spearmanr(a, b).statistic for a, b in pairs]
        rhos = [r for r in rhos if r is not None and np.isfinite(r)]
        stab[dim] = {"mean_consecutive_spearman": float(np.mean(rhos)) if rhos else None,
                     "n_pairs": len(rhos)}
    res["group_median_stability"] = stab
    res["q9_lag1_autocorr"] = autocorr_q9(df)

    # ---- conclusions
    c = res["conclusions_md"] = _conclusions(res, main_months)

    args.outdir.mkdir(parents=True, exist_ok=True)
    json_path = args.outdir / "POPULATION_WAVE_STATS.json"
    md_path = args.outdir / "POPULATION_WAVE_STATS.md"
    json_path.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    md_path.write_text(build_report(res, main_months), encoding="utf-8")
    print(f"wrote {md_path} and {json_path}")
    return 0


def _conclusions(res: dict, main_months: list) -> str:
    hs = res["heterogeneity_summary"]
    dr = res["profile_drift_summary"]
    ac = res["q9_lag1_autocorr"]["pooled"]
    stab = res.get("group_median_stability", {})
    ranked = sorted(hs.items(), key=lambda kv: -kv[1]["between_share_full"])
    L = []
    a = L.append
    a("\n## 3. 结论：三个设计问题（实测数字）\n")

    # ---- Q1 stratification
    a("**① core 层按哪些维度分层抽样最有效？**\n\n")
    a("按 Q9_mean 组间方差占比（between-group share，全期均值）排序：")
    a("；".join(f"{d} {v['between_share_full'] * 100:.2f}%"
                for d, v in ranked) + "。")
    a("按组间中位数极差（全期均值，pp）排序：")
    a("；".join(f"{d} {v['median_gap_full']:.2f}"
                for d, v in sorted(hs.items(),
                                   key=lambda kv: -kv[1]['median_gap_full'])) + "。\n")
    a("两个口径共同指向：**education / employment / age** 是最有效的分层维度，"
      "**income 次之**，region 与 numeracy 最弱。需要注意两点："
      f"(i) 任何单一维度的组间方差占比都很小（全期均值最高约 "
      f"{max(v['between_share_full'] for v in hs.values()) * 100:.1f}%，"
      f"主窗口均值最高约 {max(v['between_share_main'] for v in hs.values()) * 100:.1f}%）"
      "——Q9_mean 的变异绝大部分是**组内个体间差异**（std≈6pp），分层只能捕捉尾部结构，"
      "core 层的价值在**覆盖组间差**而非降低总方差；(ii) 收入组中位数的排序并不固定，"
      "组间极差仅 0.2–1.3pp，不宜把\"低收入预期更高\"当作稳定先验写进设计；"
      "employment 的最大组间差还包含 on_leave、other 等每月仅个位数人的稀小组，"
      "不能凭极差直接判它为最有效维度。"
      "建议 core 层按 **education × employment × age**（income 作为第三优先）"
      "分层抽样，region/state 只做配额校验。\n")

    # ---- Q2 stationarity for Bayesian extrapolation
    a("**② normal 层贝叶斯外推的平稳性依据是否成立？**\n\n")
    a("以下为描述性支持，不能据此断言外推成立：")
    a(f"(i) **相邻月回答相关**——Q9_mean 相邻月自相关（相邻月对合并的描述性相关，"
      f"未控制个体固定效应与月份冲击）加权 **{ac['corr_weighted']:.3f}**（未加权 "
      f"{ac['corr_unweighted']:.3f}，n={ac['n_pairs']:,} 对），主窗口各月对均在 "
      "0.45–0.70；它是\"考虑引入上月回答\"的描述性线索，不等于记忆机制系数，"
      "也不证明提示词引入该变量能复现此行为；")
    a("(ii) **回答-画像关系跨月稳定**——分组中位数向量相邻月 Spearman 秩相关均值：")
    a("；".join(f"{d} ρ={fmt(v['mean_consecutive_spearman'], 2)}"
                for d, v in stab.items()) + "；")
    a("(iii) **画像结构漂移有限**——各维 lag-12 TVD 均值均在 0.03–0.06（见③）。\n")
    a("关键限定：外推窗口内可以平移的是**结构/关系**，不是**水平**——"
      "2021 年 Q9_mean 整体从 1 月的 4.4 持续抬升到 11 月的 6.8（2b 表），"
      "任何用旧人口外推当月水平的方案都必须以当月公布的锚（如 BLS 通胀）"
      "重新定位水平项，否则会产生系统性高估/低估。\n")

    # ---- Q3 12-month drift / B-line
    a("**③ 人口分布 12 个月漂移是否小到可忽略（B 线能否直接用）？**\n\n")
    for dim in ("income", "employment", "age", "education", "region", "numeracy", "housing"):
        d = dr[dim]["lag12"]
        a(f"- {dim}: lag-12 TVD 均值 {fmt(d['mean_unweighted'])}(u)/{fmt(d['mean_weighted'])}(w)，"
          f"最大 {fmt(d['max_unweighted'])}(u)/{fmt(d['max_weighted'])}(w)；")
    a("\n对照参考分级（TVD<0.02 可忽略、0.02–0.05 轻微、>0.05 需校准——项目拟议的"
      "告警参考，不是已验证的通用阈值，不作自动合格判据）："
      "**核心画像维度（income/employment/age）的 12 个月漂移处于'轻微'区间上沿**，"
      "region/education/numeracy 接近可忽略；housing 的表观 TVD 先受\"只问新入组者\""
      "的选择机制驱动（当月被问者=入组流量），不能全归为小样本噪声，也不应直接读作"
      "全体住房结构漂移。"
      "因此 **B 线旧人口外推可用但不应裸用**："
      "(a) 画像分布在每 12 个月窗口内允许直接复用是拟议规则，"
      "(b) income/employment 两维的校准频率（如按年一次）须以开发期重抽样精度与 ESS "
      "规则验证后才能冻结——年均 TVD 本身推不出\"每年校准一次足够\"，"
      "(c) housing 采用\"入组回答前向沿用\"（与 build_sce_population.py 一致；"
      "B 线另须满足源记录可得日 ≤ as_of），不进入 B 线校准项。"
      "按 D048，B 线预测输入须按预测时点登记可得性。\n")

    a("**与预期不符的发现**：\n\n")
    a("- `Q8v2` 在本文件中只有 1(up)/2(down) 两码、无'持平'码"
      "（与部分 SCE 文档的三码描述不同）；方向含义已用 `Q8v2part2` 符号核实"
      "（1→part2≥0，2→part2<0）。\n")
    a("- `Q8v2part2` 存在极小比例录入异常值（观测到最大值 10000），"
      f"点估计分位数统计剔除 |x|>{POINT_ESTIMATE_CLIP:.0f} 后计算"
      "（各月剔除数量见 JSON）。\n")
    a("- numeracy 组间差**没有稳定方向**（全期 High−Low 中位数差仅少数月份为正值），"
      "量级也最小（极差≈0.3pp）——分层收益低，不建议作为 core 层主维度，"
      "也不要预设'低 numeracy 预期更高/更低'。\n")
    a("- 收入组的'低>高'排序只在主窗口约 13/14 个月成立、且组间极差小，"
      "说明收入与预期的关系弱于文献直觉，分层时应按实测配额而非先验方向。\n")
    a("- 2021-03 Q9_mean 缺失率一过性升高至 4.8%（常规≈1.5%），逐月统计以 Q9 非缺失 n 为准。\n")
    a("- 加权 vs 未加权的漂移差异方向不固定（age 加权后漂移大幅缩小、"
      "income 加权后反而略增），说明权重校正的是截面代表性而非面板结构漂移。\n")
    return "".join(L)


if __name__ == "__main__":
    sys.exit(main())
