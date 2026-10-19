"""Read completed temperature outputs; publish aggregates and two figures only."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from report_sce_q8_delta import ROOT, WORK, READER, read, plt, fontManager

sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation import cognition as shared
from studies.sce_inflation_expectations.evaluation.metrics import quantile, wasserstein1

KEY = 'temperature-results-20261019'


def main(source, trial):
    source, trial = source.resolve(), trial.resolve(); s = read(source/'summary.json')
    protocol = s['protocol']; manifest = read(trial/'manifest.json')
    dest = WORK/'temperature_results_v1'
    if (dest.exists() or f'id="{KEY}"' in READER.read_text()
            or protocol != read(trial/'protocol.json') or protocol['mechanism'] != 'temperature_sensitivity'):
        raise ValueError('Matching completed temperature study and fresh result directory required')
    arms = protocol['arms']; q9 = {a:s['arms'][a]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells'] for a in arms}
    q8 = {a:s['arms'][a]['q8']['aggregate_equal_month_repeat_cells'] for a in arms}
    intervals = (s.get('additional_paired_intervals') or {}).get('temperature_10_minus_baseline', {}).get('intervals')
    gates = {'primary_q9_w1_upper95_below_zero': bool(intervals and intervals['cross_section_w1_pp'][1]<0),
        'q9_center_point_no_worse': q9[arms[2]]['q9_center_mae_pp'] <= q9['baseline']['q9_center_mae_pp'],
        'model_validity_and_scorability_gate': not s['accuracy_descriptive_only']}
    counts = dict(calls=0,errors=0,retries=0,input_tokens=0,output_tokens=0); start=[]; end=[]; models=set(); finish={}
    for j in manifest['jobs']:
        audit = ROOT/'outputs/local_runs'/j['run_id']; receipt=read(audit/'run_manifest.json')
        counts['calls']+=receipt['cost']['call_count']; counts['input_tokens']+=receipt['cost']['total_prompt_tokens']; counts['output_tokens']+=receipt['cost']['total_completion_tokens']
        start.append(receipt['started_at_utc']); end.append(receipt['finished_at_utc'])
        for line in (audit/'llm_calls.jsonl').read_text().splitlines():
            c=json.loads(line); counts['errors']+=bool(c.get('error')); counts['retries']+=c['attempt_idx']>0
            models.add(c['returned_model']); k=c.get('finish_reason'); finish[k]=finish.get(k,0)+1
    elapsed=(datetime.fromisoformat(max(end))-datetime.fromisoformat(min(start))).total_seconds()
    cases=read(source/'cases_private.json'); support=shared._common_person_months(cases,arms,protocol['generation_repeats'],'q9')
    baseline=[]
    for m in protocol['months']:
        for r in protocol['generation_repeats']:
            rows=shared._cell_rows(cases,m,r,support)
            if not all(shared.finite(x['real']['previous_q9_mean']) for x in rows):
                raise ValueError('Carry reference would change the registered support')
            w=np.array([x['survey_weight'] for x in rows]); y=np.array([x['real']['q9_mean'] for x in rows]); old=np.array([x['real']['previous_q9_mean'] for x in rows])
            baseline.append({'center_mae_pp':abs(quantile(y,w,.5)-quantile(old,w,.5)),
                'w1_pp':wasserstein1(y,w,old,w),'personal_mae_pp':float(np.average(abs(y-old),weights=w))})
    carry={k:float(np.mean([x[k] for x in baseline])) for k in baseline[0]}
    components={question:{a:{k:float(np.mean([cell['arms'][a][k] for cell in s['temperature_dispersion']['cells'] if cell['question']==question]))
        for k in ['within_person_repeat_variance_pp2','noise_adjusted_between_variance_pp2']} for a in arms}
        for question in ['Q9_density_mean','Q8_point']}
    receipt={**counts,'estimated_cost_usd':s['estimated_actual_cost_usd'],'cap_usd':protocol['budget_cap_usd'],
        'api_elapsed_seconds':elapsed,'evaluation_seconds':s['evaluation_seconds'],'returned_model_aliases':sorted(models),
        'finish_reasons':finish,'candidate_gate_checks':gates,'candidate_passed':all(gates.values()),'same_support_carry_q9':carry,
        'mean_variance_components_equal_months':components,'protocol_sha256':manifest['protocol_sha256'],
        'source_summary_sha256':hashlib.sha256((source/'summary.json').read_bytes()).hexdigest(),
        'note':'Usage-based peak-price estimate, not vendor invoice; no private row records published.'}
    if (source/'evaluation_adapter_receipt.json').exists():
        receipt['evaluation_adapter_receipt']=read(source/'evaluation_adapter_receipt.json')
    dest.mkdir();(dest/'figures').mkdir()
    for name,data in [('summary.json',s),('run_receipt.json',receipt)]:
        (dest/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':12,'axes.spines.top':False,'axes.spines.right':False,'axes.unicode_minus':False})
    colors=['#a9b1b4','#4c9fa0','#087f80']; labels=['温度0.5','温度0.8','温度1.0']
    fig,ax=plt.subplots(figsize=(10.5,4.8)); fields=['q9_center_mae_pp','cross_section_w1_pp','individual_density_mean_mae_pp']; x=np.arange(3)
    for i,a in enumerate(arms):
        bars=ax.bar(x+(i-1)*.22,[q9[a][k] for k in fields],.22,label=labels[i],color=colors[i]);ax.bar_label(bars,fmt='%.2f',fontsize=10,padding=3)
    ax.set_xticks(x,['群体中位数MAE','跨人分布W1','逐人MAE']);ax.set_ylabel('误差／距离（百分点，越小越好）');ax.set_xlabel('Q9评价指标');ax.set_title('只调整温度后的Q9拟合：同人口、同信息、直接填写');ax.legend()
    fig.text(.02,.01,'来源：四个开发月×24人×三组×4遍；同支持原调查权重敏感性，月份与生成遍数等权。',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(dest/'figures/accuracy.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.6))
    for ax,question,title in zip(axes,components,['Q9个人密度均值','Q8点预期']):
        for i,k in enumerate(['within_person_repeat_variance_pp2','noise_adjusted_between_variance_pp2']):
            ax.bar(np.arange(3)+(i-.5)*.35,[components[question][a][k] for a in arms],.35,
                label=['同一人重复方差','扣除重复噪声后的跨人方差'][i],color=['#b8c2c5','#087f80'][i])
        ax.set_xticks(np.arange(3),labels);ax.set_xlabel('请求温度');ax.set_ylabel('方差（百分点²）');ax.set_title(title);ax.legend(fontsize=9)
        ax.margins(y=.3)
    fig.text(.02,.01,'同月同一虚拟人固定输入重复4遍，按人等权后各月平均；噪声修正依赖近似独立重复，负估计不裁剪。',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(dest/'figures/dispersion.png',dpi=170);plt.close(fig)
    quality_rows=''.join(f'<tr><td>{labels[i]}</td><td>{q9[a]["q9_center_mae_pp"]:.3f}</td><td>{q9[a]["cross_section_w1_pp"]:.3f}</td><td>{q9[a]["cross_person_iqr_pp"]:.3f}</td><td>{q8[a]["q8_center_mae_pp"]:.3f}</td></tr>' for i,a in enumerate(arms))
    interval_text = '合法/可计分覆盖未达预设门槛，本轮误差仅作描述。'
    if intervals:
        interval_text = '；'.join(f'{label}差的95%区间为[{intervals[key][0]:+.3f}, {intervals[key][1]:+.3f}]pp'
            for label,key in [('中位数MAE','q9_center_mae_pp'),('分布W1','cross_section_w1_pp')])
    gate_labels = ['分布W1改善区间低于0','中位数误差点值不增加','合法与可计分覆盖达标']
    gate_text = '；'.join(f'{label}：'+('通过' if value else '未通过') for label,value in zip(gate_labels,gates.values()))
    cbase=components['Q9_density_mean']['baseline'];chigh=components['Q9_density_mean']['temperature_10']
    interpretation=(f'<p><strong>主Q9同一人的重复方差从{cbase["within_person_repeat_variance_pp2"]:.3f}升至'
        f'{chigh["within_person_repeat_variance_pp2"]:.3f}pp²；扣除重复噪声后的跨人方差仅从'
        f'{cbase["noise_adjusted_between_variance_pp2"]:.3f}升至{chigh["noise_adjusted_between_variance_pp2"]:.3f}pp²。</strong>'
        '温度增加了波动，却没有明显恢复主Q9的人际差异。0.8的W1改善作为辅助信号保留，不事后替换预定主比较。</p>')
    outcome='满足开发筛选，但仍须独立时期验证，不自动升级默认。' if all(gates.values()) else '未满足预登记继续条件，保留温度0.5工作参考。'
    html=f'''<section id="{KEY}" style="font-family:'Times New Roman','Kaiti SC','STKaiti',serif;max-width:1120px;margin:24px auto;padding:24px 28px 36px;border-bottom:1px solid #d7dfdc;line-height:1.75">
<h1>温度对照：拟合质量与重复波动分开检查</h1><p>2026-10-19。四个开发月、每月24人、三组各4遍；<strong>{counts['calls']}次调用，估算${s['estimated_actual_cost_usd']:.3f}／上限$6</strong>，接口错误{counts['errors']}、重试{counts['retries']}。调用约{elapsed/60:.1f}分钟，评价{s['evaluation_seconds']:.1f}秒。</p>
<p>DeepSeek官方Flash；温度0.5／0.8／1.0。其余画像、历史信念、公共信息与提示完全相同，全部直接填Q8/Q9，关闭思考；没有网格化、差值格式或新增人格标签。四遍是相同虚拟人的重复回答，不能增加真实人数。</p>
<div class="table-scroll"><table><thead><tr><th>组别</th><th>Q9中心MAE↓</th><th>Q9分布W1↓</th><th>Q9跨人IQR</th><th>Q8中心MAE↓（等人）</th></tr></thead><tbody>{quality_rows}</tbody></table></div>
<p>单位为百分点。Q9共同支持{s['common_q9_person_months']}个人月、Q8为{s['common_q8_person_months']}个人月；Q9原调查权重为敏感性口径，Q8等人权重。相同支持照抄本人上期Q9：中心{carry['center_mae_pp']:.3f}、W1 {carry['w1_pp']:.3f}。不能当全国成绩或替换十二期主结果。</p>
<figure><img src="../20261019_advisor_followup/temperature_results_v1/figures/accuracy.png" alt="三种温度的同支持Q9拟合误差"><figcaption>先对每月、每遍计分再平均，没有用四遍均值作为最终模拟答案。</figcaption></figure>
<h2>主要比较与不确定性</h2><p>执行前固定1.0对0.5为主比较，0.8为辅助。{interval_text}；负数代表高温组误差下降。{outcome}{gate_text}。区间保留同人的各月份与重复，仅适用于固定四个开发月，不代表新时期风险。</p>
<h2>同一个人摇摆，与不同人有差异</h2>{interpretation}<p>下图把重复方差与各人平均回答的差异分开。跨人方差再减去平均重复方差÷4，估计扣除重复噪声后的差异；该估计不等于真实人格参数，负数原样报告。稳定差异扩大也需要同时改善W1、个人排序或误差，才有实际价值。</p>
<figure><img src="../20261019_advisor_followup/temperature_results_v1/figures/dispersion.png" alt="Q8和Q9的重复噪声与经修正跨人方差"><figcaption>此图按人等权、月份等权，单位为百分点²；与上方调查权重敏感性误差口径分别解释。</figcaption></figure>
<p><a href="../20261019_advisor_followup/temperature_results_20261019.md">结果解释与下一步</a> · <a href="../20261019_advisor_followup/temperature_results_v1/summary.json">完整聚合</a> · <a href="../20261019_advisor_followup/temperature_results_v1/run_receipt.json">费用与分解收据</a> · <a href="../../current_todo.html">当前清单</a></p></section>'''
    (dest/'reading_section.html').write_text(html+'\n');READER.write_text(READER.read_text().replace('</body>',html+'\n</body>'))
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--trial',type=Path,required=True)
    a=p.parse_args();main(a.source,a.trial)
