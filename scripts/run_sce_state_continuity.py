#!/usr/bin/env python3
"""Prepare/authorize/run the one-attempt three-month state chain."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.state_continuity_execution import prepare, authorize, run

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('prepare'); a.add_argument('--preparation', type=Path, required=True)
    a.add_argument('--prompts', type=Path, required=True); a.add_argument('--core-check', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    a = sub.add_parser('authorize'); a.add_argument('--package', type=Path, required=True)
    a.add_argument('--confirmation', required=True)
    a = sub.add_parser('run'); a.add_argument('--package', type=Path, required=True); a.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.command == 'prepare': result = prepare(args.preparation, args.prompts, args.core_check, args.out)
    elif args.command == 'authorize': result = authorize(args.package, args.confirmation)
    else: result = run(args.package, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
