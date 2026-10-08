#!/usr/bin/env python3
"""Offline cost normalization and group diagnostics for the frozen model pilot."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ARMS = ['deepseek_reference', 'llama', 'qwen']
FIELDS = ['age_group', 'education_group', 'household_income_band', 'numeracy', 'employment_status']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bootstrap', type=int, default=10000)
    args = parser.parse_args()
    if args.bootstrap < 1000:
        raise ValueError('at least 1000 resamples required')
    receipt_path = ROOT / 'docs/sources/sce_model_followup_final_20261008.json'
    receipt = json.loads(receipt_path.read_text())
    inputs = []
    for rel, expected in receipt['artifact_sha256'].items():
        path = ROOT / rel
        if sha(path) != expected:
            raise ValueError(f'frozen artifact changed: {rel}')
        inputs.append(path)
    folder = ROOT / 'outputs/sce_model_followup_analysis_20261008_v3'
    summary = json.loads((folder / 'summary.json').read_text())
    private_path = folder / 'paired_evaluation_private.jsonl'
    rows = [json.loads(line) for line in private_path.read_text().splitlines()]
    if len(rows) != 40 or len({row['case_id'] for row in rows}) != 40:
        raise ValueError('need forty unique development cases')
    inputs += [receipt_path, private_path, Path(__file__).resolve()]
    # Uniform token workloads permit cost comparisons despite incomplete arms.
    costs = {}
    for run in ['sce_earlier_model_trial_20261008', 'sce_model_followup_20261008', 'sce_llama33_resume2_20261008']:
        path = ROOT / 'outputs' / run
        state = json.loads((path / 'run_summary.json').read_text())
        for model, value in state['models'].items():
            if value.get('endpoint'):
                rate = value['endpoint']['pricing']
                item = costs.setdefault(model, {'input_usd_per_million': float(rate['prompt']) * 1e6,
                    'output_usd_per_million': float(rate['completion']) * 1e6,
                    'api_reported_usd': 0., 'unknown_reserved_usd': 0., 'attempts': 0, 'valid_cases': 0})
                if not math.isclose(item['input_usd_per_million'], float(rate['prompt']) * 1e6):
                    raise ValueError('price changed across runs')
                if not math.isclose(item['output_usd_per_million'], float(rate['completion']) * 1e6):
                    raise ValueError('price changed across runs')
        for line in (path / 'llm_calls.jsonl').read_text().splitlines():
            call = json.loads(line)
            item = costs[call['requested_model']]
            item['attempts'] += 1
            item['valid_cases'] += 'answer' in call and not call.get('error')
            key = 'unknown_reserved_usd' if call['billing']['uncertain'] else 'api_reported_usd'
            item[key] += call['billing']['charged_or_reserved_usd']
    for item in costs.values():
        item['normalized_one_call_usd'] = (2500 * item['input_usd_per_million'] + 150 * item['output_usd_per_million']) / 1e6
        item['normalized_1000_calls_usd'] = 1000 * item['normalized_one_call_usd']
        item['observed_cost_per_valid_answer_usd'] = item['api_reported_usd'] / item['valid_cases']
    ds_path = ROOT / 'outputs/local_runs/sce-local-openai-20261005T092656Z-202105-8d2e3b2c/cost_ledger.json'
    ds = json.loads(ds_path.read_text())
    costs['deepseek_reference'] = {'input_usd_per_million': ds['price_input_per_mtok'],
        'output_usd_per_million': ds['price_output_per_mtok'],
        'normalized_1000_calls_usd': (2500 * ds['price_input_per_mtok'] + 150 * ds['price_output_per_mtok']) / 1000,
        'price_basis': 'October 5 configured ledger estimate; not verified current tariff or billed cost'}
    inputs.append(ds_path)
    rng = np.random.default_rng(20261008)
    result = {'date': '2026-10-08', 'new_llm_calls': 0, 'costs': costs,
        'normalized_workload': {'input_tokens_per_call': 2500, 'output_tokens_per_call': 150,
            'excludes': ['format retries', 'HTTP errors', 'caching', 'account purchase fees', 'taxes']},
        'months': {}, 'bootstrap': {'repetitions': args.bootstrap, 'seed': 20261008,
            'scope': 'paired case resampling within month; conditional on the single recorded model generation',
            'does_not_measure': ['LLM regeneration variance', 'month-to-month uncertainty', 'national survey design uncertainty']}}
    for month, old in summary['months'].items():
        common = [r for r in rows if r['month'] == month and all(
            type(r['Q9'].get(k)) in (int, float) and math.isfinite(r['Q9'][k]) for k in ['real', *ARMS])]
        values = {k: np.array([r['Q9'][k] for r in common]) for k in ['real', *ARMS]}
        n = len(common)
        if n != old['Q9']['n_common']:
            raise ValueError('common mask changed')
        idx = rng.integers(0, n, (args.bootstrap, n))
        real_boot = np.median(values['real'][idx], axis=1)
        group_errors = {}
        for field in FIELDS:
            groups = defaultdict(list)
            for r in common:
                groups[str(r['profile'].get(field, 'unknown'))].append(r)
            visible = {}
            for name, subset in sorted(groups.items()):
                if len(subset) < 5:
                    visible[name] = {'n': len(subset), 'sparse': True}
                    continue
                actual = float(np.median([r['Q9']['real'] for r in subset]))
                estimates = {arm: float(np.median([r['Q9'][arm] for r in subset])) for arm in ARMS}
                errors = {arm: abs(v - actual) for arm, v in estimates.items()}
                for arm, value in errors.items():
                    if not math.isclose(value, old['profile_group_diagnostics'][field][name]['Q9']['arms'][arm]['sample_median_absolute_error_pp'], abs_tol=1e-10):
                        raise ValueError('group result differs from frozen analysis')
                visible[name] = {'n': len(subset), 'real_median': actual, 'model_medians': estimates, 'median_absolute_error_pp': errors}
            eligible = [v for v in visible.values() if not v.get('sparse')]
            coverage = sum(v['n'] for v in eligible)
            group_errors[field] = {'groups': visible, 'covered_cases': coverage, 'total_common_cases': n,
                'sample_size_weighted_group_median_error_pp': {
                    arm: sum(v['n'] * v['median_absolute_error_pp'][arm] for v in eligible) / coverage for arm in ARMS} if coverage else {}}
        metrics = {}
        boot_errors = {}
        for arm in ARMS:
            error = abs(float(np.median(values[arm]) - np.median(values['real'])))
            if not math.isclose(error, old['Q9']['arms'][arm]['sample_median_absolute_error_pp'], abs_tol=1e-10):
                raise ValueError('overall result differs from frozen analysis')
            boot_errors[arm] = np.abs(np.median(values[arm][idx], axis=1) - real_boot)
            metrics[arm] = {'sample_median_absolute_error_pp': error,
                'sample_median': float(np.median(values[arm])),
                'individual_mae_pp': float(np.mean(np.abs(values[arm] - values['real']))),
                'wasserstein_1_pp': float(np.mean(np.abs(np.sort(values[arm]) - np.sort(values['real'])))),
                'bootstrap_median_error_percentile_95_pp': np.quantile(boot_errors[arm], [.025, .975]).tolist()}
            for key in ['individual_mae_pp', 'wasserstein_1_pp']:
                if not math.isclose(metrics[arm][key], old['Q9']['arms'][arm][key], abs_tol=1e-10):
                    raise ValueError(f'{key} differs from frozen analysis')
        result['months'][month] = {'common_n': n, 'real_sample_median': float(np.median(values['real'])),
            'metrics': metrics, 'group_diagnostics': group_errors,
            'qwen_minus_deepseek_median_error_bootstrap_95_pp': np.quantile(
                boot_errors['qwen'] - boot_errors['deepseek_reference'], [.025, .975]).tolist()}
    result['equal_month_average_median_absolute_error_pp'] = {
        arm: sum(v['metrics'][arm]['sample_median_absolute_error_pp'] for v in result['months'].values()) / len(result['months']) for arm in ARMS}
    if not math.isclose(sum(v['api_reported_usd'] + v['unknown_reserved_usd'] for v in costs.values() if 'api_reported_usd' in v), receipt['cumulative_charged_or_reserved_usd'], abs_tol=1e-12):
        raise ValueError('budget accounting changed')
    result['source_sha256'] = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    (args.out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'cost_1000_calls_usd': {k: v['normalized_1000_calls_usd'] for k, v in costs.items()},
        'monthly_age_group_errors': {m: v['group_diagnostics']['age_group']['sample_size_weighted_group_median_error_pp'] for m, v in result['months'].items()},
        'average_median_error': result['equal_month_average_median_absolute_error_pp'],
        'qwen_minus_ds_bootstrap': {m: v['qwen_minus_deepseek_median_error_bootstrap_95_pp'] for m, v in result['months'].items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
