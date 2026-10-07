#!/usr/bin/env python3
"""Render a standalone scientific figure from a completed baseline run (offline)."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    with (a.run_dir / 'monthly_forecasts.csv').open() as f:
        rows = list(csv.DictReader(f))
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    policies = [('current_month_cpi_release_day_end', 'After current-month CPI release'),
                ('previous_month_end', 'Previous month-end forecast')]
    for ax, (policy, label) in zip(axes, policies):
        selected = [r for r in rows if r['policy'] == policy]
        truth = sorted([r for r in selected if r['method'] == 'persistence'], key=lambda r: r['target_month'])
        months = [r['target_month'] for r in truth]
        if len(months) != 60:
            raise ValueError('The figure requires the declared 60-month common window')
        ax.plot(range(60), [float(r['truth_pp']) for r in truth], color='black', label='Official first-release SCE', linewidth=2)
        for method, name, color, linestyle in [('persistence', 'Last published SCE', 'steelblue', '--'),
                                               ('ar1_expanding', 'Expanding AR(1)', 'darkorange', ':'),
                                               ('sticky_agent_0.25', 'Rule agent: update probability 25%', 'gray', '-.')]:
            mr = sorted([r for r in selected if r['method'] == method], key=lambda r: r['target_month'])
            if [r['target_month'] for r in mr] != months:
                raise ValueError(f'Month mismatch: {method}')
            ax.plot(range(60), [float(r['prediction_pp']) for r in mr], color=color, linestyle=linestyle,
                    label=name, linewidth=1.4)
        ax.set_title(label)
        ax.set_ylabel('One-year inflation expectation (%)')
        ax.grid(alpha=.18)
        ax.legend(loc='upper left', fontsize=8, frameon=False, ncol=2)
    axes[-1].set_xticks(range(0, 60, 6), [months[i] for i in range(0, 60, 6)], rotation=30)
    axes[-1].set_xlabel('Target survey month (2020-01 to 2024-12)')
    fig.suptitle('Release-aware SCE headline baselines: 60 target months')
    fig.text(.01, .01, 'Sources: FRBNY SCE first-release archives; BLS release calendar. Offline rolling evaluation; no LLM calls.', fontsize=8)
    fig.tight_layout(rect=(0, .035, 1, .96))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.output, dpi=170)
    plt.close(fig)
    print(a.output)


if __name__ == '__main__':
    main()
