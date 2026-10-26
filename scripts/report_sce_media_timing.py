#!/usr/bin/env python3
"""Build the aggregate-only HTML, figure, and Canvas report for media timing."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studies.sce_inflation_expectations.reports.media_timing_report import publish


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="aggregate readout summary.json")
    parser.add_argument("--independent-source", type=Path, required=True,
                        help="independent aggregate bridge review JSON")
    parser.add_argument("--out", type=Path, required=True, help="fresh report directory")
    args = parser.parse_args()
    print(json.dumps(publish(args.source, args.independent_source, args.out), ensure_ascii=False, indent=2))
