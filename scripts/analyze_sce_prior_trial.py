#!/usr/bin/env python3
"""Offline observed-prior evaluation; never launches an API request."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.prior_belief_analysis import main
if __name__ == '__main__':
    main()
