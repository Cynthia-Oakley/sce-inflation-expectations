#!/usr/bin/env python3
"""Run the fixed past-only update-direction diagnostic, without network access."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.update_direction import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); result = run(args.out)
    print({k: v['summary']['center_mae_pp'] for k, v in result['frozen_scalar_diagnostic'].items()})
