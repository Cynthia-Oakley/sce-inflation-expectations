#!/usr/bin/env python3
"""Plot aggregate purchase-frequency contrast results; no API or private rows read."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.summary.read_text())
    out = args.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Use a fresh ignored output directory')
    out.mkdir(parents=True)
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False,
                         'axes.spines.right': False, 'figure.facecolor': 'white'})
    arms = ['reused_C_context', 'frequency_data', 'frequency_rule', 'copy_previous', 'history_anchor_half']
    labels = ['Earlier C (context only)', 'Frequency data', 'Data + frequency instruction',
              'Copy previous', 'Past personal anchor']
    colors = ['#708aa8', '#237468', '#bf754b', '#8a7563', '#b09c74']
    keys = ['sample_center_mae_pp', 'cross_section_w1_pp', 'delta_w1_pp']
    titles = ['Sample center MAE', 'Across-person distribution W1', 'Update distribution W1']
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), layout='constrained')
    for ax, key, title in zip(axes, keys, titles):
        values = [source['results'][a]['aggregate'][key] for a in arms]
        bars = ax.bar(range(5), values, color=colors)
        ax.bar_label(bars, fmt='%.3f', padding=4)
        ax.set_xticks(range(5), ['Earlier C', 'Data', 'Rule', 'Copy', 'Past anchor'], rotation=25)
        ax.set_title(title, fontsize=12)
        ax.set_ylabel('Percentage points; lower is better')
        ax.set_ylim(0, max(values) * 1.22)
        ax.grid(axis='y', alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle('New arms share contacts/prices; earlier C is descriptive context only', fontsize=13)
    fig.savefig(out / 'errors.png', dpi=170)
    plt.close(fig)

    months = source['protocol']['months']
    x = np.arange(len(months))
    month_labels = [f'{m // 100}-{m % 100:02}' for m in months]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout='constrained')
    for arm, label, color in zip(arms[1:3], labels[1:3], colors[1:3]):
        cells = source['results'][arm]['cells']
        iqrs = [np.mean([r['cross_person_iqr_pp'] for r in cells if r['month'] == m]) for m in months]
        slopes = [np.mean([r['slope'] for r in source['prior_position'][arm]['cells'] if r['month'] == m]) for m in months]
        axes[0].plot(x, iqrs, 'o-', color=color, label=label)
        axes[1].plot(x, slopes, 'o-', color=color, label=label)
    cells = source['results']['frequency_data']['cells']
    real_iqrs = [np.mean([r['real_cross_person_iqr_pp'] for r in cells if r['month'] == m]) for m in months]
    real_slopes = [np.mean([r['real_slope'] for r in source['prior_position']['frequency_data']['cells'] if r['month'] == m]) for m in months]
    axes[0].plot(x, real_iqrs, 'o--', color='#262d37', label='Actual respondents')
    axes[1].plot(x, real_slopes, 'o--', color='#262d37', label='Actual respondents')
    axes[0].set_title('Across-person IQR')
    axes[0].set_ylabel('Percentage points')
    axes[1].set_title('Current answer vs. own previous position')
    axes[1].set_ylabel('Within-month descriptive slope')
    for ax in axes:
        ax.set_xticks(x, month_labels)
        ax.grid(axis='y', alpha=.15)
        ax.legend(fontsize=9)
    fig.suptitle('Selected months are separated in time; lines do not show a monthly trajectory', fontsize=12)
    fig.savefig(out / 'personal_differences.png', dpi=170)
    plt.close(fig)
    print(out)


if __name__ == '__main__':
    main()
