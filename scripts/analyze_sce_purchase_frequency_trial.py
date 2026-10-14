#!/usr/bin/env python3
"""Offline evaluation entry point; never calls the simulation API."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.purchase_frequency import evaluate

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--folder', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(); result = evaluate(args.folder, args.out)
    print('completed', result['new_api_calls'], 'calls; candidate gate', result['candidate_continue_gate_passed'])
