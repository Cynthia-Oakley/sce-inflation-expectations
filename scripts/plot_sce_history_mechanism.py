#!/usr/bin/env python3
"""Plot aggregate results for the existing personal-history reading page."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(source, out):
    if out.exists():
        raise ValueError('Use a fresh figure output folder')
    summary = json.loads(source.read_text())
    assert summary['n_person_months'] == 2284
    plt.rcParams.update({'font.family': 'Times New Roman', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.3),
                             gridspec_kw={'width_ratios': [1.35, 1]})
    keys = ['simulation_only', 'simulation_plus_month', 'simulation_month_P',
            'simulation_month_prior_P', 'full_history_valid_count']
    labels = ['Simulation only', '+ Month effects', '+ Demographics',
              '+ Own previous answer', '+ Personal history summary']
    values = [100*summary['fits'][key]['r2'] for key in keys]
    axes[0].barh(np.arange(5), values, color=['#a0a7a4']*4+['#35695e'], height=.62)
    axes[0].set_yticks(np.arange(5), labels)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 48)
    axes[0].set_xlabel('In-sample R-squared (%)')
    axes[0].set_ylabel('Nested linear regression specification')
    axes[0].set_title('Start with Simulation, then add observed information', fontsize=12, pad=14)
    for y, value in enumerate(values):
        axes[0].text(value+.6, y, f'{value:.2f}%', va='center')
    values = [summary['temporal_sensitivity']['2020_2022']['valid_count_model']['coefficients']['anchor_gap'],
              summary['fits']['full_history_valid_count']['coefficients']['anchor_gap'],
              summary['temporal_sensitivity']['2023_2025']['valid_count_model']['coefficients']['anchor_gap']]
    axes[1].barh(np.arange(3), values, color=['#a0a7a4', '#35695e', '#a0a7a4'], height=.55)
    axes[1].set_yticks(np.arange(3), ['2020-2022', 'All 12 months', '2023-2025'])
    axes[1].invert_yaxis()
    axes[1].set_xlim(0, .65)
    axes[1].set_xlabel('Conditional coefficient (pp per 1 pp history gap)')
    axes[1].set_ylabel('Selected period')
    axes[1].set_title('Personal typical level retains a positive association', fontsize=12, pad=14)
    for y, value in enumerate(values):
        axes[1].text(value+.012, y, f'{value:.3f}', va='center')
    for ax in axes:
        ax.grid(axis='x', alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle('Personal history and current household inflation expectations', fontsize=15, y=.97)
    fig.subplots_adjust(left=.18, right=.975, top=.85, bottom=.25, wspace=.70)
    fig.text(.035, .07,
             'Source: frozen SCE experiment; 12 selected months in 2020-2025, 2,284 common person-months.\n'
             'Outcome: real respondent Q9 fitted mean. Two model generations averaged first; design-survey weights, equal month mass.\n'
             'History gap = personal typical past expectation minus own previous expectation. Period bars are descriptive estimates, not intervals.\n'
             'All regressions are retrospective associations; no causal updating weight or validated forecast improvement is established.', fontsize=9)
    out.mkdir(parents=True)
    path = out/'history_mechanism.png'
    fig.savefig(path, dpi=170)
    plt.close(fig)
    receipt = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'figure_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (out/'source_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    plot(args.source, args.out)
