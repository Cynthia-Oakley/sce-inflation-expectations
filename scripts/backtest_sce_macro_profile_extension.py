#!/usr/bin/env python3
"""Offline rolling population-margin comparisons; no simulation calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.macro_profile_extension import (
    build_feature_rows, evaluate, EMPLOYMENT_MODELS, INCOME_MODELS)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--population-stats', type=Path, required=True)
    ap.add_argument('--macro-observations', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--include-bea', action='store_true')
    args = ap.parse_args(); args.out.mkdir(parents=True, exist_ok=False)
    plan = {'employment_models': EMPLOYMENT_MODELS,
            'income_models': INCOME_MODELS if args.include_bea else {k: v for k, v in INCOME_MODELS.items() if len(v) == 1},
            'min_train_labels': 24, 'label_cutoff': 't-minus-10 assumed, not historical posting proof',
            'cutoff': 'previous month end America/New_York', 'ridge_alpha': 1,
            'parameter_search': False, 'evaluation_status': 'exploratory rolling; existing outcomes have already been examined; not a blind holdout',
            'employment_version_policy': 'first-release variant for direct comparison with prior pilot',
            'income_version_policy': 'latest <= as_of among archived columns; historical revisions incompletely covered',
            'income_unknown_policy': 'carry donor unknown share; regress conditional known three groups',
            'input_hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.population_stats, args.macro_observations]},
            'code_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'studies/sce_inflation_expectations/macro_profile_extension.py']},
            'created_at_utc': datetime.now(timezone.utc).isoformat(), 'real_llm_calls': 0}
    (args.out/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
    population = json.loads(args.population_stats.read_text())
    observations = [json.loads(line) for line in args.macro_observations.read_text().splitlines()]
    all_summary = {}
    for target in ['employment', 'income']:
        for weighting in ['weighted', 'raw']:
            rows, skipped = build_feature_rows(population, observations, target=target, weighting=weighting, bea=args.include_bea)
            models = plan[f'{target}_models']
            predictions, summary = evaluate(rows, target=target, models=models)
            key = f'{target}_{weighting}'; all_summary[key] = summary
            folder = args.out/key; folder.mkdir()
            for name, data in [('feature_rows.json', rows), ('predictions.json', predictions), ('skipped.json', skipped), ('summary.json', summary)]:
                (folder/name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
            print(json.dumps({key: {k: v for k, v in summary.items() if k not in ['rolling_12','yearly']}}, ensure_ascii=False), flush=True)
    (args.out/'summary.json').write_text(json.dumps(all_summary, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
