#!/usr/bin/env python3
"""Prepare/start/status a native-Terminal overnight supervisor. Prepare/status: zero API."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.monthly_main_background import KEYS, prepare, start, status, worker

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('prepare')
    for key in KEYS:
        command.add_argument('--' + key, type=Path, required=True)
    command.add_argument('--out', type=Path, required=True)
    for name in ('start', 'status', '_worker'):
        command = sub.add_parser(name)
        command.add_argument('--run-dir', type=Path, required=True)
    args = vars(parser.parse_args())
    name = args.pop('command')
    if name == 'prepare':
        result = prepare(**args)
    else:
        folder = args['run_dir']
        result = {'start': start, 'status': status, '_worker': worker}[name](folder)
    print(json.dumps(result, ensure_ascii=False, indent=2))
