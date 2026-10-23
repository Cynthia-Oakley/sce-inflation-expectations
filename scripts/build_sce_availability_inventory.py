#!/usr/bin/env python3
"""Build a machine-readable per-month P/E availability inventory for the 93-month
full-period delivery (outputs/sce_fullperiod_materialized_20261022_v2).

Read-only audit: reuses the existing coverage.json plus each month's
population_receipt.json / environment_receipt.json / news_label_index.json.
No downloads, no API calls, no writes outside the requested --out directory.

Usage:
    python scripts/build_sce_availability_inventory.py --out outputs/<new_dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DELIVERY = REPO / "outputs" / "sce_fullperiod_materialized_20261022_v2"


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_month_record(cov: dict, month_dir: Path) -> dict:
    yyyymm = cov["target_month"].replace("-", "")
    pop = load_json(month_dir / "population_receipt.json")
    env = load_json(month_dir / "environment_receipt.json")
    news = load_json(month_dir / "news_label_index.json")

    blockers: list[str] = []
    if cov.get("micro_published_at") is None:
        blockers.append("micro_publish_date_unknown")
    if not cov.get("micro_truth_available"):
        blockers.append("no_local_micro_for_target_month")
    if pop.get("synthetic"):
        blockers.append("synthetic_population_extension")

    return {
        "target_month": cov["target_month"],
        "as_of": cov["as_of"],
        "status": cov["status"],
        "population": {
            "synthetic": bool(pop.get("synthetic")),
            "frame_n": pop.get("frame_n"),
            "entries": pop.get("entries"),
            "micro_source_period": cov.get("micro_source_period"),
            "micro_published_at": cov.get("micro_published_at"),
            "raw_weight_missing_n": pop.get("raw_weight_missing_n"),
            "strict_B_eligible_receipt": bool(pop.get("strict_B_eligible")),
        },
        "truth": {
            "micro_truth_available": cov["micro_truth_available"],
            "aggregate_truth_available": cov["aggregate_truth_available"],
        },
        "environment": {
            "ready": env.get("environment_available"),
            "food_available": env.get("food_available"),
            "signals": env.get("signals"),
            "events": env.get("events"),
            "gaps": env.get("gaps", []),
        },
        "news": {
            "window": news.get("window"),
            "n_selected": news.get("n_selected"),
            "n_labeled": news.get("n_labeled"),
            "n_missing_labels": news.get("n_missing_labels"),
        },
        "diagnostics": cov.get("diagnostics", {}),
        "strict_b_blockers": blockers,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--delivery", type=Path, default=DELIVERY)
    args = ap.parse_args()

    out: Path = args.out
    if out.exists():
        raise SystemExit(f"refusing to overwrite existing directory: {out}")
    out.mkdir(parents=True)

    coverage = load_json(args.delivery / "coverage.json")
    records = []
    for cov in coverage["months"]:
        month_dir = args.delivery / cov["target_month"].replace("-", "")
        records.append(build_month_record(cov, month_dir))

    jsonl = out / "monthly_inventory.jsonl"
    with open(jsonl, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    gap_months = {}
    for rec in records:
        for gap in rec["environment"]["gaps"]:
            fam = gap.get("family", "unknown")
            gap_months.setdefault(fam, []).append(
                {
                    "target_month": rec["target_month"],
                    "reference_period": gap.get("reference_period"),
                    "reason": gap.get("reason"),
                    "substitute_reference_period": gap.get("substitute_reference_period"),
                }
            )

    summary = {
        "delivery": str(args.delivery.relative_to(REPO)),
        "n_months": len(records),
        "first_month": records[0]["target_month"],
        "last_month": records[-1]["target_month"],
        "status_counts": {},
        "synthetic_months": [r["target_month"] for r in records if r["population"]["synthetic"]],
        "micro_missing_months": [
            r["target_month"] for r in records if not r["truth"]["micro_truth_available"]
        ],
        "raw_weight_missing": {
            r["target_month"]: r["population"]["raw_weight_missing_n"]
            for r in records
            if r["population"]["raw_weight_missing_n"]
        },
        "news_missing_labels_months": [
            r["target_month"] for r in records if r["news"]["n_missing_labels"]
        ],
        "environment_gap_families": {
            fam: {"n_months": len({g["target_month"] for g in items}), "items": items}
            for fam, items in sorted(gap_months.items())
        },
        "coverage_generated_at": coverage.get("generated_at"),
        "coverage_sources": coverage.get("sources"),
        "convention": coverage.get("convention"),
        "new_api_calls": 0,
    }
    for rec in records:
        summary["status_counts"][rec["status"]] = summary["status_counts"].get(rec["status"], 0) + 1

    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(f"months={len(records)} out={out}")
    print("status_counts=", summary["status_counts"])
    print("gap_families=", {k: v["n_months"] for k, v in summary["environment_gap_families"].items()})


if __name__ == "__main__":
    main()
