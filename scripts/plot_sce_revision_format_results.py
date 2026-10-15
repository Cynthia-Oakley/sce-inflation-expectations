#!/usr/bin/env python3
"""Aggregate figures for the revision-format pilot; no API or individual rows."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main(summary, audit, out):
    out = out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    s = json.loads(summary.read_text()); a = json.loads(audit.read_text()); out.mkdir(parents=True)
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), layout='constrained')
    bars = axes[0].bar(['Direct answer', 'Report changes'], [100, 118/192*100], color=['#3b7269', '#b47949'])
    axes[0].bar_label(bars, fmt='%.1f%%', padding=4)
    axes[0].axhline(99, color='#666', ls='--', lw=1, label='99% validity gate')
    axes[0].set_ylim(0, 114); axes[0].set_ylabel('Valid answers (%)'); axes[0].set_title('Validity is the primary result'); axes[0].legend(fontsize=9)
    months = s['protocol']['months']; x = np.arange(len(months)); width = .34
    axes[1].bar(x-width/2, [48]*len(x), width, color='#3b7269', label='Direct')
    values = [a['by_month'][str(m)]['valid'] for m in months]
    b = axes[1].bar(x+width/2, values, width, color='#b47949', label='Changes');axes[1].bar_label(b,padding=3)
    axes[1].set_xticks(x, [f'{m//100}-{m%100:02}' for m in months], rotation=15)
    axes[1].set_ylim(0, 55); axes[1].set_ylabel('Valid answers out of 48 per arm'); axes[1].set_title('Failure occurs in every selected month'); axes[1].legend(fontsize=9)
    fig.suptitle('384 real requests, no retries: the change format fails the validity gate', fontsize=12)
    fig.savefig(out/'validity.png', dpi=170);plt.close(fig)

    arms = ['direct', 'revision', 'copy_previous', 'history_anchor_half']
    labels = ['Direct', 'Changes', 'Copy', 'Past anchor']
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 4.2), layout='constrained')
    for ax, key, title in zip(axes, ['sample_center_mae_pp', 'cross_section_w1_pp', 'delta_w1_pp'],
                              ['Sample center MAE', 'Across-person W1', 'Update W1']):
        values = [s['results'][arm]['aggregate'][key] for arm in arms]
        bars = ax.bar(range(4), values, color=['#3b7269', '#b47949', '#7c8589', '#a0a5a7'])
        ax.bar_label(bars, fmt='%.3f', padding=3);ax.set_xticks(range(4), labels, rotation=20)
        ax.set_ylim(0, max(values)*1.2);ax.set_title(title, fontsize=11);ax.set_ylabel('Percentage points; lower is better')
    fig.suptitle('115 common valid generation rows only: selection-affected descriptions, no accuracy inference', fontsize=11)
    fig.savefig(out/'conditional_errors.png', dpi=170);plt.close(fig)
    print(out)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--summary',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();main(args.summary,args.audit,args.out)
