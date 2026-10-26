"""Read-only figures for observable inflation triggers and matched controls."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from ..experiments.full_a_core_normal import ROOT,read,write,sha,checked

LABELS={'level_macro':'水平：SCE＋CPI','level_sim':'水平：再加模拟',
 'difference_macro':'差分：SCE＋CPI','difference_sim':'差分：再加模拟',
 'trigger_macro':'触发器：SCE＋CPI','trigger_sim':'触发器：再加模拟交叉',
 'bounded_macro':'正向项：SCE＋CPI','bounded_sim':'正向项：再加模拟修正'}
BLUE='#1764AB';ORANGE='#C75B12';GRAY='#777777';BLACK='#202020'


def build(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'docs/workstreams'):raise ValueError('Fresh report required')
    m=read(source/'manifest.json');checked(source,m['files_sha256']);checked(ROOT,m['source_sha256'])
    s=read(source/'summary.json');r=s['results'];out.mkdir(parents=True)
    with (source/'monthly_public.csv').open() as f:rows=list(csv.DictReader(f))
    year=rows[:12];x=np.arange(12);months=[v['month'][4:] for v in year]
    def v(name):return np.array([float(row[name]) for row in year])
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti','Arial Unicode MS'],
                         'axes.unicode_minus':False,'font.size':11})
    fig,ax=plt.subplots(figsize=(10,4),constrained_layout=True)
    for j,row in enumerate(year):
        if row['trigger']=='True':ax.axvspan(j-.47,j+.47,color=BLUE,alpha=.08,lw=0)
    ax.plot(x,v('cpi_change_pp'),'-o',color=ORANGE,label='已公布CPI同比：较前次发布的变化')
    ax.plot(x,v('sim_change_pp'),'-s',color=BLUE,label='模拟SCE：较上个调查月的变化')
    ax.plot(x,v('truth_pp')-v('persistence'),'--',color=BLACK,label='真实SCE月变化（仅评价）')
    ax.axhline(s['threshold_pp'],ls=':',color=GRAY,label='事先训练阈值：0.2pp')
    ax.set(xticks=x,xticklabels=months,xlabel='2021年调查月',ylabel='变化（pp）',
           title='触发信号来自当时已公布的价格，不来自本月真实SCE')
    ax.legend(fontsize=9,ncol=2,frameon=False,loc='lower left',bbox_to_anchor=(0,1.015))
    ax.set_title('触发信号来自当时已公布的价格，不来自本月真实SCE',pad=50)
    ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'observed_trigger_2021.png',dpi=160);plt.close(fig)

    fig,axes=plt.subplots(2,1,figsize=(10,8),constrained_layout=True,sharex=True,sharey=True)
    for ax,mode,title in zip(axes,['fixed','expanding'],['2019—2020固定系数：检验旧关系能否应对突变','逐月更新系数：只吸收已经公布的历史真值']):
        ax.plot(x,v('truth_pp'),'-o',color=BLACK,label='真实SCE')
        ax.plot(x,v('persistence'),'--',color=GRAY,label='上月官方SCE')
        ax.plot(x,v('trigger_sim_'+mode),'-s',color=BLUE,label='触发器＋模拟交叉')
        ax.plot(x,v('bounded_sim_'+mode),'-^',color=ORANGE,label='温和正向修正＋模拟')
        ax.set(ylabel='全国Q9中位数（%）',title=title);ax.grid(axis='y',alpha=.15)
    axes[0].legend(ncol=2,fontsize=10,frameon=False,loc='upper left')
    axes[1].set(xticks=x,xticklabels=months,xlabel='2021年调查月')
    fig.savefig(out/'prediction_2021.png',dpi=160);plt.close(fig)

    fig,ax=plt.subplots(figsize=(10,3.4),constrained_layout=True)
    keys=['difference','trigger','bounded'];values=[];lo=[];hi=[]
    for name in keys:
        p=s['paired_comparisons'][f'{name}_sim_expanding_versus_{name}_macro_expanding']['all58']
        values.append(p['mae_difference_pp']);lo.append(p['interval_95'][0]);hi.append(p['interval_95'][1])
    ax.errorbar(values,np.arange(3),xerr=[np.array(values)-lo,np.array(hi)-values],fmt='o',color=BLUE,capsize=4)
    ax.axvline(0,color=GRAY,ls='--');ax.set_yticks(np.arange(3),['差分','触发器交叉','温和正向修正']);ax.invert_yaxis()
    ax.set(xlabel='加入模拟后的MAE变化（pp；负数为改善；线为3月区块95%区间）',
           title='2021-01—2025-10：相对各自不含模拟的对照')
    ax.grid(axis='x',alpha=.15);fig.savefig(out/'matched_increment.png',dpi=160);plt.close(fig)

    periods=['year2021_H1','year2021_H2','year2021','year2022','later34','all58']
    def table(mode):
        names=[('persistence','照抄上月官方值'),('raw_simulation','原始模拟（含固定τ8扩展）')]+[(family+'_'+mode,label) for family,label in LABELS.items()]
        body=''.join('<tr><th>'+label+'</th>'+''.join(f'<td>{r[name][p]["mae_pp"]:.4f}</td>' for p in periods)+'</tr>' for name,label in names)
        return '<div class="scroll"><table><tr><th>模型</th><th>2021上半年</th><th>2021下半年</th><th>2021全年</th><th>2022全年</th><th>2023—2025.10</th><th>全58月</th></tr>'+body+'</table></div>'
    coefficients=s['fits']['trigger_sim'];co=dict(zip(coefficients['features'],coefficients['coefficients']))
    text=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>用差分与可观察触发器修正通胀预期</title>
<style>body{{margin:0;background:#faf9f5;color:#222;font:18px/1.8 "Times New Roman","Kaiti SC","STKaiti",serif}}main{{max-width:1120px;margin:auto;padding:30px 24px}}h1{{font-size:29px;line-height:1.45}}h2{{font-size:23px;margin-top:32px}}p{{text-indent:2em}}.lead{{text-indent:0;font-size:21px;border-left:4px solid {BLUE};padding:15px 20px;background:#edf2f6}}.formula{{background:white;padding:14px;overflow-wrap:anywhere}}img{{width:100%;height:auto}}small,figcaption{{color:#555;font-size:15px}}table{{width:100%;border-collapse:collapse;white-space:nowrap;background:white;font:16px/1.6 "Times New Roman","Kaiti SC","STKaiti",serif;font-variant-numeric:tabular-nums}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:right}}th:first-child{{text-align:left}}.scroll{{overflow:auto}}a{{color:{BLUE}}}details{{margin:20px 0}}summary{{cursor:pointer;font-weight:bold}}</style>
<main><small>SCE · 可观察触发器与差分 · 2026-10-26 · 0新增API</small>
<h1>触发器能改善异常初期，也可能在随后造成过度修正</h1>
<p class="lead">你的设想可以落实为“价格信号触发、系数分状态调整”。本次离线比较中，触发器交叉模型把2021上半年MAE从基线0.3000降至0.1755pp；但下半年恶化到0.3874pp，全年0.2814仍不及基线0.2500。温和正向修正全年0.2398、全58月0.2253，均略有改善。不同模型的收益与代价必须同时看，当前不据此更换正式配置。</p>
<h2>1．触发的是什么？</h2>
<p>不能事后给2021年贴一个虚拟变量再当成可预测规律。本次用最新已公布CPI同比相对前次发布的变化：超过{ s['threshold_pp']:.1f}个百分点时D＝1，否则D＝0。例如同比从2.0%升至2.3%会触发；从6.5%升至6.6%不会触发。因此它衡量涨幅加快，不是高通胀水平，也不是已经识别的结构冲击；同比变化仍包含基期效应。</p>
<p>阈值是2019-02—2020-12这23期价格变化的75%分位数，之后固定；其中有{ s['pre2021_trigger_count']}个触发月。内层选参只用前17期确定阈值，随后6期验证岭回归强度。与原先“CPI≥4%”相比，新信号在2021年前有一些支持，但5个触发月仍不足以保证稳定估计。</p>
<figure><img src="observed_trigger_2021.png" alt="2021年已发布CPI变化、模拟SCE变化、真实SCE变化和触发月份"><figcaption>浅蓝背景为触发月。真实当月SCE变化仅用于图上评价，没有用于触发判断。CPI是已发布的首发数据，可能对应上个参考月；并未使用事后才知道的当月实际CPI。</figcaption></figure>
<h2>2．差分和交叉项分别解决什么？</h2>
<p><strong>差分：</strong>让回归预测“本月比上月变多少”，最后加回上月真实SCE。这样不会强迫当前模拟水平承担全部预测，但差分本身不会凭空产生模型遗漏的上行信号。</p>
<div class="formula">Δyₜ ＝ a ＋ φΔyₜ₋₁ ＋ γΔπₜ ＋ βΔSₜ ＋ δDₜ ＋ ηDₜ·max(Δπₜ,0) ＋ θDₜ·ΔSₜ ＋ εₜ<br>最终预测：ŷₜ ＝ yₜ₋₁ ＋ 预测的Δyₜ</div>
<p>y为官方全国Q9中位数，S为既有Core＋Normal（τ固定8）的模拟全国值，π为最新已公布CPI同比。D打开时，截距和模拟变化的系数可以不同。这是带外生变量与状态交叉项的差分回归；没有拟合MA残差项，也没有自动变成ARIMA。</p>
<p><strong>温和正向修正：</strong>另比较一个限制较强的家族，在差分模型中加入正向价格变化，以及D·max(Δπ−ΔS,0)，后者只有“价格涨幅加快、模拟变化仍较小”时为正。两项系数限制为非负，其余系数自由。它只是待检验的修正函数，两种变化虽然同为pp，却不是同一经济量，差值不代表已估计的真实认知缺口；也不保证整个预测一定高于基线。</p>
<p>分段响应和干预变量是常见回归工具，可参见<a href="https://otexts.com/fpp3/regression.html#intervention-variables">Hyndman与Athanasopoulos：干预变量</a>及<a href="https://otexts.com/fpp3/regression.html#nonlinear-regression">分段线性回归</a>。这些方法支持模型写法，并不能证明本项目的具体触发阈值或经济机制成立。</p>
<h2>3．先固定旧系数，再看逐月学习</h2>
<p>为形成真正的一阶差分，2019-01仅提供滞后值，不进任何模型的训练。所有家族都用2019-02—2020-12的23期选参和拟合；之后评价2021-01—2025-10的58期。月末前最后公开SCE在全部相邻月上等于上月首发值，已逐行检查。固定版本全程不更新系数；更新版本每月仅吸收那时已经公布的更早SCE，正则化强度与阈值不再调。</p>
<p>固定交叉模型2021上半年MAE也降到0.1975pp，说明改善并非全由2021年内重估带来；但全年0.3067仍更差。其初始模拟变化系数在非触发月为{co['sim_change']:.3f}，触发月为{co['sim_change']+co['trigger_sim_change']:.3f}，容易放大随后模拟本身较大的跳升。更新模型7月预测5.508%、真实4.8%；11月预测6.448%、真实6.0%。这些过冲解释了下半年退步，不能只报告上半年改善。</p>
<figure><img src="prediction_2021.png" alt="2021年固定和逐月更新模型的预测折线与真值基线"><figcaption>上图固定2019—2020系数，下图逐月只用已公布历史重新估计。两图使用相同坐标尺度，蓝色交叉模型的早期响应与后期过冲同时可见。所有模型都采用同一月末宏观信息口径。</figcaption></figure>
<h2>4．完整比较：MAE越低越好，单位pp</h2>
<p><strong>逐月更新系数：</strong>各模型每月同样更新，SCE＋CPI与加入模拟的配对家族使用相同训练、验证和发布过滤规则；各自按同一候选集合选岭强度，数值未强制相同。完整8个家族保留，不依据2021排名修改协议。</p>
{table('expanding')}
<details><summary>展开查看：完全固定2019—2020系数的8个家族</summary>{table('fixed')}<p>固定温和正向修正2021为0.2789pp、全58月0.2496pp，均不如持续性。逐月更新的收益不能解释为仅凭2020年底知识就成功识别后来的异常。</p></details>
<p>作为不同阶段的代价检查，温和正向修正2022为0.3744pp（持续性0.3833），2023-01—2025-10为0.1675pp（持续性0.1765）；全58月0.2253（持续性0.2345），约降低3.9%。这些只是本次预设列表中的探索结果，尚未据此选定生产模型。</p>
<h2>5．哪些收益来自模拟，哪些来自统计模型？</h2>
<p>全58月差分家族不含模拟0.2349、加入模拟0.2266pp；温和正向家族0.2326→0.2253pp。温和组同时增加模拟变化与带触发的非线性修正，后者改变函数形式，因此无法把这个增量进一步分成纯模拟贡献、触发贡献或非线性贡献。触发器交叉家族全58月0.2329→0.2255，但2021全年0.2403→0.2814反而恶化。不能把全部后处理改善归给LLM，也不能说所有异常时期都受益。</p>
<figure><img src="matched_increment.png" alt="三种家族全58月加入模拟后相对宏观控制的MAE变化区间"><figcaption>3月区块重抽样、2000次、固定种子。区间未校正多模型比较，也不包含本次因观察2021弱点而提出新设计的选择不确定性。差分和温和修正的条件区间虽位于零以下，仍不能当成全新独立检验的显著预测贡献。</figcaption></figure>
<h2>6．下一步如何用这些结果？</h2>
<p>可以把“观察到的价格压力决定修正强度”保留为有依据的辅助建模方向，但不建议为了2021继续叠加年份虚拟变量或追着最小误差调阈值。差分提供了变化视角；自由交叉项更灵活也更容易过冲；方向约束能抑制部分不合理响应，现有改善仍较小。主简单组合、原始模拟与微观指标继续保留。</p>
<p>本轮是在已知历史弱点后开展的回顾性分析。虽然训练和更新按公布时间过滤，2021及后续月份已被查看，不能称新盲测；A的真实人口/历史和模型知识边界也没有消失。本次只评全国Q9；没有改变LLM个人回答，不能声称Q8、W1或IQR因此改善，也不自动升级路线B。</p>
<p><a href="../../20261026_dynamic_presentation/results_v2/index.html">此前月末公平对照与主辅指标</a> · <a href="../README.md">本轮口径与复算命令</a></p>
<small>来源：{source.relative_to(ROOT)}。原始A/B、评分、τ、历史输出、报告v05及研究包v02均未改。0新增API，0新密度拟合。</small></main></html>'''
    (out/'index.html').write_text(text)
    write(out/'readout.json',dict(source_summary_sha256=sha(source/'summary.json'),threshold_pp=s['threshold_pp'],results=r,
                                 paired_comparisons=s['paired_comparisons'],new_api_calls=0))
    write(out/'manifest.json',dict(source_manifest_sha256=sha(source/'manifest.json'),renderer_sha256=sha(Path(__file__)),
        files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print(out/'index.html')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();build(a.source,a.out)


if __name__=='__main__':main()
