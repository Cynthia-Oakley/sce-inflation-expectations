#!/usr/bin/env python3
"""Render aggregate recent-B results without API calls or re-scoring."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.reports.recent_b_report import main
if __name__=='__main__':
    main()
