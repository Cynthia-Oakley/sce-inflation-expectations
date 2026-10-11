"""Thin entry point for offline multi-period preparation."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.coverage_preparation import main

if __name__ == "__main__":
    main()
