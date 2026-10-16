#!/usr/bin/env python3
"""Zero-API, aggregate-only analysis entry point."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'studies/sce_inflation_expectations/evaluation'))
from household_finance_associations import CACHE, run


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=CACHE)
    args = parser.parse_args()
    run(args.out, args.cache)
