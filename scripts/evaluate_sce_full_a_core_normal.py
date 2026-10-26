#!/usr/bin/env python3
"""Offline readout for a sealed all-month Core + Normal A82 expansion."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.full_a_core_normal import main

if __name__ == '__main__':
    main()
