#!/usr/bin/env python3
"""Offline recent-B evaluation and descriptive population readout; no API calls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.recent_b_readout import main
if __name__ == '__main__':
    main()
