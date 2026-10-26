#!/usr/bin/env python3
"""Isolated cached-truth evaluator; never called by input preparation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.full_a_personal import main

if __name__ == '__main__':
    main()
