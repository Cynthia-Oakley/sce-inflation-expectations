#!/usr/bin/env python3
"""Offline numeracy validation on existing real and simulated SCE answers."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.numeracy_audit import run_audit

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cache', type=Path, help='Reuse an evaluation extract produced by this entry; record its hash')
    args = p.parse_args()
    run_audit(ROOT, args.output.resolve(), args.cache.resolve() if args.cache else None)
