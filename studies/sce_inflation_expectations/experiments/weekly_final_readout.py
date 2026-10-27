"""Reproducible offline audit and readable analysis of completed weekly SCE.

Read existing 47 sealed checkpoints and the frozen national evaluation only.
No generation client is instantiated, no parameters are selected or refitted.
"""
from collections import Counter
import csv
import json
import math
from pathlib import Path
import shutil

from . import weekly_evaluation as ev
from . import weekly_terminal as runtime
from . import frozen_message_queue as queue
from .weekly_partial_readout import normalized_point
from .frozen_batch import ROOT, read_json as read, dump, sha
from ..evaluation.metrics import distribution_summary, headline_errors
from ..submission_tools.reproduce import no_network

B_RUN=ROOT/'outputs/sce_recent_b_sampled_terminal_20261026_v1'
MONTHLY_RECURSION=ROOT/'docs/workstreams/20261026_belief_recursion/monthly_aggregate_readout.json'
GROUPS=('education_group','numeracy','age_group','household_income_band')


def primary_rows(rows):
    if len(rows)!=47 or len({r['step_key'] for r in rows})!=47:
        raise ValueError('47 unique weekly points required')
    selected=[r for r in rows if r['main_score_point'] in (True,'True')]
    if (len(selected)!=11 or len({r['target_reference_period'] for r in selected})!=11
            or {r['target_reference_period'] for r in selected}!={r['target_reference_period'] for r in rows}):
        raise ValueError('Exactly one primary point per each of 11 target months required')
    return selected


def _csv(path,rows):
    with path.open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def _close(left,right):
    if not math.isclose(float(left),float(right),rel_tol=0,abs_tol=1e-9):
        raise ValueError(f'Independent checkpoint/CSV/statistic mismatch: {left} vs {right}')


def analyze(folder,out):
    folder,out=Path(folder).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh outputs destination required')
    with no_network():
        protocol,package_manifest=runtime.checked(folder)
        generation=read(folder/'generation_receipt.json')
        if generation['status']!='weekly_generation_complete' or generation.get('actual_model_results') is not True:
            raise ValueError('Completed actual 47-week generation required')
        evaluation=folder/'evaluation';score=read(evaluation/'summary.json')
        evaluation_manifest=read(evaluation/'manifest.json')
        runtime._validate_files(ROOT,evaluation_manifest['source_sha256'])
        runtime._validate_files(evaluation,evaluation_manifest['files_sha256'])
        sources=dict(evaluation_manifest['source_sha256'])
        sources[str((evaluation/'manifest.json').relative_to(ROOT))]=sha(evaluation/'manifest.json')
        sources[str((evaluation/'compatibility_receipt.json').relative_to(ROOT))]=sha(evaluation/'compatibility_receipt.json')
        if (folder/'key_limit_resume_20261027/appendix_private.json').exists():
            from .weekly_key_limit_resume import validate
            validate(folder)
            sources[str((folder/'key_limit_resume_20261027/appendix_private.json').relative_to(ROOT))]=sha(folder/'key_limit_resume_20261027/appendix_private.json')
        inputs=ROOT/protocol['inputs'];plan=[normalized_point(p) for p in read(inputs/'weekly_plan.json')]
        weights=read(inputs/'weights_private.json');ids=sorted(weights)
        population=read(inputs/'population_private.json')
        profiles={r['agent_id']:r['attributes'] for r in population['personas']}
        cycles=read(inputs/'priors/cycles_private.json')
        raw_rows=list(csv.DictReader((evaluation/'weekly_national.csv').open()))
        selected=primary_rows(raw_rows)
        if len(ids)!=300 or set(profiles)!=set(ids):raise ValueError('Fixed 300-household roster required')
        row_by_key={r['step_key']:r for r in raw_rows};previous={};previous_cutoff=None;cache={}
        audit_stages={stage:Counter() for stage in ('main','repair')};errors={stage:Counter() for stage in audit_stages}
        totals=Counter();reported=reserved=0.;retained=Counter();retained_weight=Counter()
        descriptive=[];group_rows=[];checkpoint_receipts=[];budget_denied_key=None;budget_denied_repaired=False
        for p in plan:
            states,receipt=runtime.sealed(folder,p);checkpoint_receipts.append(receipt)
            if receipt.get('actual_model_results') is not True or set(states)!=set(ids):
                raise ValueError('Actual fixed identity checkpoint required')
            wave=folder/'waves'/p['step_key']
            expected=runtime.state_before(previous,cycles[p['cycle_key']]['states'],p,previous_cutoff)
            if read(wave/'states_before_private.json')!=expected:raise ValueError('Same-person predecessor mismatch')
            values={a:ev._state_center(states[a],cache) for a in ids}
            if any(ev.aware(s['fields'][f]['source_at'])>ev.aware(p['cutoff']) for s in states.values() for f in ('q8','q9')):
                raise ValueError('Future field source in sealed state')
            summary=distribution_summary([values[a] for a in ids],[weights[a] for a in ids])
            row=row_by_key[p['step_key']]
            for field,field2 in (('median_pp','sim_median_pp'),('iqr_pp','sim_iqr_pp'),('ess','sim_ess')):
                _close(summary[field],row[field2])
            q8=distribution_summary([states[a]['fields']['q8']['value'] for a in ids],[weights[a] for a in ids])
            descriptive.append(dict(step_key=p['step_key'],cutoff=p['cutoff'],month=p['target_reference_period'],
                q8_median_pp=q8['median_pp'],q9_median_pp=summary['median_pp'],q9_iqr_pp=summary['iqr_pp'],
                q9_std_pp=summary['std_pp'],reset_required=p['reset_required']))
            for dimension in GROUPS:
                for level in sorted({str(profiles[a].get(dimension) or 'unknown') for a in ids}):
                    members=[a for a in ids if str(profiles[a].get(dimension) or 'unknown')==level]
                    stats=distribution_summary([values[a] for a in members],[weights[a] for a in members])
                    group_rows.append(dict(step_key=p['step_key'],cutoff=p['cutoff'],dimension=dimension,level=level,
                        n=len(members),ess=stats['ess'],weight_share=sum(weights[a] for a in members)/sum(weights.values()),
                        simulated_median_pp=stats['median_pp'],simulated_iqr_pp=stats['iqr_pp'],
                        low_support=stats['ess']<10))
            for f in ('q8','q9'):
                lost=[a for a in ids if not states[a]['steps'][-1]['field_updated_from_model'][f]]
                if len(lost)!=receipt['remaining_fields'][f]:raise ValueError('Fallback provenance count mismatch')
                retained[f]+=len(lost);retained_weight[f]+=sum(weights[a] for a in lost)
            for stage in ('main','repair'):
                intents,replies=queue.archive(wave/stage);acc=queue.account(intents,replies)
                audit_stages[stage].update({k:acc[k] for k in ('attempts','completed','usable','unresolved')})
                if stage=='main' and len(intents)!=300:raise ValueError('Weekly primary dispatch count differs from 300')
                reported+=acc['reported_cost_usd'];reserved+=acc['spent_or_reserved_usd']
                for reply in replies:
                    if reply.get('error'):errors[stage][reply['error']]+=1
                    elif (reply.get('returned_model')!=protocol['model']
                          or reply.get('returned_provider')!=protocol['expected_provider']):
                        raise ValueError('Actual model/provider differs from frozen route')
                    if stage=='main' and reply.get('error_http_status')==403:budget_denied_key=reply['key']
                    if stage=='repair' and reply['key']=='repair1|'+str(budget_denied_key):
                        budget_denied_repaired=all(queue.fields(reply).values())
                    if not reply.get('error') and not all(queue.fields(reply).values()):
                        audit_stages[stage]['normal_response_invalid_fields']+=1
                totals.update({k:acc[k] for k in ('attempts','completed','unresolved')})
            previous,previous_cutoff=states,p['cutoff']
        for k in ('reported_cost_usd','spent_or_reserved_usd'):
            _close(generation[k],reported if k=='reported_cost_usd' else reserved)
        if totals['attempts']!=generation['physical_attempts'] or totals['unresolved']:
            raise ValueError('Generation physical/unknown dispatch accounting mismatch')
        by_score={r['target_reference_period']:r for r in score['primary_monthly_points']}
        monthly=[]
        for row in selected:
            r=by_score[row['target_reference_period']]
            _close(row['sim_median_pp'],r['forecast_pp']);_close(row['target_release_value_pp'],r['truth_pp'])
            item=dict(month=r['target_reference_period'],cutoff=r['cutoff'],truth_pp=r['truth_pp'],
                raw_pp=r['forecast_pp'],anchor_pp=r['baseline_pp'],held_prior_pp=float(row['cycle_prior_median_pp']),
                blend_pp=float(row['fixed_A_early48_MSE_blend_pp']),macro_pp=float(row['macro_without_sim_pp']),
                macro_sim_pp=float(row['macro_plus_sim_pp']),actual_lead_days=r['actual_lead_days'],
                predicted_direction=r['predicted_direction'],actual_direction=r['actual_direction'],
                anomaly=r['evaluation_only_anomaly'],month_change_pp=r['target_month_change_pp'])
            for label in ('raw','anchor','held_prior','blend','macro','macro_sim'):
                item[label+'_error_pp']=item[label+'_pp']-item['truth_pp']
                item[label+'_abs_error_pp']=abs(item[label+'_error_pp'])
            monthly.append(item)
        primary=score['evaluation']['last_week_in_month']
        for label,registered in (('raw','raw_model'),('anchor','public_SCE_persistence'),
                                 ('held_prior','same_cycle_fixed_joint_prior'),('blend','fixed_A_early48_MSE_blend'),
                                 ('macro','macro_without_sim'),('macro_sim','macro_plus_sim')):
            computed=headline_errors([r[label+'_pp'] for r in monthly],[r['truth_pp'] for r in monthly])
            for metric in ('mae_pp','rmse_pp','bias_pp','max_absolute_error_pp'):_close(computed[metric],primary[registered][metric])
        differences=[r['raw_abs_error_pp']-r['anchor_abs_error_pp'] for r in monthly]
        leave_one_out=[dict(excluded_month=r['month'],raw_minus_persistence_MAE_pp=sum(differences[:i]+differences[i+1:])/10)
                       for i,r in enumerate(monthly)]
        main_direction=dict(n=11,correct=sum(r['predicted_direction']==r['actual_direction'] for r in monthly),
                            always_flat_correct=sum(r['actual_direction']=='flat' for r in monthly),
                            true_up=sum(r['actual_direction']=='up' for r in monthly),
                            correctly_predicted_up=sum(r['actual_direction']==r['predicted_direction']=='up' for r in monthly),
                            false_up=sum(r['actual_direction']!='up' and r['predicted_direction']=='up' for r in monthly),
                            actual_not_up=sum(r['actual_direction']!='up' for r in monthly))
        anomaly_panels={}
        for flag,label in ((True,'anomaly_3_months'),(False,'other_8_months')):
            subset=[r for r in monthly if r['anomaly']==flag]
            anomaly_panels[label]={name:headline_errors([r[name+'_pp'] for r in subset],[r['truth_pp'] for r in subset])
                                   for name in ('raw','anchor','blend')}
        # Same target months, but these are descriptive cross-configuration
        # comparisons: population, exposure frequency and timing all differ.
        monthly_B=list(csv.DictReader((B_RUN/'evaluation/monthly_national.csv').open()))
        bmap={f"{r['month'][:4]}-{r['month'][4:]}":r for r in monthly_B}
        m=read(MONTHLY_RECURSION);recmap={f"{r['month'][:4]}-{r['month'][4:]}":r for r in m['monthly_national']}
        comparisons={}
        for panel,subset in (('all_11_months',monthly),('post_root_10_months',[r for r in monthly if r['month']!='2025-11'])):
            targets=[r['truth_pp'] for r in subset]
            values={'weekly_raw':[r['raw_pp'] for r in subset],'weekly_blend':[r['blend_pp'] for r in subset],
                    'public_persistence':[r['anchor_pp'] for r in subset],
                    'monthly_B_raw':[float(bmap[r['month']]['sim_pp']) for r in subset],
                    'monthly_B_blend':[float(bmap[r['month']]['frozen_combination_pp']) for r in subset],
                    'autonomous_monthly_raw':[recmap[r['month']]['recursive_pp'] for r in subset],
                    'autonomous_monthly_blend':[recmap[r['month']]['fixed_blend_pp'] for r in subset]}
            comparisons[panel]={label:headline_errors(pred,targets) for label,pred in values.items()}
        audit=dict(status='complete_no_generation_rerun_required',sealed_weeks=47,fixed_households=300,
            logical_household_weeks=14100,main=dict(audit_stages['main']),repair=dict(audit_stages['repair']),
            errors={k:dict(v) for k,v in errors.items()},physical_attempts=totals['attempts'],
            unknown_inflight=totals['unresolved'],never_dispatched_main=0,
            retained_fields=dict(retained),retained_household_weight_sums=dict(retained_weight),
            original_budget_403_repaired=budget_denied_repaired,reported_cost_usd=reported,
            spent_or_reserved_usd=reserved,unknown_fee_reservation_usd=reserved-reported,budget_cap_usd=15,
            state_identity_predecessor_time_hash_audit='passed',new_API_calls=0,
            truth_in_generation=generation['truth_read'],Normal=generation['Normal'],entry_exit=generation['entry_exit'])
        result=dict(schema='sce_weekly_completed_readout/v1',source_run=str(folder.relative_to(ROOT)),
            status='completed_offline_analysis',primary=primary,panels=score['evaluation'],operation=audit,
            raw_MAE_relative_reduction=1-primary['raw_model']['mae_pp']/primary['public_SCE_persistence']['mae_pp'],
            raw_RMSE_relative_reduction=1-primary['raw_model']['rmse_pp']/primary['public_SCE_persistence']['rmse_pp'],
            monthly_wins=sum(d<0 for d in differences),monthly_losses=sum(d>0 for d in differences),
            leave_one_month_out=leave_one_out,direction=main_direction,anomaly_panels=anomaly_panels,
            descriptive_cross_configuration=comparisons,new_API_calls=0,parameter_refit=False,
            limits=score['limits']+['Group medians and IQR describe simulated agents; no real weekly micro accuracy claim.',
                  'Cross-configuration monthly comparisons are not matched-input causal contrasts.',
                  'Last-Friday snapshot differs from a monthly survey-period aggregate; 11 target months, not 47 independent targets.'])
        out.mkdir(parents=True);dump(out/'summary.json',result);dump(out/'operation.json',audit)
        _csv(out/'monthly_primary.csv',monthly);_csv(out/'weekly_descriptive.csv',descriptive)
        _csv(out/'simulated_groups_descriptive.csv',group_rows)
        shutil.copyfile(evaluation/'weekly_national.csv',out/'weekly_national_source.csv')
        render(out,raw_rows,monthly,group_rows,result)
        for source in (Path(__file__),B_RUN/'evaluation/monthly_national.csv',MONTHLY_RECURSION,
                       folder/'worker_receipt.json',inputs/'population_private.json'):
            sources[str(source.relative_to(ROOT))]=sha(source)
        dump(out/'manifest.json',dict(source_sha256=sources,new_API_calls=0,
             files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
        return result


def render(out,weekly,monthly,groups,result):
    from datetime import datetime
    from html import escape
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib import font_manager
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':['Times New Roman','KaiTi SC'],'font.size':11,
                         'axes.spines.top':False,'axes.spines.right':False})
    colors=['#1769aa','#d36b12','#7655a5','#777777']
    dates=[datetime.fromisoformat(r['cutoff']).replace(tzinfo=None) for r in weekly]
    md=[datetime.fromisoformat(r['cutoff']).replace(tzinfo=None) for r in monthly]
    fig,ax=plt.subplots(figsize=(11,4.6),layout='constrained')
    ax.plot(dates,[float(r['sim_median_pp']) for r in weekly],color=colors[0],marker='.',label='周度原始模拟')
    ax.plot(dates,[float(r['anchor_pp']) for r in weekly],color=colors[3],ls='--',label='当时最后公开SCE')
    ax.plot(dates,[float(r['fixed_A_early48_MSE_blend_pp']) for r in weekly],color=colors[1],label='A冻结权重组合')
    ax.scatter(md,[r['truth_pp'] for r in monthly],color='#151515',s=34,zorder=5,label='月度SCE真值')
    for d,r in zip(dates,weekly):
        if r['reset_required']=='True':ax.axvline(d,color='#cccccc',lw=.6,zorder=0)
    ax.set(title='47周固定家庭状态链：发布间递推，发布后校准',xlabel='周截止日（纽约时间）',ylabel='未来12个月通胀预期（%）')
    ax.legend(loc='upper left',ncol=2,fontsize=9);ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'weekly_path.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout='constrained');xs=list(range(11))
    for offset,label,title,color in ((-.24,'raw','原始模拟',colors[0]),(0,'anchor','持续性',colors[3]),(.24,'blend','冻结组合',colors[1])):
        axes[0].bar([x+offset for x in xs],[r[label+'_abs_error_pp'] for r in monthly],width=.22,color=color,label=title)
    axes[0].set_xticks(xs,[r['month'][2:] for r in monthly],rotation=50)
    axes[0].set(title='11个月主口径绝对误差',xlabel='调查月份',ylabel='绝对误差（pp）');axes[0].legend(fontsize=8)
    axes[1].plot(xs,[r['raw_error_pp'] for r in monthly],marker='o',color=colors[0])
    axes[1].axhline(0,color=colors[3],ls='--',lw=1)
    axes[1].set_xticks(xs,[r['month'][2:] for r in monthly],rotation=50)
    axes[1].set(title='原始模拟：从高估到9月低估',xlabel='调查月份',ylabel='模拟−SCE（pp）')
    for ax in axes:ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'monthly_errors.png',dpi=170);plt.close(fig)
    labels={'education_group':'学历','numeracy':'数理能力','age_group':'年龄','household_income_band':'收入'}
    names={'college':'大学','some_college':'部分大学','high_school':'高中及以下','high':'高','low':'低',
           'Under 40':'40岁以下','40 to 60':'40—60岁','Over 60':'60岁以上',
           'under_50k':'低于5万美元','50k_to_100k':'5—10万美元','over_100k':'高于10万美元','unknown':'未知'}
    fig,axes=plt.subplots(2,2,figsize=(11,7),layout='constrained')
    for ax,dimension in zip(axes.flat,GROUPS):
        levels=sorted({r['level'] for r in groups if r['dimension']==dimension})
        for i,level in enumerate(levels):
            data=[r for r in groups if r['dimension']==dimension and r['level']==level]
            if data[0]['low_support']:
                continue  # Preserve in CSV, avoid giving one-person noise a full plot line.
            ax.plot(dates,[r['simulated_median_pp'] for r in data],color=colors[i%4],
                    ls='--' if level=='unknown' else '-',label=f"{names.get(level,level)}（n={data[0]['n']}，ESS={data[0]['ess']:.0f}）")
        ax.set(title=labels[dimension]+'分组：仅描述模拟差异',xlabel='周截止日',ylabel='组内Q9中位数（%）')
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3));ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.legend(fontsize=8);ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'groups_descriptive.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
    for ax,month,title in zip(axes,('2026-03','2026-09'),('3月：提前反应，幅度过大','9月：未捕捉上行')):
        data=[r for r in weekly if r['target_reference_period']==month]
        x=[datetime.fromisoformat(r['cutoff']).replace(tzinfo=None) for r in data]
        truth=next(r['truth_pp'] for r in monthly if r['month']==month)
        ax.plot(x,[float(r['sim_median_pp']) for r in data],marker='o',color=colors[0],label='周度原始模拟')
        ax.plot(x,[float(r['anchor_pp']) for r in data],ls='--',color=colors[3],label='当时公开SCE')
        ax.axhline(truth,color='#151515',label='当月SCE（事后评价）')
        ax.set(title=title,xlabel='周截止日',ylabel='通胀预期（%）');ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.set_xticks(x);ax.legend(fontsize=8);ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'turning_points.png',dpi=170);plt.close(fig)
    p=result['primary'];audit=result['operation'];direction=result['direction']
    metric_rows=''.join(f"<tr><td>{name}</td><td>{p[key]['mae_pp']:.4f}</td><td>{p[key]['rmse_pp']:.4f}</td><td>{p[key]['bias_pp']:+.4f}</td></tr>"
          for key,name in (('raw_model','原始周度模拟'),('public_SCE_persistence','当时公开SCE持续性'),
          ('same_cycle_fixed_joint_prior','同周期合成先验保持不动'),('fixed_A_early48_MSE_blend','A早48月冻结组合'),
          ('macro_without_sim','冻结SCE+CPI'),('macro_plus_sim','冻结SCE+CPI+模拟')))
    monthly_rows=''.join(f"<tr><td>{r['month']}</td><td>{r['truth_pp']:.3f}</td><td>{r['raw_pp']:.3f}</td>"
          f"<td>{r['raw_abs_error_pp']:.3f}</td><td>{r['anchor_abs_error_pp']:.3f}</td><td>{r['blend_abs_error_pp']:.3f}</td></tr>" for r in monthly)
    horizons=''.join(f"<tr><td>{label}</td><td>{value['raw_model']['mae_pp']:.4f}</td><td>{value['fixed_A_early48_MSE_blend']['mae_pp']:.4f}</td></tr>"
          for label,value in (('每月最后周点（主）',result['panels']['last_week_in_month']),
          ('至少提前14天',result['panels']['at_least_14_days_before_release']),('至少提前21天',result['panels']['at_least_21_days_before_release'])))
    comparison=result['descriptive_cross_configuration']['post_root_10_months']
    comparison_rows=''.join(f"<tr><td>{name}</td><td>{comparison[a]['mae_pp']:.4f}</td><td>{comparison[b]['mae_pp']:.4f}</td></tr>"
          for name,a,b in (('独立逐月B','monthly_B_raw','monthly_B_blend'),
          ('月度自主递推','autonomous_monthly_raw','autonomous_monthly_blend'),('本次周度发布后校准','weekly_raw','weekly_blend')))
    html=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>SCE周度实验完整结果</title>
<style>body{{max-width:1120px;margin:30px auto;padding:0 24px;background:#fafbfd;color:#26313d;font:18px/1.8 "Times New Roman","KaiTi SC",KaiTi,serif}}h1{{font-size:29px}}h2{{font-size:23px;margin-top:36px}}p{{text-indent:2em}}.lead{{background:#eaf2f8;padding:16px 22px;border-left:4px solid #1769aa}}.caption{{font-size:15px;color:#5e6c79}}img{{width:100%;background:white}}table{{border-collapse:collapse;width:100%;background:white;margin:18px 0}}td,th{{padding:8px;border-bottom:1px solid #dce2e9;text-align:right}}td:first-child,th:first-child{{text-align:left}}a{{color:#1769aa}}nav{{font-size:16px}}@media print{{body{{font-size:12pt}}}}</style>
<h1>周度模拟完整读数：有总体增量，仍会漏掉转折</h1>
<nav><a href="#main">主结果</a> · <a href="#months">逐月差异</a> · <a href="#leads">提前量</a> · <a href="#compare">与月度对照</a> · <a href="#micro">模拟人群结构</a> · <a href="#run">运行核查</a></nav>
<div class="lead">47周、固定300户、11个目标月全部完成。主口径原始MAE <b>0.1516pp</b>，持续性 <b>0.1727pp</b>，降低<b>12.2%</b>；RMSE降低{100*result['raw_RMSE_relative_reduction']:.1f}%。不是47个独立真实观测，也不是已验证的真人周度结构重建。</div>
<h2 id="main">1. 这轮研究了什么，主指标表现怎样</h2>
<p>固定同一批300个代理家庭，以2025年1月旧人口框架为基础，从2025年11月7日至2026年9月25日每周五作答。新的历史SCE公开后，用合格匿名联合供体对齐已公开过去指标；两次公开之间传递本人上周模拟Q8/Q9和周期内历史。新闻在当时可见窗口内逐周增加、跨周去重；没有Normal，没有受访者进出。模型为OpenRouter→SiliconFlow FP8的DeepSeek V3.2、温度0.5、关闭思考、JSON直接回答。每月新闻额度4/8/16/32篇、CPI相关度1.5、警示倍数1，参数未因途中结果调整。</p>
<p>逐人Q9十档概率经冻结算法拟合连续密度并取均值，再计算跨家庭的设计加权中位数。真实SCE只有月度值，因此预先约定每个调查月最后一个周点为主预测，11个月等权评价。以下所有方法在相同11个月比较：MAE衡量通常偏差，RMSE对大偏差更敏感，偏差为“预测减真值”。</p>
<table><thead><tr><th>方法</th><th>MAE / pp</th><th>RMSE / pp</th><th>偏差 / pp</th></tr></thead><tbody>{metric_rows}</tbody></table>
<p>同周期合成先验保持不动的MAE为0.1706，加入模型周内更新后降至0.1516，说明结果不只是复制校准锚的机械产物。冻结组合的模拟权重仍为13.3976%，MAE0.1564，略高于原始模拟；RMSE0.1884略低于原始0.1889。不能根据这11个月重新挑选权重。宏观模型加入模拟的MAE由0.1609降至0.1502，但相对原始模拟的差距很小。</p>
<img src="weekly_path.png" alt="47周模拟、固定组合、公开锚和11个月SCE真值"><div class="caption">来源：原运行47份封存检查点与冻结评价CSV。细竖线表示新公开SCE引起的先验重置；黑点为月度调查真值，显示在对应主周点，不能解读为真人周度观测。</div>
<h2 id="months">2. 平均改善来自哪里，又在哪里失败</h2>
<p>11个月中仅5个月优于持续性、6个月落后；平均误差仍然下降，是因为若干改善月节省的绝对误差较大，并非多数月份都赢。逐一删去任意一个月份后，平均MAE差仍为负（约−0.0063至−0.0335pp），说明当前总收益不是由单独一个月决定；这不替代小样本统计显著性检验。</p>
<p>3月捕捉到上行方向但反应过大；4月接近真值；5—7月部分高估；8月接近但落后于恰好不变的持续性。9月是最明显的遗漏：预测3.498%、SCE3.9%，低估0.402pp，高于基线0.3pp。这也使完整11个月MAE从前8个月的0.1365升至0.1516。</p>
<img src="monthly_errors.png" alt="11个月原始、基线、组合误差及模拟偏差"><div class="caption">相同11个目标月，各月等权；单位pp。误差符号不能与通胀高低混淆：负值表示模型低估受访者预期。</div>
<table><thead><tr><th>月份</th><th>SCE / %</th><th>模拟 / %</th><th>原始误差 / pp</th><th>基线误差 / pp</th><th>组合误差 / pp</th></tr></thead><tbody>{monthly_rows}</tbody></table>
<h2 id="leads">3. 有提前信息，但还不能称可靠预警器</h2>
<p>按调用前固定的±0.1pp容忍带，主点方向正确{direction['correct']}/11，其中5个月本来处于平稳带。真实上行有5个月，正确判上行3个月、漏掉12月、9月，其中9月还判成下降；没有出现错误上行警报（0/6个非上行月）。三个“大幅变化月”（绝对月变动≥0.3pp）中，1月、3月方向正确，9月失败。只有3个异常月，不能泛化为异常期稳定有效。</p>
<img src="turning_points.png" alt="3月和9月周度更新与月度真实指标对比"><div class="caption">3月13日模拟已升至3.510%，公开锚为3.0%，目标3月SCE于4月7日才发布；这是约25天提前的上行信号，也包含幅度高估。9月11—25日模拟约3.50%，没有捕捉到目标3.9%的上升。事件归因尚未识别。</div>
<table><thead><tr><th>预定评分点</th><th>原始MAE / pp</th><th>固定组合MAE / pp</th></tr></thead><tbody>{horizons}</tbody></table>
<p>至少21天面板的原始MAE0.1323较低，但三个面板复用同11个月，不能当成三次独立验证，也不以更好结果替换月末主指标。月末周点距离目标发布7—13天。这里只能说明特定回顾性样本具有一定提前信息，尚不能证明越早预测越好。</p>
<h2 id="compare">4. 与已有月度方案怎样比较</h2>
<p>下表统一使用2025年12月至2026年9月的10个月，排除月度自主递推复用的共同首月，持续性MAE为0.1900。不同方案的人口框架、新闻增量、观察时点及初始化方式不全相同，因此是描述性对照，不能把差距全归因于“按周递推”或“发布后校准”。</p>
<table><thead><tr><th>方案（相同后10个月）</th><th>原始MAE / pp</th><th>固定组合MAE / pp</th></tr></thead><tbody>{comparison_rows}</tbody></table>
<p>周度原始序列比旧月度自主链更接近SCE，并未呈现相同的持续单向高估；但这不是没有误差累积的证明，重置、环境与更新频率同时变化。原独立逐月B的组合指标仍好于本次周度组合，不存在“周度所有指标全面优胜”。可以将周度作为高频观测与更新节奏的拓展，而非替代所有主线结果。</p>
<h2 id="micro">5. 人群差异性：可观察模拟结构，不能验证真人结构</h2>
<img src="groups_descriptive.png" alt="学历、数理、年龄和收入四类模拟分组的周度中位数"><div class="caption">组线是固定代理家庭的组内设计加权中位数；n为真实LLM代理数，ESS为权重有效样本量。低ESS（小于10）不画线，完整数值仍在CSV；学历未知仅1户，收入未知仅2户。没有近期真人同组真值，不能根据这些曲线判断哪个人群拟合更好，也不能把组差当成人口特征因果效应。</div>
<p>跨人IQR、标准差与Q8仅作模拟结构描述。300户反复47周不等于14,100个独立居民；在缺少真人周度微观资料时，不计算W1准确性或个人预测命中率。新闻和模型的历史文本、知识边界沿原协议保留，因此仍称回顾性时点模拟，不称当时实际封存的事前预测。</p>
<h2 id="run">6. 运行是否完整，是否需要重跑</h2>
<p>14,100主请求＋28次一次补跑＝14,128物理尝试，47周均封存，未发送和未知在途均为0。原额度403已经通过绑定原记录的一次补跑修复；没有放宽所有403。实报费用${audit['reported_cost_usd']:.4f}，未知费用预留${audit['unknown_fee_reservation_usd']:.4f}，计及预留${audit['spent_or_reserved_usd']:.4f}，低于原$15上限。主批与补批、前后段费用只累计一次。</p>
<p>Q8与Q9各只有2个户周在一次补跑后仍保留本人旧字段，占14,100户周约0.014%。它们已进入后继状态；按预先约定显式保留，建议不为完整率回写旧轨迹。身份、前驱、字段时间、原始账本与评价来源哈希，以及主指标独立复算均通过。没有需要新API修复的阻断问题，本次整理新增模型调用为0。</p>
<p>下一步可将完整11个月结果纳入报告与研究包：主指标用0.1516pp，保留固定组合、宏观对照、9月漏报及微观不可评价边界。前8个月阶段性读数保持原样，不替换成全期结论。<a href="summary.json">全部统计</a> · <a href="monthly_primary.csv">11个月CSV</a> · <a href="weekly_descriptive.csv">47周结构CSV</a> · <a href="simulated_groups_descriptive.csv">模拟分组CSV</a> · <a href="operation.json">运行对账</a></p></html>'''
    (out/'index.html').write_text(html,encoding='utf-8')
