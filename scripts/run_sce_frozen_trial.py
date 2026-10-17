#!/usr/bin/env python3
"""Shared frozen-prompt trials: prepare, dry-run, gated run, worker, evaluate."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
# Prefer the maintained study source; official Core remains an external dependency.
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import dispatch, worker, read_json

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'dry-run', 'run', 'worker', 'evaluate'])
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--job-index', type=int)
    parser.add_argument('--scripted', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.config is None: parser.error('prepare requires --config')
        config = read_json(args.config)
        if config['mechanism'] == 'synthetic_psychological_state':
            from studies.sce_inflation_expectations.experiments.psychological_state import prepare
        elif config['mechanism'] == 'previous_financial_outlook':
            from studies.sce_inflation_expectations.experiments.financial_outlook import prepare
        else:
            parser.error('Unknown mechanism adapter')
        prepare(args.folder, config); return
    if args.action == 'evaluate':
        if args.out is None: parser.error('evaluate requires --out')
        from studies.sce_inflation_expectations.evaluation.frozen_trial import evaluate
        evaluate(args.folder, args.out); return
    if args.action == 'worker': return worker(args.folder, args.job_index, args.scripted)
    dispatch(args.folder, args.action == 'dry-run', args.workers)

if __name__ == '__main__': main()
