#!/usr/bin/env python3
"""Offline evaluation of the 12-month reference scale-up."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.reference_validation import audit_prepared, evaluate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--draws', type=int, default=1000)
    parser.add_argument('--audit-prepared', action='store_true')
    args = parser.parse_args(argv)
    if args.audit_prepared:
        result = audit_prepared(args.folder)
        print(json.dumps({'status': 'prepared_inputs_audited_no_current_targets_read', 'prepared_files': result['prepared_file_count'], 'evaluation_api_calls': 0}))
    else:
        out = args.out or ROOT / 'outputs' / ('sce_reference_validation_evaluation_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        result = evaluate(args.folder, out, args.draws)
        print(json.dumps({'status': result['status'], 'output': str(out.resolve()), 'primary_month_scope': 'new_months', 'scopes': result['scopes']}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
