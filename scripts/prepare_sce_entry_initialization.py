#!/usr/bin/env python3
"""Offline recent-donor support and soft aggregate calibration; zero API."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.evaluation.entry_initialization import prepare

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--months', nargs='+', default=['202505', '202506', '202507'])
    p.add_argument('--sizes', nargs='+', type=int, default=[96, 512])
    a = p.parse_args()
    result = prepare(a.out, months=tuple(a.months), sizes=tuple(a.sizes))
    print(f'Completed {len(result["units"])} offline units; no API calls.')
