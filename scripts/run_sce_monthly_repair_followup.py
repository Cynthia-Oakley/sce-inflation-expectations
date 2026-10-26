#!/usr/bin/env python3
"""Six-position follow-up, reusing the existing repair queue and evaluator."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments import monthly_main_repair_followup as repair

if __name__ == '__main__':
    repair.bind_adapter()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    for name in ('previous', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('run', 'watch', '_worker', '_pipeline', '_generate', '_evaluate'):
        p = sub.add_parser(name); p.add_argument('--run-dir', type=Path, required=True)
        if name == 'run':
            p.add_argument('--confirm-six-position-repair', action='store_true')
    args = vars(parser.parse_args()); command = args.pop('command')
    folder = args.get('run_dir')
    if command == 'prepare':
        result = repair.prepare(**args)
    elif command == 'run':
        result = repair.run(folder, args['confirm_six_position_repair'])
    else:
        result = getattr(repair.base, command.lstrip('_'))(folder)
        if command == '_pipeline':
            repair.base.atomic_json(folder / 'pipeline_receipt.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
