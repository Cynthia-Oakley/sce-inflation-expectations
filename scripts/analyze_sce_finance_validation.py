#!/usr/bin/env python3
"""Offline evaluation of completed Q1 cross-month validation runs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.finance_validation import audit_prepared, evaluate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--draws', type=int, default=1000)
    parser.add_argument('--audit-prepared', action='store_true', help='Audit frozen inputs only; do not open current outcomes')
    args = parser.parse_args(argv)
    if args.audit_prepared:
        result = audit_prepared(args.folder)
        print(json.dumps({'status': 'prepared_inputs_audited_no_outcomes_read', 'prepared_files': result['prepared_file_count'], 'evaluation_api_calls': 0}))
    else:
        out = args.out or ROOT / 'outputs' / ('sce_finance_validation_evaluation_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        result = evaluate(args.folder, out, args.draws)
        print(json.dumps({'status': result['status'], 'output': str(out.resolve()), 'facts_minus_baseline': result['facts_minus_baseline']}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
