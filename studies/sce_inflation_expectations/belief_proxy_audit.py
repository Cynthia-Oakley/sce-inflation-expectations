"""Offline, aggregate-only audit of candidate belief proxies. Not a persona builder."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantile(values, weights, q=0.5) -> float:
    x, w = np.asarray(values, float), np.asarray(weights, float)
    keep = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x, w = x[keep], w[keep]
    if not len(x):
        return float("nan")
    order = np.argsort(x, kind="stable")
    return float(x[order][np.searchsorted(np.cumsum(w[order]), q * w.sum())])


def ess(weights) -> float:
    w = np.asarray(weights, float)
    return float(w.sum() ** 2 / (w @ w)) if len(w) and (w @ w) else 0.0


def audit_sce(path: Path):
    fields = ["date", "weight", "Q9_mean", "Q9c_mean"]
    df = pd.read_excel(path, header=1, usecols=fields).apply(pd.to_numeric, errors="coerce")
    rows = []
    for month, group in df.groupby("date", sort=True):
        valid = group["Q9_mean"].notna() & group["Q9c_mean"].notna()
        valid &= np.isfinite(group[fields]).all(axis=1) & (group["weight"] > 0)
        paired = group.loc[valid]
        w = paired["weight"].to_numpy()
        x = paired["Q9_mean"].to_numpy()
        y = paired["Q9c_mean"].to_numpy()
        mx, my = np.average(x, weights=w), np.average(y, weights=w)
        vx, vy = np.average((x - mx) ** 2, weights=w), np.average((y - my) ** 2, weights=w)
        corr = np.average((x - mx) * (y - my), weights=w) / np.sqrt(vx * vy)
        rows.append({"month": str(int(month)), "all_rows": len(group),
                     "q9c_nonmissing": int(group["Q9c_mean"].notna().sum()),
                     "paired_valid": len(paired), "paired_weight_ess": ess(w),
                     "one_year_weighted_median_paired": quantile(x, w),
                     "three_year_weighted_median_paired": quantile(y, w),
                     "one_minus_three_weighted_median": quantile(x - y, w),
                     "weighted_pearson_r": float(corr)})
    return pd.DataFrame(rows), {
        "rows": len(df), "months": len(rows), "first_month": rows[0]["month"],
        "last_month": rows[-1]["month"],
        "q9c_nonmissing": int(df["Q9c_mean"].notna().sum()),
        "paired_valid": sum(r["paired_valid"] for r in rows),
        "interpretation": "Q9c is a three-year-horizon annual inflation expectation; not a trust measure or identified persistence parameter. Same-wave Q9/Q9c are evaluation-only here.",
    }


def audit_gss(path: Path):
    cols = ["confed", "partyid", "age", "degree", "region", "wtssps"]
    df = pd.read_stata(path, columns=cols, convert_categoricals=False)
    valid = df["confed"].isin([1, 2, 3]) & df["partyid"].isin(range(8))
    valid &= df["age"].between(18, 89) & df["degree"].isin(range(5))
    valid &= df["region"].isin([1, 2, 3, 4]) & (df["wtssps"] > 0)
    donors = df.loc[valid].copy()
    donors["party_group"] = donors["partyid"].map({0: "democrat_or_lean", 1: "democrat_or_lean", 2: "democrat_or_lean", 3: "independent", 4: "republican_or_lean", 5: "republican_or_lean", 6: "republican_or_lean", 7: "other"})
    donors["age_group"] = pd.cut(donors["age"], [17, 39, 59, 89], labels=["under40", "40to59", "60plus"])
    donors["college"] = donors["degree"].ge(3)
    cells = []
    for key, g in donors.groupby(["age_group", "college", "region"], observed=True):
        cells.append({"age_group": str(key[0]), "college": bool(key[1]), "region": int(key[2]), "n": len(g), "ess": ess(g["wtssps"])})
    party = []
    for key, g in donors.groupby("party_group"):
        w = g["wtssps"].to_numpy()
        party.append({"party_group": key, "n": len(g), "ess": ess(w),
                      "weighted_share_great_deal": float(np.average(g["confed"].eq(1), weights=w)),
                      "weighted_share_only_some": float(np.average(g["confed"].eq(2), weights=w)),
                      "weighted_share_hardly_any": float(np.average(g["confed"].eq(3), weights=w))})
    return {
        "rows": len(df), "confed_valid": int(df["confed"].isin([1, 2, 3]).sum()),
        "joint_demographic_party_confed_donors": len(donors), "joint_ess": ess(donors["wtssps"]),
        "weight": "WTSSPS from current revised public file; A exploration only, not certified 2021 B vintage",
        "construct": "Confidence in executive branch of federal government; neither interpersonal trust nor Fed confidence",
        "party_table": party, "support_cells": cells,
        "min_cell_ess": min(c["ess"] for c in cells),
        "cells_ess_below_10": sum(c["ess"] < 10 for c in cells),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sce", type=Path, required=True)
    parser.add_argument("--gss", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output_root / f"belief_proxy_audit_{stamp}_{uuid4().hex[:8]}"
    out.mkdir(parents=True, exist_ok=False)
    monthly, sce = audit_sce(args.sce)
    gss = audit_gss(args.gss)
    monthly.to_csv(out / "sce_horizon_monthly.csv", index=False)
    summary = {"created_at_utc": stamp, "analysis_class": "offline_descriptive_feasibility",
               "inputs": [{"path": str(p.resolve()), "sha256": digest(p)} for p in [args.sce, args.gss]],
               "sce": sce, "gss": gss, "real_llm_calls": 0,
               "does_not_estimate": ["causal effect", "persistence parameter", "true SCE respondent trust", "B-ready distribution"]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(out.resolve()), "sce": sce, "gss_joint": gss["joint_demographic_party_confed_donors"], "gss_min_cell_ess": gss["min_cell_ess"], "gss_party_table": gss["party_table"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
