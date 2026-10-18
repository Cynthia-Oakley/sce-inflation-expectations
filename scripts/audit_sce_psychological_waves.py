#!/usr/bin/env python3
"""Audit downloaded public GSS waves; never calls a model."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.psychological_waves import audit

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    for wave, item in audit(args.manifest, args.out).items():
        print(wave, item['joint_weighted_n'], 'joint main-sample records;', item['complete_matching_n'], 'complete matching records')
