"""MAE-first review of cached seven-month media results; no new model calls."""
import html
import json
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt, font_manager

from ..experiments.frozen_batch import ROOT, dump, read_json, sha
from .media_mechanism_trends import REGIMES, STYLES

ORDER = ['A82', 'R0', 'Q0', 'Q1', 'Q3', 'Q2']
PRIMARY = ['A82', 'Q0', 'Q1', 'Q3']
MAE = 'q9_center_mae_pp'


def summarize(view):
    result = {}
    for arm, values in view.items():
        rows = values['monthly']
        y21 = [r for r in rows if r['month'] // 100 == 2021]
        other = [r for r in rows if r['month'] // 100 != 2021]
        all_mae = float(np.mean([r[MAE] for r in rows]))
        if not np.isclose(all_mae, values['metrics'][MAE], atol=1e-12, rtol=0):
            raise ValueError('Cached monthly MAE does not reconcile')
        result[arm] = {
            'all_mae_pp': all_mae,
            'y2021_three_month_mae_pp': float(np.mean([r[MAE] for r in y21])),
            'other_four_month_mae_pp': float(np.mean([r[MAE] for r in other])),
            'worst_month_mae_pp': max(r[MAE] for r in rows),
            'worst_month': max(rows, key=lambda r: r[MAE])['month'],
            'rmse_pp': values['metrics']['center_rmse_pp'],
            'w1_pp': values['metrics']['cross_section_w1_pp'],
            'iqr_pp': values['metrics']['cross_person_iqr_pp'],
            'q8_center_mae_pp': values['metrics']['q8_center_mae_pp'],
            'monthly': rows,
        }
    return result


def chart(s, path, arms, view='main', bias=False):
    x = np.arange(len(s['months']))
    fig, ax = plt.subplots(figsize=(12.4, 5.4))
    key = 'q9_center_bias_pp' if bias else MAE
    for arm in arms:
        color, marker, line = STYLES[arm]
        ax.plot(x, [r[key] for r in s[view][arm]['monthly']], color=color,
                marker=marker, linestyle=line, linewidth=2.2, markersize=6,
                label=s['labels'][arm])
    if bias:
        ax.axhline(0, color='#777777', linewidth=1, linestyle=':')
    else:
        ax.set_ylim(bottom=0)
    ax.set_xticks(x, [f'{str(m)[:4]}-{str(m)[4:]}\n{REGIMES[m]}' for m in s['months']])
    ax.set_xlabel('目标调查月份（七个离散选期；等距排列）')
    ax.set_ylabel('模拟中位数−真人中位数（pp）' if bias else '该月Q9中心绝对误差（pp）')
    support = '524个本人真实上期个人月' if view != 'main' else '641个共同个人月'
    ax.set_title(('误差方向：负值为低估，正值为高估' if bias else '逐月MAE：先看2021低估与2022高估') + ' · ' + support)
    ax.grid(axis='y', alpha=.15)
    fig.legend(*ax.get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.5,.93),
               ncol=4, frameon=False, fontsize=11)
    fig.tight_layout(rect=(0,0,1,.82))
    fig.savefig(path, dpi=170)
    plt.close(fig)


def make_canvas(d, path):
    template = '''import {H1,H2,Text,Stack,Grid,Stat,Select,Table,LineChart,Callout,Divider,useState,useHostTheme} from "cursor/canvas";
const D=__DATA__;
const F=(n:number)=>n.toFixed(3);
const date=(m:number)=>String(m).slice(0,4)+"-"+String(m).slice(4);
export default function MediaMAEReview(){
 const t=useHostTheme();const [v,setV]=useState("main");const [candidate,setCandidate]=useState("Q3");
 const V=D.views[v];const names=v==="main"?D.order:[...D.order,"copy_previous"];
 const selected=candidate==="copy_previous"&&v==="main"?"Q3":candidate;
 const q0=V.Q0;const c=V[selected];
 return <Stack gap={18} style={{padding:24,maxWidth:1180,margin:"0 auto",fontFamily:'"Times New Roman","Kaiti SC","STKaiti",serif',color:t.text.primary,background:t.bg.editor}}>
 <Text>SCE新闻机制 · 2026-10-25 · 只读已封存结果 · 新API 0</Text>
 <H1>先检验总体MAE与2021误差，再解释微观分布</H1>
 <Text>CPI相关新闻加权是当前最有潜力的候选，但它在2021低估与2022高估之间仍有明显取舍。警示与CPI联合组尚未运行。</Text>
 <Grid columns={3} gap={18}><Stat label="七期MAE：Q0 → CPI加权" value="0.485 → 0.439 pp"/><Stat label="2021三期MAE：Q0 → CPI加权" value="0.529 → 0.374 pp"/><Stat label="2022-06：CPI组仍高估" value="+1.331 pp"/></Grid>
 <Callout tone="info" title="阅读顺序">首要看七期等权MAE及2021三个样本月；其次看其他四月、最大误差、误差方向、两遍与删月敏感性；最后看W1/IQR解释分布代价。此顺序用于后续决策，不改写旧实验的预设判定。</Callout>
 <Select value={v} onChange={setV} options={[{value:"main",label:"主比较：641共同个人月"},{value:"with_previous_truth",label:"基线比较：524真实上期个人月"}]}/>
 <H2>配置与时期：Q9中心MAE（pp）</H2>
 <Table headers={["配置","全部七期","2021三期","其他四期","RMSE","最大月误差"]} rows={names.map(a=>[D.labels[a],F(V[a].all_mae_pp),F(V[a].y2021_three_month_mae_pp),F(V[a].other_four_month_mae_pp),F(V[a].rmse_pp),date(V[a].worst_month)+" / "+F(V[a].worst_month_mae_pp)])}/>
 <Text>七期：2019-05、2020-09、2021-06/09/12、2022-06、2023-12；每月96个不同人、新组各两遍，A82原一遍。主比较不是全国82个月误差；“其他四期”也不是完整其他年份。来源：冻结评价缓存。</Text>
 <Select value={selected} onChange={setCandidate} options={names.filter(a=>a!=="Q0").map(a=>({value:a,label:D.labels[a]}))}/>
 <H2>逐月MAE：四档新闻组与所选候选</H2>
 <LineChart categories={D.months.map(date)} series={[{name:"Q0 四档新闻",data:q0.monthly.map(r=>r.q9_center_mae_pp),tone:"info"},{name:D.labels[selected],data:c.monthly.map(r=>r.q9_center_mae_pp),tone:"warning"}]} height={320} showValues valueSuffix=" pp"/>
 <Text>横轴：目标月，离散月份等距连接；纵轴：Q9中心绝对误差（pp）。每点为两遍各自误差的平均，A82只有原一遍；并非先平均预测再算误差。来源：上述同支持缓存。</Text>
 <H2>误差方向：改善低估，还是放大高估？</H2>
 <LineChart categories={D.months.map(date)} series={[{name:"Q0偏差",data:q0.monthly.map(r=>r.q9_center_bias_pp),tone:"info"},{name:D.labels[selected]+"偏差",data:c.monthly.map(r=>r.q9_center_bias_pp),tone:"warning"}]} height={280} beginAtZero={false} referenceLines={[{value:0,label:"与真人中位数一致"}]} valueSuffix=" pp"/>
 <Text>横轴：目标月；纵轴：模拟中心−真人中心（pp）。负为低估，正为高估；来源同上。不能用正负偏差的抵消代替MAE。</Text>
 <Callout tone="warning" title="CPI组的两处关键边界">2021-06从Q0的1.113降到0.725pp，但仍明显低估；2022-06从1.307升到1.331pp。去掉2021-06，Q3相对Q0的七期剩余平均MAE变化为+0.011pp。两遍MAE均改善，也不能证明跨时期稳定。</Callout>
 <H2>下一轮：只补CPI×警示的联合组</H2>
 <Table headers={["CPI权重","警示关","警示×2"]} rows={[["关","Q0：已有","Q1：已有"],["×1.5","Q3：已有","X_CA：待新增"]]}/>
 <Text>相同七期、每期96人、两遍；模型仍为DeepSeek V3.2 / SiliconFlow FP8，温度0.5。其余P、历史、环境、新闻池、数量档和随机流固定。只提高抽中相关/警示文章的权重，不修改文章措辞，也不是对CPI数值或最终预测加权。</Text>
 <Text>联合组1,344位置中，419个完全相同提示的成功旧答复用、1个旧失败保留，仅924个新请求；估$0.94、建议硬上限$4。先补官方Core干跑与新执行/评价接线，再另行确认发送范围和预算。当前是离线草稿，未启动。</Text>
 <Text>判断联合组是否比Q3进一步降低MAE，同时检查2021与2022；再用四组差分判断是否超出单项收益的相加。不能按月份挑不同组拼出“最好曲线”。旧三档＋CPI另472次为可选，当前不优先。</Text>
 <H2>辅助：W1与IQR用于解释代价</H2>
 <Table headers={["配置","W1(pp)","跨人IQR(pp)","Q8中心MAE(pp)"]} rows={names.map(a=>[D.labels[a],F(V[a].w1_pp),F(V[a].iqr_pp),F(V[a].q8_center_mae_pp)])}/>
 <Text>主支持真人跨人IQR为5.359pp；模型Q3为2.338pp，宽度仍不足。Q8单独评价，不与Q9混算。基线视图另需本人真实上期，不能拿两个视图的数直接比较。</Text>
 <Divider/><Text>七期均已查看，仅为探索性机制结果；没有新增模拟、没有重拟Q9、未修改旧结果和默认配置。CPI×新闻量的分档结果已在原折线报告展示；四档跨人不同，不能据此挑有利档位。</Text>
 </Stack>;
}
'''
    Path(path).write_text(template.replace('__DATA__', json.dumps(d, ensure_ascii=False, separators=(',',':'))))


def publish(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('Fresh output directory required')
    s = read_json(source / 'trend_data.json')
    for name, digest in s['source_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('Original cached source changed: ' + name)
    d = {'status':'cached_mae_priority_review', 'new_api_calls':0, 'new_q9_fits':0,
         'months':s['months'], 'labels':s['labels'], 'support':s['support'], 'order':ORDER,
         'views':{v:summarize(s[v]) for v in ('main','with_previous_truth')},
         'source_trend_sha256':sha(source / 'trend_data.json'), 'source_sha256':s['source_sha256']}
    out.mkdir(parents=True)
    font = ROOT / 'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'], 'font.size':11,
                        'axes.unicode_minus':False, 'axes.spines.top':False,'axes.spines.right':False})
    chart(s, out/'monthly_mae.png', PRIMARY)
    chart(s, out/'monthly_bias.png', PRIMARY, bias=True)
    chart(s, out/'baseline_mae.png', ['Q0','Q3','copy_previous'], view='with_previous_truth')
    canvas_name = 'SCE-media-MAE-review-20261025.canvas.tsx'
    make_canvas(d, out / canvas_name)
    dump(out/'summary.json', d)
    def table(headers, rows):
        return '<div class="scroll"><table><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(c))+'</td>' for c in r)+'</tr>' for r in rows)+'</table></div>'
    def f(x):return f'{x:.3f}'
    period_rows = [[s['labels'][a], *[f(d['views']['main'][a][k]) for k in
        ('all_mae_pp','y2021_three_month_mae_pp','other_four_month_mae_pp','rmse_pp')]] for a in ORDER]
    monthly_rows = [[f'{str(m)[:4]}-{str(m)[4:]}', *[f(d['views']['main'][a]['monthly'][i][MAE]) for a in PRIMARY]] for i,m in enumerate(s['months'])]
    aux_rows = [[s['labels'][a], *[f(d['views']['main'][a][k]) for k in ('w1_pp','iqr_pp','q8_center_mae_pp')]] for a in ORDER]
    baseline_rows = [[s['labels'][a], *[f(d['views']['with_previous_truth'][a][k]) for k in ('all_mae_pp','y2021_three_month_mae_pp','other_four_month_mae_pp')]] for a in ['Q0','Q1','Q3','copy_previous']]
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>新闻机制：MAE优先审阅与交叉方案</title>
<style>body{margin:0;background:#f5f4f0;color:#202631;font:18px/1.75 "Times New Roman","Kaiti SC","STKaiti",serif}main{max-width:1140px;margin:auto;padding:30px}h1{font-size:31px;line-height:1.4}h2{font-size:24px;margin-top:38px;border-top:1px solid #c8ced3;padding-top:18px}p{text-indent:2em;margin:.7em 0}.note{font-size:16px;color:#536071}.focus{background:white;border-left:4px solid #d65f00;padding:14px 22px}.focus p{text-indent:0}img{width:100%;height:auto;background:white}table{border-collapse:collapse;width:100%;background:white;font-size:17px}td,th{padding:9px 11px;border-bottom:1px solid #d9dce0;text-align:right}th{background:#edf1f4}td:first-child,th:first-child{text-align:left}.scroll{overflow:auto}a{color:#006da8}details{margin:20px 0}li{margin:10px 0}@media(max-width:750px){main{padding:18px}body{font-size:17px}}</style><main>
<p class="note">水上挽月 · 2026-10-25 · 冻结结果离线整理 · 0新增API / 0新增Q9拟合</p>
<h1>新闻机制：先看MAE与2021误差，再解释分布</h1>
<div class="focus"><p><b>当前建议：</b>优先补齐“CPI相关新闻×警示新闻”的联合组。CPI组的七期中心MAE为0.439pp、2021三期为0.374pp，是现有候选中最值得继续的方向；但2021-06仍低估0.725pp，2022-06高估1.331pp，尚不能说已解决异常时期误差。</p></div>
<p>按用户最新关注，后续先看总体MAE、2021三个样本月及其他时期的误差；再看最大误差、误差方向和稳健性；最后用W1和IQR解释微观分布的收益与代价。分布指标继续披露，但不要求每次中心改善都必须同时改善所有分布指标。这个顺序用于后续研究，不改写旧实验的预设判定。</p>
<h2>一、这些数字具体指什么？</h2>
<p>每个人的Q9十档概率按原冻结算法拟合连续密度，取个人密度均值，再取同月跨人的设计加权中位数；模型中位数与同支持真人中位数之差取绝对值，最后对月份和两遍等权。<b>因此0.439pp是月度总体中心误差的平均，不是每个人平均只错0.439pp。</b>Q8另外计算。</p>
<p>本批七期各96人，同一人生成两遍，不是每期192个独立人。六组共同Q9有效支持为641个人月；A82仅原一遍。以下是同支持样本比较，不能与82个月全国MAE0.317直接混比。“2021”仅6/9/12月，“其他时期”仅2019-05、2020-09、2022-06、2023-12四点，不代表完整年份。</p>
<h2>二、已有实验的整体表现</h2>
__PERIOD_TABLE__
<p><b>A82</b>为原归档配置；<b>R0</b>修正重要CPI新闻路由；<b>Q0</b>在R0基础上改为4/8/16/32四档新闻量；<b>Q1</b>在Q0上加警示权重2倍；<b>Q3</b>在Q0上加CPI直接相关权重1.5倍。Q1与Q3尚未叠加。<b>Q2</b>混入Fox，旧结果保留，后续暂停。CPI加权指新闻抽取相关度，不是加权CPI数值，也不是对最终预测做回归。</p>
<p>CPI组相对Q0，整体MAE下降9.5%、2021三期下降29.4%；相对A82原配置，2021三期下降58.6%。但在其他四期，Q3为0.488pp，高于Q0的0.451与A82的0.365pp。这说明收益主要来自改善部分上行时期的低估，不能称全时期一致改善。</p>
<h2>三、逐月表现与异常点</h2>
<img src="monthly_mae.png" alt="A82、四档量、警示及CPI加权的逐月中心MAE折线图">
__MONTH_TABLE__
<img src="monthly_bias.png" alt="上述四组模拟中位数减真人中位数的偏差折线图">
<ol><li><b>2021-06低估明显缓解，但仍是难点。</b>A82误差1.752pp，四档新闻Q0为1.113，警示Q1为0.792，CPI组Q3为0.725；真人样本中心5.100%，Q3平均中心约4.375%。方向正确，距离仍不小。</li>
<li><b>2021-09/12已接近，不宜为6月一味抬高所有月份。</b>Q3误差分别0.158与0.239pp；9月优于Q0的0.241，12月与Q0的0.235基本接近。A82原9月误差仅0.056pp，因此“原方案2021很差”不等于每一个2021月份都差。</li>
<li><b>2022-06是最需要保护的高估月份。</b>Q0误差1.307pp、Q1为1.237、Q3为1.331；Q3平均中心7.844%，真人样本为6.513%。警示加权在本月反而略降低预测，不能把“警示”简单等同于上涨信号。</li>
<li><b>疫情期的代价不能被2021改善掩盖。</b>2020-09误差Q0为0.135pp、Q1为0.382、Q3为0.240；警示与CPI单项均退步。2023-12则Q0为0.080、Q1为0.063、Q3为0.036pp，绝对误差已经较小。</li></ol>
<p>稳健性上，Q3两遍相对Q0的整体MAE分别下降0.044、0.048pp；但仅3/7个月改善，删去2021-06后，剩余月平均MAE差变成<b>+0.011pp</b>。Q1整体MAE近持平，但RMSE从Q0的0.679降到0.612pp，说明“整体MAE近持平”并不等于大误差结构完全相同。七个月不足以确认跨时期稳定性。</p>
<h2>四、与照抄上期相比，处于什么位置？</h2>
<p>只在确有本人真实上期Q9的524个人月中比较，新人不虚构真人上期值。以下Q3为0.433pp，不是上面641支持的0.439pp；基线在这批样本整体仍更好。</p>
__BASELINE_TABLE__
<img src="baseline_mae.png" alt="真实上期支持下四档新闻、CPI与照抄上期的逐月MAE">
<p>例如2021-09，基线误差0.787pp、Q3为0.135pp，模型提供了有价值的当月调整；但2021-06基线0.194pp、Q3为0.557，2021-12基线0.056、Q3为0.465。不能事后挑每个月更好的方法拼接验证成绩。若再评价历史值与模型的组合，必须在较早月份拟权、较晚月份检验，不能在这七期中反复挑最优权重。</p>
<h2>五、下一轮交叉实验怎样做？</h2>
__CROSS_TABLE__
<p><b>只增加右下角X_CA：</b>固定新闻池、已审校标签、共同3篇、四档人数、个人历史、非新闻环境、模型、温度和随机流，叠加CPI1.5倍与警示2倍。两条件均满足的文章，加权部分得分乘3；仍有50%均匀抽取与不放回抽样，并非实际曝光概率乘3。不强化文章原话，也不增加一条“应当看涨”的指令。</p>
<p>同七期、96人、两遍，共1,344个联合位置，419个相同提示成功旧答可复用，1个相同提示旧失败保留缺失；<b>只新增924请求，估费$0.94，建议新批硬上限$4。</b>原Q0/Q1/Q3不重跑。模型仍DeepSeek V3.2，经OpenRouter固定SiliconFlow FP8，温度0.5、关闭思考、JSON。当前只有离线输入草稿，尚需官方Core干跑、新版复用执行/评价接线和范围预算授权，不会现在启动。</p>
<p>先看联合组相对最有潜力的Q3是否进一步降低七期与2021三期MAE，同时披露其他四期和最大月误差；尤其检查2022-06高估是否放大。随后查看两遍与删月敏感性，再报告W1/IQR/Q8。四组须统一支持；另外列原641支持上的缺失情况，不因新失败改变样本后直接套用旧平均数。</p>
<p>联合组优于Q3，表示叠加有用；只有进一步计算<code>L(X_CA)−L(Q3)−L(Q1)+L(Q0)</code>，才能在该损失尺度上描述是否超出两单项的相加。MAE与中位数非线性，这不等同于真人行为的因果互补系数。七期都已查看，仍是探索性机制补全，不能称独立验证。</p>
<p>“CPI×四档新闻”本身已经是Q3；现有数据可以分档看差异，不必新增调用。若问题是“旧三档与新四档，哪一种更有利于CPI加权”，才需要可选X_3C旧三档＋CPI组，另472次、估$0.45、建议帽$2。当前优先做X_CA一项，不同时再调剂量或重启Fox。</p>
<details><summary>辅助查看：W1、IQR和独立Q8</summary>__AUX_TABLE__<p>主支持真人跨人IQR为5.359pp，Q3只有2.338pp，模型仍过度集中。Q3相对Q0的W1从2.742降到2.668；Q8中心MAE从0.864升到0.907pp。它们用于说明收益与代价，不能替代核心MAE，也不因核心改善而省略。两遍W1方向不一致。</p></details>
<p class="note">来源：已封存Terminal运行、评价与results_v2/trend_data.json；逐文件哈希已核。原v1/v2、冻结协议、提示与主报告v0.4均保留。连线连接离散选期，不代表中间月份运行。<a href="../results_v2/index.html">完整12指标折线页</a> · <a href="../CROSSED_DESIGN_20261025.md">交叉草稿及剩余接线</a></p></main></html>'''
    page = page.replace('__PERIOD_TABLE__', table(['配置','七期MAE','2021三期MAE','其他四期MAE','七期RMSE'], period_rows))
    page = page.replace('__MONTH_TABLE__', table(['月份','A82原配置','Q0四档','Q1警示','Q3 CPI'],monthly_rows))
    page = page.replace('__BASELINE_TABLE__', table(['配置','七期MAE','2021三期MAE','其他四期MAE'],baseline_rows))
    page = page.replace('__CROSS_TABLE__', table(['CPI权重','警示关','警示×2'],[['关','Q0：旧答复用','Q1：旧答复用'],['×1.5','Q3：旧答复用','X_CA：新增联合组']]))
    page = page.replace('__AUX_TABLE__', table(['配置','W1(pp)','跨人IQR(pp)','Q8中心MAE(pp)'],aux_rows))
    (out/'index.html').write_text(page)
    dump(out/'manifest.json', {'source_trend_sha256':d['source_trend_sha256'], 'source_code_sha256':sha(__file__),
                             'new_api_calls':0, 'new_q9_fits':0,
                             'file_sha256':{f.name:sha(f) for f in out.iterdir() if f.is_file()}})
    return {'status':'mae_first_review_written','path':str(out/'index.html'),'new_api_calls':0,'new_q9_fits':0}
