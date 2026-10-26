#!/usr/bin/env python3
"""Render a static HTML and Canvas explanation of existing frozen inputs; zero API."""
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.reports.mechanism_guide import render

if __name__ == '__main__':
    print(json.dumps(render(), ensure_ascii=False, indent=2))
