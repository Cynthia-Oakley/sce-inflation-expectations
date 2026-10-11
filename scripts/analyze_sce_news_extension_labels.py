#!/usr/bin/env python3
"""Thin offline entry for new-period news-label acceptance and libraries."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.news_extension_label_analysis import main
if __name__ == '__main__':
    main()
