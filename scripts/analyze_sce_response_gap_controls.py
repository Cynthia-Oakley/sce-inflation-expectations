#!/usr/bin/env python3
"""Describe conditional response gaps without API calls or density refitting."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.response_gap_controls import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, default=ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1')
    parser.add_argument('--prepared', type=Path, default=ROOT/'outputs/sce_reference_validation_trial_20261017_v2')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    run(args.evaluation, args.prepared, args.out)
