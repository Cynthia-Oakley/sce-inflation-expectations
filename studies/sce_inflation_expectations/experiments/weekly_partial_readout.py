"""Offline readout of immutable weekly checkpoints, without completing a run.

This is deliberately separate from the frozen final evaluator. An incomplete
calendar month never becomes a primary score point merely because a run stops.
"""
from collections import Counter
import csv
import json
from pathlib import Path

from . import weekly_evaluation as ev
from . import weekly_terminal as run
from . import frozen_message_queue as queue
from .frozen_batch import ROOT, read_json as read, dump, sha
from ..evaluation.metrics import distribution_summary, headline_errors
from ..submission_tools.reproduce import no_network


def normalized_point(point):
    """Normalize the actual compact execution plan, without changing it."""
    result = dict(point)
    period = ev.aware(point['cutoff']).astimezone(ev.NY).strftime('%Y-%m')
    if point.get('month', period.replace('-', '')) != period.replace('-', ''):
        raise ValueError('Execution month differs from New York cutoff month')
    if point.get('target_reference_period', period) != period:
        raise ValueError('Target month differs from New York cutoff month')
    reference, publication = point['cycle_key'].split('|')
    if reference != point['anchor_reference_period']:
        raise ValueError('Cycle/public anchor mismatch')
    result.setdefault('target_reference_period', period)
    result.setdefault('anchor_published_date', publication)
    return result


def completed_primary_points(plan, sealed_keys):
    """Use the last scheduled point of a fully sealed calendar month."""
    groups = {}
    for point in plan:
        groups.setdefault(point['target_reference_period'], []).append(point)
    return [max(points, key=lambda p: p['cutoff'])
            for points in groups.values()
            if all(p['step_key'] in sealed_keys for p in points)]


def _csv(path, rows):
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def _render(out, rows, monthly, result):
    """Small scientific figures and the established local HTML report format."""
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
    dates=[datetime.fromisoformat(r['cutoff']).replace(tzinfo=None) for r in rows]
    md=[datetime.fromisoformat(r['cutoff']).replace(tzinfo=None) for r in monthly]
    fig,ax=plt.subplots(figsize=(11,4.6),layout='constrained')
    ax.plot(dates,[r['sim_median_pp'] for r in rows],color='#1769aa',marker='.',label='周度原始Q9模拟')
    ax.plot(dates,[r['anchor_pp'] for r in rows],color='#777777',ls='--',label='当时最后公开SCE')
    ax.plot(dates,[r['fixed_blend_pp'] for r in rows],color='#d36b12',label='固定组合（模拟权重13.40%）')
    ax.scatter(md,[r['truth_pp'] for r in monthly],color='#151515',s=38,zorder=5,label='月度SCE真值（非周度真值）')
    for d,r in zip(dates,rows):
        if r['reset_required']:ax.axvline(d,color='#cccccc',lw=.6,zorder=0)
    ax.set(title='已封存35周：公开锚校准与周内信念更新',xlabel='周截止日（纽约时间）',ylabel='未来12个月通胀预期（%）')
    ax.legend(loc='upper left',ncol=2,fontsize=9);ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'weekly_path.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    xs=list(range(len(monthly)))
    for offset,field,label,color in ((-.24,'raw_abs_error_pp','周度原始模拟','#1769aa'),
                                   (0,'baseline_abs_error_pp','持续性基线','#888888'),
                                   (.24,'blend_abs_error_pp','固定组合','#d36b12')):
        axes[0].bar([x+offset for x in xs],[r[field] for r in monthly],width=.22,label=label,color=color)
    axes[0].set_xticks(xs,[r['target_reference_period'][2:] for r in monthly],rotation=40)
    axes[0].set(title='每月最后周点的绝对误差',xlabel='调查月份',ylabel='绝对误差（pp）');axes[0].legend(fontsize=8)
    axes[1].plot(dates,[r['sim_iqr_pp'] for r in rows],color='#1769aa')
    axes[1].set(title='模拟家庭之间的Q9均值IQR',xlabel='周截止日',ylabel='模拟四分位距（pp；仅描述）')
    axes[1].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    for ax in axes:ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'errors_and_dispersion.png',dpi=170);plt.close(fig)
    metrics=result['metrics'];audit=result['operation']
    table=''.join(f"<tr><td>{escape(r['target_reference_period'])}</td><td>{r['truth_pp']:.3f}</td>"
                  f"<td>{r['sim_median_pp']:.3f}</td><td>{r['raw_abs_error_pp']:.3f}</td>"
                  f"<td>{r['baseline_abs_error_pp']:.3f}</td><td>{r['blend_abs_error_pp']:.3f}</td></tr>" for r in monthly)
    metric_table=''.join(f"<tr><td>{label}</td><td>{metrics[key]['mae_pp']:.4f}</td>"
                         f"<td>{metrics[key]['rmse_pp']:.4f}</td><td>{metrics[key]['bias_pp']:+.4f}</td></tr>"
                         for key,label in (('raw','原始周度模拟'),('public_persistence','当时公开SCE持续性'),
                         ('same_cycle_prior','同周期合成先验保持不动'),('fixed_blend','固定A早48月MSE组合'),
                         ('macro_without_sim','冻结SCE+CPI'),('macro_plus_sim','冻结SCE+CPI+模拟')))
    html=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>周度模拟：中途停止与已完成部分分析</title>
<style>body{{max-width:1100px;margin:35px auto;padding:0 22px;color:#26313d;background:#fafbfd;font:18px/1.75 "Times New Roman","KaiTi SC",KaiTi,serif}}h1{{font-size:29px}}h2{{margin-top:32px;font-size:23px}}p{{text-indent:2em}}.notice{{padding:15px 20px;background:#fff0d8;border-left:4px solid #d36b12}}img{{width:100%;background:white}}table{{width:100%;border-collapse:collapse;margin:15px 0;background:white}}th,td{{text-align:right;padding:8px;border-bottom:1px solid #dce2e9}}th:first-child,td:first-child{{text-align:left}}.caption{{font-size:15px;color:#586673}}a{{color:#1769aa}}code{{font-size:14px}}@media print{{body{{font-size:12pt}}}}</style>
<h1>周度模拟：35周已完成，8个完整月份的阶段性结果</h1>
<div class="notice">本批尚未完成：35/47周已封存，停止于2026-07-10。这里不把7月3日冒充7月月末点，也不报告完整11月成绩。分析新增API调用为0。</div>
<h2>1. 停止情况与数据完整性</h2>
<p>触发停止的是一次HTTP403（PermissionDeniedError）。原始日志没有保存错误正文，不能仅凭错误类区分权限、预算或内容拦截。之后的只读密钥检查确认该key累计额度上限$100、使用约$100.05、剩余0；这与停止相符。上限是整把key的累计限制，并不是这批$15的预算。先提高key限额，再显式处理已登记403与接续；本页没有自动续跑。</p>
<p>主请求已尝试{audit['main_attempted']:,}次，补批{audit['repair_attempted']}次，共{audit['physical_attempts']:,}次物理尝试。还有{audit['never_dispatched_main']:,}个主位置从未发送，没有未知在途请求。费用实报${audit['reported_cost_usd']:.4f}，另有${audit['unknown_fee_reservation_usd']:.4f}未知费用预留；剩余批预算约${audit['remaining_budget_usd']:.2f}。35个封存周通过原始账本哈希、300户固定身份、前驱状态与字段时间检查。Q8、Q9各有2个户周在一次补跑后仍沿用此前字段，未删除个体。</p>
<h2>2. 主指标：每月最后一个预定周点，对比当月SCE</h2>
<p>评价范围为2025-11至2026-06，共8个月。原始模拟MAE为{metrics['raw']['mae_pp']:.4f}pp，持续性为{metrics['public_persistence']['mae_pp']:.4f}pp，下降{100*(1-metrics['raw']['mae_pp']/metrics['public_persistence']['mae_pp']):.1f}%；8个月中有5个月绝对误差更低。同周期先验保持不动的MAE为{metrics['same_cycle_prior']['mae_pp']:.4f}pp，这个对照有助于区分校准本身与校准后的模型更新。</p>
<table><thead><tr><th>方法（相同8个月）</th><th>MAE / pp</th><th>RMSE / pp</th><th>平均偏差 / pp</th></tr></thead><tbody>{metric_table}</tbody></table>
<p>固定组合沿用A早48个月冻结的模拟权重{result['fixed_simulation_weight']:.6f}，没有在这8个月重新选权。其MAE高于原始模拟：这段样本中，较小的模拟权重会将有效的变化信号拉回上期值。该现象不能据此改变本批冻结参数，亦不能预断剩余三个月。</p>
<img src="weekly_path.png" alt="已封存35周的模拟、公开锚、固定组合和月度真值"><div class="caption">来源：sce_weekly_terminal_20261027_v1的35份封存检查点。细竖线表示已公开SCE触发的校准周；黑点是月度调查真值，不存在真人周度真值。最后一个点是7月3日，仅描述。</div>
<h2>3. 收益与偏差出现在哪里</h2>
<p>2025年12月、2026年1—4月优于持续性；11月、5月、6月不如持续性。3月预测3.651%、真值3.4%，仍然高估，但比照抄3.0%的误差小；4月预测3.631%、真值3.6%，接近调查中心。6月预测3.972%、真值3.7%，为目前最大的绝对误差0.272pp。8个月有7个月偏高，平均偏差+0.098pp，因此不能只呈现平均收益。</p>
<img src="errors_and_dispersion.png" alt="逐月误差与模拟横截面IQR"><div class="caption">相同8个完整月、月等权、单位pp。IQR是300户模拟Q9均值的横截面四分位距；由于没有真人周度微观资料，不作为微观准确性证据，不计算真人W1。</div>
<table><thead><tr><th>月份</th><th>SCE / %</th><th>模拟 / %</th><th>原始误差 / pp</th><th>持续性误差 / pp</th><th>组合误差 / pp</th></tr></thead><tbody>{table}</tbody></table>
<h2>4. 提前量与解释边界</h2>
<p>主点距目标数据发布有10—13天；至少14天面板的原始MAE为{result['horizons']['at_least_14_days_before_release']['raw']['mae_pp']:.4f}pp，至少21天面板为{result['horizons']['at_least_21_days_before_release']['raw']['mae_pp']:.4f}pp。所有提前量都按全47周原计划先选日期，再检查已完成部分，未按误差选周。三个面板复用相同8个月，不是三批独立证据，不能因21天数值更好就更换主指标。</p>
<p>这是一条固定300户、发布后校准先验、发布之间由本人模拟信念递推的轨迹。没有新旧受访者轮换，也没有Normal扩展。300户不是每月1200个独立受访者。人口和文本版本、模型知识边界沿原协议保留。本次8个月结果优于持续性，但只能称阶段性线索；不得与完整11月的月度方案直接比较成“周度方法优胜”。</p>
<h2>5. 接续与评价工程</h2>
<p>已封存35周不应重跑。两次字段保留已登记且已经影响后继状态，不能随意改写历史。需要接续的是7月10日尚未发送的69个位置及后续11周的3300个位置；已尝试的403不能当作普通网络错误悄悄自动重发，需要单独确认处理方式。</p>
<p>另发现冻结最终评价器假设执行计划含target_reference_period与anchor_published_date，而实际紧凑计划省略了这两个可推导字段。新建兼容入口从纽约截止日与cycle_key补出元数据，原计划、研究输入和冻结评价器均保持不变。该问题影响离线评价启动，不影响已经生成的回答。</p>
<p>错误码说明参考<a href="https://openrouter.ai/docs/api_reference/errors-and-debugging">OpenRouter官方文档</a>；本项目的key限额判断来自额外只读账户查询。完整数字：<a href="summary.json">汇总JSON</a>、<a href="monthly_complete.csv">8月CSV</a>、<a href="weekly_national.csv">35周CSV</a>、<a href="operation.json">运行对账</a>。未新增模型调用、未重新拟合任何参数、未覆盖旧归档。</p></html>'''
    (out/'index.html').write_text(html,encoding='utf-8')


def analyze(folder, out):
    folder, out = Path(folder).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh outputs destination required')
    with no_network():
        protocol, manifest = run.checked(folder)
        inputs = ROOT/protocol['inputs']
        plan = [normalized_point(p) for p in read(inputs/'weekly_plan.json')]
        weights = read(inputs/'weights_private.json')
        cycles = read(inputs/'priors/cycles_private.json')
        keys = {p['step_key'] for p in plan if (folder/'checkpoints'/p['step_key']).is_dir()}
        # Only a contiguous prefix is a legitimate recursively generated path.
        if [p['step_key'] for p in plan if p['step_key'] in keys] != [p['step_key'] for p in plan[:len(keys)]]:
            raise ValueError('Sealed checkpoints are not a contiguous prefix')
        if not keys:
            raise ValueError('No sealed actual checkpoints')
        ids = set(weights)
        if len(ids) != 300 or any(w <= 0 for w in weights.values()):
            raise ValueError('Positive-weight fixed 300-household roster required')
        fixed = ev._public_cycle_summaries(cycles, {p['cycle_key'] for p in plan}, ids, weights)
        rows, sources, cache = [], {}, {}
        previous = {}; previous_cutoff = None
        for point in plan[:len(keys)]:
            states, receipt = run.sealed(folder, point)
            if receipt.get('actual_model_results') is not True or set(states) != ids:
                raise ValueError('Actual complete household checkpoint required')
            wave = folder/'waves'/point['step_key']
            before = read(wave/'states_before_private.json')
            expected = run.state_before(previous, cycles[point['cycle_key']]['states'], point, previous_cutoff)
            if before != expected:
                raise ValueError('Same-household predecessor linkage changed')
            centers = [ev._state_center(states[a], cache) for a in sorted(ids)]
            ww = [weights[a] for a in sorted(ids)]
            summary = distribution_summary(centers, ww)
            q8 = distribution_summary([states[a]['fields']['q8']['value'] for a in sorted(ids)], ww)
            updated = {f: sum(bool(states[a]['steps'][-1]['field_updated_from_model'][f]) for a in ids)
                       for f in ('q8', 'q9')}
            for state in states.values():
                if any(ev.aware(state['fields'][f]['source_at']) > ev.aware(point['cutoff']) for f in ('q8','q9')):
                    raise ValueError('Household field comes from after weekly cutoff')
            row = {k:point[k] for k in ('step_key','cutoff','target_reference_period','cycle_key',
                                       'reset_required','anchor_reference_period','anchor_pp')}
            row.update(sim_median_pp=summary['median_pp'], sim_iqr_pp=summary['iqr_pp'],
                       q8_median_pp=q8['median_pp'], sim_ess=summary['ess'],
                       cycle_prior_median_pp=fixed[point['cycle_key']]['median_pp'],
                       q8_retained_n=300-updated['q8'], q9_retained_n=300-updated['q9'])
            rows.append(row)
            for path in (folder/'checkpoints'/point['step_key']).glob('*.json'):
                sources[str(path.relative_to(ROOT))] = sha(path)
            for path in wave.rglob('manifest.json'):
                sources[str(path.relative_to(ROOT))] = sha(path)
            sources[str((wave/'wave_plan.json').relative_to(ROOT))] = sha(wave/'wave_plan.json')
            previous, previous_cutoff = states, point['cutoff']

        # All saved state/provenance checks precede opening evaluation targets.
        catalog = read(run.CATALOG)
        releases = catalog['headline_releases']
        truths = {r['reference_period']:r for r in releases}
        for release in releases:
            path = ev._verify_catalog_source(release['source_file'],release['source_sha256'])
            sources[str(path.relative_to(ROOT))] = sha(path)
        clocks = ev.schedule([r['cutoff'] for r in rows], releases)
        for row, clock in zip(rows, clocks):
            for field in ('anchor_reference_period','cycle_key','anchor_pp','target_reference_period'):
                if row[field] != clock[field]: raise ValueError('Public release clock mismatch')
        params = read(ev.MACRO_PARAMETERS)
        alpha = params['blends']['mse']['simulation_weight']
        if abs(alpha-ev.REGISTERED_MSE_WEIGHT)>1e-9:
            raise ValueError('Registered A-only frozen blend required')
        overrides, _ = ev._food_catalog_publication_overrides(ev.FOOD_CATALOG, sources)
        by_key = {r['step_key']:r for r in rows}
        for point in plan[:len(keys)]:
            r=by_key[point['step_key']]
            r['fixed_blend_pp']=(1-alpha)*r['anchor_pp']+alpha*r['sim_median_pp']
            a,b=ev._fixed_macro_predictions(point,r['sim_median_pp'],catalog['cpi_first_releases'],params,sources,overrides)
            r['macro_without_sim_pp']=a['prediction_pp'];r['macro_plus_sim_pp']=b['prediction_pp']
        selected=completed_primary_points(plan,keys)
        monthly=[]
        for p in selected:
            r=dict(by_key[p['step_key']]);truth=truths[p['target_reference_period']]['value_pp']
            r['truth_pp']=truth
            for label,field in (('raw','sim_median_pp'),('baseline','anchor_pp'),('held','cycle_prior_median_pp'),
                                ('blend','fixed_blend_pp'),('macro','macro_without_sim_pp'),('macro_sim','macro_plus_sim_pp')):
                r[label+'_abs_error_pp']=abs(r[field]-truth) if r[field] is not None else None
            r['raw_bias_pp']=r['sim_median_pp']-truth
            monthly.append(r)
        metrics={}
        for label,field in (('raw','sim_median_pp'),('public_persistence','anchor_pp'),('same_cycle_prior','cycle_prior_median_pp'),
                            ('fixed_blend','fixed_blend_pp'),('macro_without_sim','macro_without_sim_pp'),('macro_plus_sim','macro_plus_sim_pp')):
            valid=[r for r in monthly if r[field] is not None]
            metrics[label]=headline_errors([r[field] for r in valid],[r['truth_pp'] for r in valid])
        # Horizon selections come from the FULL plan, then require sealed points
        # and fully completed months. Stopping cannot select an earlier forecast.
        complete_targets={r['target_reference_period'] for r in monthly}
        selections=ev.score_cutoffs(plan,releases)
        horizons={}
        for panel in sorted({s['panel'] for s in selections}):
            picked=[]
            for s in selections:
                if s['panel']!=panel or s['target_reference_period'] not in complete_targets or s['cutoff'] is None:continue
                found=[r for r in rows if r['cutoff']==s['cutoff']]
                if len(found)!=1:raise ValueError('Expected predeclared sealed horizon point')
                r=found[0];truth=truths[r['target_reference_period']]['value_pp']
                picked.append(dict(truth=truth,raw=r['sim_median_pp'],baseline=r['anchor_pp'],
                                   blend=r['fixed_blend_pp'],lead_days=s['actual_lead_days']))
            horizons[panel]={label:headline_errors([r[label] for r in picked],[r['truth'] for r in picked])
                             for label in ('raw','baseline','blend')}
            horizons[panel]['actual_lead_days']=[r['lead_days'] for r in picked]

        stages=Counter();errors=Counter();remaining=Counter();unknown=0;physical=0;reported=reserved=0.
        pending_main=0;main_attempted=0;repair_attempted=0;hard=[]
        for point in plan:
            wave=folder/'waves'/point['step_key']
            for stage in ('main','repair'):
                intents,replies=queue.archive(wave/stage);acc=queue.account(intents,replies)
                physical+=acc['attempts'];unknown+=acc['unresolved']
                reported+=acc['reported_cost_usd'];reserved+=acc['spent_or_reserved_usd']
                stages[stage]+=acc['attempts']
                if stage=='main':main_attempted+=len(intents);pending_main+=300-len(intents)
                else:repair_attempted+=len(intents)
                for reply in replies:
                    if reply.get('error'):errors[reply['error']]+=1
                    if reply.get('error_http_status') in (401,402,403):
                        hard.append(dict(week=point['step_key'],stage=stage,error=reply['error'],
                                         http_status=reply['error_http_status'],at_utc=reply['finished_at_utc']))
            if point['step_key'] in keys:
                remaining.update(read(folder/'checkpoints'/point['step_key']/'receipt.json')['remaining_fields'])
        audit=dict(status='stopped_partial_not_final',sealed_weeks=len(keys),planned_weeks=len(plan),
            first_sealed=rows[0]['step_key'],last_sealed=rows[-1]['step_key'],
            completed_target_months=len(monthly),main_attempted=main_attempted,repair_attempted=repair_attempted,
            physical_attempts=physical,never_dispatched_main=pending_main,unresolved_dispatches=unknown,
            errors=dict(errors),hard_errors=hard,retained_fields_sealed_weeks=dict(remaining),
            reported_cost_usd=reported,spent_or_reserved_usd=reserved,unknown_fee_reservation_usd=reserved-reported,
            remaining_budget_usd=protocol['budget_cap_usd']-reserved,new_API_calls=0,
            no_automatic_paid_resumption=True)
        result=dict(status='partial_checkpoint_readout',primary='last_scheduled_week_of_fully_sealed_month',
            provisional=True,metrics=metrics,horizons=horizons,operation=audit,
            fixed_simulation_weight=alpha,new_API_calls=0,
            limits=['Only completed months; July partial week is descriptive, not a month-end score.',
                    'No true weekly microdata; simulation IQR is descriptive; no W1 accuracy claim.',
                    'Targets now opened only in this separate offline analysis; continuing cannot change frozen settings.',
                    'These are retrospective weekly states, not historically sealed live forecasts.'])
        out.mkdir(parents=True)
        _csv(out/'weekly_national.csv',rows);_csv(out/'monthly_complete.csv',monthly)
        dump(out/'summary.json',result);dump(out/'operation.json',audit)
        dump(out/'generation_receipt_snapshot.json',read(folder/'generation_receipt.json'))
        _render(out,rows,monthly,result)
        sources.update({str(p.relative_to(ROOT)):sha(p) for p in (run.CATALOG,ev.MACRO_PARAMETERS,
                      inputs/'weekly_plan.json',inputs/'weights_private.json',inputs/'priors/cycles_private.json',
                      folder/'generation_receipt.json',folder/'package/manifest.json',Path(__file__))})
        dump(out/'manifest.json',dict(source_sha256=sources,
             files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()},new_API_calls=0))
        return result
