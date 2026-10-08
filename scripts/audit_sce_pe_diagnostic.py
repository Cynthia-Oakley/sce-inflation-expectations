#!/usr/bin/env python3
"""Read archived P/E/B messages and answers; no network, no providers."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.pe_diagnostic import run
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    run(ROOT, args.out.resolve())
