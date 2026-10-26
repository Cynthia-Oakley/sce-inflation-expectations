"""National-only evaluation in a separate process after recent-B generation."""
from collections import defaultdict,Counter
from datetime import datetime,timezone
from html import escape
import csv,json
from pathlib import Path

from .frozen_batch import ROOT,read_json,dump,sha
from .state_continuity_execution import verify
from ..evaluation.metrics import distribution_summary,headline_errors
from ..evaluation.cognition import _score_bins

CATALOG=ROOT/'data/evaluation/sce_baselines_latest_20261007/aggregate_inputs.json'


def evaluate(folder):
    folder=Path(folder);p,_=verify(folder/'package');receipt=read_json(folder/'combined/receipt.json')
    if receipt['main_logical_positions']!=p['planned_calls']:raise ValueError('Complete main scope required for national evaluation')
    pop=read_json(ROOT/p['population_preflight']/'selected_proxy_population_private.json')
    plans={r['month']:r for r in read_json(ROOT/p['population_preflight']/'monthly_input_plan.json')}
    # Target values are first opened by this evaluation process, after generation.
    releases={r['reference_period']:r for r in read_json(CATALOG)['headline_releases']}
    groups=defaultdict(list)
    for line in (folder/'combined/positions_private.jsonl').read_text().splitlines():
        row=json.loads(line);groups[row['month']].append(row)
    score_cache={};monthly=[];failures=Counter();sources={str(CATALOG.relative_to(ROOT)):sha(CATALOG)}
    def score(bins):
        key=tuple(bins)
        if key not in score_cache:score_cache[key]=_score_bins(bins)
        return score_cache[key]
    for month in p['months']:
        weights={r['persona']['agent_id']:r['analysis_weight'] for r in pop[month]};rows=groups[month]
        if len(rows)!=512 or len({r['agent_id'] for r in rows})!=512 or set(weights)!={r['agent_id'] for r in rows}:raise ValueError('Fixed B roster mismatch')
        initial=read_json(ROOT/p['input_templates']/month/'initial_states_private.json')
        means=[];w=[];q8=[];actual=[];actualw=[];prior=[]
        for r in rows:
            aid=r['agent_id'];weight=weights[aid];state=r['state_after'];updated=state['transition']['field_updated_from_model']
            view=score(state['fields']['q9']['value']);fallback=False
            if view['mean'] is None:
                view=score(initial[aid]['fields']['q9']['value']);fallback=True;failures['q9_density_fallback']+=1
            if view['mean'] is None:raise ValueError('Unscorable assigned prior must be disclosed, not dropped')
            means.append(view['mean']);w.append(weight);q8.append(state['fields']['q8']['value'])
            prior.append(score(initial[aid]['fields']['q9']['value'])['mean'])
            failures['q8_retained_prior']+=not updated['q8'];failures['q9_retained_prior']+=not updated['q9']
            if updated['q9'] and not fallback:actual.append(view['mean']);actualw.append(weight)
        ref=f'{month[:4]}-{month[4:]}';truth=releases[ref]
        if sha(ROOT/truth['source_file'])!=truth['source_sha256']:raise ValueError('Target national archive changed')
        sources[truth['source_file']]=truth['source_sha256']
        sim=distribution_summary(means,w);baseline=plans[month]['last_public_national_anchor']
        alpha=p['frozen_combination_simulation_share']
        monthly.append({'month':int(month),'as_of':plans[month]['as_of'],'truth_pp':truth['value_pp'],'sim_pp':sim['median_pp'],
            'anchor_pp':baseline['value_pp'],'anchor_reference_period':baseline['reference_period'],
            'frozen_combination_pp':(1-alpha)*baseline['value_pp']+alpha*sim['median_pp'],
            'prior_median_pp':distribution_summary(prior,w)['median_pp'],
            'sim_cross_person_iqr_pp_descriptive_only':sim['iqr_pp'],'sim_q8_median_pp_descriptive_only':distribution_summary(q8,w)['median_pp'],
            'usable_model_q9_only_median_pp_sensitivity':distribution_summary(actual,actualw)['median_pp'] if actual else None,
            'usable_model_q9_n':len(actual),'fixed_n':512,'truth_published_date':truth['published_date']})
    result={'status':'completed_recent_B_national_only_evaluation','completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'months':len(monthly),'new_api_calls':0,'research_line':p['research_line'],'strict_B_eligible':False,
        'model':headline_errors([r['sim_pp'] for r in monthly],[r['truth_pp'] for r in monthly]),
        'persistence':headline_errors([r['anchor_pp'] for r in monthly],[r['truth_pp'] for r in monthly]),
        'frozen_combination':headline_errors([r['frozen_combination_pp'] for r in monthly],[r['truth_pp'] for r in monthly]),
        'combination_simulation_share':p['frozen_combination_simulation_share'],
        'model_win_months':sum(abs(r['sim_pp']-r['truth_pp'])<abs(r['anchor_pp']-r['truth_pp'])-1e-10 for r in monthly),
        'monthly':monthly,'quality':dict(failures),'call_receipt':receipt,'source_sha256':sources,
        'limits':['Historical as-of input backtest run after outcomes were released; not a new ex-ante sealed forecast.',
                  'No recent person-level truth; simulated IQR/Q8 are descriptive, not micro accuracy.',
                  'Source P/prior use declared source-wave eligibility and calibrate only to already public past national Q9; micro historical byte vintages are not certified.',
                  'Historical news/policy text versions and model knowledge cutoff not fully verified.',
                  '11 dependent monthly outcomes are a small evaluation window; no parameter re-fitting.']}
    out=folder/'evaluation';out.mkdir();dump(out/'summary.json',result)
    with (out/'monthly_national.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(monthly[0]));writer.writeheader();writer.writerows(monthly)
    make_figure(monthly,out)
    model=result['model']['mae_pp'];base=result['persistence']['mae_pp']
    body=f'<h1>近期11个月SCE时点回测</h1><p>模型MAE {model:.3f}pp；持续性基线 {base:.3f}pp；胜出 {result["model_win_months"]}/11期。</p><p>代理人口与合成先验；微观可得性按封存规则处理，历史文件/文本版本及模型知识边界未完全认证。</p><img src="national_results.png" alt="逐月全国SCE与误差"><p>微观IQR和Q8仅描述模拟输出，不报告真人微观拟合。</p><a href="summary.json">完整汇总</a> · <a href="monthly_national.csv">逐月数据</a>'
    (out/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>SCE近期回测</title><style>body{max-width:1080px;margin:30px auto;padding:20px;font-family:"Times New Roman","Kaiti SC",serif;color:#242424;line-height:1.8}img{width:100%}a{color:#0078b5}</style>'+body+'</html>')
    return result


def make_figure(rows,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib import font_manager
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC'],'axes.unicode_minus':False})
    x=np.arange(len(rows));fig,axes=plt.subplots(2,1,figsize=(11,6),sharex=True,layout='constrained')
    for key,label,color,style in [('truth_pp','官方SCE','#242424','-'),('anchor_pp','最后公开值','#777777','--'),('sim_pp','模型','#c76800','-')]:
        axes[0].plot(x,[r[key] for r in rows],style,label=label,color=color,marker='o',markersize=3)
    axes[0].set_ylabel('未来12个月通胀预期（%）');axes[0].legend(frameon=False)
    axes[1].bar(x-.16,[abs(r['sim_pp']-r['truth_pp']) for r in rows],width=.32,color='#c76800',label='模型')
    axes[1].bar(x+.16,[abs(r['anchor_pp']-r['truth_pp']) for r in rows],width=.32,color='#777777',label='基线')
    axes[1].set_ylabel('绝对误差（pp）');axes[1].set_xticks(x,[str(r['month'])[:4]+'-'+str(r['month'])[4:] for r in rows],rotation=40);axes[1].legend(frameon=False)
    for ax in axes:ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'national_results.png',dpi=180);plt.close(fig)
