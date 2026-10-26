"""Publish cached media mechanism findings; no API and no probability refitting."""
import argparse
import html
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
import numpy as np

from ..experiments.frozen_batch import ROOT, dump, read_json, sha

NAMES=['A82','R0','Q0','Q1','Q2','Q3']
SHORT=['A82原配置','R0 路由','Q0 四档量','Q1 警示','Q2 Fox','Q3 CPI']
COLORS=['#888888','#555555','#006da8','#888888','#888888','#d65f00']
METRICS=[('q9_center_mae_pp','中心MAE'),('cross_section_w1_pp','跨人W1'),('cross_person_iqr_pp','跨人IQR')]


def f(value,n=3):
    return f'{value:.{n}f}'


def figures(s,out):
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],
        'font.size':11,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(15,4.7))
    for ax,(key,title) in zip(axes,METRICS):
        vals=[s['main'][a]['metrics'][key] for a in NAMES]
        bars=ax.bar(range(6),vals,color=COLORS)
        ax.bar_label(bars,fmt='%.3f',padding=4,fontsize=10)
        ax.set_xticks(range(6),SHORT,rotation=28,ha='right')
        ax.set_title(title+('（越小越好）' if key!='cross_person_iqr_pp' else '（对照真人）'))
        ax.set_ylabel('百分点（pp）');ax.set_xlabel('实验配置');ax.margins(y=.2);ax.grid(axis='y',alpha=.12)
        if key=='cross_person_iqr_pp':
            human=s['main']['Q0']['metrics']['real_cross_person_iqr_pp']
            ax.axhline(human,color='#111111',linestyle='--',label=f'真人 {human:.3f}');ax.legend(fontsize=10)
    fig.suptitle('七期同支持比较：641个人月；A82原一遍，其余两遍等权',fontsize=14)
    fig.tight_layout();fig.savefig(out/'overall.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,4.7));x=np.arange(7)
    for arm,color,marker in [('A82','#555555','s'),('Q0','#006da8','o'),('Q3','#d65f00','D')]:
        rows=s['main'][arm]['monthly']
        axes[0].plot(x,[r['q9_center_bias_pp'] for r in rows],color=color,marker=marker,label=s['labels'][arm])
    axes[0].axhline(0,color='#111111',linestyle='--');axes[0].set_title('各月中心偏差：负为低估，正为高估')
    axes[0].set_ylabel('模拟中位数−真人中位数（pp）');axes[0].legend(fontsize=10)
    pair=next(r for r in s['effects'] if r['candidate']=='Q3')
    bars=axes[1].bar(x,[r['q9_center_mae_pp'] for r in pair['monthly']],color='#d65f00')
    axes[1].bar_label(bars,fmt='%+.3f',padding=4,fontsize=10)
    axes[1].axhline(0,color='#111111',linestyle='--');axes[1].set_title('Q3相对Q0：各月MAE变化')
    axes[1].set_ylabel('MAE差（pp）；负值表示Q3更好');axes[1].margins(y=.2)
    for ax in axes:
        ax.set_xticks(x,[str(m)[:4]+'-'+str(m)[4:] for m in s['months']],rotation=30,ha='right')
        ax.set_xlabel('目标月份（七个离散月份）');ax.grid(axis='y',alpha=.13)
    fig.tight_layout();fig.savefig(out/'monthly.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5));levels=['low','middle','high'];labels=['上期低预期组','上期中预期组','上期高预期组']
    for arm,color in [('Q0','#006da8'),('Q3','#d65f00')]:
        groups=[next(g for g in s['groups'] if g['dimension']=='prior' and g['label']==level and g['arm']==arm) for level in levels]
        for ax,key in zip(axes,['q9_center_bias_pp','cross_section_w1_pp']):
            ax.plot(range(3),[r['metrics'][key] for r in groups],marker='o',color=color,label=s['labels'][arm])
    axes[0].axhline(0,color='#111111',linestyle='--');axes[0].set_title('低预期组被抬高，高预期组被压低');axes[0].set_ylabel('组内中心偏差（pp）')
    axes[1].set_title('高预期组的分布距离仍最大');axes[1].set_ylabel('跨人W1（pp）')
    for ax in axes:
        ax.set_xticks(range(3),labels);ax.set_xlabel('按每月本人真实上期预期排序分三组');ax.legend();ax.grid(axis='y',alpha=.13)
    fig.tight_layout();fig.savefig(out/'prior_groups.png',dpi=170);plt.close(fig)


def canvas(s,path):
    data=json.dumps(s,ensure_ascii=False,separators=(',',':'))
    template='''import {H1,H2,Text,Stack,Grid,Stat,Select,BarChart,LineChart,Table,Callout,Divider,useState,useHostTheme} from "cursor/canvas";
const D=__DATA__;
const F=(x:number)=>x.toFixed(3);
const date=(x:number)=>String(x).slice(0,4)+"-"+String(x).slice(4);
const K={q9_center_mae_pp:"中心MAE",cross_section_w1_pp:"跨人W1",cross_person_iqr_pp:"跨人IQR"};
export default function MediaMechanism(){
 const theme=useHostTheme(); const [tab,setTab]=useState("main");const [metric,setMetric]=useState("q9_center_mae_pp");const [candidate,setCandidate]=useState("Q3");const [dimension,setDimension]=useState("prior");
 const order=["A82",...D.arms];const view=tab==="baseline"?D.with_previous_truth:D.main;
 const names=tab==="baseline"?[...order,"copy_previous"]:order;
 const rows=D.effects.find(r=>r.candidate===candidate&&r.base==="Q0");
 const gs=D.groups.filter(g=>g.dimension===dimension&&g.arm==="Q0");
 const groupLabels={low:"上期低预期",middle:"上期中预期",high:"上期高预期","4":"4篇","8":"8篇","16":"16篇","32":"32篇"};
 return <Stack gap={18} style={{padding:24,maxWidth:1160,margin:"0 auto",fontFamily:'"Times New Roman","Kaiti SC","STKaiti",serif',background:theme.bg.editor,color:theme.text.primary}}>
 <Text>SCE · 七期探索性新闻机制对照 · 每月96人 · DeepSeek V3.2 / SiliconFlow FP8</Text>
 <H1>运行完成；CPI相关新闻权重有局部收益</H1>
 <Text>Q3相对Q0的中心MAE下降约9.5%，但收益集中于2021-06；分布过度集中与持续性基线差距仍在。没有据此改写A82/B11或重跑主线。</Text>
 <Grid columns={3} gap={20}><Stat label="技术可用 / 全部请求" value="6,704 / 6,720"/><Stat label="API报告费用" value="$4.500"/><Stat label="Q3对Q0：中心MAE变化" value="−0.046 pp"/></Grid>
 <Select value={tab} onChange={setTab} options={[{value:"main",label:"五组与A82：641个人月"},{value:"effects",label:"机制增量与月份"},{value:"baseline",label:"照抄上期：524个人月"},{value:"groups",label:"条件分组"},{value:"run",label:"运行与研究边界"}]}/>
 {(tab==="main"||tab==="baseline")&&<Stack gap={14}>
 <H2>{tab==="main"?"相同人口、相同权重的配置比较":"有真实上期回答者：单独与基线比较"}</H2>
 <Select value={metric} onChange={setMetric} options={Object.entries(K).map(([value,label])=>({value,label}))}/>
 <BarChart categories={names.map(a=>D.labels[a])} series={[{name:K[metric]+"（pp）",data:names.map(a=>view[a].metrics[metric]),tone:"info"}]} horizontal height={340} valueSuffix=" pp" showValues referenceLines={metric==="cross_person_iqr_pp"?[{value:view.Q0.metrics.real_cross_person_iqr_pp,label:"真人跨人IQR",tone:"neutral"}]:[]}/>
 <Text>纵轴：配置；横轴：{K[metric]}（pp）。MAE/W1越小越好；IQR应与真人比较。七个月等权，新组两遍等权，A82仅原一遍。来源：本批缓存评价。</Text>
 <Table headers={["配置","中心MAE(pp)","W1(pp)","跨人IQR(pp)","Q8中心MAE(pp)"]} rows={names.map(a=>[D.labels[a],F(view[a].metrics.q9_center_mae_pp),F(view[a].metrics.cross_section_w1_pp),F(view[a].metrics.cross_person_iqr_pp),F(view[a].metrics.q8_center_mae_pp)])}/>
 <Callout tone="warning" title="两层支持不能混比">主比较641个人月含不同历史状态者；524个人月视图额外要求本人真实上期记录。不能拿主视图Q3的0.439和另一视图基线0.332直接比较。同基线支持上Q3为0.433pp。</Callout>
 </Stack>}
 {tab==="effects"&&<Stack gap={14}>
 <H2>把每一项增量与Q0比较</H2>
 <Select value={candidate} onChange={setCandidate} options={[{value:"Q1",label:"Q1：警示新闻×2"},{value:"Q2",label:"Q2：混入Fox"},{value:"Q3",label:"Q3：CPI相关度×1.5"}]}/>
 <BarChart categories={rows.monthly.map(r=>date(r.month))} series={[{name:"候选−Q0：中心MAE差",data:rows.monthly.map(r=>r.q9_center_mae_pp),tone:"warning"}]} height={290} valueSuffix=" pp" showValues/>
 <Text>横轴：七个目标月；纵轴：MAE差（pp）。负为改善，正为恶化；每月对两遍等权。来源：同支持641个人月。</Text>
 <Text>总体MAE差{F(rows.delta.q9_center_mae_pp)}pp；改善月份{rows.center_win_months}/7。两遍分别{F(rows.per_repeat_delta["1"].q9_center_mae_pp)}、{F(rows.per_repeat_delta["2"].q9_center_mae_pp)}pp。</Text>
 <LineChart categories={D.months.map(date)} series={[{name:"A82原配置偏差",data:D.main.A82.monthly.map(r=>r.q9_center_bias_pp),tone:"neutral"},{name:"Q0偏差",data:D.main.Q0.monthly.map(r=>r.q9_center_bias_pp),tone:"info"},{name:"Q3偏差",data:D.main.Q3.monthly.map(r=>r.q9_center_bias_pp),tone:"warning"}]} height={280} valueSuffix=" pp" referenceLines={[{value:0,label:"与真人中心一致"}]}/>
 <Text>横轴：七个离散目标月；纵轴：模拟中心−真人中心（pp）。2021年仍偏低、2022-06偏高。曲线只连接离散观测，不表示连续逐月验证。</Text>
 <Callout tone="info" title="收益与稳健性分开判断">Q3两遍中心MAE均改善，但W1第二遍略退步；剔除2021-06后，MAE差变为+0.011pp。不能称跨月份稳定或接近严格帕累托。</Callout>
 </Stack>}
 {tab==="groups"&&<Stack gap={14}>
 <H2>收益在哪些条件下出现？</H2>
 <Select value={dimension} onChange={setDimension} options={[{value:"prior",label:"上期预期：低／中／高"},{value:"news_count",label:"相同新闻量档：4／8／16／32"}]}/>
 <BarChart categories={gs.map(g=>groupLabels[g.label])} series={[{name:"Q0中心MAE",data:gs.map(g=>g.metrics.q9_center_mae_pp),tone:"info"},{name:"Q3中心MAE",data:gs.map(g=>D.groups.find(x=>x.dimension===dimension&&x.label===g.label&&x.arm==="Q3").metrics.q9_center_mae_pp),tone:"warning"}]} height={280} valueSuffix=" pp"/>
 <Text>横轴：条件分组；纵轴：组中心MAE（pp）；组月／遍等权。各组每月共同支持20—32人，描述性分析，不作因果解释。来源：缓存回答及预登记分组。</Text>
 <Text>低预期组仍被模型抬高，高预期组仍被压低。Q3主要减轻高预期组误差，没有恢复组内真人分散程度；新闻量也没有单调的拟合收益。</Text>
 </Stack>}
 {tab==="run"&&<Stack gap={14}>
 <H2>技术运行成功，16份缺失保留</H2>
 <Text>已尝试6,720次、全部回包入档，无未知在途。15次连接失败，1份Q9重复bin5且缺bin8；没有看到拒答。Q8有效字段独立保留。9份Q9按登记规则归一化。</Text>
 <Text>生成耗时约64.4分钟；API报告$4.49955，未知费用预留$0.05753，合计已计及预留$4.55708。预留不是已确认扣费。没有自动失败重发或供应商回退。</Text>
 <H2>解释边界</H2><Text>同支持子样本指标并非全国headline；A82原一遍的历史对照也包含生成和托管时点差异。七期已参与既有分析，两遍不是独立新闻分配种子，未进行独立时间外验证。</Text>
 <Text>R0修路由；Q0改新闻量为4/8/16/32；Q1只加警示权重；Q2同时改变媒体和文章内容；Q3只加CPI直接相关权重。后面三组都各自对Q0，不是逐项累加。</Text>
 </Stack>}
 <Divider/><Text>来源：sce_media_mechanism_terminal_20261025_v2 / round_0001；cached readout 2026-10-25。新分析0 API、0 Q9重拟合；不包含原始个人或新闻文本。</Text>
 </Stack>;
}
'''
    Path(path).write_text(template.replace('__DATA__',data))


def publish(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists():raise ValueError('Fresh report directory required')
    s=read_json(source/'summary.json');out.mkdir(parents=True)
    dump(out/'summary.json',s);figures(s,out);canvas(s,out/'SCE-media-mechanism-results-20261025.canvas.tsx')
    rows=''.join('<tr><td>'+s['labels'][a]+'</td>'+''.join('<td>'+f(s['main'][a]['metrics'][k])+'</td>' for k in
        ('q9_center_mae_pp','center_rmse_pp','cross_section_w1_pp','cross_person_iqr_pp','q8_center_mae_pp'))+'</tr>' for a in NAMES)
    brows=''.join('<tr><td>'+s['labels'][a]+'</td>'+''.join('<td>'+f(s['with_previous_truth'][a]['metrics'][k])+'</td>' for k in
        ('q9_center_mae_pp','cross_section_w1_pp','cross_person_iqr_pp'))+'</tr>' for a in ['A82',*s['arms'],'copy_previous'])
    mrows=''.join('<tr><td>'+str(month)[:4]+'-'+str(month)[4:]+'</td>'+''.join('<td>'+f(s['main'][a]['monthly'][i]['q9_center_mae_pp'])+'</td>' for a in NAMES)+'</tr>' for i,month in enumerate(s['months']))
    htmlpage='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>新闻机制V3：七期结果</title>
<style>body{margin:0;background:#f5f4f0;color:#202631;font:18px/1.75 "Times New Roman","Kaiti SC","STKaiti",serif}main{max-width:1180px;margin:auto;padding:30px}h1{font-size:32px;line-height:1.3}h2{font-size:25px;border-top:1px solid #c8ced3;padding-top:22px;margin-top:36px}h3{font-size:21px}p{margin:.7em 0}img{width:100%;height:auto;background:white}.lead{font-size:21px}.note{font-size:16px;color:#536071}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}.stats b{display:block;font-size:28px;color:#006da8}.focus{background:white;border-left:5px solid #d65f00;padding:18px 22px}table{border-collapse:collapse;width:100%;font-size:17px;background:white}td,th{padding:9px 12px;border-bottom:1px solid #d9dce0;text-align:right}td:first-child,th:first-child{text-align:left}th{background:#edf1f4}details{margin:18px 0}a{color:#006da8}.scroll{overflow:auto}@media(max-width:750px){main{padding:18px}.stats{grid-template-columns:1fr}body{font-size:17px}}</style><main>
<p class="note">水上挽月 · SCE · 2026-10-25 · 研究中的探索性机制结果</p>
<h1>新闻机制V3：相关价格信息有收益，微观差距仍在</h1>
<p class="lead">运行与评价均成功。提高CPI直接相关新闻的抽取权重，带来本轮最清晰的中心误差信号；增加警示新闻和混入Fox的整体收益较弱，尚未突破照抄上期基线。</p>
<div class="stats"><div><b>99.76%</b>技术可用率：6,704 / 6,720</div><div><b>$4.500</b>API已报告费用；未知费预留另计</div><div><b>−9.5%</b>Q3相对Q0的中心MAE</div></div>
<h2>1. 这轮究竟比较了什么</h2>
<p>2019-05、2020-09、2021-06/09/12、2022-06、2023-12，每期96人，五组各两遍。人口、个人历史信念、价格、采购角色、政策、模型及温度保持不变，主要替换新闻分配。模型为DeepSeek V3.2，经OpenRouter固定SiliconFlow FP8，温度0.5。</p>
<p><b>R0：</b>沿原3/8/20篇，只修正重要CPI新闻路由；<b>Q0：</b>改4/8/16/32篇；<b>Q1：</b>Q0加警示文章抽取权重2倍；<b>Q2：</b>Q0部分个人新闻来自Fox；<b>Q3：</b>Q0加CPI直接相关权重1.5倍。Q1/Q2/Q3分别对Q0，不是逐项叠加。A82为这些人的原一遍归档回答。</p>
<h2>2. 五组及原配置：统一支持后看收益与代价</h2>
<p>以下统一使用641个人月：真人与各组两遍均可计分的人，权重相同，七个月及模型两遍等权；A82仍只有原一遍。中心指个人Q9拟合密度均值的跨人加权中位数，不是Q8，也不是完整全国headline。</p>
<img src="overall.png" alt="同支持配置的中心MAE、W1与IQR"><div class="scroll"><table><tr><th>配置</th><th>Q9中心MAE(pp)</th><th>Q9中心RMSE(pp)</th><th>W1(pp)</th><th>跨人IQR(pp)</th><th>Q8中心MAE(pp)</th></tr>__ROWS__</table></div>
<div class="focus"><b>主要信号：Q3相对Q0。</b>中心MAE从0.485降至0.439pp（−9.5%），W1从2.742降至2.668pp，个人预期均值MAE从3.941降至3.910pp；跨人IQR从2.315增至2.338pp，真人为5.359pp。中心有所改善，宽度的缺口没有被补齐。Q8中心MAE则从0.864增至0.907pp。</div>
<p>相对A82原回答，Q3中心MAE为0.596→0.439pp；但W1为2.619→2.668pp，IQR为2.482→2.338pp。因此不能把整套新设计称为全面改善，也不能把单一历史生成对照当成纯粹路由因果效应。</p>
<h2>3. 哪些月份改善？2021年有所缓解，2022年仍高估</h2>
<img src="monthly.png" alt="各月中心偏差与CPI权重的增量收益">
<p>2021年三个样本月的中心MAE：A82为0.902、R0为0.545、Q0为0.529、Q1为0.471、Q2为0.396、Q3为0.374pp。Q3相对Q0主要改善6月：1.113→0.725pp；9月为0.241→0.158pp，12月基本不变。2022-06仍明显高估，Q0为+1.307、Q3为+1.331pp。</p>
<p><b>稳健性：</b>Q3两遍中心MAE差分别为−0.044、−0.048pp；但只有3/7月中心误差改善，删除2021-06后平均差变为+0.011pp。W1两遍差为−0.169、+0.022pp。收益值得记录，尚不能称跨月份稳定的分布改善。</p>
<p>Q1警示权重的主MAE为0.485→0.488pp，Q2混入Fox为0.485→0.482pp，均接近持平；两遍改善方向反转。它们能在2021年6月帮助上调，但同时在其他时期付出代价，不能据本轮证明“更负面／多媒体就更接近居民”。</p>
<details><summary>展开逐月中心MAE（两遍等权；pp）</summary><div class="scroll"><table><tr><th>月份</th><th>A82</th><th>R0</th><th>Q0</th><th>Q1</th><th>Q2</th><th>Q3</th></tr>__MONTHS__</table></div></details>
<h2>4. 与照抄本人上期比较：单独使用524个人月</h2>
<p>新人和缺历史者没有真实上期回答，不能替他们虚构“照抄本人上期”。下表进一步限定为具有真人上期记录的共同524个人月。它与上面的641个人月是不同支持，不能交叉取数比较。</p>
<div class="scroll"><table><tr><th>配置</th><th>中心MAE(pp)</th><th>W1(pp)</th><th>跨人IQR(pp)</th></tr>__BASELINE__</table></div>
<p>在这一支持上，Q3中心MAE为0.433pp，持续性基线为0.332pp；W1为2.375对1.003pp。新闻机制的局部改进确实存在，但仍未超过这个简单基线。</p>
<h2>5. 分组告诉我们：均值压缩仍是核心缺口</h2>
<img src="prior_groups.png" alt="上期高低预期组的中心偏差和分布距离">
<p>按本人上期真实预期排序分三组，Q0低预期组中心偏差为+1.212pp，高预期组为−1.858pp；Q3分别为+1.254和−1.731pp。CPI相关信息减轻了高预期组的低估，但低预期组没有同步受益。高预期组W1为4.233→3.988pp，仍远大于中间组。</p>
<p>这与“模型把不同居民的预期往共同中心拉”的既有诊断一致。提高内容相关性可能帮助更新方向；仅增加情绪强度或媒体标签，尚不足以恢复个人信念持续性和组内差异。这是数据支持的机制线索，不是已识别的因果结论。每个组月约20—32人，不能据此继续精细调参。</p>
<h2>6. 运行、费用与下一步</h2>
<p>6,720次全部尝试、全部回包入档，0未知在途。15次连接失败；另1份回答重复bin5、缺bin8，保留合法Q8，Q9不猜测修复。没有观察到拒答。9份合法十档进行了登记的等比例归一化。生成约64.4分钟，API报告费用$4.49955，未知费用预留$0.05753，合计$4.55708；预留不等于确认扣费。</p>
<p><b>建议：</b>记录CPI相关度权重为有希望的局部候选，不把警示2倍、Fox或整套四档量一并升级。当前不因这批结果重跑A82/B11；先把机制证据、收益和代价加入报告及研究包。如保留最后一次验证，应使用未参与调整的时期和额外新闻分配种子，同时保护2022年及近期高估时期。</p>
<p class="note">七个月均已在A82中出现，仅为探索性机制诊断；固定新闻分配下的两遍是模型随机性，不是独立分配种子。新分析0 API、0 Q9重拟合。原运行、原评价及原报告不覆盖。<a href="summary.json">聚合数据</a></p></main></html>'''
    (out/'index.html').write_text(htmlpage.replace('__ROWS__',rows).replace('__BASELINE__',brows).replace('__MONTHS__',mrows))
    dump(out/'manifest.json',dict(source=str(source.relative_to(ROOT)),source_sha256=sha(source/'summary.json'),
        new_api_calls=0,new_q9_fits=0,files_sha256={f.name:sha(f) for f in out.iterdir() if f.is_file()}))
    return {'status':'report_written','index':str(out/'index.html'),'new_api_calls':0,'new_q9_fits':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args();print(json.dumps(publish(a.source,a.out),ensure_ascii=False,indent=2))
