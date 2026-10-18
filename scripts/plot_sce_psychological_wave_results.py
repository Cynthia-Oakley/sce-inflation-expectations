#!/usr/bin/env python3
"""Render the saved aggregate comparison; no data fitting or model calls."""
import argparse
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); s = json.loads(args.summary.read_text()); args.out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC', 'STKaiti'], 'font.size': 11,
                         'axes.unicode_minus': False, 'svg.fonttype': 'none'})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.2))
    fig.subplots_adjust(top=.83, bottom=.15, hspace=.40, wspace=.25)
    arms = ['baseline', 'old_matched', 'new_matched', 'new_permuted']
    names = ['不加心理', '旧2018匹配', '新波次匹配', '新波次打乱']
    colors = ['#9aa1a7', '#afc6d4', '#245f7d', '#bf9563']; x = np.arange(len(s['months'])); width = .19
    metrics = [('q9_center_mae_pp', '群体中位数MAE（pp）'), ('cross_section_w1_pp', '跨人分布距离W1（pp）'),
               ('individual_density_mean_mae_pp', '个人Q9均值MAE（pp）'), ('cross_person_iqr_pp', '人与人之间的IQR（pp）')]
    real_line = None
    for ax, (metric, title) in zip(axes.flat, metrics):
        for i, (arm, name, color) in enumerate(zip(arms, names, colors)):
            cells = s['arms'][arm]['auxiliary_survey_weighted']['q9']['cells']
            values = [np.mean([c[metric] for c in cells if c['month'] == m]) for m in s['months']]
            ax.bar(x+(i-1.5)*width, values, width, label=name, color=color)
        if metric == 'cross_person_iqr_pp':
            cells = s['arms']['baseline']['auxiliary_survey_weighted']['q9']['cells']
            values = [np.mean([c['real_cross_person_iqr_pp'] for c in cells if c['month'] == m]) for m in s['months']]
            real_line, = ax.plot(x, values, 'o--', color='#333333', label='同样本真人（IQR）', linewidth=1.4, markersize=4)
        ax.set_title(title, fontsize=14, pad=10); ax.set_ylabel('百分点（pp）'); ax.set_xlabel('SCE调查月')
        ax.set_xticks(x, [f'{m//100}-{m%100:02d}' for m in s['months']]); ax.set_axisbelow(True)
        ax.grid(axis='y', color='#e6e6e6', linewidth=.7)
        for spine in ('top', 'right'): ax.spines[spine].set_visible(False)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles+[real_line], labels+['同样本真人（IQR）'], ncol=5, loc='upper center', bbox_to_anchor=(.5, .926), frameon=False)
    fig.suptitle('心理背景按波次更新：中心点值较旧2018略好，尚未优于原输入', fontsize=17, y=.98)
    fig.text(.5, .06, '来源：冻结轨迹重算；3期×48人×两遍，设计×调查权重。旧回答复用；年度／相邻波次代理，A条件历史重建。', ha='center', fontsize=11)
    fig.text(.5, .025, '误差与W1越低越好；IQR应接近真人。每个月先对两遍误差平均；不是全国SCE headline。', ha='center', fontsize=10, color='#555555')
    for ext in ('png', 'svg'): fig.savefig(args.out/f'wave_psychology_results.{ext}', dpi=160)
    svg = args.out/'wave_psychology_results.svg'; svg.write_text('\n'.join(t.rstrip() for t in svg.read_text().splitlines())+'\n')
    plt.close(fig)


if __name__ == '__main__': main()
