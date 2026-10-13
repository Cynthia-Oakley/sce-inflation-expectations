#!/usr/bin/env python3
"""Zero-API SCE prior inventory and conditional-update input preparation."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studies.sce_inflation_expectations.prior_belief_trial_preparation import prepare


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--reference-cache", type=Path)
    args = p.parse_args()
    prepare(ROOT, args.out, args.reference_cache)
