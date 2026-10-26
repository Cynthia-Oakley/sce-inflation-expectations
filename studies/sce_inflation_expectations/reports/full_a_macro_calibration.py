"""Separate HTML explanation of official targets, scaling and ARX calibration."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from ..experiments.full_a_core_normal import ROOT, checked, read, sha, write

LABELS={
 'persistence':'官方历史持续性', 'Core_pure':'未扩展Core原始模拟',
 'CoreNormal_tau8_pure':'扩展后原始模拟',
 'Core_blend_mse':'未扩展：MSE拟权组合','CoreNormal_tau8_blend_mse':'扩展后：MSE拟权组合',
 'CoreNormal_tau8_blend_mae':'扩展后：MAE拟权组合',
 'Core_AR_public_level':'历史SCE线性校正',
 'Core_macro_without_sim':'历史SCE＋CPI，不含模拟',
 'Core_macro_plus_sim':'历史SCE＋CPI＋Core模拟',
 'Core_regime_without_sim':'历史SCE＋CPI＋状态，不含模拟',
 'Core_regime_plus_sim':'历史SCE＋CPI＋状态＋Core模拟交叉',
 'CoreNormal_tau8_macro_plus_sim':'历史SCE＋CPI＋扩展模拟',
 'CoreNormal_tau8_regime_plus_sim':'历史SCE＋CPI＋状态＋扩展模拟交叉',
 'Core_blend_mae':'未扩展：MAE拟权组合'}


def build(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'docs/workstreams'):
        raise ValueError('Fresh workstream report required')
    manifest=read(source/'manifest.json');checked(source,manifest['files_sha256']);checked(ROOT,manifest['source_sha256'])
    s=read(source/'summary.json');r=s['results'];out.mkdir(parents=True)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti','Arial Unicode MS'],
                         'axes.unicode_minus':False,'font.size':11})
    keys=['persistence','Core_blend_mse','CoreNormal_tau8_blend_mse',
          'Core_macro_without_sim','CoreNormal_tau8_macro_plus_sim','CoreNormal_tau8_regime_plus_sim']
    values=[r[k]['later34']['mae_pp'] for k in keys]
    fig,ax=plt.subplots(figsize=(10,5),constrained_layout=True)
    bars=ax.barh(np.arange(len(keys)),values,color=['#777777','#5A8CB5','#1764AB','#B58A68','#C77730','#BD530D'])
    ax.bar_label(bars,labels=[f'{v:.4f}' for v in values],padding=5)
    ax.set_yticks(np.arange(len(keys)),[LABELS[k] for k in keys]);ax.invert_yaxis()
    ax.set(xlabel='全国Q9中位数MAE（pp，越低越好）',xlim=(0,.25),
           title='后34个月：复杂校准暂未超过简单组合（2023-01—2025-10）')
    ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
    fig.savefig(out/'later_mae.png',dpi=160);plt.close(fig)

    with (source/'monthly_predictions_public.csv').open() as f: monthly=list(csv.DictReader(f))[48:]
    fig,ax=plt.subplots(figsize=(11,4.4),constrained_layout=True);x=np.arange(len(monthly))
    for key,label,color,style in [('truth_pp','官方SCE','#222222','-'),('persistence','官方历史持续性','#888888','--'),
       ('CoreNormal_tau8_blend_mse','扩展后简单组合','#1764AB','-'),
       ('CoreNormal_tau8_regime_plus_sim','含状态与交叉项','#C75B12','-')]:
        ax.plot(x,[float(v[key]) for v in monthly],label=label,color=color,ls=style,lw=1.8)
    ticks=np.arange(0,len(monthly),4)
    ax.set_xticks(ticks,[monthly[i]['month'][:4]+'-'+monthly[i]['month'][4:] for i in ticks],rotation=25)
    ax.set(xlabel='目标调查月份',ylabel='一年期预期通胀率（%）',title='同一后期窗口的逐月预测：固定早48个月参数')
    ax.legend(ncol=2);ax.grid(alpha=.18)
    fig.savefig(out/'later_series.png',dpi=160);plt.close(fig)

    rows=''
    for k in ['persistence','Core_pure','CoreNormal_tau8_pure','Core_blend_mse','CoreNormal_tau8_blend_mse',
               'CoreNormal_tau8_blend_mae','Core_AR_public_level','Core_macro_without_sim',
               'CoreNormal_tau8_macro_plus_sim','Core_regime_without_sim','CoreNormal_tau8_regime_plus_sim']:
        a=r[k];rows+=f'<tr><th>{LABELS[k]}</th><td>{a["training48"]["mae_pp"]:.4f}</td><td>{a["later34"]["mae_pp"]:.4f}</td><td>{a["later34"]["rmse_pp"]:.4f}</td></tr>'
    cn=s['fits']['CoreNormal_tau8_blend_mse'];cnr=r['CoreNormal_tau8_blend_mse'];b=s['measurement_bridge']
    html=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SCE真值口径、缩放与组合指标</title><style>body{{margin:0;background:#faf9f5;color:#222;font:18px/1.8 "Times New Roman","Kaiti SC","STKaiti",serif}}
main{{max-width:1120px;margin:auto;padding:32px 24px}}h1{{font-size:30px;line-height:1.4}}h2{{font-size:23px;margin-top:32px}}p{{margin:12px 0}}
.lead{{font-size:21px;border-left:4px solid #1764AB;padding:15px 20px;background:#edf2f6}}.note,figcaption{{font-size:15px;color:#555}}img{{width:100%;height:auto}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;background:white}}td,th{{padding:9px;border-bottom:1px solid #ddd;text-align:right}}th:first-child{{text-align:left}}a{{color:#1764AB}}code{{overflow-wrap:anywhere}}</style>
<main><small>SCE · A82历史重建的离线宏观校准 · 0新API · 0新密度拟合 · 原结果保留</small>
<h1>全国主结果对照官方SCE；当前简单组合优于本轮复杂校准</h1>
<p class="lead">固定原τ=8扩展，MSE在早48个月拟得模拟权重{cn['simulation_weight']*100:.2f}%。后34个月MAE为{cnr['later34']['mae_pp']:.4f}pp，持续性基线为{r['persistence']['later34']['mae_pp']:.4f}pp。加入CPI、状态和交叉项的初步方案暂未超过简单组合；不据本页自动切换配置，τ约202不采用。</p>
<h2>1．真值与基线是两个不同概念</h2>
<p>全国真值采用纽约联储发布的当月SCE一年期预期通胀率，主表沿用新闻稿首发的一位小数值。持续性基线则使用原登记截止前最后公开的官方SCE值；因发布时间先后，有时不是紧邻上个月。两者都不是本项目自行重算的全国SCE。</p>
<p>官方说明预期通胀率来自各人Q9密度均值的中位数，Q8点预测另列。参见<a href="https://www.newyorkfed.org/microeconomics/sce/sce-faq">纽约联储FAQ</a>。本项目模型和真人微观比较共同使用冻结近似计分器，不能声称完全复刻官方密度拟合与汇总。</p>
<p>把真人原始答卷按本项目算法重算，再与官方全国值比较，82个月平均绝对差{b['mae_pp']:.4f}pp，最大差{b['max_absolute_gap_pp']:.4f}pp。它包含密度拟合、样本清洗、权重、分位数及公布精度等差别，不能全归因于某一项，也不能直接从模型MAE里减去。</p>
<p>同算法真人目标下，原Core与扩展的中心MAE为{b['core_mae_against_common_score_human_pp']:.4f}和{b['normal_mae_against_common_score_human_pp']:.4f}pp；官方目标对应0.2984和0.3014pp。主报告保留官方结果，微观机制评价另报同算法结果，不按成绩选择目标。</p>
<h2>2．过采样、降权与Normal怎样衔接</h2>
<p>实际Core名单沿54格采样，每个有人的小格尽量保底8名，余量按人口质量分配，且不重复抽同一人。格内抽样概率π=n/N；设计权重为原调查权重/π，再校准回真实格质量。因此小格在Core中可占较大比例，但汇总不会增加其人口占比。这套缩放在原512人抽样时已经存在。</p>
<p>Normal扩展估计条件分布时复用Core校准权重；计算完整有限人口时，实际Core只保留自己的原始调查权重，Normal也只贡献自身质量一次。不会把已放大到全人口的Core，再与完整Normal重复叠加。98,382个人月仍只有41,970个真实模型Core，统计扩展不增加独立信息。</p>
<p>τ是相邻格的等效先验强度，不是202个真实邻居；应与每格有效Core人数比较，而非与全月1300比较。若一格有效10人，τ=202使同格在Normal条件分布中仅占4.7%，确实是很强的汇聚，不能仅凭训练误差略低就采用。</p>
<h2>3．扩展后的加权平均效果</h2>
<p>组合形式为：历史官方SCE×(1−λ)＋当月模拟SCE×λ。只在2019-01—2022-12拟合λ，检查2023-01—2025-10。MAE拟权时λ=0，没有保留模拟；MSE拟权时λ={cn['simulation_weight']:.6f}，后期MAE{cnr['later34']['mae_pp']:.6f}、RMSE{cnr['later34']['rmse_pp']:.6f}pp。未扩展组合对应0.184125/0.256272pp，因此扩展没有带来新的组合收益。</p>
<p>扩展组合全82个月MAE为{cnr['all82_descriptive']['mae_pp']:.6f}pp，持续性为{r['persistence']['all82_descriptive']['mae_pp']:.6f}pp；全期包含训练月份，不能作为独立检验。后期MAE差值的六个月块区间跨零，改善仍有限。</p>
<h2>4．复杂模型：先做受控的小比较</h2>
<p>用已公开历史SCE作锚，预测当月相对该锚的变化。候选因子为历史SCE水平、最新已发布CPI同比与锚的差、CPI同比相对前次发布的变化、模拟与锚的差。状态方案另加CPI≥4%的预设虚拟变量及其与模拟差值的交叉项；阈值未优化。</p>
<p>所有线性方案使用岭回归（含不惩罚的截距），正则强度仅在早36个月训练、随后12个月验证选择，再用早48个月重估并封存系数。后34个月没有用于选强度。CPI使用原月度参考截止前的BLS首发；不拿尚未发布的目标月实际CPI作因子。宏观不含模拟的模型作为配对对照，避免把CPI的贡献算成模拟的贡献。</p>
<figure><img src="later_mae.png" alt="后34月简单组合与CPI及交叉项校准的全国MAE"><figcaption>2023-01—2025-10，34个月等权，纵向标签区分方法，横轴单位pp且从0开始。蓝色为简单组合，橙色为更复杂的统计校准。</figcaption></figure>
<table><thead><tr><th>模型</th><th>训练48月MAE</th><th>后34月MAE</th><th>后34月RMSE</th></tr></thead><tbody>{rows}</tbody></table>
<figure><img src="later_series.png" alt="官方SCE与固定参数的简单及复杂预测序列"><figcaption>单位%；均为同一后期窗口。参数来自早48个月；这不是新封存的未来预测。</figcaption></figure>
<h2>5．怎样理解与采用</h2>
<p>这轮复杂模型在训练集看起来更好，但后期没有超过简单组合。在相同CPI线性结构中加入扩展模拟，MAE由0.2142变为0.2149pp；含状态与交叉项时约0.2094pp。只能说本轮预设的小组方案未提供更好的后期MAE，不能据此否定所有时序方法。当前不再追着后期误差调虚拟变量或挑年份。</p>
<p>宏观拟合的独立时间样本只有82个月，不是98,382个人月。A模拟含个人日期的信息，CPI与官方历史锚按原共享参考截止；组合仍属历史重建诊断，不等于同一截止前可实现的严格B预测。两段历史都曾被查看，后34月不称新的盲测。以上结果是衍生预测指标的性能，不是LLM个体行为机制已获得验证。</p>
<p><a href="../README.md">方法与全部复算入口</a> · <a href="../results_v1/index.html">原Core＋Normal报告</a> · <a href="../tau_sensitivity_v1/index.html">τ宽范围搜索</a></p>
<p class="note">来源：{source.relative_to(ROOT)}；逐月公开宏观输入/预测、训练内选参及系数全部单独保留。官方FAQ核查日2026-10-26。原A/B生成、τ8预测、τ敏感性、报告v05和研究包v02不覆盖。</p></main></html>'''
    (out/'index.html').write_text(html)
    write(out/'readout.json',s)
    write(out/'manifest.json',dict(source_manifest_sha256=sha(source/'manifest.json'),renderer_sha256=sha(Path(__file__)),
          files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print(out/'index.html')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();build(a.source,a.out)


if __name__=='__main__':main()
