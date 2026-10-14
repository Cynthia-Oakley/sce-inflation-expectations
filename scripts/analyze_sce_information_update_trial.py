#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.evaluation.information_update import evaluate

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--folder', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(); r = evaluate(args.folder, args.out)
    print('completed', r['new_api_calls'], 'new calls; reused', r['reused_A_answer_rows'], '; candidate gate', r['candidate_continue_gate_passed'])
