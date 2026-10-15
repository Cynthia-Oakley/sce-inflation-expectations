#!/usr/bin/env python3
"""Prepare the source-limited offline matching prototype. No network or API."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'studies/sce_inflation_expectations/evaluation'))
from frequency_matching_candidate import run

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    run(p.parse_args().out)
