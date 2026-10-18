#!/usr/bin/env python3
"""Locate observed human/model update mismatches using verified cached inputs."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.update_mismatch_profiles import analyze


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze(args.out)
    print(json.dumps({'status': result['status'], 'output': str(args.out.resolve()),
                      'new_api_calls': 0, 'n_person_months': result['n_person_months'],
                      'groups_at_0_5pp': {k: v['equal_month_overview']['n_person_months']
                          for k, v in result['profiles_by_threshold']['0.5'].items()}}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
