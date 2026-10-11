#!/usr/bin/env python3
"""Offline preparation and budget-gated paired confidence experiment."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.confidence_trial import main
if __name__ == '__main__':
    main()
