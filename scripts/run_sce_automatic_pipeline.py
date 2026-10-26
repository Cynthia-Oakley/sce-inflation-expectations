#!/usr/bin/env python3
"""Check, or once-launch, an approved call ledger followed by local evaluation."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.automatic_pipeline import read, inspect, execute


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--execute', action='store_true', help='Explicitly dispatch already-authorized requests')
    parser.add_argument('--out', type=Path, help='Fresh pipeline receipt directory, required for execution')
    args = parser.parse_args()
    if args.execute and args.out is None:
        parser.error('--execute requires --out')
    plan = read(args.plan)
    result = execute(plan, args.out) if args.execute else inspect(plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
