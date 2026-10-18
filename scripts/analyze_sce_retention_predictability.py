#!/usr/bin/env python3
"""Predict reported stability from past-only records; zero paid calls."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.retention_predictability import run


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    result = run(parser.parse_args().out)
    print('Completed; new API calls:', result['new_api_calls'],
          '; seconds:', round(result['timing_seconds']['total_before_writing'], 2))
