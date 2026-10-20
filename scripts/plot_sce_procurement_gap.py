#!/usr/bin/env python3
"""Publish aggregate-only conditional diagnostics and two scientific figures."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
COLORS = ['#7c8d98', '#b38147', '#087f80']
LABELS = ['旧DeepSeek＋完整统计', 'Qwen＋食品共同背景', 'Qwen＋角色匹配']


def plot(source, dest):
    if dest.exists():
        raise ValueError('Fresh public destination required')
    s = json.loads((source/'summary.json').read_text())
    d = s['six_month_configuration_comparison']; arms = d['arms']; months = d['months']
    font = ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():
        font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC', 'STKaiti'],
        'font.size': 11, 'axes.unicode_minus': False, 'axes.spines.top': False, 'axes.spines.right': False})
    dest.mkdir(parents=True); (dest/'figures').mkdir()
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.8)); x = np.arange(len(months))
    for j, arm in enumerate(arms):
        values = [d['monthly'][str(m)]['metrics'][arm]['center_mae_pp'] for m in months]
        axes[0].bar(x+(j-1)*.25, values, .24, color=COLORS[j], label=LABELS[j])
    axes[0].set_xticks(x, [f'{m//100}-{m%100:02d}' for m in months], rotation=25)
    axes[0].set_ylabel('群体中位数MAE（通胀百分点）'); axes[0].set_title('差距主要集中在2021年9月'); axes[0].legend(fontsize=8)
    diff = [d['monthly'][str(m)]['metrics'][arms[2]]['center_mae_pp']-
            d['monthly'][str(m)]['metrics'][arms[0]]['center_mae_pp'] for m in months]
    bars = axes[1].bar(x, diff, color=['#b66050' if v > 0 else '#087f80' for v in diff])
    axes[1].bar_label(bars, fmt='%+.3f', padding=3, fontsize=9); axes[1].axhline(0, color='#6b777b', linewidth=.8)
    axes[1].set_xticks(x, [f'{m//100}-{m%100:02d}' for m in months], rotation=25)
    axes[1].set_ylabel('新配置减旧配置的MAE（百分点）'); axes[1].set_title('负值表示新配置较好'); axes[1].margins(y=.18)
    fig.text(.015, .015, '553共同个人月；六期均为开发月。模型、环境呈现与格式同时变化，不能把差异当作纯模型效应。', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1)); fig.savefig(dest/'figures/monthly_gap.png', dpi=165); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.8))
    bands = ['below_2', '2_to_below_4', '4_to_below_8', '8_or_above']; x = np.arange(4)
    truth = [d['groups']['prior_band'][b]['metrics'][arms[0]]['truth_mean_pp'] for b in bands]
    axes[0].plot(x, truth, 'o-', color='#20282c', label='真人本期', linewidth=2.4)
    for j, arm in enumerate(arms):
        axes[0].plot(x, [d['groups']['prior_band'][b]['metrics'][arm]['model_mean_pp'] for b in bands],
                     'o--', color=COLORS[j], label=LABELS[j])
    axes[0].set_xticks(x, ['上期<2%', '上期2—4%', '上期4—8%', '上期≥8%'])
    axes[0].set_ylabel('本期个人预期的加权均值（%）'); axes[0].set_title('低预期端更接近，高预期端仍被拉低'); axes[0].legend(fontsize=8)
    qs = [10, 25, 50, 75, 90]; x = np.arange(5)
    axes[1].plot(x, [d['total']['metrics'][arms[0]][f'truth_q{q}_pp'] for q in qs], 'o-',
                 color='#20282c', linewidth=2.4, label='真人')
    for j, arm in enumerate(arms):
        axes[1].plot(x, [d['total']['metrics'][arm][f'model_q{q}_pp'] for q in qs],
                     'o--', color=COLORS[j], label=LABELS[j])
    axes[1].set_xticks(x, ['P10', 'P25', 'P50', 'P75', 'P90'])
    axes[1].set_ylabel('跨人预期分位数（%）'); axes[1].set_title('分布改善主要见于低预期端'); axes[1].legend(fontsize=8)
    fig.text(.015, .015, '各月/各遍分别计算后等权平均；左图是组内均值，右图是跨人分位数。尾部依赖冻结近似Q9计分规则。', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1)); fig.savefig(dest/'figures/conditional_distribution.png', dpi=165); plt.close(fig)

    # Full per-cell aggregates remain in the ignored analysis package. The public
    # note needs group summaries and monthly metrics, not thousands of repeats.
    def compact(value):
        if isinstance(value, dict):
            return {k: compact(v) for k, v in value.items() if k != 'cells'}
        if isinstance(value, list):
            return [compact(v) for v in value]
        return value
    (dest/'summary.json').write_text(json.dumps(compact(s), ensure_ascii=False, indent=2)+'\n')
    print('Saved aggregate summary and two figures:', dest)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--source', type=Path, required=True)
    p.add_argument('--dest', type=Path, required=True); a = p.parse_args(); plot(a.source.resolve(), a.dest.resolve())
