#!/usr/bin/env python3
"""Compare two saved generations; no API calls or Q9 refitting."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.repeat_value import report

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); result = report(a.cases, a.out)
    print({k: v['equal_month_means'] for k, v in result['arms'].items()})
