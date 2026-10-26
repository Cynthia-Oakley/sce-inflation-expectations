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
    parser.add_argument('--phase', choices=['gate', 'main'])
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.config is None: parser.error('prepare requires --config')
        config = read_json(args.config)
        if config['mechanism'] == 'synthetic_psychological_state':
            from studies.sce_inflation_expectations.experiments.psychological_state import prepare
        elif config['mechanism'] == 'wave_psychological_state':
            from studies.sce_inflation_expectations.experiments.psychological_wave_state import prepare
        elif config['mechanism'] == 'previous_financial_outlook':
            from studies.sce_inflation_expectations.experiments.financial_outlook import prepare
        elif config['mechanism'] == 'public_consumer_context':
            from studies.sce_inflation_expectations.experiments.public_consumer_context import prepare
        elif config['mechanism'] == 'q8_delta_absolute_q9':
            from studies.sce_inflation_expectations.experiments.q8_delta import prepare
        elif config['mechanism'] == 'temperature_sensitivity':
            from studies.sce_inflation_expectations.experiments.temperature import prepare
        elif config['mechanism'] == 'fixed_model_migration':
            from studies.sce_inflation_expectations.experiments.model_migration import prepare
        elif config['mechanism'] == 'fixed_model_migration_completion':
            from studies.sce_inflation_expectations.experiments.model_migration import prepare_completion as prepare
        elif config['mechanism'] == 'procurement_price_engineering':
            from studies.sce_inflation_expectations.experiments.procurement_prices import prepare
        elif config['mechanism'] == 'procurement_price_qwen':
            from studies.sce_inflation_expectations.experiments.procurement_qwen import prepare
        elif config['mechanism'] == 'procurement_price_qwen_normalization':
            from studies.sce_inflation_expectations.experiments.procurement_qwen import prepare_normalized as prepare
        elif config['mechanism'] == 'price_background_qwen':
            from studies.sce_inflation_expectations.experiments.price_background import prepare
        elif config['mechanism'] in ('v32_same_input','v32_same_input_siliconflow'):
            from studies.sce_inflation_expectations.experiments.model_comparison import prepare
        elif config['mechanism'] == 'v32_new2025_validation':
            from studies.sce_inflation_expectations.experiments.post2025_trial import prepare
        elif config['mechanism'] == 'v32_news_matching':
            from studies.sce_inflation_expectations.experiments.news_matching import prepare
        else:
            parser.error('Unknown mechanism adapter')
        prepare(args.folder, config); return
    if args.action == 'evaluate':
        if args.out is None: parser.error('evaluate requires --out')
        from studies.sce_inflation_expectations.evaluation.frozen_trial import evaluate
        evaluate(args.folder, args.out); return
    if args.action == 'worker': return worker(args.folder, args.job_index, args.scripted)
    dispatch(args.folder, args.action == 'dry-run', args.workers, args.phase)

if __name__ == '__main__': main()
