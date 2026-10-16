#!/usr/bin/env python3
"""Offline analysis of a completed SCE household-finance three-arm trial."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studies.sce_inflation_expectations.evaluation.household_finance import evaluate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', '--prepared-dir', dest='folder', type=Path, required=True)
    parser.add_argument('--out', '--output-dir', dest='out', type=Path)
    parser.add_argument('--draws', '--bootstrap-draws', dest='draws', type=int, default=1000)
    args = parser.parse_args(argv)
    out = args.out or ROOT / 'outputs' / ('sce_household_finance_evaluation_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    summary = evaluate(args.folder, out, draws=args.draws)
    print(json.dumps({'status': summary['status'], 'output': str(out.resolve()),
                      'primary_metric': summary['primary_metric'], 'primary_contrast': summary['primary_contrast'],
                      'primary_continuation_gate': summary['primary_continuation_gate']}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
