#!/usr/bin/env python3
"""Check previous Q2 using validated caches; no original workbooks or API."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
# Prefer the maintained study source; official Core remains an external dependency.
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.evaluation.outlook_forward import run
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', required=True, type=Path)
    result = run(p.parse_args().out); print(result['expanding_summary'])
