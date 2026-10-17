#!/usr/bin/env python3
"""Scientific figures from the frozen 12-wave evaluation; aggregate outputs only."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

SCOPE_NAMES = {'new_months':'Additional 8 months', 'old_months':'Previous 4 months', 'all_months':'All 12 months'}
COLORS = {'model':'#21695b','truth':'#34414a','sample':'#738ca4','copy':'#b08655','anchor':'#8c8e91'}


def render(source, out):
    source,out=Path(source).resolve(),Path(out).resolve()
    s=json.loads(source.read_text())
    if s['status']!='completed_sce_reference_scaleup_evaluation' or out.exists():
        raise ValueError('Complete frozen evaluation and fresh figure folder required')
    plt.rcParams.update({'font.family':'Times New Roman','font.size':11,
                         'axes.spines.top':False,'axes.spines.right':False})
    out.mkdir(parents=True)
    months=s['protocol']['months'];cells=s['cells']
    dates=[datetime(m//100,m%100,15) for m in months]
    def means(key):
        return [np.mean([row[key] for row in cells if row['month']==m]) for m in months]
    model=means('simulated_center_pp');sample=means('matched_sample_truth_center_pp');full=means('full_wave_center_pp')
    spreads=np.array([[min(r['simulated_center_pp'] for r in cells if r['month']==m),
                       max(r['simulated_center_pp'] for r in cells if r['month']==m)] for m in months])
    copied=[np.mean([r['matched_sample_truth_center_pp']+r['scalar_baseline_metrics_same_sample']['copy_previous']['q9_center_bias_pp']
                     for r in cells if r['month']==m]) for m in months]
    fig,ax=plt.subplots(figsize=(12.8,6))
    ax.plot(dates,full,'o-',color=COLORS['truth'],label='Full SCE microdata wave, same fitter',lw=1.8)
    ax.plot(dates,sample,'s--',color=COLORS['sample'],label='Same selected real respondents',lw=1.4)
    ax.errorbar(dates,model,yerr=np.vstack([np.array(model)-spreads[:,0],spreads[:,1]-np.array(model)]),
                fmt='o-',color=COLORS['model'],label='Simulation: two-generation mean and range',capsize=4,lw=1.8)
    ax.plot(dates,copied,'^:',color=COLORS['copy'],label='Copy own previous response, same sample',lw=1.4)
    ax.set_ylabel('Q9 weighted median of individual density means (%)')
    ax.set_xlabel('Selected survey month (connecting lines do not add observations)')
    ax.xaxis.set_major_locator(mdates.YearLocator());ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.grid(axis='y',alpha=.15)
    fig.suptitle('Inflation expectations: 12 selected waves, 192 returners per wave',fontsize=15)
    handles,labels=ax.get_legend_handles_labels()
    fig.legend(handles,labels,ncol=2,loc='upper center',bbox_to_anchor=(.5,.925),frameon=False,fontsize=10)
    fig.subplots_adjust(top=.76,bottom=.23,left=.085,right=.98)
    fig.text(.05,.055,'Source: frozen SCE reference scale-up evaluation, selected months in 2020-2025. Design-survey weights.\n'
             'Two model generations use identical prompts; bars are their range, not confidence intervals.\n'
             'Current real demographics and observed past beliefs are A reconstruction conditions; this is not autonomous B forecasting.\n'
             'All curves use the same approximate raw-bin fitter; the full-wave curve is not a substituted published headline.',fontsize=9)
    fig.savefig(out/'monthly_centers.png',dpi=175);plt.close(fig)

    scopes=['new_months','old_months','all_months'];x=np.arange(3)
    fig,axes=plt.subplots(1,2,figsize=(12.5,5.6))
    left_specs=[('Model',COLORS['model'],lambda d:d['model_metrics_equal_month_repeat_cells']['q9_center_mae_pp']),
                ('Copy own previous',COLORS['copy'],lambda d:d['macro_center_errors']['copy_previous_center_mae_pp']),
                ('Personal history anchor',COLORS['anchor'],lambda d:d['macro_center_errors']['history_anchor_half_center_mae_pp'])]
    right_specs=[('Model',COLORS['model'],lambda d:d['macro_center_errors']['reference_vs_full_wave_center_mae_pp']),
                 ('Previous full-wave center',COLORS['copy'],lambda d:d['macro_center_errors']['previous_full_wave_carry_center_mae_pp'])]
    for ax,title,specs in zip(axes,['Matched selected respondents','Complete SCE microdata wave'],[left_specs,right_specs]):
        width=.23 if len(specs)==3 else .30
        for i,(label,color,getter) in enumerate(specs):
            vals=[getter(s['scopes'][scope]) for scope in scopes]
            ax.bar(x+(i-(len(specs)-1)/2)*width,vals,width,color=color,label=label)
        ax.axhline(.3,color='#9d5454',lw=1,ls='--',label='Project goal: 0.3 pp')
        ax.set_xticks(x,[SCOPE_NAMES[k] for k in scopes],fontsize=9)
        ax.set_title(title,fontsize=12);ax.set_xlabel('Pre-registered time scope')
        ax.set_ylabel('Center MAE (percentage points, lower is better)');ax.grid(axis='y',alpha=.15)
        ax.legend(loc='upper left',fontsize=8,frameon=False)
    fig.suptitle('Macro accuracy: compare each model with a baseline for the same target',fontsize=14)
    fig.subplots_adjust(left=.07,right=.98,top=.82,bottom=.23,wspace=.25)
    fig.text(.04,.05,'Absolute errors are calculated by month and generation, then averaged with equal month weights.\n'
             'Left and right panels have different real targets and must not be substituted for each other.\n'
             'The 0.3 pp line is a project benchmark, not a literature-defined success threshold.',fontsize=9)
    fig.savefig(out/'macro_accuracy.png',dpi=175);plt.close(fig)

    specs=[('individual_density_mean_mae_pp','Individual mean MAE (pp)'),
           ('cross_section_w1_pp','Across-person W1 (pp)'),('cross_person_iqr_pp','Across-person IQR (pp)')]
    fig,axes=plt.subplots(1,3,figsize=(13.2,5.4))
    for ax,(metric,title) in zip(axes,specs):
        model=[s['scopes'][scope]['model_metrics_equal_month_repeat_cells'][metric] for scope in scopes]
        copied=[s['scopes'][scope]['scalar_baselines_equal_month_repeat_cells']['copy_previous']['metrics'][metric] for scope in scopes]
        ax.bar(x-.17,model,.32,color=COLORS['model'],label='Simulation')
        ax.bar(x+.17,copied,.32,color=COLORS['copy'],label='Copy own previous')
        if metric=='cross_person_iqr_pp':
            real=[s['scopes'][scope]['model_metrics_equal_month_repeat_cells']['real_cross_person_iqr_pp'] for scope in scopes]
            ax.plot(x,real,'s--',color=COLORS['truth'],label='Real same respondents')
        ax.set_title(title,fontsize=12);ax.set_xlabel('Time scope');ax.set_xticks(x,['New 8','Old 4','All 12'])
        ax.set_ylabel('Inflation percentage points');ax.grid(axis='y',alpha=.15);ax.legend(fontsize=8,frameon=False)
    fig.suptitle('Microstructure: center accuracy alone does not establish realistic households',fontsize=14)
    fig.subplots_adjust(left=.065,right=.98,top=.81,bottom=.22,wspace=.28)
    fig.text(.04,.05,'Same scored respondents and design-survey weights, equal month/generation averages.\n'
             'Individual MAE and W1: lower is better. Across-person IQR should approach the real spread, not be maximized.\n'
             'A cross-sectional gap is distinct from each respondent\'s subjective uncertainty.',fontsize=9)
    fig.savefig(out/'microstructure.png',dpi=175);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(11.8,5.5))
    for ax,key,title in zip(axes,['same_sample_center_mae_pp','full_wave_center_mae_pp'],['Matched-sample center MAE','Full-wave center MAE']):
        data=[]
        for size in (48,96):
            data.append([r['scopes']['new_months']['model_metrics_equal_month_repeat_cells']['q9_center_mae_pp']
                         if key=='same_sample_center_mae_pp' else r['scopes']['new_months']['macro_center_errors']['reference_vs_full_wave_center_mae_pp']
                         for r in s['nested_sampling']['by_seed'] if r['sample_size']==size])
        ax.boxplot(data,positions=[1,2],widths=.45,showfliers=True)
        fullval=s['scopes']['new_months']['model_metrics_equal_month_repeat_cells']['q9_center_mae_pp'] if key=='same_sample_center_mae_pp' else s['scopes']['new_months']['macro_center_errors']['reference_vs_full_wave_center_mae_pp']
        ax.scatter([3],[fullval],color=COLORS['model'],s=65,zorder=4)
        ax.axhline(.3,color='#9d5454',ls='--',lw=1)
        ax.set_xticks([1,2,3],['48 (30 subsets)','96 (30 subsets)','192 (full draw)'],fontsize=9)
        ax.set_xlabel('People per month');ax.set_ylabel('MAE (percentage points)');ax.set_title(title,fontsize=12)
        ax.grid(axis='y',alpha=.15)
    fig.suptitle('Population-size sensitivity: eight additional months, no extra API calls',fontsize=14)
    fig.subplots_adjust(left=.07,right=.98,top=.82,bottom=.24,wspace=.25)
    fig.text(.04,.055,'Thirty pre-registered nested subsets reuse identical model answers and their appropriate design weights.\n'
             'Boxes show correlated sample sensitivity, not independent model runs or confidence intervals.\n'
             'No seed or subset is selected on its result; the 192-person point is the registered primary population.',fontsize=9)
    fig.savefig(out/'sample_size.png',dpi=175);plt.close(fig)
    (out/'source_receipt.json').write_text(json.dumps({'source':str(source),
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'plot_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'new_api_calls':0,
        'figures':['monthly_centers.png','macro_accuracy.png','microstructure.png','sample_size.png'],
        'note':'Aggregate research figures only; no person-level observations published.'},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();render(a.source,a.out)
