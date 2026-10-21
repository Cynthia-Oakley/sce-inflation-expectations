#!/usr/bin/env python3
"""Publish aggregate model-comparison figures from cached scores; no API/refit."""
import argparse
from collections import Counter
from datetime import datetime
import html
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
LABELS={'qwen_cached':'Qwen 2.5-72B','deepseek_v32':'DeepSeek V3.2','carry':'照抄本人上期'}
COLORS={'qwen_cached':'#783caf','deepseek_v32':'#d56a00','carry':'#737b85'}


def cached_diagnostics(source,dest):
    """Selection and calendar sensitivity on existing scores only."""
    from studies.sce_inflation_expectations.evaluation import cognition as shared
    from studies.sce_inflation_expectations.evaluation.price_background_readout import summarize
    source,dest=Path(source).resolve(),Path(dest).resolve()
    if dest.exists():raise ValueError('Fresh diagnostic directory required')
    s=json.loads((source/'summary.json').read_text());cases=json.loads((source/'cases_private.json').read_text())
    arms=s['protocol']['arms'];months=s['protocol']['months'];repeats=s['protocol']['generation_repeats']
    support=shared._common_person_months(cases,arms,repeats,'q9')
    raw={(m,u) for m,u in support if all(r['arms'][a]['raw_validation_status']=='valid'
         for r in cases if (r['month'],r['userid'])==(m,u) for a in arms)}
    restricted=summarize(cases,arms,months,repeats,raw)
    leave={}
    for month in months:
        rest=summarize([r for r in cases if r['month']!=month],arms,[m for m in months if m!=month],repeats,support)
        leave[str(month)]={a:{k:v[k] for k in ('center_mae_pp','w1_pp','delta_w1_pp')} for a,v in rest['metrics'].items()}
    result=dict(new_api_calls=0,scorer_calls=0,raw_valid_support_person_months=restricted['person_months'],
        raw_valid_support_metrics=restricted['metrics'],leave_one_month_out=leave,
        generation={str(rep):summarize(cases,arms,months,[rep],support)['metrics'] for rep in repeats},
        source_sha256={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in ('summary.json','cases_private.json')},
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        note='Cached normalized scores on originally valid response support; changing sample is not a causal normalization-effect estimate.')
    dest.mkdir();(dest/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return dict(raw_valid_support_person_months=restricted['person_months'],new_api_calls=0,scorer_calls=0)


def publish(source,ledger,dest,repeat_summary=None,diagnostics_summary=None):
    source,ledger,dest=[Path(p).resolve() for p in (source,ledger,dest)]
    if dest.exists():raise ValueError('Fresh public result directory required')
    s=json.loads((source/'summary.json').read_text())
    if s['status']!='completed_exact_message_model_comparison':raise ValueError('Complete comparison required')
    p=s['protocol'];arms=p['comparison_arms'];months=p['months'];r=s['readout'];metrics=r['metrics']
    cases=json.loads((source/'cases_private.json').read_text())
    scorable={a:int(sum(row['arms'][a].get('mean') is not None and row['arms'][a].get('iqr') is not None
                    and np.isfinite(row['arms'][a]['mean']) and np.isfinite(row['arms'][a]['iqr']) for row in cases)) for a in arms}
    rows=[json.loads(line) for line in (ledger/'new_calls_private.jsonl').read_text().splitlines()]
    if len(rows)!=768:raise ValueError('Full registered new-model ledger required')
    cost=json.loads((ledger/'run_receipt.json').read_text())
    prior=p.get('previous_AtlasCloud_spent_or_reserved_usd',0)
    raw_ok=normalized=0;reasoning=[]
    from studies.sce_inflation_expectations.q9_normalization import response_view
    from studies.sce_inflation_expectations.model import validate_sce_bins
    for row in rows:
        if row.get('usage'):
            reasoning.append((row['usage'].get('completion_tokens_details') or {}).get('reasoning_tokens'))
        if not row.get('error') and row['finish_reason']=='stop':
            try:
                v=response_view(row['raw_response_text']);raw_ok+=validate_sce_bins(v['raw_bins'])[0];normalized+=v['applied']
            except (ValueError,TypeError):pass
    fee=dict(new_requests=len(rows),new_response_errors=sum(bool(row['error']) for row in rows),
        original_q9_valid=raw_ok,normalized_responses=normalized,scorable_q9_by_arm=scorable,
        returned_providers=dict(Counter(str(row.get('returned_provider')) for row in rows)),
        reasoning_token_counts=dict(Counter(str(v) for v in reasoning)),
        api_reported_new_cost_usd=cost['api_reported_new_cost_usd'],
        earlier_route_spent_or_reserved_usd=prior,
        campaign_spent_or_reserved_usd=cost['combined_spent_or_reserved_usd']+prior,
        new_api_seconds=cost['seconds'],automatic_retries=cost['automatic_retries'],
        model_control='Archived Qwen; not contemporaneous controls',
        original_AtlasCloud_attempts=18 if prior else 0,original_AtlasCloud_responses_excluded=5 if prior else 0,
        new_provider=p['expected_provider'],max_concurrency=cost['max_concurrent_requests'])
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':11,
        'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    dest.mkdir(parents=True);(dest/'figures').mkdir()
    monthly={}
    for m in months:
        cells=[c for c in r['cells'] if c['month']==m]
        if not cells:raise ValueError('Every registered month must retain common support')
        monthly[m]={a:{key:float(np.mean([c['arms'][a][key] for c in cells if c['arms'][a][key] is not None]))
                       for key in cells[0]['arms'][a]} for a in metrics}
        for a in metrics:
            monthly[m][a]['center_rmse_pp']=float(np.sqrt(np.mean([c['arms'][a]['center_bias_pp']**2 for c in cells])))
    x=np.arange(len(months));names=[*arms,'carry'];ticks=[f'{m//100}-{m%100:02}' for m in months]
    fig,axes=plt.subplots(1,2,figsize=(13.5,4.8))
    axes[0].plot(x,[monthly[m][arms[0]]['truth_center_pp'] for m in months],'o-',color='#25282c',label='真人本期',linewidth=2.3)
    for a,marker in zip(names,['s','^','x']):
        axes[0].plot(x,[monthly[m][a]['predicted_center_pp'] for m in months],marker+'--',color=COLORS[a],label=LABELS[a])
    axes[0].set_title('各月群体中位数');axes[0].set_ylabel('未来12个月通胀预期（%）')
    for j,a in enumerate(names):
        bars=axes[1].bar(x+(j-1)*.25,[monthly[m][a]['w1_pp'] for m in months],.23,color=COLORS[a],label=LABELS[a])
        axes[1].bar_label(bars,fmt='%.2f',fontsize=8,padding=3)
    axes[1].set_title('各月跨人分布距离W1');axes[1].set_ylabel('通胀百分点（越低越接近）');axes[1].margins(y=.18)
    for ax in axes:ax.set_xticks(x,ticks);ax.set_xlabel('四个非连续开发月');ax.legend(fontsize=8)
    fig.text(.015,.012,f'共同支持{r["person_months"]}个人月／{r["unique_persons"]}人；各两遍。左图逐遍中位数再平均，仅作展示；正式MAE先逐遍计绝对误差。',fontsize=9)
    fig.tight_layout(rect=(0,.055,1,1));fig.savefig(dest/'figures/monthly_models.png',dpi=165);plt.close(fig)

    groups=s['prior_groups'];order=['below_2','2_to_below_4','4_to_below_8','8_or_above']
    bands=[v for v in order if v in groups and groups[v]['unique_persons']>=8]
    fig,axes=plt.subplots(1,2,figsize=(13.5,4.8));x=np.arange(len(bands))
    axes[0].plot(x,[groups[b]['metrics'][arms[0]]['truth_mean_pp'] for b in bands],'o-',color='#25282c',linewidth=2.3,label='真人本期')
    for a,marker in zip(names,['s','^','x']):
        axes[0].plot(x,[groups[b]['metrics'][a]['model_mean_pp'] for b in bands],marker+'--',color=COLORS[a],label=LABELS[a])
    labels=dict(zip(order,['上期<2%','上期2—4%','上期4—8%','上期≥8%']))
    axes[0].set_xticks(x,[labels[b] for b in bands]);axes[0].set_xlabel('本人上期Q9预期分组')
    axes[0].set_ylabel('本期个人预期的设计加权均值（%）');axes[0].set_title('高低先验人群的本期回答');axes[0].legend(fontsize=8)
    keys=['across_person_iqr_pp','delta_w1_pp'];x=np.arange(2)
    for j,a in enumerate(names):
        bars=axes[1].bar(x+(j-1)*.25,[metrics[a][k] for k in keys],.23,color=COLORS[a],label=LABELS[a])
        axes[1].bar_label(bars,fmt='%.2f',fontsize=9,padding=3)
    axes[1].set_xticks(x,['跨人IQR（对照真人）','变化分布W1（越低越接近）']);axes[1].set_ylabel('通胀百分点')
    axes[1].set_xlabel('不同统计量，不能相加');axes[1].set_title(f'人群分歧与更新；真人IQR {metrics[arms[0]]["truth_across_person_iqr_pp"]:.2f}pp')
    axes[1].legend(fontsize=8);axes[1].margins(y=.18)
    fig.text(.015,.012,'先逐月逐遍按设计权重计算，再等权平均。先验组是描述性条件比较；稀疏格和人数见聚合文件，不作因果解释。',fontsize=9)
    fig.tight_layout(rect=(0,.055,1,1));fig.savefig(dest/'figures/conditional_models.png',dpi=165);plt.close(fig)
    base,new=arms
    f=lambda a,k:f'{metrics[a][k]:.3f}'
    center_word='降低' if metrics[new]['center_mae_pp']<metrics[base]['center_mae_pp'] else '升高'
    w1_word='降低' if metrics[new]['w1_pp']<metrics[base]['w1_pp'] else '升高'
    q8={a:s['arms'][a]['auxiliary_survey_weighted']['q8']['aggregate_equal_month_repeat_cells'] for a in arms}
    ci=(s.get('paired_intervals') or {}).get('intervals',{})
    ci_text='；'.join(f'{html.escape(k)}：[{v[0]:+.3f}, {v[1]:+.3f}]' for k,v in ci.items()
                     if k in ('q9_center_mae_pp','cross_section_w1_pp','delta_w1_pp') and v)
    prob={a:s['arms'][a]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells'] for a in arms}
    high=s['prior_groups']['8_or_above']['metrics']
    no_june=[m for m in months if m!=202206]
    leave_center={a:float(np.mean([monthly[m][a]['center_mae_pp'] for m in no_june])) for a in names}
    repeat_text='';repeat_public=None
    if repeat_summary is not None:
        repeat_public=json.loads(Path(repeat_summary).read_text())
        if repeat_public['source_sha256']!=hashlib.sha256((source/'cases_private.json').read_bytes()).hexdigest():
            raise ValueError('Repeat diagnostic must use these exact scored cases')
        repeat_public['source']=str((source/'cases_private.json').relative_to(ROOT))
        values={a:repeat_public['arms'][a]['equal_month_means'] for a in arms}
        repeat_text=f'''<h2>5. 两次生成：没有靠增加随机波动来扩大人际差异</h2><p>同一人两次Q9预期的平均绝对差，Qwen为{values[base]['mean_absolute_repeat_gap_pp']:.3f}pp，V3.2为{values[new]['mean_absolute_repeat_gap_pp']:.3f}pp；两次生成之间的个人排序Pearson相关为{values[base]['person_pearson_equal_weight']:.3f}→{values[new]['person_pearson_equal_weight']:.3f}。这与较稳定地保留个人差异的解释一致；只有两遍，不能当成精确方差分解。种子控制样本/输入，未向服务端传生成seed，不保证逐字复现。</p>'''
    diagnostic_public=None;diagnostic_link=''
    if diagnostics_summary is not None:
        diagnostic_public=json.loads(Path(diagnostics_summary).read_text())
        if diagnostic_public['source_sha256']['cases_private.json']!=hashlib.sha256((source/'cases_private.json').read_bytes()).hexdigest():
            raise ValueError('Sensitivity diagnostics must use these exact cases')
        diagnostic_link=' · <a href="diagnostics.json">原始合法支持、删月与逐遍结果</a>'
    text=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V3.2与Qwen同输入比较</title>
<style>body{{margin:0;background:#f6f5f1;color:#25282c;font:19px/1.75 "Times New Roman","Kaiti SC","STKaiti","KaiTi",serif}}main{{max-width:1180px;margin:auto;padding:36px 28px 70px}}h1{{font-size:33px;line-height:1.35}}h2{{font-size:25px;margin-top:32px}}.meta,figcaption,small{{color:#62676d}}.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}.metric,figure{{background:white;padding:18px}}.metric strong{{display:block;font-size:27px}}.finding{{background:white;padding:20px;border-left:4px solid #555}}figure{{margin:28px 0}}img{{width:100%;height:auto}}figcaption{{font-size:16px}}a{{color:#783caf}}li{{margin:8px 0}}@media(max-width:720px){{main{{padding:22px 16px}}.metrics{{grid-template-columns:1fr}}h1{{font-size:27px}}}}</style>
<main><p class="meta">水上挽月 · SCE历史条件重建 · 2026-10-21</p><h1>DeepSeek V3.2与Qwen：相同输入下的比较</h1>
<p>四期各96人、每人两遍。V3.2固定{html.escape(p['expected_provider'])} FP8，Qwen固定DeepInfra FP8；旧Qwen回答复用，人口、环境、真实上期信念与完整提示逐字一致。</p>
<p class="finding">本轮V3.2相对Qwen：群体中位数MAE<strong>{center_word}</strong>，跨人分布W1<strong>{w1_word}</strong>。这是四个开发月的结果；模型与托管实现共同变化，不等于参数规模的单独效果，也不自动证明全国或未来预测改进。</p>
<div class="metrics"><div class="metric">群体中位数MAE · pp<strong>{f(base,'center_mae_pp')} → {f(new,'center_mae_pp')}</strong><small>照抄本人上期 {f('carry','center_mae_pp')}</small></div>
<div class="metric">跨人分布W1 · pp<strong>{f(base,'w1_pp')} → {f(new,'w1_pp')}</strong><small>照抄 {f('carry','w1_pp')}；越低越接近</small></div>
<div class="metric">跨人IQR · pp<strong>{f(base,'across_person_iqr_pp')} → {f(new,'across_person_iqr_pp')}</strong><small>真人 {f(base,'truth_across_person_iqr_pp')}；并非越大越好</small></div></div>
<h2>1. 比较配置与信息边界</h2><p>2020-09、2021-09、2022-06、2025-03，分别覆盖疫情、通胀上升、高通胀与近期阶段。保持温度0.5、JSON、关闭思考、最多1024输出token和相同归一化规则。输入包含合成食品采购角色、食品价格背景、8篇新闻、政策和本人真实上期Q8/Q9及更早摘要。仍是回访者A线条件重建，不是新入组或B线自主连续预测。</p>
<h2>2. 月度中心与完整分布</h2><p>共同支持{r['person_months']}个人月／{r['unique_persons']}人。V3.2格式合法768份，连续密度统计可计分{scorable[new]}份；格式合法不等于每个派生量都可计算。按原有规则排除不可计分个人月，保留原始回答，不补造结果；双方使用相同配对支持。主统计量为每人Q9拟合密度均值，再计算跨人设计加权中位数；按月份和生成遍数等权计算MAE。RMSE：Qwen {f(base,'center_rmse_pp')}、V3.2 {f(new,'center_rmse_pp')}、照抄 {f('carry','center_rmse_pp')}pp。</p>
<figure><img src="figures/monthly_models.png" alt="四期真人、Qwen、V3.2和照抄的中位数及分布W1"><figcaption>两遍生成不计作两倍人数；四个时点不连续，折线不代表中间月份的实际轨迹。</figcaption></figure>
<h2>3. 原有信念保留与跨月更新</h2><p>变化W1：Qwen {f(base,'delta_w1_pp')}、V3.2 {f(new,'delta_w1_pp')}、照抄 {f('carry','delta_w1_pp')}pp。按本人上期预期分组，可以查看高预期人群是否仍被推向中间；该条件差距不能单独识别模型内部推理。</p>
<p>上期预期≥8%的{s['prior_groups']['8_or_above']['person_months']}个人月，真人本期组均值{high[base]['truth_mean_pp']:.3f}%，Qwen为{high[base]['model_mean_pp']:.3f}%，V3.2为{high[new]['model_mean_pp']:.3f}%。低先验&lt;2%的人群，V3.2的组均值反而比Qwen更偏低；改善不是每一项条件偏差都缩小。</p>
<figure><img src="figures/conditional_models.png" alt="四个先验组的条件回答及人群IQR、变化分布W1"><figcaption>不同组跨月的平均仅基于该组实际有支持的格子；人数、ESS和稀疏标记见聚合JSON。</figcaption></figure>
<h2>4. Q8及统计边界</h2><p>Q8单独评价，共同支持{s['common_q8_person_months']}个人月。Q8群体中位数MAE：Qwen {q8[base]['q8_center_mae_pp']:.3f}、V3.2 {q8[new]['q8_center_mae_pp']:.3f}pp；不能与Q9主成绩混用。</p>
<p>个人概率表达也更接近：通缩各档全填0的加权人数占比，Qwen为{prob[base]['zero_deflation_rate']*100:.1f}%，V3.2为{prob[new]['zero_deflation_rate']*100:.1f}%，真人为{prob[base]['real_zero_deflation_rate']*100:.1f}%。每人内部的概率密度IQR均值为{prob[base]['individual_density_iqr_mean_pp']:.2f}→{prob[new]['individual_density_iqr_mean_pp']:.2f}pp，真人{prob[base]['real_individual_density_iqr_mean_pp']:.2f}pp；这表示每个人自己的不确定性，与跨人IQR是不同指标。</p>
<p><strong>与Qwen相比，四个月中心MAE、W1都改善；与照抄相比仍不能说稳定胜出。</strong>去掉2022-06，V3.2中心MAE为{leave_center[new]:.3f}，照抄为{leave_center['carry']:.3f}pp，优势仅约{leave_center['carry']-leave_center[new]:.3f}pp。总体W1和个人MAE仍落后于照抄，变化W1也不是逐月都改善。</p>
<p>V3.2减Qwen的配对95%区间：{ci_text}。按人聚类、固定这四个月的区间不能代表跨月份总体的不确定性。旧Qwen不是同期随机生成的控制，完整训练截止与托管权重未获固定证明。未在这四个月拟合最终组合权重，不能据样本内最优组合宣布预测成功。</p>
{repeat_text}
<h2>执行与复现</h2><p>新增{fee['new_requests']}次，接口错误{fee['new_response_errors']}次；Q9原始合法{raw_ok}/768，等比例归一化{normalized}份。新增回包报告费用${fee['api_reported_new_cost_usd']:.6f}，含此前失败预留的总记账${fee['campaign_spent_or_reserved_usd']:.6f}／$4。新批调用{fee['new_api_seconds']/60:.1f}分钟、最多{fee['max_concurrency']}并发，无自动重试。早先AtlasCloud的18次尝试单列，其中5份有效回答全部排除于本轮成绩。</p>
<p><a href="summary.json">聚合结果与分组</a> · <a href="cost_receipt.json">费用与运行记录</a> · <a href="../v32_results_20261021.md">完整结果与复算</a>{diagnostic_link} · <a href="../v32_siliconflow_plan.md">本轮配置</a></p>
<p class="meta">计分输入：{html.escape(str(source.relative_to(ROOT)))}。本页与JSON只有聚合，不发布逐人画像、提示或回答。</p></main></html>'''
    # Only aggregate content is published; profile/cases and raw messages stay private.
    # Group-month cells with few people are kept private; publish pooled groups
    # and sparse-cell counts, not potentially identifying one-person outcomes.
    public_groups={k:{key:value for key,value in group.items() if key!='cells'}
                   for k,group in s['prior_groups'].items() if group['unique_persons']>=8}
    trial=ROOT/json.loads((ledger/'protocol.json').read_text())['call_ledger_parent']
    protocol_hash=json.loads((trial/'manifest.json').read_text())['protocol_sha256']
    aggregate=dict(status=s['status'],protocol_sha256=protocol_hash,
        months=months,arms=arms,metrics=metrics,monthly=monthly,prior_groups=public_groups,
        common_q9_person_months=r['person_months'],unique_persons=r['unique_persons'],
        common_q8_person_months=s['common_q8_person_months'],q8=q8,q9_expression=prob,paired_intervals=s['paired_intervals'],
        coverage=s['coverage'],scorable_q9_by_arm=scorable,source_evaluation=str(source.relative_to(ROOT)))
    (dest/'index.html').write_text(text)
    (dest/'summary.json').write_text(json.dumps(aggregate,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (dest/'cost_receipt.json').write_text(json.dumps(fee,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    if repeat_public is not None:
        (dest/'repeat_summary.json').write_text(json.dumps(repeat_public,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    if diagnostic_public is not None:
        (dest/'diagnostics.json').write_text(json.dumps(diagnostic_public,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print('Published aggregate report:',dest)


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
    import studies
    studies.__path__=[str(ROOT/'studies'),*studies.__path__]
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--ledger',type=Path);parser.add_argument('--dest',type=Path,required=True)
    parser.add_argument('--diagnostics-only',action='store_true');parser.add_argument('--repeat-summary',type=Path)
    parser.add_argument('--diagnostics-summary',type=Path)
    a=parser.parse_args()
    if a.diagnostics_only:print(cached_diagnostics(a.source,a.dest))
    else:
        if a.ledger is None:parser.error('Publication requires --ledger')
        publish(a.source,a.ledger,a.dest,a.repeat_summary,a.diagnostics_summary)
