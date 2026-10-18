#!/usr/bin/env python3
"""Small public readout and capacity check; no refit, API, or model selection."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.retention_predictability import (
    METHODS, TRAJECTORY, auc, month_weights)
from studies.sce_inflation_expectations.evaluation.response_gap import MONTHS, prepare_pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or not args.out.resolve().is_relative_to(ROOT):
        raise ValueError('Use a fresh output within the project')
    source = json.loads((args.folder/'summary.json').read_text())
    predictions = pd.read_parquet(args.folder/'predictions_private.parquet')
    good = predictions.loc[predictions.eligible_label & np.isfinite(predictions.weight) & (predictions.weight > 0)].copy()
    within_auc = {}
    for method in METHODS:
        values = []
        for _, d in good.groupby('month'):
            value = auc(d.label_stable.to_numpy(float), d[method].to_numpy(float), d.weight.to_numpy(float))
            if value is not None: values.append(value)
        within_auc[method] = float(np.mean(values))
    pairs = [r for r in prepare_pairs(json.loads((TRAJECTORY/'cases_private.json').read_text()), months=MONTHS, n_per_month=192) if r['paired_eligible']]
    reach_rows = []
    for r in pairs:
        for repeat in (1, 2):
            truth, prior, sim = r['truth_mean_pp'], r['prior_mean_pp'], r['model_repeats'][str(repeat)]['mean']
            reach_rows.append({'month': r['month'], 'weight': r['design_survey_weight']/2,
                               'outside_segment': float(truth < min(prior, sim)-1e-8 or truth > max(prior, sim)+1e-8),
                               'requires_opposite_direction': float((truth-prior)*(sim-prior) < -1e-8),
                               'requires_larger_same_direction': float((truth-prior)*(sim-prior) > 0 and abs(truth-prior) > abs(sim-prior)+1e-8),
                               'same_exact_point': float(abs(truth-prior) < 1e-8),
                               'distance_to_segment_pp': float(max(min(prior, sim)-truth, truth-max(prior, sim), 0.))})
    reach = pd.DataFrame(reach_rows); w = month_weights(reach)
    capacity = {name: float(np.dot(w, reach[name])) for name in reach.columns if name not in ('month', 'weight')}
    coefficients = {}
    for name in ('past_stable_rate', 'past_exact_rate', 'prior_iqr', 'prior_abs_change', 'history_sd', 'history_count'):
        values = [f['fit']['history']['coefficients_standardized_not_causal'][name] for f in source['folds']]
        coefficients[name] = {'minimum': min(values), 'maximum': max(values),
                              'positive_years': sum(v > 0 for v in values), 'negative_years': sum(v < 0 for v in values)}
    brief = {'status': source['status'], 'new_api_calls': 0, 'refitted_q9_vectors': 0,
             'n_forward_person_months': source['n_forward_test_person_months'],
             'n_forward_months': source['all_forward_probability_scores']['history']['n_months'],
             'n_simulation_person_months': source['n_simulation_person_months'],
             'full_period_probability_scores': {m: {k: v for k,v in r.items() if k != 'calibration'} for m,r in source['all_forward_probability_scores'].items()},
             'mean_within_month_auc': within_auc,
             'annual_probability_scores': [{'year': f['year'], 'n_train': f['n_train'], 'n_test': f['n_test'],
                                             'train_last_month': max(f['train_months']),
                                             'methods': {m: {k: v for k,v in r.items() if k != 'calibration'} for m,r in f['methods'].items()}} for f in source['folds']],
             'frozen_probability_scores': {m: {k: v for k,v in r.items() if k != 'calibration'} for m,r in source['frozen_simulation_support_probability_scores'].items()},
             'scalar_diagnostic': source['scalar_diagnostic'],
             'probability_prior_sim_segment_capacity_posthoc': capacity,
             'capacity_notice': 'Geometry of scalar intervals only; uses current truth to diagnose reachability. Never a deployable forecast, Q9 mixture, causal result or achievable macro-MAE bound.',
             'history_coefficient_direction': coefficients,
             'official_and_frozen_label_disagreement': source['official_and_frozen_label_disagreement'],
             'timing_seconds': source['timing_seconds'], 'limits': source['limits'],
             'source_sha256': {**source['source_sha256'],
                str((args.folder/'summary.json').resolve().relative_to(ROOT)): hashlib.sha256((args.folder/'summary.json').read_bytes()).hexdigest()},
             'prediction_cache_sha256': hashlib.sha256((args.folder/'predictions_private.parquet').read_bytes()).hexdigest(),
             'report_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.out.mkdir(parents=True)
    (args.out/'summary.json').write_text(json.dumps(brief, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'within_month_auc': within_auc, 'capacity_posthoc': capacity}, ensure_ascii=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC', 'STKaiti', 'serif'],
                         'axes.unicode_minus': False, 'font.size': 11})
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.4))
    years = [f['year'] for f in source['folds']]
    for method, label, color in [('population_rate', '只用总体稳定率', '#687b82'), ('history', '使用个人过去记录', '#326a56')]:
        axes[0].plot(years, [f['methods'][method]['brier'] for f in source['folds']], marker='o', label=label, color=color)
    axes[0].set(title='每年前推：个人历史提高稳定判断的预测力', xlabel='评价年份（训练截至上一年）', ylabel='Brier分数（越小越好）')
    axes[0].legend(frameon=False); axes[0].grid(axis='y', alpha=.2)
    methods = ['pure_sim', 'history', 'carry']
    numbers = [source['scalar_diagnostic'][m]['summary']['center_mae_pp'] for m in methods]
    bars = axes[1].bar(['原Simulation', '历史概率加权\n标量诊断', '照抄本人上期'], numbers, color=['#9c6748', '#326a56', '#687b82'], width=.58)
    for bar, value in zip(bars, numbers):
        axes[1].text(bar.get_x()+bar.get_width()/2, value+.012, f'{value:.3f}', ha='center')
    axes[1].axhline(.2, color='#9c6748', linestyle='--', label='持续目标0.20pp')
    axes[1].set(title='十二期同支持：尚未超过持续性基线', ylabel='Q9群体中位数MAE（pp）', ylim=(0, .54))
    axes[1].legend(frameon=False); axes[1].grid(axis='y', alpha=.2)
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False)
    fig.text(.06, .02, '来源：既有SCE缓存，2020—2025共70个评价月/66,476个人月；右图为原12期/2,284人月/两遍分别评价。\n概率加权仅组合个人派生均值，尚未生成新Q9或独立验证；本轮0新API。', fontsize=9, color='#56605c')
    fig.tight_layout(rect=(0, .12, 1, 1))
    fig.savefig(args.out/'retention_and_goal.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
