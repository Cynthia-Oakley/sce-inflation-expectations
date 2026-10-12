#!/usr/bin/env python3
"""Offline analysis only; no simulation or model calls."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.lifetime_analysis import main
if __name__ == '__main__':
    main()
