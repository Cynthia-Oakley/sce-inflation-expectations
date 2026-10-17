#!/usr/bin/env python3
"""Render aggregate-only charts from a completed frozen cross-month evaluation."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ARMS = ('baseline', 'financial_facts', 'copy_previous', 'history_anchor_half')
LABELS = ('Reference input', 'Financial facts', 'Copy previous', 'Personal history anchor')
COLORS = ('#6c7880', '#377867', '#ab8452', '#899caa')


def render(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    summary = json.loads(source.read_text())
    if summary['status'] != 'completed_sce_household_finance_crossmonth_evaluation':
        raise ValueError('Completed cross-month real evaluation required')
    if out.exists():
        raise ValueError('Fresh figure output required')
    result = summary['design_weighted']
    months = summary['protocol']['months']
    specs = [('q9_center_mae_pp', 'Sample Q9 median MAE'),
             ('individual_density_mean_mae_pp', 'Individual Q9 mean MAE'),
             ('cross_section_w1_pp', 'Across-person W1')]
    for arm in ARMS:
        for key, _ in specs:
            value = result[arm]['aggregate_equal_month_repeat_cells'][key]
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Missing metric: ' + arm + '/' + key)
    plt.rcParams.update({'font.family': 'Times New Roman', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    out.mkdir(parents=True)
    fig, axes = plt.subplots(1, 3, figsize=(13.3, 5.2))
    for i, (ax, (key, title)) in enumerate(zip(axes, specs)):
        values = [result[arm]['aggregate_equal_month_repeat_cells'][key] for arm in ARMS]
        ax.barh(range(len(ARMS)), values, height=.6, color=COLORS)
        ax.set_yticks(range(len(ARMS)), LABELS if i == 0 else [''] * len(ARMS))
        ax.invert_yaxis()
        ax.set_xlim(0, max(max(values) * 1.25, .1))
        ax.set_title(title, fontsize=12)
        ax.set_xlabel('Inflation percentage points (lower is better)')
        ax.grid(axis='x', alpha=.18)
        for j, value in enumerate(values):
            ax.text(value + max(values) * .025, j, f'{value:.3f}', va='center')
    fig.suptitle('Financial-circumstances replication: four other months', fontsize=15)
    fig.subplots_adjust(left=.18, right=.98, top=.8, bottom=.25, wspace=.27)
    fig.text(.03, .065,
        f'2022-06, 2023-06, 2024-10, 2025-09; 48 selected returners/month; two generations per model arm.\n'
        f'Common scored Q9 support: {summary["common_support"]["q9_person_months"]}/192 person-months. '
        'Identical human/model design-survey weights; equal month/repeat-cell average.\n'
        'Historical A-line conditions include actual prior beliefs and current Q1; not national or real-time B forecasts.\n'
        'These months had old-model results; this is not a wholly blind project-level test.',
        fontsize=9, color='#444')
    fig.savefig(out / 'accuracy.png', dpi=170)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    x, width = np.arange(len(months)), .18
    for index, (arm, label, color) in enumerate(zip(ARMS, LABELS, COLORS)):
        cells = result[arm]['cells']
        vals = [np.mean([row['q9_center_mae_pp'] for row in cells if row['month'] == month]) for month in months]
        ax.bar(x + (index - 1.5) * width, vals, width, label=label, color=color)
    ax.set_xticks(x, [f'{m // 100}-{m % 100:02}' for m in months])
    ax.set_ylabel('Sample Q9 median MAE (percentage points)')
    ax.set_xlabel('Selected survey month (two-generation average)')
    fig.suptitle('Monthly center errors under the same pre-registered weights', y=.96)
    ax.grid(axis='y', alpha=.18)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, frameon=False, loc='upper center', bbox_to_anchor=(.5, .91))
    fig.subplots_adjust(left=.10, right=.98, top=.72, bottom=.23)
    fig.text(.04, .06,
        'Each error compares the model and real weighted medians on exactly the same scored people.\n'
        'Four selected months; per-person paired intervals do not establish stability across all calendar periods.',
        fontsize=9, color='#444')
    fig.savefig(out / 'monthly_center.png', dpi=170)
    plt.close(fig)
    (out / 'source_receipt.json').write_text(json.dumps({
        'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'plot_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'new_api_calls': 0, 'figures': ['accuracy.png', 'monthly_center.png'],
        'weights': 'design_survey_weight; same selected model and human; equal month/repeat cells',
    }, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    render(args.source, args.out)
