#!/usr/bin/env python3
"""Thin offline entry; never resends a request."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.news_label_completion_preparation import main
if __name__ == '__main__':
    main()
