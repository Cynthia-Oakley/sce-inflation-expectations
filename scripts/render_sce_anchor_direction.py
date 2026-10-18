#!/usr/bin/env python3
"""Render aggregate anchor-alignment diagnostics, without accessing person rows."""
import argparse
from pathlib import Path
import json
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError('Fresh output directory required')
    s = json.loads(a.summary.read_text())
    a.out.mkdir(parents=True)
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC', 'STKaiti'],
                         'font.size': 12, 'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.unicode_minus': False})
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.6), gridspec_kw={'width_ratios': [1.25, 1]})
    group = s['per_generation_sensitivity']['groups']['opposed']
    labels = ['基本保持', '沿个人较早常态方向', '沿最新CPI方向']
    colors = ['#919a9d', '#356f61', '#ad7449']
    bottom = np.zeros(2)
    for key, label, color in zip(('stable', 'personal_direction', 'common_direction'), labels, colors):
        values = np.array([group[k]['direction_shares'][key]*100 for k in ('truth', 'model')])
        axes[0].barh([1, 0], values, left=bottom, color=color, height=.55, label=label)
        for y, value, left in zip([1, 0], values, bottom):
            axes[0].text(left+value/2, y, f'{value:.1f}%', ha='center', va='center', color='white', fontsize=11)
        bottom += values
    axes[0].set(yticks=[1, 0], yticklabels=['真人', '模型（两遍分别统计）'], xlim=(0, 100),
                xlabel='该组中的加权占比（%）', title='两种方向冲突的392个人月')
    axes[0].legend(loc='upper center', bbox_to_anchor=(.5, -.2), frameon=False, fontsize=10)
    y = np.array([0, 1]); width=.32
    for name, label, color, shift in [('real', '真人', '#356f61', -width/2), ('sim', '模型', '#ad7449', width/2)]:
        values = [s['associations'][k][name]['older_only_slope_holding_prior_fixed'] for k in ('all', 'at_least_four_past_answers')]
        axes[1].bar(y+shift, values, width, color=color, label=label)
        for x, value in zip(y+shift, values):
            axes[1].text(x, value+.014, f'{value:.3f}', ha='center', va='bottom', fontsize=11)
    axes[1].set(xticks=y, xticklabels=['至少2次过去回答', '至少4次过去回答'], ylim=(0, .62),
                ylabel='个人较早常态高1pp时，本期回答的条件差异（pp）', title='个人较早历史的关联仍较弱')
    axes[1].legend(frameon=False)
    fig.suptitle('模型更少沿个人历史方向调整；尚不能据此认定公共信息的因果作用', fontsize=15, y=.99)
    fig.text(.02, .015, '来源：十二期冻结模拟与同样本真人；2020—2025年，2,284个人月。左图阈值0.5pp，CPI是过去同比，非未来预期真值。\n右图控制月份、上期回答、历史次数及七类人口特征；关联斜率不是心理权重。无新API、无新Q9拟合。', fontsize=10, color='#56605f')
    fig.tight_layout(rect=(0, .15, 1, .94))
    fig.savefig(a.out/'anchor_directions.png', dpi=170, bbox_inches='tight')
    plt.close(fig)
    shutil.copyfile(a.summary, a.out/'summary.json')
    print(str(a.out/'anchor_directions.png'))


if __name__ == '__main__':
    main()
