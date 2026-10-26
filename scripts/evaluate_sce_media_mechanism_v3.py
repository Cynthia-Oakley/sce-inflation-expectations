#!/usr/bin/env python3
"""Evaluate real V3 calls, then compare with the original A82 generation."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies

studies.__path__ = [str(ROOT / "studies"), *studies.__path__]
from studies.sce_inflation_expectations.evaluation.frozen_trial import evaluate
from studies.sce_inflation_expectations.evaluation.media_mechanism_v3 import compare_with_a82


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("fresh output directory required")
    args.out.mkdir(parents=True)
    evaluate(args.folder, args.out / "new_arms")
    result = compare_with_a82(args.out / "new_arms", args.folder, args.out / "comparison")
    print(json.dumps({"status": result["schema"], "out": str(args.out), "new_api_calls": 0}))


if __name__ == "__main__":
    main()
