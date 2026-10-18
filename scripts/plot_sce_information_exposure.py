#!/usr/bin/env python3
"""Scientific figures from the six-arm aggregate readout; no private records."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

COLORS = {3: '#9c633c', 8: '#347367', 20: '#376a99'}


def plot(summary, out):
    data = json.loads(Path(summary).read_text())
    out = Path(out)
    out.mkdir(exist_ok=False, parents=True)
    monthly = data['weighted_monthly']
    x = np.arange(len(monthly))
    labels = [str(row['month'])[:4]+'-'+str(row['month'])[4:] for row in monthly]
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.9), sharey=True, constrained_layout=True)
    for ax, mode in zip(axes, ('complete', 'reduced')):
        truth = [m['arms']['baseline']['truth_center_pp'] for m in monthly]
        carry = [m['arms']['carry']['predicted_center_pp'] for m in monthly]
        ax.plot(x, truth, color='#222222', lw=2.2, marker='o', label='Observed SCE, same people')
        ax.plot(x, carry, color='#888888', lw=1.5, ls='--', marker='s', label='Copy previous answer')
        for n in (3, 8, 20):
            arm = 'baseline' if n == 8 and mode == 'complete' else f'news_{n}_{mode}'
            values = [m['arms'][arm]['predicted_center_pp'] for m in monthly]
            ax.plot(x, values, color=COLORS[n], marker='.', lw=1.5, label=f'{n} news articles')
        ax.set(title='Complete macro statistics' if mode == 'complete' else 'Reduced macro statistics',
               xticks=x, xticklabels=labels, xlabel='Selected survey month (not consecutive)')
        ax.tick_params(axis='x', rotation=35)
        ax.grid(axis='y', color='#e3e7e5', lw=.6)
        ax.spines[['top', 'right']].set_visible(False)
        ax.legend(fontsize=8, loc='best')
    axes[0].set_ylabel('Weighted median of individual Q9 density means (%)')
    fig.suptitle('Information exposure: same-household SCE reconstruction', fontsize=13)
    fig.savefig(out/'monthly_centers.png', dpi=180)
    plt.close(fig)
    metrics = data['weighted_metrics']
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.3), constrained_layout=True)
    for ax, key, title in zip(axes, ('center_mae_pp', 'w1_pp'), ('Group-median MAE', 'Cross-person Wasserstein distance')):
        for offset, mode, label, color in [(-.18, 'complete', 'Complete statistics', '#347367'), (.18, 'reduced', 'Reduced statistics', '#9c633c')]:
            values = [metrics['baseline' if n == 8 and mode == 'complete' else f'news_{n}_{mode}'][key] for n in (3, 8, 20)]
            bars = ax.bar(np.arange(3)+offset, values, .34, color=color, label=label)
            for bar, value in zip(bars, values):
                ax.text(bar.get_x()+bar.get_width()/2, value, f'{value:.3f}', ha='center', va='bottom', fontsize=9)
        ax.axhline(metrics['carry'][key], color='#555555', ls='--', lw=1.2, label='Copy previous answer')
        ax.set(title=title, xlabel='News articles shown', ylabel='Percentage points (lower is better)', xticks=np.arange(3), xticklabels=['3', '8', '20'])
        ax.margins(y=.2)
        ax.spines[['top', 'right']].set_visible(False)
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc='upper center', bbox_to_anchor=(.5, -.01), ncol=3, fontsize=9)
    fig.suptitle('Six development months, 96 households per month, two generations', fontsize=12)
    fig.savefig(out/'metric_comparison.png', dpi=180, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    plot(args.summary, args.out)
