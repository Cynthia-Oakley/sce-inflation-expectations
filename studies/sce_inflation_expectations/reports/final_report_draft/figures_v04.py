"""Join frozen A82 and B11 aggregate timelines for display, never fit jointly."""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/sce_research_report_figures_20261025_v04b'
A=ROOT/'outputs/sce_fullperiod_analysis_20261024_v1/summary.json'
B=ROOT/'outputs/sce_recent_b_readout_20261025_v2/summary.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if OUT.exists():raise ValueError('Fresh report-figure version required')
    a=json.loads(A.read_text())['official_national']['monthly']
    b=json.loads(B.read_text())['evaluation']['monthly']
    b=[{**r,'month':str(r['month'])[:4]+'-'+str(r['month'])[4:]} for r in b]
    assert len(a)==82 and len(b)==11 and a[-1]['month']=='2025-10' and b[0]['month']=='2025-11'
    rows=[{**r,'line':'A'} for r in a]+[{**r,'line':'B'} for r in b]
    assert len({r['month'] for r in rows})==93
    for left,right in zip(rows,rows[1:]):
        ly,lm=map(int,left['month'].split('-'));ry,rm=map(int,right['month'].split('-'))
        assert ry*12+rm==ly*12+lm+1
    OUT.mkdir()
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC'],'font.size':17,
                         'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    blue,orange,black,gray='#0078b5','#c76800','#242424','#777777'
    fig,axes=plt.subplots(2,1,figsize=(12.6,6.5),gridspec_kw={'height_ratios':[1.15,1]},layout='constrained')
    x=np.arange(93);ax=axes[0]
    ax.axvspan(81.5,92.5,color=orange,alpha=.08,zorder=0)
    ax.plot(x,[r['truth_pp'] for r in rows],color=black,linewidth=1.8,label='官方全国SCE')
    ax.plot(x,[r['anchor_pp'] for r in rows],color=gray,linestyle='--',linewidth=1.3,label='截止前公开值基线')
    ax.plot(np.arange(82),[r['sim_pp'] for r in a],color=blue,linewidth=1.8,label='A：历史重建（82期）')
    ax.plot(np.arange(82,93),[r['sim_pp'] for r in b],color=orange,marker='o',markersize=3,linewidth=1.8,label='B：时点回测（11期）')
    ax.axvline(81.5,color=black,linestyle=(0,(4,3)),linewidth=1.1)
    ax.text(81,6.45,'A / B 分界',ha='right',va='center',fontsize=14)
    ticks=[i for i,r in enumerate(rows) if r['month'].endswith('-01') and not r['month'].startswith('2026')]+[82,92]
    ax.set_xticks(ticks,[rows[i]['month'] for i in ticks],fontsize=13,rotation=20)
    ax.set(xlim=(-.5,92.5),ylabel='一年期通胀预期（%）',title='连续月份展示：两段输入制度分别评价')
    ax.legend(frameon=False,ncol=4,fontsize=13,loc='upper left')
    ax=axes[1];q=np.arange(11)
    ax.plot(q,[r['truth_pp'] for r in b],color=black,marker='o',markersize=4,label='官方SCE')
    ax.plot(q,[r['sim_pp'] for r in b],color=orange,marker='s',markersize=4,label='B模拟')
    ax.plot(q,[r['anchor_pp'] for r in b],color=gray,linestyle='--',marker='.',label='公开值基线')
    ax.set_xticks(q,[r['month'][2:] for r in b],fontsize=13)
    ax.set(ylabel='一年期通胀预期（%）',xlabel='目标调查月份',title='B段放大：MAE 模型0.241pp / 基线0.173pp')
    ax.legend(frameon=False,ncol=3,fontsize=14,loc='upper left')
    for ax in axes:ax.grid(axis='y',alpha=.17)
    fig.savefig(OUT/'national_A82_B11.png',dpi=210,bbox_inches='tight');plt.close(fig)
    data={'status':'report_only_joined_timeline','A_months':82,'B_months':11,'split':'2025-11',
          'rows':rows,'joint_error_metric_computed':False,'continuous_person_state_rollout':False,
          'new_api_calls':0,'new_q9_fits':0,
          'sources':{str(p.relative_to(ROOT)):sha(p) for p in (A,B,Path(__file__))},
          'scope':'A uses historical current P and own past answers where available; B uses lagged proxy P and calibrated synthetic prior. Display continuity is not identical inputs or recursive beliefs.'}
    (OUT/'figure_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'out':str(OUT),'A_months':82,'B_months':11,'new_api_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
