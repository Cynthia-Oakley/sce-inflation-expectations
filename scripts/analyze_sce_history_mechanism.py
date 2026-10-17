#!/usr/bin/env python3
"""Offline follow-up: personal history coefficients, Sim-only R2 and SCE proxies."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation'))
from history_mechanism import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    run(args.out)
