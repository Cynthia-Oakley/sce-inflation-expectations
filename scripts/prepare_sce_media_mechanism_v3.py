#!/usr/bin/env python3
"""Assemble the seven-month V3 frozen prompts; no API or target answers."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies

studies.__path__ = [str(ROOT / "studies"), *studies.__path__]
from studies.sce_inflation_expectations.experiments.fox_mechanism_preparation import load_fox_labels, load_fox_pool
from studies.sce_inflation_expectations.experiments.media_mechanism_v3 import MONTHS
from studies.sce_inflation_expectations.experiments.media_mechanism_v3_preparation import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fox-labels", type=Path, default=ROOT / "outputs/sce_fox_mechanism_labels_20261025_v1")
    parser.add_argument("--fox-review", type=Path, default=ROOT / "outputs/sce_fox_mechanism_label_audit_20261025_v1/review.json")
    args = parser.parse_args()
    labels = load_fox_labels(args.fox_labels, args.fox_review if args.fox_review.exists() else None)
    fox = {month: load_fox_pool(ROOT, month, labels, require_english=True) for month in MONTHS}
    manifest = prepare(args.out, fox, fox_labels_dir=args.fox_labels,
                       fox_review_path=args.fox_review if args.fox_review.exists() else None)
    print(json.dumps({key: manifest[key] for key in (
        "status", "planned_calls", "estimated_cost_all_slots_usd",
        "conservative_reservation_all_slots_usd", "new_api_calls")}))


if __name__ == "__main__":
    main()
