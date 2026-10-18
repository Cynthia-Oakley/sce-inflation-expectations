#!/usr/bin/env python3
"""Render the existing reading-page supplement from cached aggregate results."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.response_gap_report import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic', type=Path, default=ROOT/'outputs/sce_response_gap_diagnostic_20261018_v1')
    parser.add_argument('--controls', type=Path, default=ROOT/'outputs/sce_response_gap_controls_20261018_v3')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    run(args.diagnostic, args.controls, args.out)
