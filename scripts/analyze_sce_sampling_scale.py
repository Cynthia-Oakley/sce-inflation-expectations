#!/usr/bin/env python3
"""Offline 48/96/192-person sampling scale using existing SCE waves."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.evaluation.sampling_scale import run

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--draws', type=int, default=1000)
    p.add_argument('--seed', type=int, default=20261021)
    a = p.parse_args()
    result = run(a.out, a.draws, a.seed)
    print(result['pooled_equal_month'])
