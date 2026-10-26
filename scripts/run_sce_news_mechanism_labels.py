#!/usr/bin/env python3
"""Budget-gated supplemental news label runner."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.news_mechanism_label_runner import main

if __name__ == "__main__":
    main()
