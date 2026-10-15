#!/usr/bin/env python3
"""Static figures from aggregate coverage/age analysis, no API."""
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
    fig,ax=plt.subplots(1,2,figsize=(12.3,4.8),layout='constrained',gridspec_kw={'width_ratios':[1,1.35]})
    fields=['entry_age','fine_income','family_composition','other_home','financial_decision_role']
    names=['Age at entry','11 income brackets','Family composition','Other home ownership','Financial decisions']
    vals=[s['coverage']['overall'][k]['available'] for k in fields]
    bars=ax[0].barh(range(5),vals,color='#708aa8');ax[0].bar_label(bars,padding=3,fontsize=10)
    ax[0].set(yticks=range(5),yticklabels=names,xlim=(0,215),xlabel='Selected person-months with a prior valid record',
              title='Historical coverage among 192 selected people');ax[0].invert_yaxis()
    cats=['food_at_home','food_away_from_home','household_cleaning_paper','personal_care_products']
    labels=['Groceries','Meals away','Household supplies','Personal-care products']
    for offset,group,color in [(-.12,'40 to 60','#237468'),(.12,'Over 60','#bf754b')]:
        for i,k in enumerate(cats):
            item=s['ce_age']['models']['with_family_composition'][k]['age_coefficients']
            key=next(n for n in item if n.endswith('[T.'+group+']'));r=item[key];v=r['difference_days'];lo,hi=r['ci95']
            ax[1].errorbar(v,i+offset,xerr=[[v-lo],[hi-v]],fmt='o',color=color,capsize=3,label=group if i==0 else None)
    ax[1].axvline(0,color='#667777',ls='--',lw=.8);ax[1].grid(axis='x',alpha=.15)
    ax[1].set(yticks=range(4),yticklabels=labels,xlabel='Conditional difference from under-40 CUs (days/week)',
              title='CE age differences after other controls');ax[1].invert_yaxis();ax[1].legend(loc='lower left',fontsize=9)
    fig.suptitle('Offline audit: own records strictly before target month; CE 2020 Q1-Q4\n9,525 complete CU-weeks / 5,154 CUs; income, housing, region, education, quarter and family composition controlled',fontsize=10)
    fig.savefig(out/'coverage_age.png',dpi=170);plt.close(fig);print(out)


if __name__=='__main__':main()
