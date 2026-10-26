"""Model identity and matched macro controls; preserve previous results."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from ..experiments.full_a_core_normal import ROOT,read,write,sha,checked
from ..evaluation.aggregate_blend import fit_weight,metrics


def build(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'docs/workstreams'):raise ValueError('Fresh report required')
    manifest=read(source/'manifest.json');checked(source,manifest['files_sha256']);checked(ROOT,manifest['source_sha256'])
    s=read(source/'summary.json');r=s['results'];old=s['old_shared_midmonth_2021'];out.mkdir(parents=True)
    with (source/'monthly_inputs_public.csv').open() as f:rows=list(csv.DictReader(f))
    # Same registered early48/later34 convex formula under the extra clock;
    # do not replace or rename the original primary 48/34 result.
    y=np.array([float(v['truth_pp']) for v in rows]);a=np.array([float(v['baseline_pp']) for v in rows]);sim=np.array([float(v['expanded_model_pp']) for v in rows])
    combos={}
    for loss in ['mae','mse']:
        w=fit_weight(y[:48],a[:48],sim[:48],loss);p=a+w*(sim-a)
        combos[loss]=dict(simulation_weight=w,later34=metrics(p[48:],y[48:]),all82_descriptive=metrics(p,y))
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti','Arial Unicode MS'],'axes.unicode_minus':False,'font.size':11})
    pairs=[('persistence','persistence','官方历史持续性'),
     ('Core_macro_without_sim_rolling','macro_without_sim_expanding','SCE＋CPI动态回归'),
     ('CoreNormal_tau8_macro_plus_sim_rolling','macro_plus_sim_expanding','SCE＋CPI＋模拟动态回归'),
     ('Core_regime_without_sim_rolling','regime_without_sim_expanding','SCE＋CPI＋状态，不含模拟'),
     ('CoreNormal_tau8_regime_plus_sim_rolling','regime_plus_sim_expanding','SCE＋CPI＋状态＋模拟交叉')]
    fig,ax=plt.subplots(figsize=(10,5.2),constrained_layout=True);x=np.arange(len(pairs))
    v0=[old[o]['year2021']['mae_pp'] for o,n,label in pairs];v1=[r[n]['year2021']['mae_pp'] for o,n,label in pairs]
    b0=ax.barh(x-.18,v0,height=.34,color='#1764AB',label='原共同月中参考');b1=ax.barh(x+.18,v1,height=.34,color='#C75B12',label='新增月末宏观对照')
    for bars,values in [(b0,v0),(b1,v1)]:ax.bar_label(bars,labels=[f'{v:.4f}' for v in values],padding=4,fontsize=10)
    ax.set_yticks(x,[label for o,n,label in pairs]);ax.invert_yaxis()
    ax.set(xlabel='2021全年全国Q9 MAE（pp，越低越好）',xlim=(0,.43),title='信息截止不同，基线和模拟增量也会不同')
    ax.legend(loc='lower center',bbox_to_anchor=(.5,1.02),ncol=2,frameon=False)
    ax.set_title('信息截止不同，基线和模拟增量也会不同',pad=43)
    ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
    fig.savefig(out/'clock_comparison.png',dpi=160);plt.close(fig)

    comp=s['matched_comparisons']['macro_plus_sim_expanding_versus_macro_without_sim_expanding']
    periods=['year2021','year2022','later34','all58'];labels=['2021年','2022年','2023-01—2025-10','2021-01—2025-10']
    delta=[-comp[p]['mae_reduction_pp'] for p in periods];ci=np.array([comp[p]['paired_interval']['interval_95'] for p in periods])
    fig,ax=plt.subplots(figsize=(10,3.7),constrained_layout=True)
    ax.errorbar(delta,np.arange(4),xerr=np.array([np.array(delta)-ci[:,0],ci[:,1]-np.array(delta)]),
                 fmt='o',color='#1764AB',capsize=4)
    ax.axvline(0,color='#777777',ls='--');ax.set_yticks(np.arange(4),labels);ax.invert_yaxis()
    ax.set(xlabel='加入模拟后的MAE变化（pp；负值为改善；线为区块95%区间）',
           title='月末信息：相对于SCE＋CPI同结构模型，模拟增量较小')
    ax.grid(axis='x',alpha=.18)
    fig.savefig(out/'matched_increment.png',dpi=160);plt.close(fig)
    table=''.join(f'<tr><th>{label}</th><td>{old[o]["year2021"]["mae_pp"]:.4f}</td><td>{r[n]["year2021"]["mae_pp"]:.4f}</td><td>{r[n]["year2021_H2"]["mae_pp"]:.4f}</td><td>{r[n]["year2022"]["mae_pp"]:.4f}</td><td>{r[n]["later34"]["mae_pp"]:.4f}</td></tr>' for o,n,label in pairs)
    text=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>动态模型类型、主辅指标与公平基线</title>
<style>body{{margin:0;background:#faf9f5;color:#222;font:18px/1.8 "Times New Roman","Kaiti SC","STKaiti",serif}}main{{max-width:1120px;margin:auto;padding:32px 24px}}h1{{font-size:29px;line-height:1.4}}h2{{font-size:23px;margin-top:30px}}
.lead{{font-size:21px;border-left:4px solid #1764AB;padding:15px 20px;background:#edf2f6}}.formula{{padding:15px;background:white;font-size:19px;overflow-wrap:anywhere}}img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;background:white}}td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:right}}th:first-child{{text-align:left}}small,figcaption{{color:#555;font-size:15px}}a{{color:#1764AB}}</style>
<main><small>SCE · 主指标／辅助指标／公平对照 · 离线补充 · 0 API</small>
<h1>当前是扩展窗口回归，具有ARX形式；没有估计ARIMA误差过程</h1>
<p class="lead">简单加权作为主衍生指标，动态回归作为辅助分析。0.1465pp是原截止口径下2021年下半年的MAE，全年为0.2740pp。加入更充分的月末宏观对照后，无交叉项联合模型2021全年0.2416pp，对应SCE＋CPI控制0.2447pp；增量小，不能沿用原基线强度宣称大幅提高异常预测能力。</p>
<h2>1．究竟是什么模型，有没有差分？</h2>
<p>代码用岭回归估计“当月SCE相对最新公开SCE的修正”。系数每月按已公开标签扩大训练窗口后重估。由于使用历史SCE与外生CPI、模拟信号，可理解为ARX式条件均值回归；最新公开SCE有时滞后两个月，因此不严格标成固定一阶AR(1)。</p>
<div class="formula">yₜ − Aₜ ＝ cₜ ＋ b₁,ₜ Aₜ ＋ b₂,ₜ(πₜ−Aₜ) ＋ b₃,ₜ Δπₜ ＋ b₄,ₜ(Sₜ−Aₜ) ＋ b₅,ₜ Dₜ ＋ b₆,ₜ Dₜ(Sₜ−Aₜ) ＋ εₜ</div>
<p>A为最后公开官方SCE，π为最新已发布CPI同比，S为模拟全国值，D表示CPI同比≥4%。无状态组删去最后两项；不含模拟对照删去模拟差与其交叉项。</p>
<p>没有加入滞后预测误差，故没有MA误差项；也没有估计ARIMA(p,d,q)或季节差分。y−A是相对公开锚的变化，A不一定等于相邻月份y，因此不能据此称ARIMA的d=1。Δπ是连续两次已公布CPI同比的差，不是CPI价格指数差分。宏观简单加权也不是时序术语里的MA模型。</p>
<p>“动态”指逐月更新系数，不是已实现卡尔曼滤波、马尔可夫状态切换，或个人信念递推。未来若加入ARIMA残差，需要另行验证阶数、平稳性和残差结构；当前没有这些实现。术语参见<a href="https://otexts.com/fpp3/dynamic-regression.html">Hyndman与Athanasopoulos：动态回归</a>。</p>
<h2>2．报告采用主、辅助两层，但保留原始模拟</h2>
<p><strong>主衍生指标：</strong>历史官方SCE与模拟SCE的凸组合，明确训练与评价月份。原共同参考口径下，早48月MSE拟模拟权重约13.5%，后34月MAE约0.1850pp，对照0.1941pp；MAE拟权为0也披露。原始模拟MAE与微观指标仍单独展示，不能用后处理掩盖个体分布缺口。</p>
<p><strong>辅助指标：</strong>按同一可得信息、同一训练/更新规则比较动态SCE＋CPI与加入模拟的模型。辅助指标解释模拟信号有无增量，不自动取代主指标，也不能把复杂统计模型的全部收益算成LLM贡献。</p>
<h2>3．为什么还要补月末宏观对照？</h2>
<p>原动态模型及宏观对照都按原CPI首发日的共同月中截止构造宏观锚；A模拟则按每个人作答日前一天，最晚覆盖月底。这不是完全相同的信息范围。现在仅新增月末宏观对照，保留原结果：例如2021-06，6/10只知道4月SCE3.4%，但月底已知道6/14公布的5月SCE4.0%；12月也有同类情况。</p>
<p>月末对照在纽约时间月末结束前选择最后已公开的历史SCE，CPI仍是已发布的首发，不读尚未公开的目标月SCE或目标月实际CPI。拟合家族与2019—2020的18/6选参规则不变；参数每月只使用当时已公开标签。先验时点、真实当期人口和模型知识等A线边界仍在，月末敏感性不等于认证严格B预测。</p>
<figure><img src="clock_comparison.png" alt="2021全年原月中与新增月末宏观对照下的不同模型MAE"><figcaption>单位pp；蓝色原共同月中、橙色新增月末。改变截止同时改变可得锚和训练标签，不能把跨口径差值全部归给模拟机制。</figcaption></figure>
<table><thead><tr><th>方法</th><th>原口径2021全年</th><th>月末2021全年</th><th>月末2021下半年</th><th>月末2022全年</th><th>月末后34月</th></tr></thead><tbody>{table}</tbody></table>
<h2>4．这会如何改变贡献的表述？</h2>
<p>原口径同结构状态控制0.2885→加入模拟0.2740pp，增量0.0144pp；下半年0.1593→0.1465pp。新增月末、无状态交叉项结构则为0.2447→0.2416pp，增量约0.0032pp；持续性已为0.2500pp。状态交叉项组在新口径下恶化到0.3639pp，说明稀疏高状态下的交叉项并不稳健，不能仅凭原来最小分数选它。</p>
<figure><img src="matched_increment.png" alt="月末口径加入模拟后相对同结构宏观对照的MAE变化区间"><figcaption>只展示事先列出的无状态交叉项家族。加入模拟的净MAE改善：2021约0.0032、2022为恶化约0.0007、后34月改善约0.0009pp；区间均跨零。含交叉项的不稳定结果完整保留在上表和数据中。</figcaption></figure>
<p>应表述为“在预设的回顾性动态校准中，模拟信号在部分异常阶段提供有限增量；增量对截止口径与模型形式敏感”。目前不表述为“已经证明大幅提高异常通胀初期预测能力”。不能把0.1465称全年值，或与另一时间窗口的0.1850直接比较。</p>
<h2>5．简单组合也要接受相同的更强基线</h2>
<p>仅为时点敏感性，把月末锚也代入原早48/后34组合规则：MAE与MSE拟模拟权重均为{combos['mse']['simulation_weight']:.3f}，后34月为{combos['mse']['later34']['mae_pp']:.6f}pp，即月末持续性。原口径13.5%权重与0.1850pp成绩没有被改写，但不能拿它与月末基线交叉比较后宣称增量。</p>
<p>用户确定的主、辅助呈现层级可以保留；最终研究结论必须同时展示公平宏观对照与时点敏感性。当前不再依据这些后期成绩挑参数，也不自动把任一新方案升级到路线B。只有82个宏观月，2021仅12个月；各年份已经查看，不称新的盲测。</p>
<p><a href="../../20261026_measurement_anomaly/results_v2/index.html">原计分与2021专项</a> · <a href="../../20261026_core_normal_full_a/macro_calibration_v1/index.html">原主组合与宏观校准</a></p>
<small>来源：{source.relative_to(ROOT)}；原始A/B、近似评分、Core＋Normal、原报告和研究包均保留。新增API、密度拟合均为0。</small></main></html>'''
    (out/'index.html').write_text(text)
    write(out/'readout.json',dict(analysis=s,extra_month_end_48_34_combinations=combos))
    write(out/'manifest.json',dict(source_manifest_sha256=sha(source/'manifest.json'),renderer_sha256=sha(Path(__file__)),
          files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print(out/'index.html')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();build(a.source,a.out)


if __name__=='__main__':main()
