#!/usr/bin/env python3
"""Recompute frozen analysis with a strict missing-value JSON export adapter."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.confidence_analysis_export import main
if __name__ == '__main__':
    main()
