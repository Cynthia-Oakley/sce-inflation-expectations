#!/usr/bin/env python3
"""Analyze a completed news trial offline, without new API calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.news_exposure_analysis import analyze

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(ROOT, args.trial, args.out)
    print(json.dumps({'analysis_directory': str(args.out), 'calls': result['actual_simulation_calls'],
                      'estimated_cost_usd': result['estimated_simulation_cost_usd']}, ensure_ascii=False))
