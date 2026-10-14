#!/usr/bin/env python3
"""Render frozen aggregate results into the existing project reading page."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import html
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.evaluation.metrics import quantile

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--analysis',type=Path,required=True)
    args=parser.parse_args();folder=args.folder.resolve();out=args.analysis.resolve()
    summary=json.loads((out/'summary.json').read_text());lock=json.loads((folder/'weight_lock.json').read_text());manifest=json.loads((folder/'manifest.json').read_text())
    dev=json.loads((folder/'development_cases_private.json').read_text());evaluation=json.loads((out/'cases_private.json').read_text())
    cases=[r for r in dev+evaluation if r['common']];months=sorted({r['month'] for r in cases})
    styles={'actual':('Observed','#202020'),'self_update':('LLM with history','#37659e'),'new_signal':('LLM without history','#a5593b'),'copy_previous':('Copy previous / selected program','#5c8757')}
    centers={k:[] for k in styles};iqrs={k:[] for k in styles}
    for month in months:
        for key in styles:
            med=[];spread=[]
            for repeat in (1,2):
                x=[r[key] for r in cases if r['month']==month and r['repeat']==repeat]
                med.append(quantile(x,None,.5));spread.append(quantile(x,None,.75)-quantile(x,None,.25))
            centers[key].append(float(np.mean(med)));iqrs[key].append(float(np.mean(spread)))
    labels=[str(m)[:4]+'-'+str(m)[4:] for m in months]
    for name,series,ylabel,title in [('centers',centers,'Inflation expectation (%)','Same-cohort Q9 centers'),('dispersion',iqrs,'Across-person IQR (percentage points)','Across-person spread')]:
        fig,ax=plt.subplots(figsize=(10,4.5))
        for key,(label,color) in styles.items():ax.plot(labels,series[key],marker='o',linewidth=1.8,color=color,label=label)
        ax.axvline(3.5,color='#999999',linestyle=':',linewidth=1);ax.set(xlabel='Selected survey month (not a continuous time series)',ylabel=ylabel,title=title)
        ax.legend(loc='best',fontsize=8);ax.grid(axis='y',alpha=.18);fig.tight_layout();fig.savefig(out/(name+'.png'),dpi=180);plt.close(fig)
    grid=lock['grid'];fig,ax=plt.subplots(figsize=(8,4.5))
    for key,label in [('sample_center_mae_pp','Center MAE'),('cross_section_w1_pp','Cross-person W1'),('delta_w1_pp','Change W1')]:
        ax.plot([r['alpha'] for r in grid],[r['aggregate'][key]/max(.001,lock['copy_previous'][key]) for r in grid],marker='o',label=label)
    ax.axhline(1,color='#999999',linestyle=':');ax.set(xlabel='Weight on new LLM signal',ylabel='Error / copy-previous error',title='Development-only weight selection');ax.legend();fig.tight_layout();fig.savefig(out/'weight_selection.png',dpi=180);plt.close(fig)
    run_receipts=[];tokens=Counter();statuses=Counter();models=set();fingerprints=set();mismatches=0
    for job in manifest['jobs']:
        d=ROOT/'outputs/local_runs'/job['run_id'];r=json.loads((d/'run_manifest.json').read_text());run_receipts.append(r)
        statuses.update(r['decisions_by_validation_status'])
        tokens['prompt']+=r['cost']['total_prompt_tokens'];tokens['completion']+=r['cost']['total_completion_tokens']
        expected={x['agent_id']:x['prompt_sha256'] for x in json.loads((folder/str(job['month'])/f"preview_{job['arm']}.json").read_text())}
        for line in (d/'llm_calls.jsonl').read_text().splitlines():
            row=json.loads(line);mismatches+=row['prompt_sha256']!=expected[row['agent_id']];models.add(row['returned_model']);fingerprints.add(row['system_fingerprint'])
    simulation_cost=sum(r['cost']['estimated_cost_usd'] for r in run_receipts)
    news=json.loads((ROOT/'outputs/sce_expanded_news_run_20261014_v1/completion_summary.json').read_text())
    receipt=dict(actual_calls=sum(r['cost']['call_count'] for r in run_receipts),answer_statuses=dict(statuses),
                 simulation_token_cost_estimate_usd=simulation_cost,news_token_cost_estimate_usd=news['peak_uncached_cost_estimate_usd'],
                 simulation_cap_usd=12.,news_cap_usd=2.5,total_token_cost_estimate_usd=simulation_cost+news['peak_uncached_cost_estimate_usd'],
                 actual_sent_prompt_hash_mismatches=mismatches,tokens=dict(tokens),returned_models=sorted(models),
                 system_fingerprints=sorted(fingerprints),automatic_retries=0,billing_note='Peak uncached token usage estimate, not provider bill',
                 common_person_months_unique=len({(r['month'],r['userid']) for r in cases}),common_generation_rows=len(cases),
                 generated_scorable_rows=sum(r['self_update'] is not None for r in dev+evaluation)+sum(r['new_signal'] is not None for r in dev+evaluation),
                 completed_at_utc=datetime.now(timezone.utc).isoformat())
    (out/'execution_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    if mismatches or receipt['actual_calls']!=3072:raise ValueError('Run accounting or input mismatch')
    columns=[('self_update','LLM自行更新'),('new_signal','不含本人先验的LLM'),('program','冻结程序方案＝上期延续'),('copy_previous','上期照抄基线'),('history_anchor_half','过去个人均值锚基线')]
    table=[]
    for key,label in columns:
        a=summary['results'][key]['aggregate']
        table.append('<tr><td>'+label+'</td>'+''.join(f'<td>{a[k]:.3f}</td>' for k in ['sample_center_mae_pp','cross_section_w1_pp','delta_w1_pp','cross_person_iqr_pp'])+'</tr>')
    real_iqr=summary['results']['self_update']['aggregate']['real_cross_person_iqr_pp']
    explanatory=(f'按预先登记的三项相对误差综合标准，开发期选择的新信息权重为{lock["alpha"]:.2f}。这次程序方案因此退回上期延续，并没有证明加入LLM新信号更好。'
                 '它不是说居民从不更新；真人在更新，但本次LLM信号和组合方式没有同时保护好总体中心、人际差异和更新分布。')
    text=f'''# 八期扩大实验：结果与解释（2026-10-14）

## 结论

{explanatory}

- 实际完成3072次模拟：八期各96人、两组、各两次。格式有效{statuses.get('valid',0)}份；无效{statuses.get('invalid',0)}份，错误{statuses.get('error',0)}份，没有重试。
- 新闻补标445批3555篇，约${news['peak_uncached_cost_estimate_usd']:.4f}；模拟约${simulation_cost:.4f}，合计约${receipt['total_token_cost_estimate_usd']:.4f}。均为高峰token估算，不是厂商账单。
- 1536条开发回答与1536条评价回答分开；权重锁定后才运行评价期。全部实际提示哈希与预览一致。
- 预先登记的评价筛选：{'通过' if summary['predefined_success_gate_passed'] else '未通过'}。不会用评价结果再改权重。

## 计量和统计解释

中位数MAE比较同一批受访者的模拟中心与真实中心；W1比较整个横截面分布；变化W1比较每个人本月减去本人上月后的变化分布。三个对象一起看，不能只把方差变大当成功。

每月两次生成先分别评分，再等权平均。两次生成不是两倍独立受访者。置信区间把同一人的两次生成一起重抽；另给四个月重抽的敏感性区间。只解释这些选定月份和回访者的条件结果，不外推为全国长期预测表现。小样本普通中心误差和全国80月基线不能混比。

概率结合先在十档原始概率上做，再用统一冻结计分器拟合；没有把拟合后的两个均值直接相加。因此这是部分调整的工程对照，不是严格贝叶斯更新，也不直接识别人类心理参数。开发期综合标准以照抄基线的每项误差归一化，三项相对改善同权；换别的损失权重可能选不同a，本次不事后改规则。

## 范围和边界

人口为当前真实画像中具有合法上期回答的回访者，P中权重恒为1，调查权重只在评价侧。八期不是连续月序列，首次参与者和B路线用自己模拟状态递推尚未验证。更早本人历史摘要仅在自行更新组进入LLM，程序组只直接保留上期原始概率，因此这是架构整体对照，不是纯程序权重的因果效应。

2020年4月的CE篮子使用2020Q4结构代理，2019信心来自2024历史汇总、原始公布日未知；它们明确作为回顾P的合成代理，不能搬作严格PIT预测输入。其他信心按此前已发布年度分布合成，2025已补官方问卷。E价格采用已归档的发布时间检查，政策取截止前声明，NYT文本vintage/纸面日期与EIA历史修订等已知局限仍保留。

模型请求与返回别名仍为deepseek-flash；别名和fingerprint不能证明固定权重或训练截止，没有排除模型世界知识泄漏。旧模型Action的p/e_snapshot_id是继承占位标签，真实输入追溯以本轮实际Population/Environment/Simulation文件哈希和源代码快照为准。

## 路径与复算

- 输入/协议/配置/权重封存：`{folder.relative_to(ROOT)}/`
- 32个真实运行与DuckDB：`outputs/local_runs/`，run_id列于输入manifest；个人原始资料只保留在忽略目录。
- 评价摘要与原始评分：`{out.relative_to(ROOT)}/summary.json`、cases_private.json。
- 复算（零API）：`python scripts/analyze_sce_expanded_trial.py evaluate --folder {folder.relative_to(ROOT)} --out outputs/<新的目录>`。
- 不重复select覆盖已封存权重，不重跑3072 API。准备v1/v2未完成，仅归档，不可当结果。
'''
    report=ROOT/'docs/workstreams/20261013_behavior/codex_expanded_results_20261014.md';report.write_text(text)
    def image_link(name):return '../../../'+str((out/(name+'.png')).relative_to(ROOT))
    section=f'''<section id="expanded-trial-results" style="border-bottom:1px solid #ddd;padding-bottom:24px;margin-bottom:36px">
<h1>八期扩大实验：已完成</h1><p><strong>{html.escape(explanatory)}</strong></p>
<p>八期各96人、两组、各两次，3072真实请求；模拟约${simulation_cost:.2f}，新闻约${news['peak_uncached_cost_estimate_usd']:.2f}，合计约${receipt['total_token_cost_estimate_usd']:.2f}（token估算，非账单）。无重试，全部实际提示与预览一致。</p>
<h2>固定规则后的四期评价</h2><p>2022-06、2023-06、2024-10、2025-09。误差单位均为百分点，越小越好。真人跨人IQR为{real_iqr:.3f}pp；表中IQR是人际差异，不能与一个人回答内的概率区间宽度混淆。</p>
<div style="overflow-x:auto"><table style="width:100%;min-width:650px"><thead><tr><th>方法</th><th>中位数MAE</th><th>人际分布W1</th><th>变化分布W1</th><th>人际IQR</th></tr></thead><tbody>{''.join(table)}</tbody></table></div>
<p>预登记筛选：<strong>{'通过' if summary['predefined_success_gate_passed'] else '未通过'}</strong>。这四期不用于重选权重。评价只针对同一批回访者，不是全国SCE headline，也不是B路线未来预测。</p>
<h2>中位数和人际差异</h2><img src="{image_link('centers')}" alt="八期同样本中位数" style="width:100%;height:auto"><img src="{image_link('dispersion')}" alt="八期跨人IQR" style="width:100%;height:auto">
<p>黑：真人；蓝：LLM自行利用历史；棕：不含本人先验的LLM；绿：照抄上期＝本次冻结程序方案。点为两次中位数/IQR的平均，评分为两次各自误差的平均；八点不是连续月度曲线。虚线分隔开发与评价。</p>
<h2>为什么没有选正的结合比例？</h2><img src="{image_link('weight_selection')}" alt="开发期结合比例选择" style="width:100%;height:auto"><p>三个误差都除以照抄基线的对应误差。加入新信号可减少更新分布误差，却增大中心与人际分布误差；按事先综合标准选中0。换评价权重可能改变选项，本轮保留原规则，避免看结果挑标准。</p>
<p>区间含义、输入时间边界、个人概率宽度和复算见<a href="codex_expanded_results_20261014.md">完整记录</a>；<a href="{image_link('summary').replace('summary.png','summary.json')}">原始聚合摘要</a>。下方保留开跑前诊断与计划，不能当本轮新结果。</p></section>'''
    page=ROOT/'docs/workstreams/20261013_behavior/codex_expansion_diagnostic_20261014.html';s=page.read_text()
    if 'id="expanded-trial-results"' in s:raise ValueError('Results section already installed; do not overwrite')
    if '<main>' not in s:raise ValueError('Existing reading layout not found')
    s=s.replace('<main>','<main>'+section,1);page.write_text(s)
    print('Rendered results, three figures, and actual-input/cost receipts')

if __name__=='__main__':main()
