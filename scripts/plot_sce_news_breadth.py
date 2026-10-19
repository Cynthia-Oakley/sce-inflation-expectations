#!/usr/bin/env python3
"""Figures from aggregate news-allocation results; no personal data or APIs."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

COLORS={'carry':'#777777','history_anchor_half':'#b49b7f','baseline':'#376a99',
        'news_randomized':'#b07939','news_matched':'#347367'}
LABELS={'carry':'Copy previous answer','history_anchor_half':'Half history anchor',
        'baseline':'Uniform 8','news_randomized':'Random 3 / 8 / 20','news_matched':'Matched 3 / 8 / 20'}


def plot(source,out):
    data=json.loads(Path(source).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=False)
    plt.rcParams.update({'font.family':'serif','font.serif':['Times New Roman','DejaVu Serif'],'font.size':10})
    rows=data['weighted_monthly'];x=np.arange(len(rows));labels=[str(r['month'])[:4]+'-'+str(r['month'])[4:] for r in rows]
    fig,ax=plt.subplots(figsize=(11.8,5),constrained_layout=True)
    ax.plot(x,[r['arms']['baseline']['truth_center_pp'] for r in rows],color='#222222',marker='o',lw=2.2,label='Observed SCE, same people')
    for arm in ('carry','baseline','news_randomized','news_matched'):
        ax.plot(x,[r['arms'][arm]['predicted_center_pp'] for r in rows],color=COLORS[arm],
            marker='s' if arm=='carry' else '.',ls='--' if arm=='carry' else '-',lw=1.5,label=LABELS[arm])
    ax.set(title='News allocation: same-household reconstruction',xticks=x,xticklabels=labels,
        xlabel='Six selected development months (not consecutive)',ylabel='Weighted median of personal Q9 density means (%)')
    ax.grid(axis='y',color='#e3e7e5',lw=.6);ax.spines[['top','right']].set_visible(False)
    ax.legend(ncol=2,fontsize=9)
    fig.savefig(out/'monthly_centers.png',dpi=180);fig.savefig(out/'monthly_centers.svg');plt.close(fig)
    metrics=data['weighted_metrics'];arms=list(COLORS)
    fig,axes=plt.subplots(1,3,figsize=(13.3,4.4),constrained_layout=True)
    for ax,key,title in zip(axes,('center_mae_pp','w1_pp','across_person_iqr_pp'),
            ('Group-median MAE','Cross-person W1 distance','Across-person IQR')):
        values=[metrics[a][key] for a in arms]
        bars=ax.bar(np.arange(len(arms)),values,color=[COLORS[a] for a in arms],width=.7)
        for bar,value in zip(bars,values):
            ax.text(bar.get_x()+bar.get_width()/2,value,f'{value:.3f}',ha='center',va='bottom',fontsize=9)
        if key=='across_person_iqr_pp':
            ax.axhline(metrics['baseline']['truth_across_person_iqr_pp'],color='#222222',ls='--',label='Observed SCE')
            ax.legend(fontsize=9)
        ax.set(title=title,xticks=np.arange(len(arms)),xticklabels=['Prior','History','8 each','Random','Matched'],ylabel='Percentage points')
        ax.spines[['top','right']].set_visible(False);ax.margins(y=.22)
    fig.suptitle('Six development months, 96 households/month, two generations; common valid support')
    fig.savefig(out/'metric_comparison.png',dpi=180);fig.savefig(out/'metric_comparison.svg');plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--summary',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();plot(a.summary,a.out)
