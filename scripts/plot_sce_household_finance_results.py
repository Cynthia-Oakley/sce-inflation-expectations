#!/usr/bin/env python3
"""Draw aggregate-only household-finance pilot figures in a fresh directory."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ARMS = ('baseline', 'financial_facts', 'financial_perspective')
LABELS = ('Original input', 'Financial facts', 'Facts + perspective')
COLORS = ('#697680', '#417a68', '#a27648')


def render(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    summary = json.loads(source.read_text())
    if summary['status'] != 'completed_sce_household_finance_development_pilot_evaluation':
        raise ValueError('Completed real household-finance evaluation required')
    if out.exists():
        raise ValueError('Fresh output directory required')
    rows = [summary['arms'][a]['q9']['aggregate_equal_month_repeat_cells'] for a in ARMS]
    specs = [('individual_density_mean_mae_pp', 'Individual Q9 mean MAE'),
             ('q9_center_mae_pp', 'Sample Q9 median MAE'),
             ('cross_section_w1_pp', 'Across-person W1')]
    for metric, _ in specs:
        if not all(isinstance(r.get(metric), (int, float)) and math.isfinite(r[metric]) for r in rows):
            raise ValueError('Missing finite plotted metric: ' + metric)
    plt.rcParams.update({'font.family': 'Times New Roman', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    out.mkdir(parents=True)
    fig, axes = plt.subplots(1, 3, figsize=(13, 5), sharey=True)
    for i, (ax, (key, title)) in enumerate(zip(axes, specs)):
        values = [r[key] for r in rows]
        ax.barh(range(3), values, color=COLORS, height=.58)
        ax.set_yticks(range(3))
        if i == 0:
            ax.set_yticklabels(LABELS)
        else:
            ax.tick_params(axis='y', labelleft=False)
        ax.set_title(title, fontsize=12)
        ax.set_xlabel('Inflation percentage points (lower is better)')
        ax.set_xlim(0, max(max(values)*1.3, .1))
        ax.grid(axis='x', alpha=.2)
        for j, v in enumerate(values):
            ax.text(v+max(values)*.03, j, f'{v:.3f}', va='center')
    axes[0].invert_yaxis()
    fig.suptitle('Household financial circumstances: three-arm development pilot', fontsize=15)
    fig.subplots_adjust(left=.18, right=.98, top=.80, bottom=.27, wspace=.28)
    support = summary['common_support']['q9_common_scorable_person_months']
    fig.text(.035, .07,
        f'2020-04, 2021-05/11, 2022-03; 24 selected people/month, two generations; Q9 common support {support}/96 person-months.\n'
        'Equal month and generation weights. Human and model raw Q9 use the same frozen approximate density scorer.\n'
        'Previously inspected development sample; not an independent test, causal effect, national estimate or real-time forecast.\n'
        f'Source: {source.name}; SHA-256 {hashlib.sha256(source.read_bytes()).hexdigest()[:16]}.',
        fontsize=9, color='#444444')
    fig.savefig(out/'accuracy.png', dpi=170)
    plt.close(fig)
    (out/'source_receipt.json').write_text(json.dumps({'source': str(source),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'new_api_calls': 0, 'figures': ['accuracy.png']}, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    render(args.source, args.out)
