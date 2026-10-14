#!/usr/bin/env python3
"""Render aggregate, zero-API mechanism evidence into the existing reading page."""
import argparse
import json
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'outputs/.matplotlib-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

def render(audit,frequency,out):
    out=out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('fresh ignored output directory required')
    data=json.loads((audit/'summary.json').read_text());freq=json.loads((frequency/'summary.json').read_text())
    out.mkdir(parents=True)
    public={k:data[k] for k in ['status','completed_at','new_api_calls','source_sha256','private_frame_sha256','analysis_code_sha256','official_associations','expanded_compression','limits']}
    public['frequency_preparation']=freq
    target=ROOT/'docs/literature/sce/heterogeneity_and_probability/behavior_mechanism_evidence_summary_20261014.json'
    target.write_text(json.dumps(public,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    models=data['official_associations']['models']
    keys=['gender=Female','_AGE_CAT=Over 60','_EDU_CAT=High School','_HH_INC_CAT=Under 50k','_NUM_CAT=Low']
    labels=['Female vs male','Over 60 vs under 40','High school vs college','Under 50k vs over 100k','Low vs high numeracy']
    fig,axes=plt.subplots(1,3,figsize=(13,4.7),sharey=True)
    for ax,name,title in zip(axes,['q8_point','q9_mean','q9_iqr'],['Q8 point expectation','Q9 density mean','Q9 within-person IQR']):
        vals=[models[name]['coefficients'][k] for k in keys]
        b=np.array([v['estimate'] for v in vals]);lo=np.array([v['ci95'][0] for v in vals]);hi=np.array([v['ci95'][1] for v in vals])
        ax.errorbar(b,np.arange(len(keys)),xerr=np.array([b-lo,hi-b]),fmt='o',color='#28655f',capsize=4)
        ax.axvline(0,color='#aaa',lw=1);ax.set_title(title);ax.set_xlabel('Conditional mean difference (pp)');ax.grid(axis='x',alpha=.2)
    axes[0].set_yticks(np.arange(len(keys)),labels);axes[0].invert_yaxis()
    fig.suptitle('Official SCE, 2017-01 to 2025-10: demographic controls and month intercepts')
    fig.tight_layout();fig.savefig(out/'conditional_associations.png',dpi=150);plt.close(fig)
    periods=data['expanded_compression']['by_month'];months=sorted(periods)
    actual=[periods[m]['measures']['actual']['previous_position_slope'] for m in months]
    model=[periods[m]['measures']['self_update']['previous_position_slope'] for m in months]
    x=np.arange(len(months));fig,ax=plt.subplots(figsize=(10,4.2))
    ax.bar(x-.18,actual,.36,label='Observed respondents',color='#28655f');ax.bar(x+.18,model,.36,label='LLM with own history',color='#bf7750')
    ax.set_xticks(x,[m[:4]+'-'+m[4:] for m in months]);ax.set_ylabel('Within-month slope on own previous mean')
    ax.set_title('Persistence of relative personal position: descriptive, not a psychological weight')
    ax.grid(axis='y',alpha=.2);ax.legend();fig.tight_layout();fig.savefig(out/'prior_position.png',dpi=150);plt.close(fig)
    rel='../../../'+str(out.relative_to(ROOT))
    section=f'''<section id="behavior-mechanism-evidence" style="border-bottom:1px solid #ddd;padding-bottom:28px;margin-bottom:36px">
<h1>机制设计：已做数据检查和离线准备</h1>
<p><strong>本轮新增API调用0。人口特征的作用需要分开看：有些对应预期高低，有些主要对应不确定性；本人过去信念有更强的信息。</strong></p>
<h2>SCE控制变量检查</h2>
<p>2017年1月—2025年10月，106个月、130,216条受访者月记录。控制月份、年龄、教育、收入、数理能力、地区、就业和性别。图中是平均差异与按人聚类的95%区间，不是全国中位数，也不是因果贡献。</p>
<ul><li>女性Q8点预期平均高2.115pp，Q9个人密度均值高0.431pp，两者不能混用。</li>
<li>低数理能力Q9均值差−0.031pp、区间跨0；个人密度IQR却宽2.275pp。它更适合先从不确定性机制理解。</li>
<li>同样的96,683条相邻回访记录，人口变量对同月差异的解释比例约1.25%，加入本人上期信念后约32.77%。这是描述性解释，不是预测成绩。</li></ul>
<figure><img src="{rel}/conditional_associations.png" alt="人口字段对点预期、密度均值和个人不确定区间的不同关联"><figcaption>三项结果的有效样本略有不同。各项分开解释，不能据不同系数宣称某种问法的因果影响。</figcaption></figure>
<h2>模型仍压缩原有个人位置</h2>
<p>复用八期756个完整人月，按同人的可用生成取平均。上期较高者本期仍较高的关系，在模型中比真人弱；年龄、收入、数理能力组都看到这个现象。斜率是统计关系，不等于应注入的更新比例。</p>
<figure><img src="{rel}/prior_position.png" alt="八期真人与LLM的个人上期位置关系"><figcaption>同月去均值、同一完整样本、等人权重；不能唯一确定压缩来自措辞、信息还是模型。</figcaption></figure>
<h2>实际准备了什么？</h2>
<ol><li>CE Diary分类购买日数：2,835个家庭周、1,440个家庭，保留缺失、来源和周权重；各类日集合并集全部复现旧总日数。尚待条件匹配及价格类别对齐。</li>
<li>本人信念提示：明确“这是你当前判断的起点，回答不变是允许的”，其余P/E、上期回答与问卷保持。已生成完整离线对照预览，尚未真实测试。</li>
<li>频率提示：明确“高频购买类别的价格变化有更大影响”。后续先比较同一频率数据有无该说明，再比较人口匹配与置换。</li></ol>
<h2>Events与记忆怎样结合？</h2>
<p>事件触发与个人经历相关的联想，再影响信念调整。年龄机制继续保留；旧历史叙述失败不证明记忆没有作用。理解风格先做同人随机交叉；构造代表性人口时需要外部调查的条件分布，不能把随机比例称为真实美国比例。</p>
<p>性别差异通过购物分工传导有研究支持，但SCE没有直接购物频率；本轮只检验性别关联，尚未识别购物的中介作用。</p>
<p><a href="../../literature/sce/heterogeneity_and_probability/behavior_mechanism_evidence_20261014.md">完整解释、统计边界与下一步</a> · <a href="../../literature/sce/heterogeneity_and_probability/behavior_mechanism_evidence_summary_20261014.json">聚合结果</a></p>
</section>'''
    page=ROOT/'docs/workstreams/20261013_behavior/codex_expansion_diagnostic_20261014.html'
    html=page.read_text()
    if 'id="behavior-mechanism-evidence"' in html:
        html=re.sub(r'<section id="behavior-mechanism-evidence".*?</section>',lambda _:section,html,count=1,flags=re.S)
    else:html=html.replace('<main>','<main>'+section,1)
    page.write_text(html)
    print('Rendered two scientific figures and aggregate evidence; no API calls')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audit',type=Path,required=True);p.add_argument('--frequency',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();render(a.audit,a.frequency,a.out)
