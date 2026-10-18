#!/usr/bin/env python3
"""Describe archived human/model gaps without APIs or refitting probabilities."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.response_gap import analyze


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'outputs/sce_reference_validation_evaluation_20261017_v1')
    parser.add_argument('--out', type=Path, required=True, help='Fresh private directory under outputs')
    args = parser.parse_args(argv)
    result = analyze(args.source, args.out)
    print(json.dumps({'status': result['status'], 'output': str(args.out.resolve()),
                      'evaluation_api_calls': 0, 'refitted_bin_vectors': 0,
                      'paired_person_months': result['coverage']['total']['paired_person_months'],
                      'reconciliation_passed': result['reconciliation']['passed'],
                      'scopes': result['scopes']}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
