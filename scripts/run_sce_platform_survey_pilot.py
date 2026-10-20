#!/usr/bin/env python3
"""Prepare/run an explicitly approved official MCP format pilot."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.platform_survey_pilot import main

if __name__ == "__main__":
    main()
