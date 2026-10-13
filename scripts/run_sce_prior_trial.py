#!/usr/bin/env python3
"""Prepare/dry-run/run the isolated observed-prior trial, with explicit budget."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.prior_belief_trial import main
if __name__ == '__main__':
    main()
