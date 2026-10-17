#!/usr/bin/env python3
"""Time-ordered personal-history checks on cached scores; no network or API."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation'))
from history_forward import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    result = run(parser.parse_args().out)
    print('Completed with zero new API calls; seconds:', round(result['timing_seconds']['total_before_writing'], 3))
