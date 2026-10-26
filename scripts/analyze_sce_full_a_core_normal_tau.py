#!/usr/bin/env python3
"""Offline tau follow-up; no API calls and no original output replacement."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.full_a_core_normal_tau import main

if __name__ == '__main__':
    main()
