#!/usr/bin/env python3
"""Offline analysis of a completed SCE cognition presentation trial."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studies.sce_inflation_expectations.evaluation.cognition import evaluate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, type=Path,
                        help="Prepared cognition trial folder with completed local run artifacts")
    parser.add_argument("--out", type=Path,
                        help="Fresh ignored output directory under outputs/ (default: timestamped)")
    parser.add_argument("--draws", type=int, default=1000,
                        help="Exploratory person-cluster bootstrap draws (default: 1000)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = args.out or ROOT / "outputs" / (
        "sce_cognition_trial_evaluation_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    summary = evaluate(args.folder, out, draws=args.draws)
    compact = {
        "status": summary["status"],
        "output": str(out.resolve()),
        "primary_contrast": summary["primary_contrast"],
        "primary_metric": summary["primary_metric"],
        "coverage_ok": all(item["valid_fraction"] >= .99 and item["scorable_fraction"] >= .99
                            for item in summary["coverage"].values()),
        "pilot_continuation_gates_by_detailed_vs_label": summary["pilot_continuation_gates_by_detailed_vs_label"],
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
