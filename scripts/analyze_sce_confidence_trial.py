#!/usr/bin/env python3
"""Extract evaluation truth or analyze paired confidence trial, no API calls."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.confidence_analysis import main
if __name__ == '__main__':
    main()
