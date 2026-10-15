#!/usr/bin/env python3
"""Figures for existing-data CE quarter/matching checks; no private rows/API."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('--summary',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();s=json.loads(a.summary.read_text());out=a.out.resolve();root=Path(__file__).resolve().parents[1]
    if out.exists() or not out.is_relative_to(root/'outputs'):raise ValueError('Fresh ignored output required')
    out.mkdir(parents=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    labels=['Groceries','Meals away','Household supplies','Personal-care products']
    cats=list(s['quarterly']['1']['selected_distribution'])
    colors=['#237468','#708aa8','#bf754b','#9782a3']
    fig,ax=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    for k,label,color in zip(cats,labels,colors):
        ax[0].plot(range(1,5),[s['quarterly'][str(q)]['fixed_income_age_standardized']['categories'][k]['mean_days'] for q in range(1,5)],
                   'o-',color=color,label=label)
    ax[0].set(xticks=[1,2,3,4],xticklabels=['2020 Q1','Q2','Q3','Q4'],ylabel='Expected recorded days per week',
              title='Same 192 profiles; income and age held fixed',ylim=(0,3.25))
    ax[0].legend(fontsize=9,ncol=2,loc='upper right');ax[0].grid(axis='y',alpha=.15)
    fields=['household_income_band','age_group','housing_tenure','region','education_group'];x=np.arange(5)
    old=s['current_actual_matching'];new=s['pooled_equal_quarter_source']['matching']['field_retention']
    for offset,counts,col,label in [(-.18,[old[k]['required_and_kept'] for k in fields],'#708aa8','Original Q4'),
                                    (.18,[new[k]['retained'] for k in fields],'#237468','Four-quarter pool')]:
        b=ax[1].bar(x+offset,counts,width=.36,color=col,label=label);ax[1].bar_label(b,fontsize=9,padding=3)
    ax[1].set(xticks=x,xticklabels=['Income','Age','Housing','Region','Education'],ylim=(0,240),
              ylabel='Profiles retaining the matching requirement',title='Larger pools preserve more matching fields')
    ax[1].legend(fontsize=9,loc='upper right')
    fig.suptitle('Offline source/matching audit: no new simulation or API calls',fontsize=12)
    fig.savefig(out/'quarter_matching.png',dpi=170);plt.close(fig)

    fig,ax=plt.subplots(figsize=(9,4.3),layout='constrained')
    for i,(k,label) in enumerate(zip(cats,labels)):
        r=s['quarterly']['4']['current_priority_matching']['categories'][k];lo,hi=r['seed_mean_central95']
        ax.plot([lo,hi],[i,i],color='#708aa8',lw=6,alpha=.6)
        ax.scatter(r['original_assigned_mean'],i,color='#bf754b',s=45,zorder=3,
                   label='Original assigned mean' if i==0 else None)
    ax.set(yticks=range(4),yticklabels=labels,xlabel='Mean recorded days per week across 192 profiles',
           title='Original four means fall inside the central 95% of 200 donor draws')
    ax.invert_yaxis();ax.grid(axis='x',alpha=.15);ax.legend(loc='lower right')
    fig.savefig(out/'seed_check.png',dpi=170);plt.close(fig)
    print(out)


if __name__=='__main__':main()
