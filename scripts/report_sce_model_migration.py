"""Read a sealed model comparison; publish aggregates without API calls or refits."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from report_sce_q8_delta import ROOT,WORK,READER,read,plt,fontManager

sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation import cognition as shared
from studies.sce_inflation_expectations.evaluation.metrics import quantile,wasserstein1
from studies.sce_inflation_expectations.evaluation.temperature import dispersion_readout

KEY='qwen-migration-results-20261019'
LABEL={'baseline':'DeepSeek旧回答','qwen':'Qwen2.5新回答'}


def main(source,trial):
    source,trial=source.resolve(),trial.resolve();s=read(source/'summary.json');protocol=read(trial/'protocol.json')
    dest=WORK/'qwen_migration_results_v1'
    if dest.exists() or f'id="{KEY}"' in READER.read_text() or s['protocol']!=protocol:
        raise ValueError('Fresh matching readout required')
    cases=read(source/'cases_private.json');arms=['baseline','qwen'];months=protocol['months'];repeats=protocol['generation_repeats']
    support=shared._common_person_months(cases,arms,repeats,'q9')
    q9={a:s['arms'][a]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells'] for a in arms}
    q8={a:s['arms'][a]['q8']['aggregate_equal_month_repeat_cells'] for a in arms}
    cell_rows=[]
    for m in months:
        for r in repeats:
            rows=shared._cell_rows(cases,m,r,support);w=np.array([x['survey_weight'] for x in rows])
            y=np.array([x['real']['q9_mean'] for x in rows]);old=np.array([x['real']['previous_q9_mean'] for x in rows])
            if not np.isfinite(old).all():raise ValueError('Carry comparison would change common support')
            cells={'month':m,'repeat':r,'n_person_months':len(rows),'real_center_pct':quantile(y,w,.5),
                'real_cross_iqr_pp':quantile(y,w,.75)-quantile(y,w,.25),'carry_center_pct':quantile(old,w,.5),
                'carry_center_mae_pp':abs(quantile(old,w,.5)-quantile(y,w,.5)),
                'carry_w1_pp':wasserstein1(old,w,y,w),'carry_iqr_pp':quantile(old,w,.75)-quantile(old,w,.25),
                'carry_person_mae_pp':float(np.average(abs(old-y),weights=w)),
                'real_mean_absolute_update_pp':float(np.average(abs(y-old),weights=w))}
            for a in arms:
                p=np.array([x['arms'][a]['mean'] for x in rows])
                cells[a+'_center_pct']=quantile(p,w,.5)
                cells[a+'_mean_absolute_update_pp']=float(np.average(abs(p-old),weights=w))
            cell_rows.append(cells)
    carry={k:float(np.mean([c[k] for c in cell_rows])) for k in ['carry_center_mae_pp','carry_w1_pp','carry_iqr_pp','carry_person_mae_pp','real_cross_iqr_pp','real_mean_absolute_update_pp']}
    dprotocol={**protocol,'arms':arms}
    dispersion=dispersion_readout(cases,dprotocol)
    dispersion['limits']='Only two repetitions: noisy API-repeat variance estimates, not human personality. Equal people, separate from design-weighted accuracy.'
    components={question:{a:{k:float(np.mean([c['arms'][a][k] for c in dispersion['cells'] if c['question']==question]))
        for k in ['within_person_repeat_variance_pp2','noise_adjusted_between_variance_pp2']} for a in arms}
        for question in ['Q9_density_mean','Q8_point']}
    # Pre-existing profile categories, all levels; no target-driven split or fitted coefficient.
    groups=[]
    for field in ['education_group','numeracy']:
        labels=sorted({str(r['profile'][field]) for r in cases})
        for label in labels:
            subset=[r for r in cases if str(r['profile'][field])==label]
            subset_support=shared._common_person_months(subset,arms,repeats,'q9')
            sizes=[len(shared._cell_rows(subset,m,repeats[0],subset_support)) for m in months]
            groups.append({'field':field,'label':label,'n_common_person_months':len(subset_support),
                'n_by_month':dict(zip(map(str,months),sizes)),'sparse_months_below_8':[m for m,n in zip(months,sizes) if n<8],
                'by_arm':{a:shared._summarize_arm(subset,a,months,repeats,subset_support,set())['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells'] for a in arms},
                'interpretation':'Descriptive only; sparse cells, no fitted calibration or causal attribution.'})
    all_jobs={}
    for package in [ROOT/protocol.get('completion_of',str(trial.relative_to(ROOT))),ROOT/protocol.get('analysis_of_trial',str(trial.relative_to(ROOT)))]:
        for j in read(package/'manifest.json')['jobs']:
            d=ROOT/'outputs/local_runs'/j['run_id']
            if (d/'run_manifest.json').exists():all_jobs[j['run_id']]=d
    counts=Counter();fees=0.;estimated=0.;returned=set();providers=set();sums=Counter();phase_times={}
    for name,d in all_jobs.items():
        rec=read(d/'run_manifest.json');estimated+=rec['cost']['estimated_cost_usd']
        counts['requests']+=rec['cost']['call_count'];counts['input_tokens']+=rec['cost']['total_prompt_tokens'];counts['output_tokens']+=rec['cost']['total_completion_tokens']
        phase='original' if name.startswith(Path(protocol.get('completion_of',str(trial))).name+'-') else 'completion'
        phase_times.setdefault(phase,[]).append((rec['started_at_utc'],rec['finished_at_utc']));counts[phase+'_requests']+=rec['cost']['call_count']
        for line in (d/'llm_calls.jsonl').read_text().splitlines():
            call=json.loads(line);counts['interface_errors']+=bool(call.get('error'));counts['automatic_retry_requests']+=call['attempt_idx']>0
            if not call.get('error'):counts['received_responses']+=1
            if call.get('api_reported_cost_usd') is not None:fees+=call['api_reported_cost_usd'];counts['reported_cost_calls']+=1
            if call.get('returned_model'):returned.add(call['returned_model'])
            if call.get('returned_provider'):providers.add(call['returned_provider'])
    for r in cases:
        if r['arms']['qwen']['validation_status']!='valid':sums[str(round(sum(r['arms']['qwen']['q9_bins']),6))]+=1
    phase_seconds={k:(datetime.fromisoformat(max(e for b,e in v))-datetime.fromisoformat(min(b for b,e in v))).total_seconds() for k,v in phase_times.items()}
    receipt={**counts,'evaluated_qwen_responses':len(cases),'reused_original_qwen_responses':72 if protocol.get('completion_of') else 0,
        'new_completion_requests':counts['completion_requests'],'planned_completion_requests':120 if protocol.get('completion_of') else None,
        'reused_deepseek_responses':len(cases),'excluded_partial_successes':counts['received_responses']-len(cases),'excluded_incomplete_months':protocol.get('excluded_incomplete_months',[]),
        'manual_replayed_units':1 if protocol.get('completion_of') else 0,'reported_cost_usd':fees,'estimated_usage_cost_usd':estimated,
        'combined_cap_usd':protocol['budget_cap_usd'],'unreceived_request_billing_unknown':bool(counts['interface_errors']),
        'returned_models':sorted(returned),'returned_providers':sorted(providers),'invalid_q9_sum_counts_in_evaluated_answers':dict(sums),
        'phase_api_span_seconds':phase_seconds,'evaluation_seconds':s['evaluation_seconds'],
        'technical_gate_passed':not s['accuracy_descriptive_only'],'automatic_upgrade':False,
        'q9_common_person_months':s['common_q9_person_months'],'q8_common_person_months':s['common_q8_person_months'],
        'unique_respondents':len({r['userid'] for r in cases}),'same_support_carry_q9':carry,
        'mean_variance_components_equal_people_months':components,
        'protocol_sha256':read(trial/'manifest.json')['protocol_sha256'],
        'source_summary_sha256':hashlib.sha256((source/'summary.json').read_bytes()).hexdigest(),
        'note':'Costs deduplicate reused jobs and include excluded partial answers. Reported successful-call cost is not a vendor invoice; failed connection may be billable. No probability repair, no new API or refit by this report.'}
    dest.mkdir();(dest/'figures').mkdir()
    for name,value in [('summary.json',s),('run_receipt.json',receipt),('monthly_readout.json',cell_rows),('group_descriptions.json',groups),('dispersion_readout.json',dispersion)]:
        (dest/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':12,'axes.spines.top':False,'axes.spines.right':False,'axes.unicode_minus':False})
    colors={'baseline':'#839295','qwen':'#087f80','carry':'#b08342','real':'#252e32'}
    fig,axes=plt.subplots(1,2,figsize=(12,4.8));fields=['q9_center_mae_pp','cross_section_w1_pp','delta_w1_pp'];x=np.arange(3)
    for i,a in enumerate(arms):
        bars=axes[0].bar(x+(i-.5)*.31,[q9[a][k] for k in fields],.31,label=LABEL[a],color=colors[a]);axes[0].bar_label(bars,fmt='%.2f',padding=3,fontsize=10)
    axes[0].set_xticks(x,['样本中位数MAE','跨人分布W1','变化分布W1']);axes[0].set_ylabel('百分点，越小越好');axes[0].set_title('Q9：同支持下的拟合差距');axes[0].legend(fontsize=10)
    widths=[carry['real_cross_iqr_pp'],q9['baseline']['cross_person_iqr_pp'],q9['qwen']['cross_person_iqr_pp'],carry['carry_iqr_pp']]
    bars=axes[1].bar(np.arange(4),widths,color=[colors[k] for k in ['real','baseline','qwen','carry']]);axes[1].bar_label(bars,fmt='%.2f',padding=3)
    axes[1].set_xticks(np.arange(4),['真人','DeepSeek','Qwen2.5','照抄上期']);axes[1].set_ylabel('跨人IQR（百分点）');axes[1].set_title('差异是否更接近真人，需要与W1一起判断');axes[1].margins(y=.15)
    fig.text(.02,.01,'完整开发月份、各24人、两遍；Q9共同支持及原设计权重；不合法Q9未归一化，误差仅作描述。',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(dest/'figures/structure.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10.8,4.8));x=np.arange(len(months))
    for k,label in [('real','真人'),('baseline','DeepSeek旧回答'),('qwen','Qwen2.5新回答'),('carry','照抄本人上期')]:
        y=[float(np.mean([c[k+'_center_pct'] for c in cell_rows if c['month']==m])) for m in months]
        ax.plot(x,y,'o-' if k=='real' else 'o--',label=label,color=colors[k],linewidth=2)
    ax.set_xticks(x,[f'{m//100}-{m%100:02d}' for m in months]);ax.set_xlabel('非连续开发月份');ax.set_ylabel('Q9样本中心（%）');ax.set_title('个人Q9密度均值的跨人中位数：逐月比较');ax.legend(ncol=2,fontsize=10)
    fig.text(.02,.01,'各月中心为两次生成的平均，仅用于画图；MAE仍先逐月逐遍计误差，不先平均回答。',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(dest/'figures/monthly.png',dpi=170);plt.close(fig)
    rows=''.join(f'<tr><td>{LABEL[a]}</td><td>{q9[a]["q9_center_mae_pp"]:.3f}</td><td>{q9[a]["cross_section_w1_pp"]:.3f}</td><td>{q9[a]["delta_w1_pp"]:.3f}</td><td>{q9[a]["cross_person_iqr_pp"]:.3f}</td><td>{q8[a]["q8_center_mae_pp"]:.3f}</td></tr>' for a in arms)
    html=f'''<section id="{KEY}" style="font-family:'Times New Roman','Kaiti SC','STKaiti',serif;max-width:1120px;margin:24px auto;padding:24px 28px 36px;border-bottom:1px solid #d7dfdc;line-height:1.75">
<h1>Qwen2.5同输入迁移：微观结构与数值合法性</h1>
<p>2026-10-19。原计划2020-04、2021-05/11、2022-03各24人，两次生成。实际只纳入全部重复完成的月份：{'、'.join(f'{v//100}-{v%100:02d}' for v in months)}；未完成月份{protocol.get('excluded_incomplete_months',[])}排除。只换模型，直接填Q8/Q9；P/E、本人真实上期信念、提示和温度0.5均保持一致。Qwen2.5-72B固定DeepInfra，DeepSeek前两遍旧回答直接复用。</p>
<p>共发出<strong>{counts['requests']}次Qwen请求</strong>，成功收到{counts['received_responses']}份，其中{len(cases)}份用于完整月份评价；其余{counts['received_responses']-len(cases)}份成功回包与{counts['interface_errors']}次连接错误保留存档。首次中断获用户允许一次整单元补发；再次中断便停止。自动重试{counts['automatic_retry_requests']}次。供应商报告费用${fees:.4f}，含未知计费请求的保守使用量估${estimated:.4f}／合计上限$1。</p>
<p><strong>数值合法性未达到99%技术门槛。</strong>不合法Q9保留原值、不归一化；下列Q9只比较两模型均有效且两遍可计分的{s['common_q9_person_months']}个人月。模型失败可能不是随机缺失，因此以下数值仅作描述，不能据此宣布模型替换成功。Q8独立保留{s['common_q8_person_months']}个人月。</p>
<div class="table-scroll"><table><thead><tr><th>模型</th><th>Q9中心MAE↓</th><th>跨人W1↓</th><th>变化W1↓</th><th>跨人IQR</th><th>Q8中心MAE↓（等人）</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Q9按原设计调查权重、月份/遍数等权；Q8此列按人等权。同支持照抄上期Q9中心MAE {carry['carry_center_mae_pp']:.3f}、分布W1 {carry['carry_w1_pp']:.3f}；真人跨人IQR {carry['real_cross_iqr_pp']:.3f}。不是全国SCE成绩，不能与旧四遍或十二期的数值直接拼比。</p>
<figure><img src="../20261019_advisor_followup/qwen_migration_results_v1/figures/structure.png" alt="Qwen与DeepSeek的Q9拟合及跨人差异"><figcaption>人际IQR扩大只有在分布距离也改善时才有意义；不把随机撒宽视为恢复真实异质性。</figcaption></figure>
<figure><img src="../20261019_advisor_followup/qwen_migration_results_v1/figures/monthly.png" alt="实际完成的非连续开发月的真人、两个模型及照抄上期中心"><figcaption>同一支持、同权重比较；两遍重复没有增加真人样本量。</figcaption></figure>
<p>本次是历史A线回访者条件重建。这些开发月都已看过，旧DeepSeek不是同期随机对照；同一温度不代表两模型同等随机性。Qwen完整知识截止与托管权重修订仍未核实。没有在本批拟合宏观组合权重，也没有改默认模型。</p>
<p><a href="../20261019_advisor_followup/qwen_migration_results.md">完整解释与下一步</a> · <a href="../20261019_advisor_followup/qwen_migration_results_v1/run_receipt.json">调用与费用</a> · <a href="../20261019_advisor_followup/qwen_migration_results_v1/group_descriptions.json">学历/数理分组</a> · <a href="../../current_todo.html">当前清单</a></p></section>'''
    (dest/'reading_section.html').write_text(html+'\n');READER.write_text(READER.read_text().replace('</body>',html+'\n</body>'))
    print(json.dumps({'receipt':receipt,'q9':q9,'q8':q8},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--trial',type=Path,required=True)
    a=p.parse_args();main(a.source,a.trial)
