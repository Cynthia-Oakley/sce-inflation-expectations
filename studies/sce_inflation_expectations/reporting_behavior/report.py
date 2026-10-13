"""Render aggregate-only results; no raw respondent rows or API calls."""
from pathlib import Path
import argparse
from html import escape
import json
import os
import tempfile

os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'sce_reporting_mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from .analysis import MODELS,sha,dump


LABELS={'training_population':'训练期总体比例','demographic':'人口条件比例',
        'demographic_personal_history':'人口＋本人历史填法','previous_belief_shape':'上期信念形状',
        'previous_belief_shape_personal_history':'上期形状＋本人历史'}


def render(primary,controls,out):
    primary,controls,out=Path(primary).resolve(),Path(controls).resolve(),Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a new reading directory')
    out.mkdir(parents=True)
    s=json.loads((primary/'summary.json').read_text())
    c=json.loads((controls/'summary.json').read_text())
    plt.rcParams.update({'font.family':'Arial Unicode MS','axes.unicode_minus':False,'font.size':11,
                         'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    scores=s['periods']['evaluation']
    fig,ax=plt.subplots(figsize=(10,5.2))
    values=[scores[m]['brier'] for m in MODELS]
    colors=['#929c96','#929c96','#326a56','#929c96','#326a56']
    ax.barh([LABELS[m] for m in MODELS],values,color=colors)
    ax.invert_yaxis();ax.set_xlim(0,.37)
    for i,v in enumerate(values):ax.text(v+.004,i,f'{v:.3f}',va='center')
    ax.set_xlabel('归一化Brier概率预测误差（0—1，越小越好）')
    ax.set_ylabel('事先固定的预测方法')
    ax.set_title('预测下一次概率填法：本人历史有额外信息')
    fig.text(.02,.015,'来源：SCE原始十档问卷；2022-01至2025-10，46月、51,796人月；训练仅2017—2019。绿色为加入本人历史。',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1));fig.savefig(out/'pattern_prediction.png',dpi=160);fig.savefig(out/'pattern_prediction.svg');plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    control_values=[c['evaluation']['shape_and_count']['brier'],c['evaluation']['shape_count_personal_history']['brier'],c['permutation']['mean_brier']]
    axes[0].bar(['形状＋既往\n作答次数','再加本人\n历史填法','换成他人的\n相近条件历史'],control_values,color=['#929c96','#326a56','#929c96'])
    axes[0].set_ylabel('归一化Brier误差（越小越好）');axes[0].set_xlabel('补充对照方法');axes[0].set_ylim(0,.36)
    for i,v in enumerate(control_values):axes[0].text(i,v+.006,f'{v:.3f}',ha='center')
    axes[0].set_title('补充控制后仍有本人历史价值')
    z=s['observed_shapes']['zero_deflation_transition']
    zvalues=[z['probability_zero_now_if_zero_before']*100,z['probability_zero_now_if_positive_before']*100]
    axes[1].bar(['上期通缩\n概率为0','上期通缩\n概率大于0'],zvalues,color=['#326a56','#929c96'])
    axes[1].set_ylabel('本期也填0的比例（%）');axes[1].set_xlabel('上期回答条件');axes[1].set_ylim(0,100)
    for i,v in enumerate(zvalues):axes[1].text(i,v+2,f'{v:.1f}%',ha='center')
    axes[1].set_title('填0具有持续性，但原因未识别')
    fig.text(.02,.015,'来源：46月真实SCE。左图为看到主结果后登记的探索性补查，置换5次；右图43,266对严格相邻月。',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(out/'history_controls.png',dpi=160);fig.savefig(out/'history_controls.svg');plt.close(fig)

    r=s['rounding_reuse']['aggregate'];five=r['deterministic_5'];ten=r['deterministic_10'];rnd=r['balanced_random_5']
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    labels=['原回答','5%取整','10%取整','随机5%\n取整']
    cv=[five['original_center_mae_pp'],five['mapped_center_mae_pp'],ten['mapped_center_mae_pp'],rnd['mapped_center_mae_pp']]
    axes[0].bar(labels,cv,color=['#929c96','#326a56','#929c96','#929c96']);axes[0].set_ylim(0,.8)
    axes[0].set_ylabel('同样本中位数平均绝对误差（百分点）');axes[0].set_xlabel('机械测量情景');axes[0].set_title('计分中心会移动')
    for i,v in enumerate(cv):axes[0].text(i,v+.012,f'{v:.3f}',ha='center')
    iv=[five['original_person_iqr_pp'],five['mapped_person_iqr_pp'],ten['mapped_person_iqr_pp'],five['real_person_iqr_pp']]
    axes[1].bar(['原回答','5%取整','10%取整','真人'],iv,color=['#929c96','#929c96','#929c96','#326a56']);axes[1].set_ylim(0,7.2)
    axes[1].set_ylabel('不同人预期的中间50%跨度（百分点）');axes[1].set_xlabel('同一有效样本的分布');axes[1].set_title('人际差异仍未恢复')
    for i,v in enumerate(iv):axes[1].text(i,v+.1,f'{v:.2f}',ha='center')
    fig.text(.02,.015,'来源：既有四期48人信心实验，两组各两遍、16单元、763共同有效记录；冻结近似计分/经验中位数。无新模拟、未择优。',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(out/'reporting_sensitivity.png',dpi=160);fig.savefig(out/'reporting_sensitivity.svg');plt.close(fig)

    gain=1-scores['demographic_personal_history']['brier']/scores['demographic']['brier']
    sgain=1-scores['previous_belief_shape_personal_history']['brier']/scores['previous_belief_shape']['brier']
    pc=s['contrasts'][1]['person_cluster']['interval_95']
    text=f'''# 概率表达线结果：个人历史有信息，取整只能解决部分问题

2026-10-13。全部使用已有数据，新API调用0；未改原始回答、P/E、模拟配置、冻结近似计分或Kimi的信念更新模块。

## 一、最重要的结论

本人过去的概率填法比年龄、教育、数理能力更有预测信息；加入上期信念形状后仍有增量。但问卷无法把稳定信念、调查熟悉度与报告习惯完全分开，因此这里只识别了“有个人持续性的作答模式”，没有识别出确定的心理人格。

概率表达是可继续研究的f模块。现有机械取整可以移动聚合指标，却远不足以恢复真人的人际差异。下一步需要与信念更新线结合，不能只靠把概率圆整或删尾部宣布成功。

## 二、方法与样本

真实缓存2017-01至2025-10共130216人月，十档与正权重有效128244条、16957个可见受访者。2017—2019训练46794条，2020—2021验证29654条，2022—2025-10复核51796条、7129人、46月。全部跨度的部分描述统计和四个开发期此前已看过，不称全项目盲测。

观测类型只有三类：至少一档不是5%的倍数、全部为5%倍数但非全部10%倍数、全部为10%倍数。它们是数字形状，不等同真实心理类型；只有一档100%的回答必然归入最后一类，即使没有取整习惯。

人口参考按年龄三档×教育三档×numeracy两档训练18个条件比例。信念形状参考按上次有效问卷的非零档数、官方个人Q9不确定性与最大概率分档，分界由训练期计算。小格少于100行或20人回退参考；20个平均权重观测的伪计数作收缩。本人历史只累计当前回答之前的有效填法，固定先验强度3；无历史者回退参考。所有数值参数在新结果之前登记，没有在本次验证/复核中挑最优值。

这里的本人历史和当前真实人口属于A条件诊断，微观发布滞后使它不能直接用于当时的B预测。首次可见不等于首次参加SCE；漏访后的历史可用于表达模式预测，严格相邻月另作敏感性。

## 三、预测填法的结果

46个月归一化Brier误差（越小越好）：

- 训练期总体比例：{scores['training_population']['brier']:.3f}。
- 人口条件比例：{scores['demographic']['brier']:.3f}。
- 人口＋本人历史：{scores['demographic_personal_history']['brier']:.3f}，相对人口参考降低{100*gain:.1f}%。
- 上期信念形状：{scores['previous_belief_shape']['brier']:.3f}。
- 上期形状＋本人历史：{scores['previous_belief_shape_personal_history']['brier']:.3f}，降低{100*sgain:.1f}%。

人口参考猜对类型的比例47.9%，加本人历史约65.0%；形状加历史约65.4%。已有至少3次有效历史者约72%，无历史者不从本人历史获得改善。因此应保留不确定的个人模式分布，不能给每个人硬贴永远不变的一类。

2022/2023/2024/2025四个分期以及严格相邻月结果方向一致，2020—2021验证期也有改善；不是只选一个好月份。这里预测的是填法，不是通胀率，Brier值没有百分点单位。

![预测填法](pattern_prediction.png)

## 四、统计学解释：为什么使用这些方法

预测给出三类的概率q，真实观测用对应的0/1向量Z表示。归一化Brier为`0.5 × Σ(q_k−Z_k)²`。它同时惩罚猜错和过度确信，是适合概率预测的评分；只看分类准确率可能漏掉人口模型仅小幅改变概率的作用。[官方定义](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html)

个人历史估计是收缩规则：`q_it = (3 × q_reference + 本人各类历史次数) / (3 + 历史次数)`。历史少时靠参考分布，历史多时更尊重本人；可理解为一个Dirichlet工作模型下的后验预测。固定先验3是本项目预设，不是从本次成绩估计的心理权重。由于问卷可能跨期相关、类型会变，这个工作模型不等于已经证明每个人存在固定的潜在风格。

训练和评价按时间分开；每条预测不含自己的当期/未来答案。真实权重在月内归一、月份等权，避免大样本月份支配结果。当前截面权重没有恢复完整纵向复杂抽样设计，有效集也条件于合法回答，选择偏差仍需保留。

同人重复观测不能当独立样本。因此把整个人的评价记录一起重抽1000次，比较同一批行上两个方法的Brier差值；另以连续6个月循环块重抽月份差值，检查公共时期与序列相关的影响。两种区间分开给出，均条件于已拟合的训练表；没有覆盖训练估计、官方复杂抽样及未来结构变化的全部不确定性，也不是联合双向聚类区间。[聚类推断原文](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf)

形状加历史相对形状参考的误差差值约−0.048；按人重抽95%区间[{pc[0]:.3f}, {pc[1]:.3f}]，月份块区间同样在0以下。这支持在当前条件与时期中存在稳定预测增量，不能推出心理风格的因果效应或未来通胀预测更准。

## 五、补充控制：作答熟悉度与本人身份

看到主结果存在冷启动差别后，另登记补查；以下是探索性补充，不替换主五种方法。按上期形状与过去有效观测次数分组，参考Brier {c['evaluation']['shape_and_count']['brier']:.3f}，再加本人历史{c['evaluation']['shape_count_personal_history']['brier']:.3f}，改善仍存在。可见观测次数不是精确survey tenure，因而仍不能彻底排除调查学习。

保持月份、上期形状和历史次数组，将历史类型比例换成另一匿名人的，同时保留接收者的历史强度；不使用当前标签。5次置换平均Brier {c['permutation']['mean_brier']:.3f}，明显差于本人{c['evaluation']['shape_count_personal_history']['brier']:.3f}；可置换覆盖86.2%，单人格子保持。它支持个人对应关系有信息，不是随机分配一个总体风格即可；分组不是随机实验，也未控制所有个人因素，不作因果或显著性检验。

真实通缩概率填0也有持续性：上期为0者下期仍为0约86.2%，上期大于0者下期填0约18.7%。但10%网格组个人不确定性中位数约2.34pp，精细组约5.86pp；信念集中与表达方式明显交织。零可能是实际信念，也可能是近零取整。[作者报告测量研究](https://molinari.economics.cornell.edu/docs/GMM_Rounding.pdf)

![补充控制与零概率](history_controls.png)

## 六、对SCE计分的影响与局限

复用旧四期48人信心实验的767份合法模型问卷及既有取整结果；同时保留真人有效、三种映射皆可评分的763条共同模拟记录。16个时期×组别×生成单元等权，均用项目冻结近似计分和经验CDF中位数；不是全国预测，也不同于旧敏感性表的np.median。未重跑LLM或选择最优取整。

- 原回答样本中心MAE {five['original_center_mae_pp']:.3f}pp；5%取整{five['mapped_center_mae_pp']:.3f}pp；10%取整{ten['mapped_center_mae_pp']:.3f}pp。
- W1原{five['original_w1_pp']:.3f}pp，5%后{five['mapped_w1_pp']:.3f}pp，改善只有约2.7%。
- 人际IQR原{five['original_person_iqr_pp']:.2f}pp，5%后{five['mapped_person_iqr_pp']:.2f}pp、10%后{ten['mapped_person_iqr_pp']:.2f}pp，真人{five['real_person_iqr_pp']:.2f}pp。

本次聚合中心平均向上移动约0.18pp（5%）或0.40pp（10%）；均值拟合不线性，概率改动合计0也不意味着个人均值或中位数不变。这里拟合家族未切换，仍存在拟合参数与概率质量移动。单次随机5%情景只能诊断原始概率无偏与非线性计分，不估计其期望或稳定效果。

5%与10%在本样本改善误差，不足以把5%选为最佳真人机制；样本原本偏低时向上移动就可能改善中心。机械圆整只是测量敏感性，未识别真人的潜在信念。原始Q8也明显同质，故报告层不能独自解决全部问题。

![测量敏感性](reporting_sensitivity.png)

## 七、下一轮可审查的两种候选（均未运行）

**候选1：个人报告习惯作为有来源的状态说明。**从训练期人口参考及本人此前问卷，保留三类观测模式的概率；条件A用真实历史，B初始化用当时可得历史参考并保留合成属性。把惯常表达方式说明放在本人信念/更新之后，不告诉模型应该预测多少；允许细报或近似报，不强行规定通缩为0、非零档数或点值等于密度均值。先验证提示是否让模型保持本人差异，不能以写进提示代替效果。

**候选2：透明的程序报告映射。**在不改变原LLM输出记录的前提下，使用预先分配、带来源不确定性的报告模式生成一份单独问卷输出；保持合计100、保存映射前后及计分差异。模式依据训练资料与历史状态，不按当期真值或哪个映射误差更小选择。持续性与信念形状交织，第一版应是明确情景对照，不冒称已精确识别人类心理。

两种方案都须保留原生回答及人口/本人/置换等必要参照；实际样本、提示、模式分配与预算另登记。与Kimi的更新器汇合后再选择第一轮真实对照，避免同时修改P/E、更新规则与报告层而无法解释结果。

## 八、复核与路径

6项独立检查通过：网格/合法概率定义、严格历史顺序、当前答案扰动不改变当前预测、收缩算术、Brier边界及常数差重抽样。全部46月Brier由私有预测文件独立公式复算，差值0；概率合计及15保护文件哈希通过。原始/个人行未提交，所有新调用0。

完整主结果：`outputs/sce_reporting_behavior_20261013_v1/summary.json`；补充：`outputs/sce_reporting_controls_20261013_v1/summary.json`。个人预测只留主目录`predictions_private.parquet`。本阅读稿为聚合结果，源码位于唯一study的reporting_behavior目录。主结果的code哈希与补充另保存，原结果未覆盖。

复算入口：`python scripts/analyze_sce_reporting_behavior.py --out outputs/<新的主结果目录>`；补充加`--primary-run outputs/<主结果目录>`，输出到另一个新目录。参数使用登记文件，不在CLI临时调参。B预测的模型状态闭环与最终全国实验尚未完成。
'''
    (out/'report.md').write_text(text)
    # Small Markdown subset sufficient for this generated report; escaped text only.
    body=[];paragraph=[]
    def flush():
        if paragraph:
            body.append('<p>'+inline(' '.join(paragraph))+'</p>');paragraph.clear()
    def inline(line):
        import re
        result=escape(line)
        result=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'<a href="\2">\1</a>',result)
        result=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',result)
        result=re.sub(r'`([^`]+)`',r'<code>\1</code>',result)
        return result
    for line in text.splitlines():
        if not line:flush();continue
        if line.startswith('!['):
            flush();imagefile=line.split('](')[1][:-1];body.append(f'<figure><img src="{escape(imagefile)}" alt="分析图"></figure>')
        elif line.startswith('# '):flush();body.append('<h1>'+escape(line[2:])+'</h1>')
        elif line.startswith('## '):flush();body.append('<h2>'+escape(line[3:])+'</h2>')
        elif line.startswith('- '):flush();body.append('<p class="item">'+inline(line[2:])+'</p>')
        else:paragraph.append(line)
    flush()
    html='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCE概率表达分析</title><style>
*{box-sizing:border-box}body{margin:0;background:#fafaf7;color:#26332f;font-family:system-ui,-apple-system,"PingFang SC",sans-serif}main{max-width:1040px;margin:auto;padding:32px 24px}h1{font-size:27px;line-height:1.45}h2{font-size:22px;margin-top:38px;border-top:1px solid #dce2dc;padding-top:22px}p{line-height:1.85;font-size:16px;overflow-wrap:anywhere}.item{padding-left:18px;border-left:3px solid #dce2dc}code{font-size:13px;background:#eef1eb;padding:2px 4px}a{color:#326a56}figure{margin:24px 0}img{width:100%;height:auto;display:block}@media(max-width:600px){main{padding:20px 16px}h1{font-size:24px}}
</style></head><body><main>'''+''.join(body)+'</main></body></html>'
    (out/'index.html').write_text(html)
    dump(out/'reading_receipt.json',{'primary_sha256':sha(primary/'summary.json'),'controls_sha256':sha(controls/'summary.json'),
                                    'figures':{p.name:sha(p) for p in out.glob('*.png')},'new_api_calls':0})
    print(str(out/'index.html'))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--primary',type=Path,required=True);ap.add_argument('--controls',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();render(args.primary,args.controls,args.out)
