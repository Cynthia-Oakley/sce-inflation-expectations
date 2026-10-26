#!/usr/bin/env python3
"""Prepare monthly recent-B proxy frames without paid API calls."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.recent_b_rolling_preflight import main
if __name__=='__main__':main()
