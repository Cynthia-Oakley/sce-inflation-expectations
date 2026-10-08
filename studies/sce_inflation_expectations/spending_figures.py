"""Static, exportable aggregate figures for the spending-data diagnostic."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def make_figures(summary_path, destination):
    d=json.loads(Path(summary_path).read_text());out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,axes=plt.subplots(1,3,figsize=(12,3.8))
    names=['Q9 expectation center','Q9 personal uncertainty','Q8 point forecast']
    for ax,key,name in zip(axes,d['protocol']['outcomes'],names):
        data=d['structural_experiment'][key]['years'];years=list(data)
        gains=[data[y]['arms']['demographics']['mae_pp']-data[y]['arms']['demographics_actual_basket']['mae_pp'] for y in years]
        shuffle=[data[y]['arms']['demographics']['mae_pp']-data[y]['arms']['demographics_shuffled_basket']['mae_pp'] for y in years]
        x=np.arange(len(years));ax.bar(x-.18,gains,.36,label='Actual basket',color='#167d8d')
        ax.bar(x+.18,shuffle,.36,label='Shuffled basket',color='#c59769')
        ax.set_xticks(x,years);ax.axhline(0,c='#414141',lw=.8);ax.set_title(name)
        ax.set_ylabel('MAE reduction vs demographics (pp)')
        for i,v in enumerate(gains):ax.annotate(f'{v:+.3f}',(i-.18,v),ha='center',va='bottom' if v>=0 else 'top',fontsize=8)
    axes[0].legend(fontsize=8)
    fig.suptitle('Train 2020–21; assessment 2022–24 (three survey waves per year)\nWithin-month differences only; not a national forecast',fontsize=11)
    fig.tight_layout();fig.savefig(out/'chronological_increment.png',dpi=180);fig.savefig(out/'chronological_increment.svg');plt.close(fig)
    months=d['descriptive']['months'];xs=np.arange(len(months))
    fig,axes=plt.subplots(1,2,figsize=(11,3.8))
    for ax,key,title in zip(axes,['Q9_mean','Q9_iqr'],['Expectation center','Personal uncertainty']):
        for group,label,c in [('high','Higher food share','#167d8d'),('low','Lower food share','#c59769')]:
            y=[g['groups']['food'][group][key]['weighted_median_pp'] for g in months.values()]
            ax.plot(xs,y,marker='o',ms=3,label=label,c=c)
        labels=[f'{m[:4]}-{m[4:]}' for m in months]
        ax.set_xticks(xs[::3],[labels[i] for i in xs[::3]]);ax.set_ylabel('Weighted group median (pp)');ax.set_title(title);ax.legend(fontsize=8)
    fig.suptitle('Actual spending survey: high vs low food-share groups\nDescriptive association; no causal or shopping-frequency claim',fontsize=11)
    fig.tight_layout();fig.savefig(out/'food_share_groups.png',dpi=180);fig.savefig(out/'food_share_groups.svg');plt.close(fig)
    return [str(p) for p in sorted(out.glob('*'))]
