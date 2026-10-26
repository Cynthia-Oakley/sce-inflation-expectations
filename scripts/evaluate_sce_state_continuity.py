#!/usr/bin/env python3
"""Evaluation-only truth preparation and cached state-chain scoring."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.evaluation.state_continuity import prepare_truth, evaluate

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('prepare-truth'); a.add_argument('--package', type=Path, required=True)
    a.add_argument('--history', type=Path, required=True); a.add_argument('--out', type=Path, required=True)
    a = sub.add_parser('evaluate'); a.add_argument('--package', type=Path, required=True)
    a.add_argument('--calls', type=Path, required=True); a.add_argument('--truth', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.command == 'prepare-truth': result = prepare_truth(args.package, args.history, args.out)
    else: result = evaluate(args.package, args.calls, args.truth, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
