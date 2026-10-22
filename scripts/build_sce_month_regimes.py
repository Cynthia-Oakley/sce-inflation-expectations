#!/usr/bin/env python3
"""Build month regime labels for the SCE full-period study (Codex priority 3).

Two strictly separated label layers over the 93 coverage months:

A. ex-post evaluation labels (真实结果层): official FRBNY SCE national
   headline series (chart.xlsx, retrieved 2026-10-21) — how much did the
   actual series move this month. Two series kept separate:
     sce_med1y_q9    = median 1-year-ahead expected inflation (density/Q9)
     sce_med1y_q8p   = median 1-year-ahead point prediction (Q8)
   Magnitude thresholds come from the FIXED reference period 2013-06..2018-12
   (all pre-window history): small <= median |Δ|, medium <= P80 |Δ|,
   large otherwise; never tuned on model results. These labels are evaluation
   information ONLY — never an ex-ante input/news/weighting switch.

B. ex-ante environment labels (当时可知层): what was publicly knowable at
   as_of — latest first-release headline CPI y/y (+ 3-release acceleration),
   latest food/energy component y/y, EIA gasoline prior-month level,
   NYT window news intensity by topic from the completed label stores,
   release anomalies (e.g. the 2025-10 CPI release canceled in the government
   shutdown). Every value carries reference_period/published_at/source.

Usage: python scripts/build_sce_month_regimes.py \
           --out outputs/sce_month_regimes_20261022_v1
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import openpyxl  # noqa: E402

from label_sce_news_pool import (  # noqa: E402
    build_pool_tolerant, load_old_labels)
from studies.sce_inflation_expectations.news_selection_trial import (  # noqa: E402
    RULE_FILE, RecallRules)

CHART = ROOT / "data/raw/sce_micro_refresh_20261021/chart.xlsx"
COVERAGE = ROOT / "outputs/sce_fullperiod_data_20261021_v1/coverage.json"
HEADLINE = ROOT / "data/raw/bls_initial_releases/headline_cpi.jsonl"
COMPONENTS = ROOT / "data/raw/bls_initial_releases/components_cpi_full.jsonl"
GASOLINE = ROOT / "data/raw/eia_gasoline/gasoline_retail_regular_monthly.jsonl"

REF_START, REF_END = "2013-06", "2018-12"  # fixed threshold reference period
FLAT_EPS = 0.005  # pp deadband for direction

SERIES = {  # csv prefix -> (chart column index, series_id, meaning)
    "q9": (1, "sce_med1y_q9",
           "median one-year-ahead expected inflation rate (density-based, Q9)"),
    "q8p": (7, "sce_med1y_q8p",
            "median one-year-ahead point prediction (Q8)"),
}


def month_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + k
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def read_chart_series() -> dict[str, dict[str, float]]:
    """{series_prefix: {'YYYY-MM': value}} from the official chart workbook."""
    wb = openpyxl.load_workbook(CHART, read_only=True)
    ws = wb["Inflation expectations"]
    out = {k: {} for k in SERIES}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 4 or not isinstance(row[0], int):
            continue
        ym = f"{row[0]:06d}"
        ym = f"{ym[:4]}-{ym[4:]}"
        for prefix, (col, _, _) in SERIES.items():
            if row[col] is not None:
                out[prefix][ym] = float(row[col])
    wb.close()
    return out


def classify(abs_change: float, t_small: float, t_large: float) -> str:
    if abs_change <= t_small:
        return "small"
    return "medium" if abs_change <= t_large else "large"


def direction(change: float) -> str:
    if abs(change) < FLAT_EPS:
        return "flat"
    return "up" if change > 0 else "down"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def latest_before(records: list[dict], as_of: str, value_key: str = "value"):
    """Latest record with published_at <= as_of (as_of ISO with tz)."""
    elig = [r for r in records if r["published_at"] <= as_of]
    return max(elig, key=lambda r: r["published_at"]) if elig else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/sce_month_regimes_20261022_v1")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cov = json.loads(COVERAGE.read_text())["months"]
    months = [m["target_month"] for m in cov]
    as_of = {m["target_month"]: m["as_of"] for m in cov}
    news_windows = {m["target_month"]: m["diagnostics"]["news_window_months"]
                    for m in cov}

    # ---------- A: ex-post truth movement ----------
    series = read_chart_series()
    thresholds = {}
    for prefix, (_, series_id, _) in SERIES.items():
        vals = series[prefix]
        ref_deltas = [abs(vals[m] - vals[month_add(m, -1)])
                      for m in vals
                      if REF_START <= m <= REF_END and month_add(m, -1) in vals]
        thresholds[prefix] = {
            "series_id": series_id,
            "reference_period": [REF_START, REF_END],
            "n_reference_changes": len(ref_deltas),
            "t_small_median_abs_change": statistics.median(ref_deltas),
            "t_large_p80_abs_change": statistics.quantiles(ref_deltas, n=100)[79],
        }

    # ---------- B: ex-ante environment ----------
    headline = load_jsonl(HEADLINE)
    components = load_jsonl(COMPONENTS)
    gasoline = {r["reference_period"]: r for r in load_jsonl(GASOLINE)}
    labels = load_old_labels()  # union of every label store incl. full run
    rules = RecallRules(json.loads(RULE_FILE.read_text()))

    rows = []
    for target in months:
        row = {"target_month": target}
        # A
        for prefix in SERIES:
            vals = series[prefix]
            cur, prev = vals.get(target), vals.get(month_add(target, -1))
            ch = round(cur - prev, 4) if cur is not None and prev is not None else None
            t = thresholds[prefix]
            row.update({
                f"{prefix}_current": cur, f"{prefix}_previous": prev,
                f"{prefix}_signed_change_pp": ch,
                f"{prefix}_abs_change_pp": abs(ch) if ch is not None else None,
                f"{prefix}_direction": direction(ch) if ch is not None else None,
                f"{prefix}_magnitude": (classify(
                    abs(ch), t["t_small_median_abs_change"],
                    t["t_large_p80_abs_change"]) if ch is not None else None),
            })
        # B: CPI headline + acceleration over the last 3 releases
        cutoff = as_of[target]
        latest = latest_before(headline, cutoff)
        if latest:
            earlier = sorted(
                (r for r in headline if r["published_at"] <= cutoff),
                key=lambda r: r["published_at"])
            third = earlier[-4] if len(earlier) >= 4 else None
            row.update({
                "cpi_yoy_latest": latest["value"],
                "cpi_ref_period": latest["reference_period"],
                "cpi_published_at": latest["published_at"],
                "cpi_source_sha256": latest["source_sha256"],
                "cpi_accel_3rel_pp": (round(latest["value"] - third["value"], 2)
                                      if third else None),
                "cpi_stale_gap_months": None,  # filled below
            })
            # staleness: expected latest ref = target minus 1 month
            exp = month_add(target, -1)
            gap = 0
            probe = exp
            while probe > latest["reference_period"]:
                gap += 1
                probe = month_add(probe, -1)
            row["cpi_stale_gap_months"] = gap
        else:
            row.update({"cpi_yoy_latest": None, "cpi_ref_period": None,
                        "cpi_published_at": None, "cpi_source_sha256": None,
                        "cpi_accel_3rel_pp": None, "cpi_stale_gap_months": None})
        # food/energy components (latest available)
        for sig in ("cpi_food_yoy", "cpi_energy_yoy"):
            sub = [r for r in components if r["signal_id"] == sig]
            hit = latest_before(sub, cutoff)
            row[sig.replace("cpi_", "").replace("_yoy", "") + "_yoy_latest"] = \
                hit["value"] if hit else None
            row[sig.replace("cpi_", "").replace("_yoy", "") + "_yoy_ref"] = \
                hit["reference_period"] if hit else None
        # gasoline: previous calendar month mean (EIA weekly -> monthly agg)
        gprev = gasoline.get(month_add(target, -1))
        gprev2 = gasoline.get(month_add(target, -2))
        row["gasoline_prev_month_mean_usd"] = gprev["price_mean"] if gprev else None
        row["gasoline_prev_month_mom_pct"] = (
            round(100 * (gprev["price_mean"] / gprev2["price_mean"] - 1), 2)
            if gprev and gprev2 else None)
        # news intensity in this month's window (labels already complete)
        pool, _ = build_pool_tolerant(ROOT, target, cutoff, rules)
        cnt = Counter()
        for r in pool:
            lab = labels.get(r["article_id"])
            if not lab:
                cnt["unlabeled"] += 1
                continue
            cnt[f"decision_{lab['decision']}"] += 1
            if lab["decision"] == "keep":
                for t in lab.get("topics") or []:
                    cnt[f"keep_topic_{t}"] += 1
        row["news_candidates"] = len(pool)
        row["news_unlabeled"] = cnt["unlabeled"]
        row["news_keep"] = cnt["decision_keep"]
        row["news_background"] = cnt["decision_background"]
        for t in ("policy", "supply_costs", "living_prices",
                  "employment_income_consumption", "economic_outlook"):
            row[f"news_keep_{t}"] = cnt[f"keep_topic_{t}"]
        # anomalies
        flags = []
        if row["cpi_stale_gap_months"] and row["cpi_stale_gap_months"] >= 2:
            flags.append(f"stale_cpi_release_gap_{row['cpi_stale_gap_months']}m")
        if target in ("2025-11", "2025-12"):
            flags.append("government_shutdown_2025_cpi_2025_10_canceled")
        row["anomaly_flags"] = ";".join(flags)
        rows.append(row)

    fieldnames = list(rows[0])
    with (args.out / "month_regimes.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    definition = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": ("month regime labels for error diagnosis; two strictly "
                    "separated layers"),
        "layer_A_ex_post": {
            "meaning": ("how much the OFFICIAL SCE national series actually "
                        "moved this month; evaluation-only, never an ex-ante "
                        "input/news/weighting switch"),
            "source": {"file": str(CHART.relative_to(ROOT)),
                       "sheet": "Inflation expectations",
                       "retrieved_at": "2026-10-21",
                       "note": ("latest-vintage official aggregates; SCE "
                                "headline aggregates are not revised")},
            "series": {p: {"series_id": s[1], "meaning": s[2]}
                       for p, s in SERIES.items()},
            "direction_deadband_pp": FLAT_EPS,
            "magnitude_rule": ("small <= median |Δ|, medium <= P80 |Δ|, large "
                               "otherwise; thresholds from the FIXED reference "
                               "period below, identical for all 93 months; "
                               "never tuned on model results"),
            "thresholds": thresholds,
        },
        "layer_B_ex_ante": {
            "meaning": ("what was publicly knowable at as_of; the ONLY layer "
                        "eligible for ex-ante mechanism conditioning, and then "
                        "only with separate pre-registration"),
            "cpi_headline": {"file": str(HEADLINE.relative_to(ROOT)),
                             "extraction": "scripts/extract_cpi_headline.py "
                                           "(first-release PDFs, quote+page+sha256)",
                             "coverage": "97/98 archived releases; 2018-10 in handoff"},
            "cpi_components": {"file": str(COMPONENTS.relative_to(ROOT)),
                               "note": "food/energy latest available <= as_of"},
            "gasoline": {"file": str(GASOLINE.relative_to(ROOT)),
                         "note": ("prior calendar month mean of EIA weekly "
                                  "retail regular; ~1 week publication lag, "
                                  "available by as_of")},
            "news_intensity": ("candidate pool of the month's two source-month "
                               "window joined to the union of all label stores; "
                               "counts of keep by topic"),
            "anomaly_flags": ["stale_cpi_release_gap_Nm",
                              "government_shutdown_2025_cpi_2025_10_canceled"],
        },
        "months": len(rows),
        "window": [months[0], months[-1]],
    }
    (args.out / "regime_definition.json").write_text(
        json.dumps(definition, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"rows": len(rows), "out": str(args.out),
                      "unlabeled_news_total": sum(r["news_unlabeled"] for r in rows)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
