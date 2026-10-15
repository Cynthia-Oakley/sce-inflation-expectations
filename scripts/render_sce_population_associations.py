#!/usr/bin/env python3
"""Render aggregate-only real-data results; no modelling or API in this step."""
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main(source, out):
    if out.exists() or not out.resolve().is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    source = source.resolve(); data = json.loads(source.read_text()); out.mkdir(parents=True)
    periods = list(data['periods']); colors = ['#49708c', '#a86c32']
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    factors = ['education_fine', 'financial_change', 'financial_risk', 'general_risk']
    labels = ['High school vs bachelor', 'Finances somewhat worse vs same',
              'Financial risk: 6/7 vs 1/2', 'General risk: 6/7 vs 1/2']
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5))
    for ax, target, title in zip(axes, ['Q9_mean', 'Q9_iqr'],
            ['Expected inflation: personal density mean', 'Personal uncertainty: density IQR']):
        for j, period in enumerate(periods):
            values = [data['periods'][period]['models'][target]['contrasts'][key] for key in factors]
            y = np.arange(len(values))+(j-.5)*.18
            b = np.array([r['estimate'] for r in values]); lo = np.array([r['ci95'][0] for r in values]); hi = np.array([r['ci95'][1] for r in values])
            ax.errorbar(b, y, xerr=[b-lo, hi-b], fmt='o', capsize=3, color=colors[j], label=period.replace('_', '-'))
        ax.axvline(0, color='#777777', lw=.8); ax.set_yticks(np.arange(4), labels); ax.invert_yaxis()
        ax.set_title(title, fontsize=11); ax.set_xlabel('Adjusted difference (percentage points)'); ax.grid(axis='x', alpha=.15)
    axes[1].set_yticklabels([]); axes[0].legend(loc='lower left', fontsize=9)
    fig.suptitle('Real SCE data: different characteristics relate to different parts of the answer', fontsize=12)
    fig.text(.015, .012, 'Month fixed effects and joint observed controls. Person-cluster 95% intervals; contrast intervals are not multiplicity-adjusted. Associations, not causal effects.', fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, .93)); fig.savefig(out/'adjusted_associations.png', dpi=180); plt.close(fig)

    items = ['QNUM1', 'QNUM2', 'QNUM3', 'QNUM5', 'QNUM6', 'QNUM8', 'QNUM9']
    item_labels = ['Discount', 'Compound interest', 'Lottery probability', 'Percent conversion',
                   'Decimal probability', 'Purchasing power', 'Diversification']
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    for j, period in enumerate(periods):
        m = data['periods'][period]['secondary']['quiz_Q9_iqr']
        vals = [m['contrasts']['correct_'+key] for key in items]
        b = np.array([v['estimate'] for v in vals]); lo = np.array([v['ci95'][0] for v in vals]); hi = np.array([v['ci95'][1] for v in vals])
        ax.errorbar(b, np.arange(7)+(j-.5)*.18, xerr=[b-lo, hi-b], fmt='o', capsize=3, color=colors[j], label=period.replace('_', '-'))
    ax.axvline(0, color='#777777', lw=.8); ax.set_yticks(np.arange(7), item_labels); ax.invert_yaxis()
    ax.set_xlabel('Adjusted personal-uncertainty difference: correct minus incorrect (pp)')
    ax.set_title('Detailed quiz answers add information beyond the existing High/Low label', fontsize=12)
    ax.grid(axis='x', alpha=.15); ax.legend(loc='lower left', fontsize=9)
    fig.text(.015, .012, 'All seven item indicators enter jointly with education, finances, risk and other controls. Exploratory person-cluster 95% intervals; no causal reading.', fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, 1)); fig.savefig(out/'quiz_uncertainty.png', dpi=180); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.8))
    for ax, key, title in zip(axes, ['cross_person_IQR', 'Q9_iqr_median'],
            ['Disagreement BETWEEN people', 'Uncertainty WITHIN each person']):
        for j, period in enumerate(periods):
            groups = data['periods'][period]['distributions']['education_fine']
            values = [groups[str(level)]['equal_month'][key]['value'] for level in [2, 5]]
            b = ax.bar(np.arange(2)+(j-.5)*.32, values, .3, color=colors[j], label=period.replace('_', '-'))
            ax.bar_label(b, fmt='%.2f', padding=3, fontsize=9)
        ax.set_xticks([0, 1], ['High school', 'Bachelor']); ax.set_ylabel('Percentage points')
        ax.set_title(title, fontsize=11); ax.set_ylim(0, 9.4); ax.grid(axis='y', alpha=.1)
    axes[0].legend(fontsize=9);fig.suptitle('Two distinct meanings of a wider answer distribution', fontsize=12)
    fig.text(.015, .012, 'Within-group survey-weighted monthly statistics, then equal-month averages. Raw group comparisons; NOT adjusted for all other population differences.', fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, .93));fig.savefig(out/'two_kinds_of_spread.png', dpi=180);plt.close(fig)

    public = {'status': data['status'], 'new_api_calls': 0, 'protocol': data['protocol'],
        'source_sha256': data['source_sha256'], 'limits': data['limits'], 'periods': {}}
    for period, b in data['periods'].items():
        def compact(m):
            return {k: v for k, v in m.items() if k in ['rows', 'persons', 'months', 'R2_within_month',
                'joint', 'contrasts', 'same_sample_base_R2', 'incremental_R2', 'seven_items_joint', 'capped_rows']}
        public['periods'][period] = {'rows': b['rows'], 'persons': b['persons'],
            'models': {k: compact(v) for k, v in b['models'].items()},
            'Q8_tail_sensitivity': compact(b['Q8_tail_sensitivity']),
            'secondary': {k: compact(v) for k, v in b['secondary'].items()},
            'first_differences': {k: {'rows': v['rows'], 'persons': v['persons'], 'coefficients': {name: c for name, c in v['coefficients'].items() if name.startswith('financial_change=')}} for k, v in b['first_differences'].items()},
            'distributions': {factor: {level: {k: v for k, v in desc.items() if k != 'monthly'} for level, desc in levels.items()} for factor, levels in b['distributions'].items()}}
    (out/'public_summary.json').write_text(json.dumps(public, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--source', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(); main(args.source, args.out)
