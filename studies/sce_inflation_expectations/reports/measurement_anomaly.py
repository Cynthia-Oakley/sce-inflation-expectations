"""Focused report: scoring bridge and publication-gated 2021 calibration."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from ..experiments.full_a_core_normal import ROOT,read,write,sha,checked


def build(measurement,anomaly,out):
    measurement,anomaly,out=map(lambda p:Path(p).resolve(),(measurement,anomaly,out))
    if out.exists() or not out.is_relative_to(ROOT/'docs/workstreams'):raise ValueError('Fresh workstream report required')
    for p in [measurement,anomaly]:
        m=read(p/'manifest.json');checked(p,m['files_sha256']);checked(ROOT,m['source_sha256'])
    a=read(anomaly/'summary.json');m=read(measurement/'summary.json');r=a['results'];out.mkdir(parents=True)
    with (anomaly/'monthly_public.csv').open() as f: rows=list(csv.DictReader(f))
    with (measurement/'monthly_public.csv').open() as f: bridge=list(csv.DictReader(f))
    b21=[x for x in bridge if x['month'].startswith('2021')]
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti','Arial Unicode MS'],
                         'axes.unicode_minus':False,'font.size':11})
    fig,axes=plt.subplots(2,1,figsize=(11,7),constrained_layout=True,sharex=True)
    x=np.arange(12)
    for key,label,color,ls in [('official_initial_pp','官方首发','#222222','-'),
       ('our_human_full_pp','真人按共同算法重算','#1764AB','--'),
       ('normal_empirical_pp','扩展模拟','#C75B12','-')]:
        axes[0].plot(x,[float(z[key]) for z in b21],label=label,color=color,ls=ls,marker='o',ms=3)
    axes[0].set(ylabel='一年期预期通胀率（%）',title='2021年：计分差远小于模拟低估幅度');axes[0].legend(ncol=3)
    axes[1].bar(x-.18,[float(z['our_human_full_pp'])-float(z['official_initial_pp']) for z in b21],
                width=.35,color='#1764AB',label='真人重算－官方首发')
    axes[1].bar(x+.18,[float(z['normal_empirical_pp'])-float(z['official_initial_pp']) for z in b21],
                width=.35,color='#C75B12',label='扩展模拟－官方首发')
    axes[1].axhline(0,color='#777777',lw=.8);axes[1].set(ylabel='带符号差值（pp）',xlabel='2021年调查月份')
    axes[1].legend(ncol=2);axes[1].set_xticks(x,[f'{i}月' for i in range(1,13)])
    for ax in axes:ax.grid(alpha=.18);ax.set_axisbelow(True)
    fig.savefig(out/'measurement_2021.png',dpi=160);plt.close(fig)

    selected=[('persistence','官方历史持续性'),('CoreNormal_tau8_pure','扩展模拟原始输出'),
      ('CoreNormal_tau8_macro_plus_sim_fixed','复杂校准：首期截止前固定参数'),
      ('Core_macro_without_sim_rolling','滚动更新：CPI，不含模拟'),
      ('CoreNormal_tau8_macro_plus_sim_rolling','滚动更新：CPI＋模拟'),
      ('CoreNormal_tau8_regime_plus_sim_rolling','滚动更新：CPI＋模拟＋状态交叉')]
    fig,ax=plt.subplots(figsize=(10,5),constrained_layout=True)
    values=[r[k]['year2021']['mae_pp'] for k,_ in selected]
    bars=ax.barh(np.arange(len(selected)),values,color=['#777777','#C75B12','#D2A280','#A4BAC9','#1764AB','#174D78'])
    ax.bar_label(bars,labels=[f'{v:.4f}' for v in values],padding=4)
    ax.set_yticks(np.arange(len(selected)),[v for _,v in selected]);ax.invert_yaxis()
    ax.set(xlabel='2021年全国Q9中位数MAE（pp，越低越好）',title='2021年：固定参数未改善，按已发布历史更新出现收益',xlim=(0,.65))
    ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
    fig.savefig(out/'anomaly_mae.png',dpi=160);plt.close(fig)

    fig,axes=plt.subplots(2,1,figsize=(11,7),constrained_layout=True,sharex=True)
    chosen='CoreNormal_tau8_regime_plus_sim_rolling'
    for key,label,color,ls in [('truth_pp','官方首发','#222222','-'),('persistence','官方历史持续性','#888888','--'),
      ('Core_regime_without_sim_rolling','同结构，不含模拟','#C75B12','-'),
      (chosen,'CPI＋模拟＋状态滚动更新','#1764AB','-')]:
        axes[0].plot(x,[float(z[key]) for z in rows],label=label,color=color,ls=ls,marker='o',ms=3)
    axes[0].set(ylabel='一年期预期通胀率（%）',title='滚动更新主要改善下半年，尚未提前捕捉上半年跃升');axes[0].legend(ncol=2)
    for key,label,color in [('persistence','持续性绝对误差','#888888'),(chosen,'滚动模型绝对误差','#1764AB')]:
        axes[1].plot(x,[abs(float(z[key])-float(z['truth_pp'])) for z in rows],label=label,color=color,marker='o')
    axes[1].set(ylabel='绝对误差（pp）',xlabel='2021年调查月份');axes[1].legend()
    axes[1].set_xticks(x,[f'{i}月' for i in range(1,13)])
    for ax in axes:ax.grid(alpha=.18)
    fig.savefig(out/'anomaly_monthly.png',dpi=160);plt.close(fig)
    full=m['periods']['all82'];year=m['periods']['year2021'];best=r[chosen]
    effect=full['core']['net_mae_change_when_using_official_target_pp']
    table=''.join(f'<tr><th>{label}</th><td>{r[k]["year2021"]["mae_pp"]:.4f}</td><td>{r[k]["year2021"]["rmse_pp"]:.4f}</td><td>{r[k]["first_half"]["mae_pp"]:.4f}</td><td>{r[k]["second_half"]["mae_pp"]:.4f}</td></tr>' for k,label in selected)
    audit=''.join(f'<tr><th>{z["month"]}</th><td>{z["n_training"]}</td><td>{z["last_training_month"]}</td><td>{z["last_training_label_published_at"]}</td><td>{z["high_CPI_training_n"]}</td></tr>' for z in a['rolling_publication_audit'])
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>计分误差与2021年动态校准</title><style>body{{margin:0;background:#faf9f5;color:#222;font:18px/1.8 "Times New Roman","Kaiti SC","STKaiti",serif}}
main{{max-width:1120px;margin:auto;padding:32px 24px}}h1{{font-size:30px;line-height:1.4}}h2{{font-size:23px;margin-top:32px}}p{{margin:12px 0}}
.lead{{font-size:21px;border-left:4px solid #1764AB;background:#edf2f6;padding:15px 20px}}.note,figcaption{{font-size:15px;color:#555}}img{{width:100%;height:auto}}
table{{width:100%;border-collapse:collapse;background:white;font-variant-numeric:tabular-nums}}td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:right}}th:first-child{{text-align:left}}a{{color:#1764AB}}details{{margin:22px 0}}</style>
<main><small>SCE · 82月计分对账／2021年专项 · 0新增API／0密度重拟 · 原结果保留</small>
<h1>2021年低估不是计分差造成的；动态统计校准出现局部收益</h1>
<p class="lead">同人、同权重对账后，密度拟合对月度中位数的平均差约0.0133pp，2021年约0.0238pp。2021年预先固定参数仍不如持续性；按已公布历史逐月更新后，扩展模拟＋CPI＋状态交叉MAE为{best['year2021']['mae_pp']:.4f}pp，对照0.3250pp。收益主要来自下半年，不称提前预测了通胀跃升，也不自动升级主配置。</p>
<h2>1．正式报告应如何声明计分差异</h2>
<p>全国主目标采用纽约联储官方首发值，微观比较对真人和模型共同使用冻结近似计分器。本项目已实现官方公开的均匀、相邻双档三角、广义Beta规则；现有冻结版还包含2026-10-03独立计分留出选定的Beta改进，不是最早的原始版本。部分开放尾Beta的约束、起点与多解选择仍未完全还原官方实现。</p>
<p>本次另读取官方提供的个人Q9_mean，仅在评价层与同一条真人记录的本地评分比较。共同有效记录96,655条：加权个人均值绝对差约{m['common_person_weighted_mae_pp']:.4f}pp；均匀分支为0，双档三角近浮点精度，闭合Beta约0.0004，开放尾Beta约0.0662pp。个人误差与跨人中位数误差是不同统计量。</p>
<p><strong>只换个人密度均值、固定同一批人和权重：</strong>82个月的月度中位数平均绝对差为{full['components_mean_absolute_pp']['density_common_effect_pp']:.6f}pp，2021年为{year['components_mean_absolute_pp']['density_common_effect_pp']:.6f}pp。样本纳入改变另列，不混进纯密度差。</p>
<p><strong>只用官方个人均值＋原调查权重＋当前经验CDF中位数：</strong>82个月均复现高精度官方chart，平均差约1.5×10⁻¹⁶pp。说明这批Q9的汇总层已对齐，不需要为修复2021而更换中位数规则。Cox对称插值已按公开公式另实现作敏感性；用于此Q9后官方字段与chart平均差约0.0031pp，故不替换原口径。该插值主要针对取整/分组回答，不能不加区分套到所有变量。</p>
<figure><img src="measurement_2021.png" alt="2021年官方SCE、真人共同算法重算及模型模拟差距"><figcaption>上图单位%；下图单位pp。差值均逐月计算，不将不同来源平均绝对差相加作贡献比例。来源：冻结问卷评分、官方个人派生字段、原权重、chart与首发目标。</figcaption></figure>
<h2>2．模型误差中，多少是计分差？</h2>
<p>令S为模拟中位数、H为真人共同算法重算值、O为官方值，则 S−O＝(S−H)＋(H−O)。这是带符号误差的精确分解；MAE含绝对值，不能把0.0269÷0.2984当“算法造成的误差比例”。</p>
<p>原Core对官方MAE为0.298407pp，对同算法真人值为0.289976pp，净差{effect:.6f}pp，约2.8%，只表示换对照目标的敏感性。2021年方向反过来：官方目标0.577424、同算法目标0.586643pp，评分桥接反而略微掩盖了低估。扩展后同样为0.565315与0.574534pp。</p>
<p>真人共同算法全国值与官方首发的平均差0.026928pp；其中同人密度层平均差0.013272，支持样本变化约0.000320／0.003421，官方个人均值汇总与chart差近0，chart与首发公布精度/版本差平均0.023147pp。这些绝对量可互相抵消，不能相加。完整逐月带符号链与MSE平方项、交叉项均已保存。</p>
<h2>3．官方算法能否直接应用？</h2>
<p><a href="https://www.newyorkfed.org/medialibrary/media/research/epr/2017/epr_2017_survey-consumer-expectations_armantier.pdf">官方方法论文附录B/C</a>公开了分布家族、支撑端、最小距离思想及插值公式；本轮核查的方法、数据入口和定向搜索中仍未找到完整官方生产拟合程序，不能把独立复现称作官方源码。Cox公式能直接实现且已离线检验；Beta余差不能靠随意换优化器、按模型成绩挑解来消除。</p>
<p>可在取得官方程序或补足固定数值规则后，另冻候选、用官方个人派生值核验，再对真人与模型统一离线重计分；无需重跑LLM。本轮不改旧计分器、原回答或主结果。已有独立R复现代码也不等于纽约联储官方实现。</p>
<h2>4．2021年应怎样检验复杂模型？</h2>
<p>上一轮早48月训练包含2021年，因此不能回答模型是否在2021年有预测价值。本轮固定用2019—2020的24个月：前18个月训练、后6个月选岭强度，随后用全部24个月重估。状态门槛CPI≥4%与因子家族沿上轮预设，没有根据2021成绩更换。</p>
<p>并列两种策略：一是2021年首期截止前拟合后全年固定参数；二是每月只用该截止前已经公开的历史SCE标签更新参数，沿用首期选定的正则强度。训练调查月止于2020-12，但该月标签在2021-01-11才公开，本轮首次截止为2021-01-13；不能称系数在2020年底已经可拟合。本轮为扩展窗口，不是固定长度滑动窗口。例如2021-06截止6/10，5月SCE要到6/14才公开，因此训练只到4月。</p>
<figure><img src="anomaly_mae.png" alt="2021年固定参数与逐月已公布数据更新的MAE比较"><figcaption>12个月等权，横轴pp且从0开始；固定训练不含2021目标，滚动只吸收此前已公布的2021目标。A模拟机制与历史本已查看，不称端到端新盲测或严格B预测。</figcaption></figure>
<table><thead><tr><th>方法</th><th>2021 MAE</th><th>2021 RMSE</th><th>上半年MAE</th><th>下半年MAE</th></tr></thead><tbody>{table}</tbody></table>
<h2>5．收益来自哪里，还有哪些限制？</h2>
<p>扩展模拟＋CPI滚动MAE为0.276722，加入状态交叉为0.274024，相对持续性0.325下降约15.7%。同结构不含模拟为0.288468，加入模拟再降低约0.0144pp，说明样本内存在有限增量；大部分改善仍可由已公开历史/CPI的动态适应提供，不能全归给LLM。</p>
<p><strong>上半年尚未改善：</strong>滚动联合组0.401572，持续性0.400000；下半年分别0.146475与0.250000。2019—2020训练样本没有CPI≥4%的状态，状态与交叉项当时不可识别，不是已经学得“高通胀效应为零”。到2021-07，才有2条已公开高CPI状态的历史训练记录。收益更像随公开信息更新后追上趋势，尚不支持提前识别异常上升。</p>
<figure><img src="anomaly_monthly.png" alt="2021年按月官方目标、持续性、无模拟控制及联合滚动预测"><figcaption>上图单位%，下图绝对误差pp。所有12个月均保留，未选择表现好的月份。状态组不含模拟与联合组使用相同的可得历史筛选。</figcaption></figure>
<p>2021只有12个时间样本，联合滚动组相对持续性的三个月区块MAE差区间约[-0.1424,+0.0199]pp，跨零。当前结果支持保留动态统计校准为候选，不把它写成已稳定胜过基线或已验证居民机制。下一步应保持规则，在2022及其他年份检查代价，而非继续按2021调参。</p>
<details><summary>逐月训练可得性与状态样本支持</summary><table><thead><tr><th>目标月</th><th>训练月数</th><th>最新训练月</th><th>该标签发布日期</th><th>高CPI训练数</th></tr></thead><tbody>{audit}</tbody></table></details>
<p class="note">原全部生成、计分器、Core＋Normal、τ敏感性、报告v05与研究包保留。本轮0新增API、0密度重拟。来源：{measurement.relative_to(ROOT)} 与 {anomaly.relative_to(ROOT)}；官方资料核查日2026-10-26。</p>
<p><a href="../../20261026_core_normal_full_a/macro_calibration_v1/index.html">前一轮后34月比较</a> · <a href="../../20261026_core_normal_full_a/README.md">Core＋Normal方法</a></p></main></html>'''
    (out/'index.html').write_text(page)
    write(out/'readout.json',dict(measurement=m,anomaly=a))
    write(out/'manifest.json',dict(measurement_manifest_sha256=sha(measurement/'manifest.json'),anomaly_manifest_sha256=sha(anomaly/'manifest.json'),
          renderer_sha256=sha(Path(__file__)),files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print(out/'index.html')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--measurement',required=True,type=Path)
    p.add_argument('--anomaly',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    build(a.measurement,a.anomaly,a.out)


if __name__=='__main__':main()
