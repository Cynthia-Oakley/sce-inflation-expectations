#!/usr/bin/env python3
"""Prepare missing local E or resolve prior fields, without model calls."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.state_continuity_inputs import (
    prepare_environments, prepare_histories, prepare_families,
)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=['environments', 'history', 'families'])
    p.add_argument('--preparation', type=Path, default=ROOT / 'outputs/sce_state_continuity_preparation_20261022_v1')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--delivery', type=Path)
    args = p.parse_args()
    if args.phase == 'history': prepare_histories(args.preparation, args.out)
    elif args.phase == 'families': prepare_families(args.preparation, args.out, delivery=args.delivery)
    else: prepare_environments(args.out)
