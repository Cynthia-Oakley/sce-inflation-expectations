#!/usr/bin/env python3
"""Offline evaluation, no API calls."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.revision_format import evaluate

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--folder', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    result = evaluate(args.folder, args.out)
    print('Completed', result['new_api_calls'], 'requests; continuation gate:', result['candidate_continue_gate_passed'])
