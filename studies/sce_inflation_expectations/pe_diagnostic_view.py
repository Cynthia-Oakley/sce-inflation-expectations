"""Standalone scientific figures and a self-contained Chinese HTML review."""
import base64
import hashlib
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


def render(root, folder, page):
    data = json.loads((folder/'summary.json').read_text())
    font_path = Path('/System/Library/Fonts/STHeiti Medium.ttc')
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(font_path)).get_name()
    plt.rcParams.update({'axes.unicode_minus': False, 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    colors = {'real': '#242a30', 'sample': '#898d91', 'deepseek': '#2875a9', 'qwen': '#bd6e22'}
    months = list(data['selected20_deepseek'])
    ticks = np.arange(len(months))
    labels = [m[4:]+'月' for m in months]
    figures = []

    def finish(fig, name):
        path = folder/(name+'.png')
        fig.savefig(path, dpi=175, bbox_inches='tight'); plt.close(fig)
        figures.append(path)

    fig, axes = plt.subplots(2, 1, figsize=(11.8, 8), sharex=True)
    for ax, key, label, official in [(axes[0], 'point', 'Q8：点预测', 'official_point_median'),
                                      (axes[1], 'density', 'Q9：个人密度均值 → 人群中位数', 'official_density_median')]:
        ax.plot(ticks, [data['full_real_official_monthly'][m][official] for m in months], color=colors['real'], lw=2, label='全国真实：官方加权口径（参照）')
        ax.plot(ticks, [data['selected20_deepseek'][m][key]['matched_real']['median'] for m in months], '--', color=colors['sample'], label='同选中真人：等权、共同有效案例')
        for arm in ['deepseek', 'qwen']:
            ax.plot(ticks, [data['selected20_'+arm][m][key]['simulated']['median'] for m in months], 'o-', color=colors[arm], label=arm.title()+'：同20人旧输入')
        ax.set_ylabel('预期通胀（%）'); ax.set_title(label, loc='left'); ax.grid(alpha=.18); ax.legend(loc='upper left', fontsize=9)
    axes[1].set_xticks(ticks, labels); axes[1].set_xlabel('调查目标月份：2021年')
    fig.suptitle('先分清统计量：约0.5%来自Q9，不是同月模型的点预测', fontsize=14)
    fig.tight_layout(rect=[0,.035,1,.96])
    fig.text(.02,.008,'Q9双方同近似计分；每月18–20例；Q8每月20例。全国参照不等同于该小样本。旧全年Qwen含DeepSeek历史回答。',fontsize=9)
    finish(fig, 'year_q8_q9')

    fig, axes = plt.subplots(2,1, figsize=(11.8,7), sharex=True)
    for ax, key, ylabel in [(axes[0], 'raw_deflation_mass_median_pct', '通缩概率合计（%）'),
                           (axes[1], 'individual_point_minus_density_median_pp', '每人Q8减Q9中心（百分点）')]:
        real_key = 'raw_real_deflation_mass_median_pct' if ax is axes[0] else 'real_individual_point_minus_density_median_pp'
        ax.plot(ticks, [data['selected20_deepseek'][m][real_key] for m in months], '--', color=colors['sample'], label='同选中真人（各统计量的有效记录）')
        for arm in ['deepseek', 'qwen']:
            ax.plot(ticks,[data['selected20_'+arm][m][key] for m in months],'o-',color=colors[arm],label=arm.title())
        ax.set_ylabel(ylabel); ax.grid(alpha=.18); ax.legend(fontsize=9)
    axes[0].set_title('原始概率已经给了多少通缩可能性？不是只有拟合后的数字',loc='left')
    axes[1].set_title('点预测与概率回答中心的偏移：用于诊断，不要求两者相等',loc='left')
    axes[1].set_xticks(ticks, labels); axes[1].set_xlabel('调查目标月份：2021年')
    fig.tight_layout(); finish(fig, 'raw_probability_diagnostics')

    fig, ax = plt.subplots(figsize=(11.8,4.6))
    ax.plot(ticks,[data['old_month_inputs'][m]['latest_known_cpi_yoy_pct'] for m in months], 'o-', color=colors['deepseek'], label='旧E提供的最新已公布CPI：目标月前两个月')
    ax.plot(ticks,[data['old_month_inputs'][m]['contemporaneous_cpi_yoy_evaluation_only_pct'] for m in months], '--', color=colors['sample'],label='目标月实际CPI：后来公布，仅用于评价')
    ax.plot(ticks,[data['full_real_official_monthly'][m]['official_density_median'] for m in months],color=colors['real'],label='全国SCE：未来12个月预期（不是当期CPI）')
    ax.set_ylabel('同比/预期（%）'); ax.set_xlabel('调查目标月份：2021年'); ax.set_xticks(ticks,labels); ax.grid(alpha=.18)
    ax.legend(fontsize=9); ax.set_title('发布时间造成的信息滞后，和居民预期的差距是两件事',loc='left')
    fig.tight_layout(); finish(fig, 'information_time')

    fig, ax = plt.subplots(figsize=(11.8,4.6))
    keys = [('college','education_group','college','大学学历'),('high_numeracy','numeracy','high','高Numeracy'),
            ('over100k','household_income_band','over_100k','收入>10万美元'),('over60','age_group','Over 60','年龄60岁以上')]
    for offset, name, label, color in [(-.25,'full202101_weighted_reference','2021年1月完整真人（调查权重）',colors['real']),
                                     (0,'old73','旧固定73人（人数占比）',colors['deepseek']),
                                     (.25,'selected20','模型对照20人（人数占比）',colors['qwen'])]:
        p=data['population_marginals'][name]
        vals=[100*(p['shares'][ref] if 'shares' in p else p['marginal_counts'][field].get(value,0)/p['n']) for ref,field,value,_ in keys]
        bars=ax.bar(np.arange(4)+offset,vals,.23,label=label,color=color);ax.bar_label(bars,fmt='%.0f',fontsize=9,padding=3)
    ax.set_xticks(np.arange(4),[x[3] for x in keys]);ax.set_ylabel('组内占比（%）');ax.set_ylim(0,110);ax.legend(fontsize=9)
    ax.set_title('P的样本组成也不同：但与同选中真人比较后，模拟偏差仍存在',loc='left');ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.tight_layout();finish(fig,'population_composition')

    records, registry_hashes = [], {}

    def load(relative):
        p=root/relative;registry_hashes[relative]=hashlib.sha256(p.read_bytes()).hexdigest();return json.loads(p.read_text())

    def item(family, arm, month, simulated, real, n, temp):
        records.append({'family':family,'arm':arm,'month':str(month).replace('-',''),'n_common':n,'temperature':temp,
                        'simulated_median_pp':simulated['median'],'real_median_pp':real['median'],
                        'median_bias_pp':simulated['median']-real['median'],
                        'simulated_iqr_pp':simulated['iqr'],'real_iqr_pp':real['iqr'],
                        'iqr_fraction_of_real':simulated['iqr']/real['iqr'] if real['iqr'] else None})

    basket=load('outputs/sce-experience-trial-20261006T080038Z-594845/analysis/summary.json')
    names={'v2_baseline':'原基线','expression_shared':'答题视角','basket_shared':'篮子+视角','focus_only':'排序+视角','basket_focus':'篮子+排序+视角'}
    for m, arms in basket['monthly_by_arm'].items():
        for name,r in arms.items():
            q=r['q9']['matched_distribution_difference'];item('篮子/排序',names[name],m,q['simulated'],q['matched_real'],q['n_matched'],0)
    q1=load('outputs/sce_q1_analysis_20261006T143540Z_33c159ad/summary.json')
    for m,r in q1['months'].items():
        for name,a in r['arms'].items():item('财务经历Q1',{'baseline':'原基线','q1_state':'加入Q1'}[name],m,a['distribution'],r['matched_real'],r['n_complete_pairs'],.5)
    exposure=load('outputs/sce_exposure_analysis_20261006T151924Z_47735326/summary.json')
    for m,r in exposure['months'].items():
        q=r['Q9']
        for name,a in q['arms'].items():item('信息接触',{'shared':'共享信息','shuffled':'随机视图','matched':'匹配视图'}[name],m,a['distribution'],q['matched_real'],q['n_common'],.5)
    models=load('outputs/sce_model_followup_analysis_20261008_v3/summary.json')
    for m,r in models['months'].items():
        q=r['Q9']
        for name,a in q['arms'].items():item('新版E模型小试',{'deepseek_reference':'DeepSeek','llama':'Llama3.1','qwen':'Qwen2.5'}[name],m,a['distribution'],q['matched_real'],q['n_common'],.5)
    for m,r in data['new_v2_months'].items():
        q=r['monthly']['density'];item('新版共享E300人','基础模拟',m,q['simulated'],q['matched_real'],q['simulated']['n'],.5)
    order=list(dict.fromkeys((x['family'],x['arm']) for x in records))
    fig, axes=plt.subplots(1,2,figsize=(13,8.5),sharey=True)
    for offset,m,c in [(-.18,'202105',colors['deepseek']),(.18,'202106',colors['qwen'])]:
        group={(r['family'],r['arm']):r for r in records if r['month']==m}
        for ax,key in zip(axes,['median_bias_pp','iqr_fraction_of_real']):
            ax.barh(np.arange(len(order))+offset,[group[k][key] for k in order],.32,color=c,label=m[4:]+'月')
    axes[0].set_yticks(np.arange(len(order)),[f'{f}：{a}' for f,a in order]);axes[0].invert_yaxis()
    axes[0].axvline(0,color='#999999',lw=.8);axes[1].axvline(1,color='#999999',ls='--',lw=.8)
    axes[0].set_xlabel('模拟中位数减同样本人群真实中位数（百分点）');axes[1].set_xlabel('模拟人际IQR / 真人IQR（1=相同跨度）')
    axes[0].set_title('水平偏差');axes[1].set_title('人群回答是否过度集中？')
    for ax in axes:ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True);ax.legend(fontsize=9)
    fig.suptitle('已有机制实验汇总：每项只与其自己的配对真人比较',fontsize=13)
    fig.tight_layout(rect=[0,.025,1,.97]);fig.text(.02,.007,'不同实验样本/输入不同，不能据此跨实验排名。篮子组温度0，其余0.5；各组18–300有效人/月。',fontsize=9)
    finish(fig,'mechanism_trials')
    registry={'rows':records,'source_sha256':registry_hashes,'limits':'Each comparison uses its own matched real sample. Not a cross-trial causal ranking.'}
    (folder/'experiment_registry.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')

    images={p.stem:'data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode() for p in figures}
    sections=[('year_q8_q9','1. 先看清图里的量','全国真实线用于参照。公平的模型比较是同一20人；Q9和Q8分开展示。千问2—12月使用的是DeepSeek上期点预测。'),
              ('raw_probability_diagnostics','2. 差距在原始回答里已经出现','通缩概率直接由原始负通胀五档相加。点预测不必等于密度均值，偏移只是诊断。'),
              ('information_time','3. E的时间到底落在哪个月','旧全年as_of为上月末，因此最新CPI属于前两个月。灰色当期CPI后来才公布，未提供给旧模型。'),
              ('population_composition','4. P提供的是哪些人口背景','已提供年龄、教育、收入、地区、就业、住房、Numeracy。旧全年没有真实购物价格、消费篮子或终身通胀经历。'),
              ('mechanism_trials','5. 现有尝试是否解决了问题','各项实验的样本和条件不同，仅展示相对各自真人的偏差与分散度，不选“全项目最佳组”。')]
    body=''.join(f'<section><h2>{html.escape(title)}</h2><p>{html.escape(caption)}</p><img src="{images[key]}" alt="{html.escape(title)}"></section>' for key,title,caption in sections)
    # Inputs are common public facts + generated answers; personal P combinations are removed.
    inputs={**{m:{'version':'旧全年4信号','as_of':r['as_of'],'input':r['actual_input_excerpt_without_persona'],
                    'signals':r['signals']} for m,r in data['old_month_inputs'].items()},
            **{'new'+m:{'version':'新版77信号+新闻摘要','as_of':r['as_of'],'input':r['actual_input_excerpt_without_persona'],
                       'signals':r['latest_signals']} for m,r in data['new_v2_months'].items()}}
    options=''.join(f'<option value="{k}">{v["version"]}：{k.replace("new","")}</option>' for k,v in inputs.items())
    payload=json.dumps(inputs,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SCE：先理解P/E与模拟差距</title><style>
body{font:16px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#232b32;margin:0;background:#fafbfc}
main{max-width:1120px;margin:auto;padding:36px 28px}h1{font-size:28px;line-height:1.4}h2{font-size:22px;margin-top:42px}p{max-width:1000px}
section{border-top:1px solid #d5dce1;margin-top:30px;padding-top:8px}img{width:100%;display:block;background:white}a{color:#246d99}li{margin:8px 0}
.note{padding:14px 18px;background:#edf3f7;border-left:3px solid #2875a9}select{font:inherit;padding:6px 10px;margin:8px 0;max-width:100%}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 ui-monospace,monospace;padding:18px;background:#f1f3f5}summary{cursor:pointer;font-weight:600}
footer{font-size:13px;color:#5b636a;margin-top:40px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{border:1px solid #d5dce1;padding:8px;text-align:left}
</style><main><h1>先理解P/E与模拟结果的差距</h1><p>水上挽月 · 美国SCE · 2026-10-08 · 本轮零新增API调用</p>
<div class="note"><strong>先修正三处理解：</strong>0.5%是Q9中心，模型同月点预测约2%；旧全年含上期答案；千问收到了DeepSeek的历史答案。当前图不代表最新版77信号E的全年效果。</div>
BODY
<section><h2>6. 检查实际发送的E和问卷</h2><p>按月选择。英文文本来自归档实际请求，保留原来的单位问题与历史答案，方便审查；个体画像组合已移除。同比是过去12个月变化，环比是过去1个月变化。</p>
<select id="month">OPTIONS</select><p id="cutoff"></p><table><thead><tr><th>观测月份</th><th>原始值/单位</th><th>指标</th><th>发布时间</th></tr></thead><tbody id="signals"></tbody></table>
<details><summary>展开实际提示词（人口段已移除）</summary><pre id="prompt"></pre></details></section>
<section><h2>7. 理论如何帮助下一步设计？</h2><ul>
<li><strong>官方信息本身就是一种干预：</strong>每个人都收到同样的完整统计，可能使模拟更像“被告知CPI的受访者”，而现实调查没有统一灌输这份材料。先区分可得信息与实际接触信息。</li>
<li><strong>居民注意的是购买体验：</strong>食品/汽油等频繁购买和显著涨价可能比支出份额更重要。已有篮子不等于实际接触；不能仅通过按支出加权保证重建成功。</li>
<li><strong>人有自己的信念历史：</strong>长期经历与近期观察会影响更新，粗年龄标签和一张全国宏观表不等于这些经历。它也不等于提醒精确的上期问卷答案。</li>
<li><strong>先修技术，再验机制：</strong>单位/版本/时间/问卷口径 → 原始概率与点预测 → 个人经历/注意/更新。当前证据不能判定哪一种解释贡献最大。</li></ul>
<p>原始文献与具体改进顺序见同目录 <a href="SCE_PE_DIAGNOSTIC_20261008.md">中文核查说明</a>。不自动启动新的模拟实验。</p></section>
<footer>来源：纽约联储SCE、BLS首发记录、已归档实际请求与既有配对评价。全国官方口径与样本等权统计分别标注；Q9使用冻结研究近似，不宣称完全复刻官方数值。私人原始记录不嵌入本页面。</footer>
<script id="data" type="application/json">PAYLOAD</script><script>
const data=JSON.parse(document.getElementById('data').textContent),sel=document.getElementById('month');
function update(){const d=data[sel.value];document.getElementById('cutoff').textContent='截止时间：'+d.as_of;document.getElementById('prompt').textContent=d.input;
const body=document.getElementById('signals');body.replaceChildren();for(const s of d.signals){const tr=document.createElement('tr');for(const v of [s.reference_period,s.value+' '+s.unit,s.measure,s.published_at]){const td=document.createElement('td');td.textContent=v;tr.appendChild(td)}body.appendChild(tr)}}
sel.addEventListener('change',update);update();</script></main></html>'''
    page.write_text(template.replace('BODY',body).replace('OPTIONS',options).replace('PAYLOAD',payload))
    return registry, figures
