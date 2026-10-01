"""Compare local Q9 density scores with public SCE derived fields and chart data.

Run: python3 scripts/audit_sce_q9_scoring.py --months 202001 202206
Reads original workbooks; writes aggregate diagnostics only to ignored outputs/.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
MICRO = ROOT / "data/raw/sce_audit_20260928/micro_2020_2024.xlsx"
CHART = ROOT / "data/raw/sce_audit_20260928/chart.xlsx"
MODULE = ROOT / "studies/sce_inflation_expectations/scoring/sce_q9.py"
spec = importlib.util.spec_from_file_location("sce_q9", MODULE)
assert spec and spec.loader
import sys

sce_q9 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sce_q9
spec.loader.exec_module(sce_q9)


def summarize(errors: list[float]) -> dict[str, float | int] | None:
    if not errors:
        return None
    ordered = sorted(errors)
    return {
        "n": len(errors),
        "median_absolute_error": median(ordered),
        "p95_absolute_error": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
        "max_absolute_error": ordered[-1],
        "within_0_001": sum(error <= 0.001 for error in errors),
        "within_0_01": sum(error <= 0.01 for error in errors),
        "within_0_1": sum(error <= 0.1 for error in errors),
    }


def audit(months: set[int]) -> dict:
    chart_book = load_workbook(CHART, read_only=True, data_only=True)
    chart = {int(row[0]): row[1] for row in chart_book["Inflation expectations"].iter_rows(min_row=5, values_only=True)
             if isinstance(row[0], (int, float)) and int(row[0]) in months}
    chart_book.close()

    book = load_workbook(MICRO, read_only=True, data_only=True)
    rows = book["Data"].iter_rows(values_only=True)
    next(rows)
    header = next(rows)
    names = ["date", "weight", "Q9_mean", "Q9_iqr", "Q9_cent25", "Q9_cent50", "Q9_cent75", "Q9_probdeflation"] + [f"Q9_bin{i}" for i in range(1, 11)]
    ix = {name: header.index(name) for name in names}
    by_month = defaultdict(lambda: {"rows": 0, "status": Counter(), "family": Counter(),
                                    "mean_errors": defaultdict(list), "iqr_errors": defaultdict(list),
                                    "beta_errors_by_support": defaultdict(list),
                                    "point_errors": defaultdict(list), "fit_losses": [],
                                    "predicted_means": [], "official_means": [], "predicted_weights": [],
                                    "official_weights": []})
    for row in rows:
        value = row[ix["date"]]
        if not isinstance(value, (int, float)) or int(value) not in months:
            continue
        month = int(value)
        data = by_month[month]
        data["rows"] += 1
        bins = [row[ix[f"Q9_bin{i}"]] for i in range(1, 11)]
        score = sce_q9.score_q9(bins)
        data["status"][score.status] += 1
        if score.family:
            data["family"][score.family] += 1
        reported_mean = row[ix["Q9_mean"]]
        weight = row[ix["weight"]]
        if isinstance(weight, (int, float)) and weight > 0:
            if isinstance(reported_mean, (int, float)):
                data["official_means"].append(float(reported_mean))
                data["official_weights"].append(float(weight))
            if score.mean is not None:
                data["predicted_means"].append(score.mean)
                data["predicted_weights"].append(float(weight))
        if score.status != "ok":
            continue
        if score.fit_loss is not None:
            data["fit_losses"].append(score.fit_loss)
        if isinstance(reported_mean, (int, float)):
            error = abs(score.mean - reported_mean)
            data["mean_errors"][score.family].append(error)
            if score.family == "generalized_beta":
                positive = [i for i, value in enumerate(bins) if value > 0]
                support = "open" if positive[0] == 0 or positive[-1] == 9 else "closed"
                continuity = "contiguous" if len(positive) == positive[-1] - positive[0] + 1 else "gapped"
                data["beta_errors_by_support"][f"{support}_{continuity}"].append(error)
        reported_iqr = row[ix["Q9_iqr"]]
        if isinstance(reported_iqr, (int, float)):
            data["iqr_errors"][score.family].append(abs(score.iqr - reported_iqr))
        for field, computed in (("Q9_cent25", score.p25), ("Q9_cent50", score.p50),
                                ("Q9_cent75", score.p75), ("Q9_probdeflation", score.prob_deflation)):
            reported = row[ix[field]]
            if isinstance(reported, (int, float)):
                data["point_errors"][field].append(abs(computed - reported))
    book.close()

    result = {"micro_source": str(MICRO.relative_to(ROOT)),
              "micro_sha256": hashlib.sha256(MICRO.read_bytes()).hexdigest(),
              "chart_source": str(CHART.relative_to(ROOT)),
              "scope": "Individual Q9 scoring and weighted headline comparison; data used for evaluation only, never Agent input.",
              "beta_replication_limit": "Minimum-distance CDF objective and alpha/beta >= 1 are documented implementation choices; not all original optimizer details are published.",
              "months": {}}
    for month, data in sorted(by_month.items()):
        predicted_headline = sce_q9.weighted_empirical_quantile(data["predicted_means"], data["predicted_weights"])
        official_micro_headline = sce_q9.weighted_empirical_quantile(data["official_means"], data["official_weights"])
        result["months"][str(month)] = {
            "rows": data["rows"], "status": dict(data["status"]), "family": dict(data["family"]),
            "individual_mean_error_by_family": {key: summarize(errors) for key, errors in data["mean_errors"].items()},
            "beta_mean_error_by_support": {key: summarize(errors) for key, errors in data["beta_errors_by_support"].items()},
            "individual_iqr_error_by_family": {key: summarize(errors) for key, errors in data["iqr_errors"].items()},
            "other_individual_field_errors": {key: summarize(errors) for key, errors in data["point_errors"].items()},
            "fitted_headline": predicted_headline,
            "official_micro_headline": official_micro_headline,
            "official_chart_headline": chart.get(month),
            "fitted_minus_chart": predicted_headline - chart[month] if month in chart else None,
            "official_micro_minus_chart": official_micro_headline - chart[month] if month in chart else None,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", nargs="+", type=int, default=[202001, 202206])
    args = parser.parse_args()
    result = audit(set(args.months))
    out = ROOT / "outputs/sce_q9_replication_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(out), "months": {
        month: {key: value for key, value in data.items() if key in
                ("rows", "status", "family", "individual_mean_error_by_family", "fitted_headline", "official_chart_headline", "fitted_minus_chart")}
        for month, data in result["months"].items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
