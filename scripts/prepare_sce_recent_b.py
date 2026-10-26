#!/usr/bin/env python3
"""Offline recent-B source qualification; never dispatches an LLM request."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.recent_b_preflight import main

if __name__=='__main__':
    main()
