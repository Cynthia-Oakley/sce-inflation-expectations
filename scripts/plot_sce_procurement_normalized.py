#!/usr/bin/env python3
"""Plot cached procurement aggregates; export public small figures and summaries."""
import argparse
from pathlib import Path
import sys
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import read_json,dump

LABEL={'shared_price':'共同价格背景','matched_role':'采购角色匹配','shuffled_role':'同月打乱','carry':'照抄本人上期',
       'history_anchor_half':'个人历史锚'}
COLOR={'shared_price':'#809196','matched_role':'#087f80','shuffled_role':'#b58245','carry':'#525b62','real':'#20282c'}


def plot(source,dest):
    source,dest=source.resolve(),dest.resolve()
    if dest.exists():raise ValueError('Fresh public figure destination required')
    s=read_json(source/'summary.json');dest.mkdir(parents=True);(dest/'figures').mkdir()
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':11,
        'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    arms=['shared_price','matched_role','shuffled_role','carry']; agg=s['weighted_metrics']
    fig,axes=plt.subplots(1,3,figsize=(13.5,4.5))
    for ax,(key,title) in zip(axes,[('center_mae_pp','群体中位数 MAE'),('w1_pp','跨人分布 W1'),('delta_w1_pp','个人变化分布 W1')]):
        y=[agg[a][key] for a in arms];bars=ax.bar(range(4),y,color=[COLOR[a] for a in arms],width=.65)
        ax.bar_label(bars,fmt='%.3f',padding=3,fontsize=10);ax.set_xticks(range(4),['共同背景','角色匹配','同月打乱','照抄上期'],rotation=18)
        ax.set_title(title);ax.set_xlabel('实验组与同支持基线');ax.set_ylabel('通胀百分点，越小越好');ax.margins(y=.2)
    fig.text(.02,.015,f'六个非连续开发月，原设计每月96人、两次生成；三组共同支持{s["common_person_months"]}个人月。Q9归一化后逐月逐遍计算误差。',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,1));fig.savefig(dest/'figures/fit_and_distribution.png',dpi=170);plt.close(fig)
    months=[m['month'] for m in s['weighted_monthly']];x=np.arange(len(months))
    fig,axes=plt.subplots(1,2,figsize=(13.5,4.8))
    for arm in arms:
        center=[m['arms'][arm]['predicted_center_pp'] for m in s['weighted_monthly']]
        axes[0].plot(x,center,'o--',color=COLOR[arm],label=LABEL[arm],linewidth=1.6)
    real=[m['arms']['carry']['truth_center_pp'] for m in s['weighted_monthly']]
    axes[0].plot(x,real,'o-',color=COLOR['real'],label='真人同支持',linewidth=2.3)
    axes[0].set_xticks(x,[f'{m//100}-{m%100:02d}' for m in months],rotation=25)
    axes[0].set_title('各月群体中心');axes[0].set_xlabel('非连续目标月份');axes[0].set_ylabel('通胀预期（%）');axes[0].legend(ncol=2,fontsize=9)
    widths=[agg[a]['across_person_iqr_pp'] for a in arms];truth=agg['carry']['truth_across_person_iqr_pp']
    bars=axes[1].bar(range(4),widths,color=[COLOR[a] for a in arms],width=.65);axes[1].bar_label(bars,fmt='%.2f',padding=3)
    axes[1].axhline(truth,color=COLOR['real'],linestyle=':',label=f'真人跨人IQR {truth:.2f}')
    axes[1].set_xticks(range(4),['共同背景','角色匹配','同月打乱','照抄上期'],rotation=18)
    axes[1].set_title('人际分歧的宽度');axes[1].set_xlabel('实验组与同支持基线');axes[1].set_ylabel('跨人IQR（通胀百分点）');axes[1].legend(fontsize=9);axes[1].margins(y=.18)
    fig.text(.02,.015,'左：每月中心取两次生成的平均，仅为绘图；MAE不由该均值计算。右：逐月逐遍IQR的平均，须结合W1判断。',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,1));fig.savefig(dest/'figures/monthly_and_iqr.png',dpi=170);plt.close(fig)
    # Only precomputed aggregates are copied. No person-level normalization rows.
    shutil.copy2(source/'summary.json',dest/'summary.json')
    shutil.copy2(source/'repeat_variance.json',dest/'repeat_variance.json')
    dump(dest/'figure_manifest.json',{'source':'cached evaluation/report only','new_api_calls':0,'new_density_fits':0,
        'figures':['fit_and_distribution.png','monthly_and_iqr.png'],'target_months':months,
        'support_person_months':s['common_person_months'],'normalization_policy':'proportional_nonnegative_v1'})
    print('Saved two figures and aggregate-only summaries:',dest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--dest',type=Path,required=True)
    a=p.parse_args();plot(a.source,a.dest)
