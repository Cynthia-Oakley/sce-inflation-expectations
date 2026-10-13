#!/usr/bin/env python3
"""Offline SCE probability-reporting analysis; no API or simulation calls."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.reporting_behavior.analysis import run


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--primary-run',type=Path,help='Run the separately registered supplementary controls against an existing primary run')
    args = ap.parse_args()
    if args.primary_run:
        from studies.sce_inflation_expectations.reporting_behavior.controls import run_controls
        run_controls(ROOT,args.out,args.primary_run)
    else:
        run(ROOT,args.out,ROOT/'docs/workstreams/20261013_behavior/codex_protocol.json')
