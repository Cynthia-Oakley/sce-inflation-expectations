#!/usr/bin/env python3
"""Publish only cached aggregate price-background statistics and two figures."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
COLORS={'food_background':'#783caf','broader_background':'#df7400','carry':'#79818a'}
LABELS={'food_background':'食品背景','broader_background':'增加总体与能源','carry':'照抄本人上期'}


def plot(source,dest):
    if dest.exists():raise ValueError('Fresh aggregate-only publication directory required')
    s=json.loads((source/'summary.json').read_text())
    if s['status']!='completed_price_background_readout':raise ValueError('Completed readout required')
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],
        'font.size':11,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    dest.mkdir(parents=True);(dest/'figures').mkdir()
    months=s['months'];arms=s['arms'];names=[*arms,'carry'];x=np.arange(len(months))
    ticks=[f'{m//100}-{m%100:02}' for m in months]
    fig,axes=plt.subplots(1,2,figsize=(13.5,4.8))
    truth=[s['monthly'][str(m)]['metrics'][arms[0]]['truth_center_pp'] for m in months]
    axes[0].plot(x,truth,'o-',color='#202328',linewidth=2.3,label='真人本期')
    for a,marker in zip(names,['s','^','x']):
        values=[s['monthly'][str(m)]['metrics'][a]['predicted_center_pp'] for m in months]
        axes[0].plot(x,values,marker+'--',color=COLORS[a],label=LABELS[a])
    axes[0].set_title('各月群体中位数');axes[0].set_ylabel('未来12个月通胀预期（%）')
    axes[0].legend(fontsize=8)
    for j,a in enumerate(names):
        values=[s['monthly'][str(m)]['metrics'][a]['center_mae_pp'] for m in months]
        axes[1].bar(x+(j-1)*.25,values,.23,color=COLORS[a],label=LABELS[a])
    axes[1].set_title('各月群体中位数MAE');axes[1].set_ylabel('绝对误差（通胀百分点）')
    axes[1].legend(fontsize=8)
    for ax in axes:ax.set_xticks(x,ticks,rotation=25);ax.set_xlabel('非连续目标月份')
    fig.text(.015,.015,f'同支持{s["person_months"]}个人月／{s["unique_persons"]}人；六个开发月，各两次生成。左图均值仅作展示；右图先逐遍算MAE再平均。',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,1));fig.savefig(dest/'figures/monthly_prices.png',dpi=165);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(13.5,4.8))
    order=['below_2','2_to_below_4','4_to_below_8','8_or_above']
    bands=[b for b in order if b in s['groups']['prior']];x=np.arange(len(bands))
    truth=[s['groups']['prior'][b]['metrics'][arms[0]]['truth_mean_pp'] for b in bands]
    axes[0].plot(x,truth,'o-',color='#202328',linewidth=2.3,label='真人本期')
    for a,marker in zip(names,['s','^','x']):
        values=[s['groups']['prior'][b]['metrics'][a]['model_mean_pp'] for b in bands]
        axes[0].plot(x,values,marker+'--',color=COLORS[a],label=LABELS[a])
    labels=dict(zip(order,['上期<2%','上期2—4%','上期4—8%','上期≥8%']))
    axes[0].set_xticks(x,[labels[b] for b in bands]);axes[0].set_xlabel('本人上期预期分组')
    axes[0].set_ylabel('本期个人预期的加权均值（%）');axes[0].set_title('不同先验人群的本期回答');axes[0].legend(fontsize=8)
    keys=['w1_pp','delta_w1_pp'];x=np.arange(2)
    for j,a in enumerate(names):
        bars=axes[1].bar(x+(j-1)*.25,[s['metrics'][a][k] for k in keys],.23,color=COLORS[a],label=LABELS[a])
        axes[1].bar_label(bars,fmt='%.2f',padding=3,fontsize=9)
    axes[1].set_xticks(x,['本期预期分布W1','相对上期变化的分布W1'])
    axes[1].set_xlabel('分布比较对象');axes[1].set_ylabel('分布距离（通胀百分点，越低越接近）')
    axes[1].set_title('跨人分布与更新分布');axes[1].legend(fontsize=8);axes[1].margins(y=.2)
    fig.text(.015,.015,'先逐月逐遍按调查设计权重计算，再等权平均；各组人数/稀疏标记见聚合文件。两个价格信号联合变化，不识别各自贡献。',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,1));fig.savefig(dest/'figures/distribution_prices.png',dpi=165);plt.close(fig)
    def compact(v):
        if isinstance(v,dict):return {k:compact(w) for k,w in v.items() if k!='cells'}
        if isinstance(v,list):return [compact(w) for w in v]
        return v
    (dest/'summary.json').write_text(json.dumps(compact(s),ensure_ascii=False,indent=2)+'\n')
    print('Published aggregate summary and two figures:',dest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--dest',type=Path,required=True)
    a=p.parse_args();plot(a.source.resolve(),a.dest.resolve())
