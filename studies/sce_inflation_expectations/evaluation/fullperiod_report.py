"""Aggregate-only report/Canvas over frozen A82 analysis; no network or fitting."""
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import html
import json
import math
import os

import numpy as np

from ..experiments.frozen_batch import ROOT, read_json, dump, sha
from .aggregate_blend import fit_weight, evaluate as blend_metrics
from .metrics import quantile
from .fullperiod_analysis import MODEL, PAST, finite, shared

LABELS={'college':'大学及以上','some_college':'部分大学教育','high_school':'高中及以下',
    'high':'高数理','low':'低数理','40 to 60':'40—60岁','Over 60':'60岁以上','Under 40':'40岁以下',
    'under_50k':'收入<5万美元','50k_to_100k':'收入5—10万美元','over_100k':'收入>10万美元',
    'entrant':'首次受访','returning':'回访者','gap_return':'间隔后回访','own_adjacent':'本人相邻上期',
    'own_older':'本人更早记录','synthetic_donor':'近期匿名供体','unknown':'未知',
    'Northeast':'东北部','Midwest':'中西部','South':'南部','West':'西部'}


def diagnostics(s):
    folder=ROOT/s['scope']['analysis_run'];cases=read_json(folder/'evaluation/cases_private.json')
    by_month=defaultdict(list)
    for r in cases:
        if finite(r['survey_weight']) and r['survey_weight']>0:by_month[r['month']].append(r)
    supports={field:shared._common_person_months(cases,[MODEL,PAST],[1],field) for field in ('q8','q9')}
    missing=defaultdict(set)
    with (folder/'combined/positions_private.jsonl').open() as stream:
        for line in stream:
            r=json.loads(line)
            for f,ok in r['state_after']['transition']['field_updated_from_model'].items():
                if not ok:missing[int(r['month']),f].add(r['agent_id'])
    bounds=[]
    for (month,field),ids in sorted(missing.items()):
        target='q9_mean' if field=='q9' else 'q8_point';key='mean' if field=='q9' else 'point'
        rows=[r for r in by_month[month] if (r['month'],r['userid']) in supports[field]]
        known=[r for r in rows if r['agent_id'] not in ids];unknown=[r for r in rows if r['agent_id'] in ids]
        if not unknown:continue
        mass=sum(r['survey_weight'] for r in unknown);total=sum(r['survey_weight'] for r in rows)
        w=[r['survey_weight'] for r in known];x=[r['arms'][MODEL][key] for r in known]
        lo=quantile(x,w,max(0.,(.5*total-mass)/(total-mass)))
        hi=quantile(x,w,min(1.,.5*total/(total-mass)))
        bounds.append(dict(month=month,field=field,missing_n=len(unknown),weight_share=mass/total,
                           possible_median_low_pp=lo,possible_median_high_pp=hi,possible_range_pp=hi-lo))
    change_cells=[]
    band_names=['不变','0—1pp','1—2pp','2—5pp','超过5pp']
    for month,rows in sorted(by_month.items()):
        rows=[r for r in rows if all(finite(x) for x in [r['real']['previous_q9_mean'],r['real']['q9_mean'],r['arms'][MODEL]['mean']])]
        if not rows:continue
        dy=np.array([r['real']['q9_mean']-r['real']['previous_q9_mean'] for r in rows])
        ds=np.array([r['arms'][MODEL]['mean']-r['real']['previous_q9_mean'] for r in rows]);w=np.array([r['survey_weight'] for r in rows])
        absolute=abs(dy);group=np.where(absolute<1e-8,0,np.where(absolute<=1,1,np.where(absolute<=2,2,np.where(absolute<=5,3,4))))
        for i,name in enumerate(band_names):
            mask=group==i
            if not mask.any():continue
            change_cells.append(dict(month=month,band=name,n=int(mask.sum()),
                human_abs_delta_pp=float(np.average(absolute[mask],weights=w[mask])),
                model_abs_delta_pp=float(np.average(abs(ds[mask]),weights=w[mask]))))
    bands=[]
    for name in band_names:
        rows=[r for r in change_cells if r['band']==name]
        bands.append(dict(band=name,person_months=sum(r['n'] for r in rows),months=len(rows),
            human_abs_delta_pp=float(np.mean([r['human_abs_delta_pp'] for r in rows])),
            model_abs_delta_pp=float(np.mean([r['model_abs_delta_pp'] for r in rows]))))
    train=[r for r in s['official_national']['monthly'] if '2019-01'<=r['month']<='2022-12']
    rechecked={}
    for loss in ('mae','mse'):
        fitted=fit_weight([r['truth_pp'] for r in train],[r['anchor_pp'] for r in train],[r['sim_pp'] for r in train],loss)
        if fitted!=s['official_national']['chronological_combinations'][loss]['simulation_weight']:
            raise ValueError('Combination recheck failed')
        rechecked[loss]=dict(simulation_weight=fitted,fit_period_pure_model=blend_metrics(train,1),
                             fit_period_persistence=blend_metrics(train,0))
    return dict(remaining_response_median_bounds=bounds,
        maximum_core_q9_mae_change_bound_pp=sum(r['possible_range_pp'] for r in bounds if r['field']=='q9')/len(s['monthly']),
        true_change_conditioned_bands=bands,
        true_change_band_limit='Groups use current human outcomes: descriptive diagnosis only, never an input or deployment switching rule.',
        combination_recheck=rechecked,new_api_calls=0,new_q9_fits=0)


def render(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists():raise ValueError('Fresh report folder required')
    s=read_json(source/'summary.json');check=diagnostics(s);out.mkdir(parents=True)
    dump(out/'diagnostic_checks.json',check)
    os.environ.setdefault('MPLCONFIGDIR','/private/tmp/sce_fullperiod_mpl')
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt,dates as mdates,font_manager
    tnr=Path('/System/Library/Fonts/Supplemental/Times New Roman.ttf')
    if tnr.exists():font_manager.fontManager.addfont(str(tnr))
    plt.rcParams.update({'font.family':'Times New Roman','font.size':12,'axes.spines.top':False,
        'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18,'figure.dpi':150,'savefig.bbox':'tight'})
    C={'human':'#202124','model':'#D55E00','past':'#0072B2','combo':'#8B5FBF'}
    def save(fig,name):
        fig.tight_layout();fig.savefig(out/(name+'.png'));fig.savefig(out/(name+'.svg'));plt.close(fig)
    national=s['official_national']['monthly'];dates=[datetime.strptime(r['month'],'%Y-%m') for r in national]
    truth=np.array([r['truth_pp'] for r in national]);sim=np.array([r['sim_pp'] for r in national]);past=np.array([r['anchor_pp'] for r in national])
    fig,axes=plt.subplots(2,1,figsize=(12,6.4),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    for name,v in [('human',truth),('past',past),('model',sim)]:
        axes[0].plot(dates,v,label={'human':'Official SCE','past':'Public persistence','model':'Simulation'}[name],
                     color=C[name],linewidth=1.7,linestyle='--' if name=='past' else '-')
    axes[0].set_ylabel('Inflation expectation (%)');axes[0].legend(ncol=3,fontsize=10,loc='upper left')
    axes[0].set_title('National one-year inflation expectations | Jan 2019–Oct 2025')
    axes[1].plot(dates,sim-truth,label='Simulation error',color=C['model'])
    axes[1].plot(dates,past-truth,label='Persistence error',color=C['past'],linestyle='--')
    axes[1].axhline(0,color=C['human'],linewidth=.7);axes[1].set_ylabel('Signed error (pp)');axes[1].set_xlabel('Reference month')
    for ax in axes:ax.axvline(datetime(2023,1,1),color=C['combo'],linestyle=':',linewidth=1)
    axes[1].xaxis.set_major_locator(mdates.YearLocator());axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    save(fig,'01_national_timeline')
    years=s['yearly'];x=np.arange(len(years));fig,axes=plt.subplots(1,2,figsize=(12,4.1))
    for ax,metric,title in [(axes[0],'mae_pp','MAE'),(axes[1],'rmse_pp','RMSE')]:
        ax.bar(x-.18,[r['model'][metric] for r in years],.36,color=C['model'],label='Simulation')
        ax.bar(x+.18,[r['persistence'][metric] for r in years],.36,color=C['past'],label='Persistence')
        ax.set_xticks(x,[r['period'] for r in years]);ax.set_ylabel(title+' (pp)');ax.set_xlabel('Year (2025: Jan–Oct)')
        ax.set_title('National '+title+' by year');ax.legend(fontsize=10)
    save(fig,'02_yearly_errors')
    monthly=s['monthly'];d=[datetime.strptime(str(r['month']),'%Y%m') for r in monthly]
    fig,axes=plt.subplots(1,2,figsize=(12,4.2))
    for arm,name,color in [('model','Simulation',C['model']),('past','Assigned starting state',C['past'])]:
        axes[0].plot(d,[r[arm]['cross_section_w1_pp'] for r in monthly],color=color,label=name)
        axes[1].plot(d,[r[arm]['cross_person_iqr_pp'] for r in monthly],color=color,label=name)
    axes[1].plot(d,[r['model']['real_cross_person_iqr_pp'] for r in monthly],color=C['human'],label='Matched humans')
    axes[0].set_ylabel('W1 to matched humans (pp)');axes[1].set_ylabel('Cross-person IQR (pp)')
    axes[0].set_title('Distribution distance on the same roster');axes[1].set_title('Between-person disagreement')
    for ax in axes:
        ax.set_xlabel('Reference month');ax.xaxis.set_major_locator(mdates.YearLocator(2));ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'));ax.legend(fontsize=9)
    save(fig,'03_microstructure')
    feature_groups=[g for g in s['groups'] if g['dimension'] in ('education_group','numeracy','household_income_band','survey_entry_status') and g['eligible_months']>0]
    short={'college':'College','some_college':'Some college','high_school':'High school','high':'High numeracy','low':'Low numeracy',
        'under_50k':'Income <50k','50k_to_100k':'Income 50–100k','over_100k':'Income >100k','entrant':'Entrants','returning':'Returners','gap_return':'Gap returners'}
    fig,axes=plt.subplots(1,2,figsize=(12,5.5));y=np.arange(len(feature_groups))
    axes[0].barh(y,[g['eligible_metrics']['q9_center_mae_pp'] for g in feature_groups],color=C['model'])
    axes[0].set_yticks(y,[short.get(g['label'],g['label']) for g in feature_groups]);axes[0].invert_yaxis()
    axes[0].set_xlabel('Group monthly-center MAE (pp)');axes[0].set_title('Errors differ across groups')
    axes[1].barh(y-.17,[g['eligible_metrics']['cross_person_iqr_pp'] for g in feature_groups],.34,color=C['model'],label='Simulation')
    axes[1].barh(y+.17,[g['eligible_metrics']['real_cross_person_iqr_pp'] for g in feature_groups],.34,color=C['human'],label='Humans')
    axes[1].set_yticks(y,[short.get(g['label'],g['label']) for g in feature_groups]);axes[1].invert_yaxis()
    axes[1].set_xlabel('Cross-person IQR (pp)');axes[1].set_title('Within-group dispersion remains compressed');axes[1].legend(fontsize=10)
    save(fig,'04_group_differences')
    bands=check['true_change_conditioned_bands'];x=np.arange(len(bands));fig,axes=plt.subplots(1,2,figsize=(12,4.3))
    names=['Unchanged','0–1','1–2','2–5','>5']
    axes[0].bar(x-.18,[r['human_abs_delta_pp'] for r in bands],.36,color=C['human'],label='Human |change|')
    axes[0].bar(x+.18,[r['model_abs_delta_pp'] for r in bands],.36,color=C['model'],label='Model |change|')
    axes[0].set_xticks(x,names);axes[0].set_xlabel('Realized human absolute change band (pp)');axes[0].set_ylabel('Average absolute update (pp)')
    axes[0].set_title('Outcome-conditioned update diagnosis');axes[0].legend(fontsize=9)
    prior=[]
    for label in ['低先验','中先验','高先验']:
        rows=[r for r in s['prior_bands'] if r['band']==label]
        prior.append(dict(label=label,human=float(np.mean([r['real_mean_delta_pp'] for r in rows])),model=float(np.mean([r['model_mean_delta_pp'] for r in rows]))))
    for name,color in [('human',C['human']),('model',C['model'])]:
        axes[1].plot(range(3),[r[name] for r in prior],marker='o',color=color,label=name.title())
    axes[1].axhline(0,color='#999999',linewidth=.7);axes[1].set_xticks(range(3),['Low','Middle','High'])
    axes[1].set_xlabel('Earlier belief: within-month tercile');axes[1].set_ylabel('Mean signed update (pp)')
    axes[1].set_title('Updating relative to the same real prior');axes[1].legend(fontsize=9)
    save(fig,'05_updates')
    reg=s['regression'];specs=['simulation_only','lag_only','lag_plus_simulation','past_history_P_month','past_history_P_month_plus_simulation']
    fig,ax=plt.subplots(figsize=(9,3.7));xx=np.arange(5);vals=[100*reg['fits'][k]['r2'] for k in specs]
    ax.barh(xx,vals,color=[C['model'],C['past'],C['combo'],C['past'],C['model']]);ax.invert_yaxis()
    ax.set_yticks(xx,['Simulation only','Own prior only','Own prior + simulation','Past history + P + month FE','Same controls + simulation'])
    for i,v in enumerate(vals):ax.text(v+.4,i,f'{v:.2f}%',va='center',fontsize=10)
    ax.set_xlim(0,50);ax.set_xlabel('Descriptive WLS R-squared (%)');ax.set_title('Individual-level incremental information | same 33,726 person-months')
    save(fig,'06_incremental_information')

    def f(x,n=3):return '—' if not finite(x) else f'{x:.{n}f}'
    def table(headers,rows):
        return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in r)+'</tr>' for r in rows)+'</tbody></table></div>'
    def figure(name,caption):return f'<figure><img src="{name}.svg" alt="{html.escape(caption)}"><figcaption>{caption}</figcaption></figure>'
    national_metrics=s['macro_whole'];late=next(r for r in s['periods'] if r['period']=='评价期2023–2025')
    q9=s['fixed_roster'][MODEL]['q9'];b9=s['fixed_roster'][PAST]['q9'];q8=s['fixed_roster'][MODEL]['q8'];b8=s['fixed_roster'][PAST]['q8']
    combo=s['official_national']['chronological_combinations']['mae'];v=s['variance_gap_within_grid_share']
    comparison_rows=[['相同人群Q9',f(q9['q9_center_mae_pp']),f(b9['q9_center_mae_pp']),'保留分配起点，含真实与合成'],
        ['完整真人波次Q9',f(s['full_wave']['q9_mean']['model']['mae_pp']),f(s['full_wave']['q9_mean']['copy_previous_full_micro']['mae_pp']),'上期完整微观波次'],
        ['官方全国Q9',f(national_metrics['model']['mae_pp']),f(national_metrics['persistence']['mae_pp']),'截止前最后公开全国值'],
        ['相同人群Q8（单列）',f(q8['q8_center_mae_pp']),f(b8['q8_center_mae_pp']),'保留分配的Q8起点']]
    yearly_rows=[[r['period'],r['n_months'],f(r['model']['mae_pp']),f(r['persistence']['mae_pp']),f(r['model']['bias_pp']),str(r['model_win_months'])+'/'+str(r['n_months'])] for r in s['yearly']]
    combo_rows=[]
    for loss in ('mae','mse'):
        co=s['official_national']['chronological_combinations'][loss]
        combo_rows.append([loss.upper(),f(co['simulation_weight']),f(co['history_weight']),f(co['evaluation']['mae_pp']),f(co['evaluation']['rmse_pp'])])
    micro_rows=[['跨人W1（pp）',f(q9['cross_section_w1_pp']),f(b9['cross_section_w1_pp']),'越小越接近真人'],
        ['跨人IQR（pp）',f(q9['cross_person_iqr_pp']),f(b9['cross_person_iqr_pp']),f(q9['real_cross_person_iqr_pp'])+'（真人）'],
        ['个人中心MAE（pp）',f(q9['individual_density_mean_mae_pp']),f(b9['individual_density_mean_mae_pp']),'同一真实有效支持'],
        ['个人密度内部IQR（pp）',f(q9['individual_density_iqr_mean_pp']),f(b9['individual_density_iqr_mean_pp']),f(q9['real_individual_density_iqr_mean_pp'])+'（真人）'],
        ['零通缩概率占比',f(q9['zero_deflation_rate']*100,1)+'%',f(b9['zero_deflation_rate']*100,1)+'%',f(q9['real_zero_deflation_rate']*100,1)+'%（真人）'],
        ['个人中心秩相关',f(q9['person_mean_spearman']),f(b9['person_mean_spearman']),'沿冻结普通Spearman口径']]
    update_rows=[['变化分布W1（pp）',f(s['update_summary']['model_delta_w1_pp']),f(s['update_summary']['past_delta_w1_pp'])+'（完全不更新）'],
        ['保持不变比例',f(100*s['update_summary']['model_unchanged_share'],1)+'%',f(100*s['update_summary']['human_unchanged_share'],1)+'%（真人）'],
        ['变化超过2pp比例',f(100*s['update_summary']['model_large_change_share'],1)+'%',f(100*s['update_summary']['human_large_change_share'],1)+'%（真人）']]
    group_rows=[]
    for g in feature_groups:
        m=g['eligible_metrics'];group_rows.append([LABELS.get(g['label'],g['label']),g['person_months'],g['eligible_months'],f(m['q9_center_mae_pp']),f(m['cross_section_w1_pp']),f(m['cross_person_iqr_pp'])+' / '+f(m['real_cross_person_iqr_pp'])])
    bound_rows=[[str(r['month']),r['field'].upper(),r['missing_n'],f(100*r['weight_share'],3)+'%',f(r['possible_median_low_pp'],5)+'—'+f(r['possible_median_high_pp'],5)] for r in check['remaining_response_median_bounds']]
    css='''*{box-sizing:border-box}body{margin:0;background:#faf9f5;color:#24262a;font:18px/1.8 "Times New Roman","Kaiti SC","STKaiti","KaiTi",serif}main{max-width:1120px;margin:auto;padding:28px 32px 70px}h1{font-size:32px;line-height:1.4;margin:12px 0}h2{font-size:25px;line-height:1.4;margin:40px 0 12px;border-top:1px solid #d5d8dc;padding-top:24px}h3{font-size:21px;margin:24px 0 8px}a{color:#006ca4}nav{display:flex;flex-wrap:wrap;gap:16px;font-size:15px}p{margin:12px 0}.lead{font-size:21px}.muted,figcaption{color:#626973;font-size:15px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;border-top:3px solid #d55e00;border-bottom:1px solid #d5d8dc;padding:18px 0;margin:25px 0}.metrics b{font-size:29px;display:block}.metrics span{display:block;font-size:15px}.note{background:#eef3f8;border-left:4px solid #0072b2;padding:13px 20px;margin:22px 0}.warning{background:#fff3e7;border-left-color:#d55e00}table{border-collapse:collapse;width:100%;font-size:16px}th,td{padding:10px 12px;border-bottom:1px solid #d5d8dc;text-align:left;vertical-align:top}th{background:#edf0f2}.table-wrap{overflow:auto}figure{margin:24px 0}figure img{width:100%;display:block;background:white}figcaption{margin-top:9px;line-height:1.6}details{margin:20px 0}summary{cursor:pointer;font-size:19px;font-weight:bold}li{margin:6px 0}code{font-size:14px;overflow-wrap:anywhere}footer{font-size:14px;color:#626973;border-top:1px solid #d5d8dc;margin-top:40px;padding-top:18px}@media(max-width:700px){main{padding:20px 16px}h1{font-size:26px}.metrics{grid-template-columns:1fr;gap:10px}body{font-size:17px}}@media print{body{background:white}nav{display:none}main{max-width:none;padding:0}h2{break-after:avoid}figure,.table-wrap{break-inside:avoid}}'''
    text=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCE全时段重建结果｜82个月</title><style>{css}</style></head><body><main>
<nav><a href="../../project_guide.html">项目机制说明</a><a href="../../workstreams/20261024_fullperiod_analysis/README.md">分析框架</a><a href="summary.json">聚合数据</a><a href="#macro">总体</a><a href="#blend">组合</a><a href="#micro">微观</a><a href="#groups">分组</a><a href="#limits">边界</a></nav>
<p class="muted">2019-01—2025-10 · 82个月 × 每月512人 · DeepSeek V3.2 / SiliconFlow FP8 · 历史条件重建A线</p>
<h1>美国居民通胀预期：全时段重建结果</h1>
<p class="lead">全期尚未超过持续性基线；2023年以后出现宏观收益，微观分歧与个体增量仍是主要缺口。</p>
<div class="metrics"><div><b>{f(national_metrics['model']['mae_pp'])} / {f(national_metrics['persistence']['mae_pp'])}</b><span>全82月全国MAE：模型 / 持续性基线，pp</span></div><div><b>{f(late['model']['mae_pp'])} / {f(late['persistence']['mae_pp'])}</b><span>后34月全国MAE：纯模型 / 基线，pp</span></div><div><b>{100*q9['cross_person_iqr_pp']/q9['real_cross_person_iqr_pp']:.1f}%</b><span>模型跨人IQR相对于真人；同支持</span></div></div>
<p class="note">本报告分析已完成的41,984个人月，技术修复后41,982份完整，剩Q8 1份/Q9 2份按冻结规则后备。Q9同支持可计分真人为40,933个人月；真人原始问卷也存在计分不支持，并非其余都属于模型接口失败。主运行一次，修复不算新增人口或独立重复生成。<strong>本次分析0 API调用、0 Q9重新拟合、0机制修改。</strong></p>
<h2 id="macro">一、总体拟合：全期差距集中在2021年</h2>
{table(['比较对象','模型中心MAE（pp）','相应基线MAE（pp）','基线含义'],comparison_rows)}
{figure('01_national_timeline','黑线：官方SCE；橙线：模型；蓝虚线：截止前公开历史值。下图为有符号误差，紫色竖线区分48月拟权期与后34月评价期。全国发布值与同支持真人不是同一比较对象。')}
<p>2021年模型全年低估，MAE {f(s['yearly'][2]['model']['mae_pp'])}pp，12个月均未胜过基线。2025年1—10月则为{f(s['yearly'][-1]['model']['mae_pp'])}pp，对照{f(s['yearly'][-1]['persistence']['mae_pp'])}pp，胜出8/10个月。2024年基线更强，因此不能将“后期平均较好”表述为“每年都胜出”。</p>
{figure('02_yearly_errors','各年月份等权，2025年仅1—10月。MAE与RMSE分开：2023年模型MAE较低，但RMSE仍略高于基线。')}
{table(['年份','月份数','模型MAE','基线MAE','模型偏差（pp）','模型胜出月'],yearly_rows)}
<p class="muted">全期模型−基线MAE差{f(national_metrics['paired_mae']['mae_difference_pp'])}pp，6月区块配对95%区间[{f(national_metrics['paired_mae']['interval_95'][0])}, {f(national_metrics['paired_mae']['interval_95'][1])}]。后34月差{f(late['paired_mae']['mae_difference_pp'])}pp，区间[{f(late['paired_mae']['interval_95'][0])}, {f(late['paired_mae']['interval_95'][1])}]，跨0；属于既有轨迹的回顾性不确定性，不能证明未来必然胜出。</p>
<h2 id="blend">二、加权组合：冻结权重未保留模拟增量</h2>
<p>公式为 (1−λ)×截止前公开历史SCE + λ×本月模拟。2019—2022年48个月拟权，2023—2025年10月34个月评价；λ限制在0—1，无截距。</p>
{table(['拟合目标','模拟权重λ','历史权重','后34月组合MAE（pp）','组合RMSE（pp）'],combo_rows)}
<p class="note warning">MAE和MSE均选λ=0，已复算核实。原因是拟权期模型MAE {f(check['combination_recheck']['mae']['fit_period_pure_model']['mae_pp'])}pp、高于历史基线{f(check['combination_recheck']['mae']['fit_period_persistence']['mae_pp'])}pp。因此<strong>最终冻结组合的后34月MAE是{f(combo['evaluation']['mae_pp'])}pp，不是纯模型的{f(late['model']['mae_pp'])}pp</strong>。后期纯模型较好，没有自动转化为事前固定组合收益；本轮不据后期结果重新挑权重。</p>
<h2 id="micro">三、微观结构：中心接近时，人际差异仍明显收缩</h2>
{table(['指标（同一人群）','模型','保留起点','解释或真人值'],micro_rows)}
{figure('03_microstructure','逐月同支持、设计权重。左为模型/起点到真人中心分布的W1；右为跨人IQR。保留起点包括本人真实历史与已声明的合成起点。')}
<p>将每月模型和真人的中位数在评价层对齐后，W1仍约{f(s['centered_w1_mean_pp'])}pp（原值{f(q9['cross_section_w1_pp'])}pp），说明分布差距主要不是一个共同中心平移。按54格作月内描述性方差分解，约{100*v:.1f}%的净方差缺口位于格内。该比例描述样本中的分解，不是人口特征的因果贡献。</p>
<h3>信念更新：不变的人被改动，大变动又被压小</h3>
<p>只用33,726个真实相邻回访个人月：两边都减去同一个本人真实上期值。不是自主递推。模型更新分布W1明显优于完全不更新，但个人更新方向一致率约{100*s['update_summary']['direction_match_share']:.1f}%。</p>
{table(['更新指标','模型','对照或真人'],update_rows)}
{figure('05_updates','左：按真人本期已经发生的变化幅度分组，比较平均绝对更新；这是事后诊断，不能作预测时的切换规则。右：按输入上期值在月内的三分位分组；并列按既有分位定义处理。')}
<h2 id="groups">四、误差人群：低数理、低收入与新人更困难</h2>
{figure('04_group_differences','仅展示满足N≥20、ESS≥10的月份。两面板展示组中心误差和组内IQR，组间样本/真人本身的波动不同，不能直接解释为某个人口特征导致错误。')}
{table(['人群','Q9个人月','满足支持月数','组中心MAE（pp）','W1（pp）','模型 / 真人IQR'],group_rows)}
<p>回访者Q9中心MAE约0.311pp，新人约0.816pp；新人个体身份先验不可观测，且其真人分布更宽。即使只看真实相邻上期者，模型W1约{f(s['genuine_previous_only'][MODEL]['q9']['cross_section_w1_pp'])}pp，对照照抄本人上期{f(s['genuine_previous_only']['genuine_previous_only']['q9']['cross_section_w1_pp'])}pp，说明微观问题不只来自新人。</p><p class="muted">分组表沿各组模型/真人可计分支持；总体基线比较还要求起点可计分，故两处人数可能不同。支持不足的月份不进入分组摘要。</p>
<details><summary>全部分组与54格月度支持</summary><p>完整聚合数据见summary.json的groups，含各格/单维分组的月度N、ESS、是否仅描述及指标。没有支持的月份不进入本页人群排名；未知画像另列。总体中位数/W1不等于分组指标的加权平均。</p></details>
<h2>五、个人增量：历史解释力强于模拟</h2>
{figure('06_incremental_information','相同33,726个个人月、9,037名真人，设计权重按月份归一化。所有R²均为样本内描述性WLS，不是预测成绩。月份固定效应属于事后控制，不作为未来输入。')}
<p>模拟单独R²为{100*reg['fits']['simulation_only']['r2']:.2f}%，上期单独为{100*reg['fits']['lag_only']['r2']:.2f}%。在历史常态/次数、人口与月份共同因素之后加入模拟，R²从{100*reg['fits']['past_history_P_month']['r2']:.3f}%升至{100*reg['fits']['past_history_P_month_plus_simulation']['r2']:.3f}%，仅增加<strong>{100*reg['incremental_r2']:.3f}个百分点</strong>；对原残余解释约{100*reg['partial_r2']:.3f}%。这是条件增量较小的证据，不是单凭共线性或一个不显著系数作判断。</p>
<details><summary>回归系数怎样解释？</summary><p>加入模拟后的模拟系数约{reg['coefficients']['simulation']:.3f}；历史常态相对上期的差值系数约{reg['coefficients']['history_gap']:.3f}。本模型同时放入上期与“常态−上期”，展开后上期系数为{reg['coefficients']['lag']-reg['coefficients']['history_gap']:.3f}、常态系数为{reg['coefficients']['history_gap']:.3f}，不能直接把原上期系数当行为权重。答题次数系数{reg['coefficients']['history_n']:.3f}pp/次是条件关联，不能证明老手更关注通胀。未给出假定人月独立的标准误或显著性星号。</p></details>
<h2 id="limits">六、验收、边界与下一阶段</h2>
<ul><li>1476项逐月指标与冻结结果相符；本轮未发现需要更改口径或机制的实现bug。</li><li>技术补齐前后同支持中心MAE变化{f(s['technical_sensitivity']['main_and_repaired_q9_mae_difference_pp'],5)}pp；全国MAE由{f(s['technical_sensitivity']['original_national']['mae_pp'])}到{f(national_metrics['model']['mae_pp'])}pp。技术修复未改变主要判断。</li><li>剩余两份不再请求；其可能取值对相应月中位数的保守范围见下表。此表固定其余模型值和当前有效真人支持，不是对答案作填补。</li></ul>
{table(['月份','字段','未成功数','该月权重占比','所有可能补值下的中位数范围（%）'],bound_rows)}
<p>固定其他模型回答和当前支持，剩两份任意补值造成的同支持Q9中心MAE变动上界约{f(check['maximum_core_q9_mae_change_bound_pp'],6)}pp，不能解释模型与基线的主要差距。</p>
<p class="note">累计API报告费<strong>${s['scope']['reported_cost_usd']:.4f}</strong>，含未知失败费用预留记账${s['scope']['accounted_including_unknown_reservations_usd']:.4f}，不是额外扣费。本轮分析费用$0；不再补这两份。</p>
<ol><li>固定现有配置和这份历史证据；报告同时呈现全期不足与后期收益，不再追逐已看月份调参。</li><li>准备2025-11至2026-09近期阶段：先核P/E历史可得版本、合成起点和全国锚。当前82月属于A条件重建，不能直接宣称严格B预测成功。</li><li>完善研究包、复算命令和报告：原始/技术补齐分开，许可与发布范围明确；近期无微观真值月先只评全国指标。</li></ol>
<p class="muted">本报告的48/34月划分是组合权重的时间外评价。部分月份曾参与机制开发，既有模型知识污染边界仍在；单次主生成无法估计LLM重复生成噪声，技术补跑不提供独立重复样本。</p>
<footer>来源：最终six_repair_v1的evaluation/readout，冻结分析声明analysis_sources.json；详细来源哈希与复算见manifest.json。生成于{datetime.now(timezone.utc).isoformat()}。本页仅聚合统计，不含个人记录、密钥或原始问卷文本。</footer>
</main></body></html>'''
    (out/'index.html').write_text(text)
    # Public aggregate mirror: no person identifiers or raw responses.
    dump(out/'summary.json',s)
    small=dict(title='SCE全时段重建结果',scope=dict(months=82,n_per_month=512,person_months=41984,
        q9_valid=s['primary_support']['q9'],genuine_q9=s['primary_support']['genuine_q9'],api_cost=s['scope']['reported_cost_usd']),
        all=national_metrics,years=s['yearly'],periods=s['periods'],
        national=[dict(month=r['month'],human=r['truth_pp'],model=r['sim_pp'],past=r['anchor_pp']) for r in national],
        micro=[dict(month=str(r['month']),model_w1=r['model']['cross_section_w1_pp'],past_w1=r['past']['cross_section_w1_pp'],
             human_iqr=r['model']['real_cross_person_iqr_pp'],model_iqr=r['model']['cross_person_iqr_pp'],past_iqr=r['past']['cross_person_iqr_pp']) for r in monthly],
        groups=[dict(dimension=g['dimension'],label=LABELS.get(g['label'],g['label']),n=g['person_months'],eligible_months=g['eligible_months'],metrics=g['eligible_metrics'])
                for g in s['groups'] if g['dimension']!='stratum' and g['eligible_months']>0],
        regression=s['regression'],updates=s['update_summary'],combination=s['official_national']['chronological_combinations'])
    dump(out/'canvas_data.json',small)
    files=[source/'summary.json',Path(__file__),ROOT/'scripts/report_sce_fullperiod_run.py']
    dump(out/'manifest.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in files},
         output_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()},new_api_calls=0,new_q9_fits=0))
    return dict(status='report_complete',report=str(out/'index.html'),new_api_calls=0)
