#!/usr/bin/env python3
"""Prepare private three-month state dependencies; no model calls or current truth."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.experiments.state_continuity import prepare

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT / "outputs/sce_fullperiod_data_20261021_v1")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--n", type=int, default=96)
    p.add_argument("--repeats", type=int, default=2)
    args = p.parse_args()
    result = prepare(args.source, args.out, n=args.n, repeats=args.repeats)
    print(json.dumps({k: v for k, v in result.items() if k != "source_sha256"}, ensure_ascii=False, indent=2))
