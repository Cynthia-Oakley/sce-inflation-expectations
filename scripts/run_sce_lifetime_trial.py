#!/usr/bin/env python3
"""Run the isolated, budget-gated Lifetime Inflation Experience trial."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.lifetime_trial import main
if __name__ == '__main__':
    main()
