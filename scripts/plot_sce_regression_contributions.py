#!/usr/bin/env python3
"""Scientific figure for the existing regression-diagnostic reading page."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(contributions, history, out):
    if out.exists():
        raise ValueError('Use a fresh figure output folder')
    a = json.loads(contributions.read_text())
    b = json.loads(history.read_text())
    assert a['n_person_months'] == b['n'] == 2284
    names = {'employment_status': 'Employment status', 'education_group': 'Education',
             'region': 'Region', 'age_group': 'Age group',
             'household_income_band': 'Household income', 'housing_tenure': 'Housing tenure',
             'numeracy': 'Numeracy (High / Low)'}
    plt.rcParams.update({'font.family': 'Times New Roman', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 6.0), gridspec_kw={'width_ratios': [1.25, 1]})
    factors = a['population_factor_contributions']
    vals = [r['average_order_r2_points'] for r in factors]
    y = np.arange(len(vals))
    axes[0].barh(y, vals, color='#35695e', height=.65)
    axes[0].set_yticks(y, [names[r['factor']] for r in factors])
    axes[0].invert_yaxis()
    for yy, v in zip(y, vals):
        axes[0].text(v+.012, yy, f'{v:.3f}', va='center', fontsize=10)
    axes[0].set_xlim(0, .8)
    axes[0].set_xlabel('Additional R-squared (percentage points)')
    axes[0].set_ylabel('Demographic factor (all categories as one block)')
    axes[0].set_title('Demographic contributions beyond prior + Sim', fontsize=12, pad=14)
    labels = ['Month + prior + P + Sim', '+ Personal history summary', '+ All past-answer blocks']
    values = [100*b['baseline_full_r2'], 100*b['blocks']['history_summary']['r2'], 100*b['all_past_blocks_r2']]
    axes[1].barh(np.arange(3), values, color=['#969d9c', '#35695e', '#596f78'], height=.6)
    axes[1].set_yticks(np.arange(3), labels, fontsize=10)
    axes[1].invert_yaxis()
    for yy, v in enumerate(values):
        axes[1].text(v+.5, yy, f'{v:.2f}%', va='center', fontsize=10)
    axes[1].set_xlim(0, 50)
    axes[1].set_xlabel('In-sample R-squared (%)')
    axes[1].set_title('Past history still adds linear information', fontsize=12, pad=14)
    for ax in axes:
        ax.grid(axis='x', alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle('Which information explains individual inflation expectations?', fontsize=15, y=.98)
    fig.subplots_adjust(left=.17, right=.97, top=.85, bottom=.25, wspace=.95)
    fig.text(.035, .065,
             'Source: frozen SCE simulation, 12 selected months in 2020-2025; 2,284 common person-months.\n'
             'Design-survey weights; months equally weighted. Two model generations averaged before regression.\n'
             'Left: exact average-order allocation among seven P factors, conditional on month, prior and Sim; sum = 1.261 R2 points.\n'
             'All estimates are retrospective in-sample associations, not causal effects or validated forecast improvements.', fontsize=9)
    out.mkdir(parents=True)
    dest = out/'factor_contributions.png'
    fig.savefig(dest, dpi=170)
    plt.close(fig)
    receipt = {'source_contributions_sha256': hashlib.sha256(contributions.read_bytes()).hexdigest(),
               'source_history_sha256': hashlib.sha256(history.read_bytes()).hexdigest(),
               'figure_sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}
    (out/'source_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(dest)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--contributions', required=True, type=Path)
    p.add_argument('--history', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    plot(a.contributions, a.history, a.out)
