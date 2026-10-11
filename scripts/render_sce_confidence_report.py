#!/usr/bin/env python3
"""Aggregate-only figures and result update in the existing news reading page."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.confidence_reporting import main
if __name__ == '__main__':
    main()
