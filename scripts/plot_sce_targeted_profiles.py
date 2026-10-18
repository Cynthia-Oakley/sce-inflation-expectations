#!/usr/bin/env python3
"""Plot aggregate profile differences; no fitting or API access."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists(): raise ValueError('Use a fresh figure path')
    s = json.loads(args.summary.read_text())['1_prior_distance_precision_profiles']
    plt.rcParams.update({'font.family': ['Times New Roman','Kaiti SC','STKaiti'],
                         'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.unicode_minus': False})
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7))
    groups = ['truth_stable_model_moves', 'truth_stable_model_stable']
    names = ['真人稳定、模型明显改变', '真人和模型都稳定']
    for row, data in enumerate([s['profiles_0_5pp'], s['interior_prior_0_to_10pp']['profiles']]):
        for col, (field, title) in enumerate([('abs_prior_minus_cpi_pp','上期预期与最新公共CPI的距离'),
                                             ('prior_iqr_pp','上期个人概率分布的IQR')]):
            ax = axes[row, col]
            values = [data[g]['features'][field]['mean'] for g in groups]
            ax.bar(np.arange(2), values, color=['#a45b38','#2e685e'], width=.5)
            ax.set_xticks(np.arange(2), names, fontsize=10)
            ax.set_ylabel('月等权加权均值（pp）')
            ax.set_title(('全部原样本' if row == 0 else '仅检验上期均值0—10%的子样本')+'：'+title, fontsize=11)
            ax.set_ylim(0,max(values)*1.22);ax.grid(axis='y', alpha=.15);ax.set_axisbelow(True)
            for x,v in enumerate(values):ax.text(x,v+.05,f'{v:.2f}',ha='center',va='bottom')
    fig.suptitle('在真人基本未变的人群中，模型更常改写远离公共统计、分布较宽的原信念', fontsize=14)
    fig.subplots_adjust(left=.085,right=.98,top=.88,bottom=.20,hspace=.40,wspace=.25)
    fig.text(.04,.035,'来源：12个预选月，2,284共同人月；按两遍模型均值定位，稳定阈值0.5pp；主绩效仍按逐遍计算。\n'
             '全样本两组n=414/326，内档子样本两组n=237/316；组内设计×调查权重、月份等权。\n'
             '过去CPI与未来一年预期不是同一目标；距离不是预测误差。此图为事后分组描述，不能识别独立CPI权重或因果。', fontsize=9,color='#46514e')
    args.out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(args.out,dpi=180);plt.close(fig)
    print(args.out)


if __name__ == '__main__': main()
