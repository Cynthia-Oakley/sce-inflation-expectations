#!/usr/bin/env python3
"""Scientific figures from aggregate offline diagnostics; no API or private records."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('--summary',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();s=json.loads(a.summary.read_text());out=a.out.resolve()
    root=Path(__file__).resolve().parents[1]
    if out.exists() or not out.is_relative_to(root/'outputs'):raise ValueError('fresh ignored output required')
    out.mkdir(parents=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white'})
    green,blue,orange,gray='#237468','#708aa8','#bf754b','#aab3b7'
    fig,ax=plt.subplots(1,2,figsize=(12,4.4),layout='constrained')
    between=s['price_proxy_variance']['between_month_share']*100;within=100-between
    ax[0].barh([0],[between],color=gray,label='Between survey months')
    ax[0].barh([0],[within],left=[between],color=green,label='Within survey month')
    ax[0].text(between/2,0,f'{between:.1f}%',ha='center',va='center')
    ax[0].text(between+within/2,0,f'{within:.1f}%',ha='center',va='center',color='white')
    ax[0].set(xlim=(0,100),yticks=[],xlabel='Share of synthetic price-proxy variance (%)',title='Most proxy variation is common across a month')
    ax[0].legend(loc='upper center',bbox_to_anchor=(.5,-.2),fontsize=9)
    x=np.arange(4);m=s['monthly_inputs']
    ax[1].bar(x-.18,[r['price_contact_proxy']['iqr'] for r in m],width=.36,color=green,label='Synthetic price-contact proxy')
    ax[1].bar(x+.18,[r['prior_q9']['iqr'] for r in m],width=.36,color=blue,label='Actual prior Q9 beliefs')
    ax[1].set_xticks(x,[str(r['month'])[:4]+'-'+str(r['month'])[4:] for r in m]);ax[1].set_ylabel('Within-month across-person IQR (pp)')
    ax[1].set_title('Different input scales; not a required equality');ax[1].set_ylim(0,6);ax[1].legend(fontsize=9)
    fig.suptitle('Four selected development months; 192 assigned person-months',fontsize=12)
    fig.savefig(out/'inputs.png',dpi=170);plt.close(fig)

    fig,ax=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    for i,(key,label,col) in enumerate([('real_q9','Actual respondents',gray),('data_q9','Frequency data',green),('rule_q9','Data + instruction',orange)]):
        c=s['full_models'][key]['coherent_prior_level_association'];b=c['coefficient'];lo,hi=c['ci95']
        ax[0].errorbar(b,i,xerr=[[b-lo],[hi-b]],fmt='o',color=col,capsize=4)
    ax[0].set_yticks([0,1,2],['Actual respondents','Frequency data','Data + instruction']);ax[0].invert_yaxis()
    ax[0].set(xlabel='Association per jointly 1pp-higher prior levels (pp)',title='Conditional prior-history association')
    coefficients=s['full_models']['change_q9']['coefficients']
    for i,k in enumerate(['f_home','f_away','f_house','f_care']):
        c=coefficients[k];b=c['coefficient'];lo,hi=c['ci95']
        ax[1].errorbar(b,i,xerr=[[b-lo],[hi-b]],fmt='o',color=green,capsize=4)
    ax[1].set_yticks(range(4),['Groceries','Meals away','Household supplies','Personal-care products']);ax[1].invert_yaxis()
    ax[1].set(xlabel='Rule minus data Q9 forecast per extra recorded day (pp)',title='Frequency moderators: exploratory, not causal')
    for item in ax:item.axvline(0,color='#667777',ls='--',lw=.8);item.grid(axis='x',alpha=.15)
    fig.suptitle('173 complete cases; months, history, demographics, CE shares and confidence controlled\nHC3 95% intervals are not simultaneous intervals; prior association is not an update weight',fontsize=11)
    fig.savefig(out/'controlled_associations.png',dpi=170);plt.close(fig)

    fig,ax=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    stages=['reused_C','frequency_data','frequency_rule'];names=['old_c','data','rule'];labels=['Earlier C*','Frequency data','Data + instruction'];x=np.arange(3)
    for measure,color,offset in [('q9',green,-.18),('q8',blue,.18)]:
        macro=[np.mean([r[measure+'_absolute_error'] for r in s['center_bridges'] if r['arm']==stage]) for stage in stages]
        micro=[s['per_person_means_common_188'][name][measure+'_abs_error'] for name in names]
        for item,values in [(ax[0],macro),(ax[1],micro)]:
            bars=item.bar(x+offset,values,width=.36,color=color,label=measure.upper());item.bar_label(bars,fmt='%.3f',padding=3,fontsize=9)
    ax[0].set_title('Error of the group median');ax[1].set_title('Mean individual absolute error')
    for item in ax:
        item.set_xticks(x,labels);item.set_ylabel('MAE (pp; different aggregation)');item.legend();item.set_ylim(0,item.get_ylim()[1]*1.12)
    fig.suptitle('Same 188 people; 2 generations retained in error averages\n*Earlier C has different input blocks and batch: descriptive reference only',fontsize=11)
    fig.savefig(out/'aggregate_individual_errors.png',dpi=170);plt.close(fig)
    print(out)


if __name__=='__main__':main()
