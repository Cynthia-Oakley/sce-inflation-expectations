"""Read-only feasibility audit of downloaded SCE workbooks; no model fitting.

Run from the repository root: python scripts/audit_sce_sources.py
Requires openpyxl and numpy. Raw downloads and audit outputs stay git-ignored.
"""
from collections import Counter, defaultdict
from pathlib import Path
import json

import numpy as np
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/sce_audit_20260928"


def quantile(values, weights, q=0.5, interpolate=True):
    pairs = [(v, w) for v, w in zip(values, weights)
             if isinstance(v, (float, int)) and np.isfinite(v)
             and isinstance(w, (float, int)) and np.isfinite(w) and w > 0]
    mass = defaultdict(float)
    for v, w in pairs:
        mass[v] += w
    if not mass:
        return None
    x = np.array(sorted(mass))
    w = np.array([mass[v] for v in x])
    cdf = w.cumsum() / w.sum()
    if interpolate:
        return float(np.interp(q, cdf - 0.5 * w / w.sum(), x))
    return float(x[np.searchsorted(cdf, q)])


def audit_micro(path, chart):
    wb = load_workbook(path, read_only=True, data_only=True)
    rows = wb["Data"].iter_rows(values_only=True)
    next(rows)
    header = next(rows)
    keys = ["date", "userid", "tenure", "weight", "survey_date", "Q8v2", "Q8v2part2",
            "Q9_mean", "Q9_iqr", "_AGE_CAT", "_EDU_CAT", "_HH_INC_CAT",
            "_REGION_CAT", "_NUM_CAT"] + [f"Q9_bin{i}" for i in range(1, 11)]
    ix = {k: header.index(k) for k in keys}
    monthly = defaultdict(list)
    seen = set()
    duplicates = 0
    missing = Counter()
    invalid_bins = 0
    for row in rows:
        if not isinstance(row[ix["date"]], (int, float)):
            continue
        r = {k: row[i] for k, i in ix.items()}
        pair = (r["date"], r["userid"])
        duplicates += pair in seen
        seen.add(pair)
        for k, v in r.items():
            missing[k] += v is None or v == ""
        bins = [r[f"Q9_bin{i}"] for i in range(1, 11)]
        invalid_bins += (not all(isinstance(v, (int, float)) and 0 <= v <= 100 for v in bins)
                         or abs(sum(v for v in bins if isinstance(v, (int, float))) - 100) > 1e-6)
        monthly[int(r["date"])].append(r)
    wb.close()
    detail = []
    for month, rs in sorted(monthly.items()):
        weights = [r["weight"] for r in rs]
        means = [r["Q9_mean"] for r in rs]
        dates = [r["survey_date"].isoformat() for r in rs if hasattr(r["survey_date"], "isoformat")]
        official = chart.get(month)
        interp = quantile(means, weights)
        step = quantile(means, weights, interpolate=False)
        point = quantile([r["Q8v2part2"] for r in rs], weights)
        detail.append({"month": month, "n": len(rs), "first_response": min(dates) if dates else None,
                       "last_response": max(dates) if dates else None,
                       "density_interpolated_median": interp, "density_step_median": step,
                       "official_density_median": official[1] if official else None,
                       "point_interpolated_median": point,
                       "official_point_median": official[7] if official else None})
    return {"file": path.name, "row_count": sum(map(len, monthly.values())), "columns": len(header),
            "months": len(monthly), "first_month": min(monthly), "last_month": max(monthly),
            "monthly_n_min": min(map(len, monthly.values())), "monthly_n_max": max(map(len, monthly.values())),
            "duplicate_person_months": duplicates, "missing": dict(missing),
            "invalid_probability_rows": invalid_bins, "monthly": detail}


def main():
    wb = load_workbook(RAW / "chart.xlsx", read_only=True, data_only=True)
    chart = {int(r[0]): list(r) for r in wb["Inflation expectations"].iter_rows(min_row=5, values_only=True)
             if isinstance(r[0], (int, float))}
    notes = [list(r) for r in wb["Notes"].iter_rows(min_row=4, values_only=True)]
    wb.close()
    report = {"checked_at": "2026-09-28", "chart_months": len(chart),
              "chart_first_month": min(chart), "chart_last_month": max(chart), "revision_notes": notes,
              "scope": "Source structure and aggregation check only; no Agent outcomes or forecast evaluation.",
              "files": []}
    for name in ["micro_2020_2024.xlsx", "micro_latest.xlsx"]:
        result = audit_micro(RAW / name, chart)
        report["files"].append(result)
        print(json.dumps({k: v for k, v in result.items() if k != "monthly"}, ensure_ascii=False), flush=True)
    out = ROOT / "outputs/sce_source_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(out, flush=True)


if __name__ == "__main__":
    main()
