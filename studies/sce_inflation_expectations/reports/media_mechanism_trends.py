"""Line-chart edition of cached news-mechanism results; no new simulation."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt

from . import media_mechanism_report as original
from ..experiments.frozen_batch import ROOT, dump, read_json, sha
from ..evaluation import cognition as shared

REGIMES={201905:'疫情前',202009:'疫情期',202106:'通胀上行',202109:'通胀上行',202112:'通胀上行',202206:'高通胀',202312:'通胀回落'}
STYLES={'A82':('#303030','s','--'),'R0':('#777777','x','-.'),'Q0':('#006da8','o','-'),
        'Q1':('#913d99','^','--'),'Q2':('#8a6541','P',':'),'Q3':('#d65f00','D','-'),
        'copy_previous':('#111111','*','--')}
METRIC_LABELS={
    'model_center_pp':('Q9预期水平','%'),
    'q9_center_mae_pp':('Q9中心MAE','pp'),
    'center_rmse_pp':('Q9中心RMSE','pp'),
    'q9_center_bias_pp':('Q9中心偏差：模拟−真人','pp'),
    'cross_section_w1_pp':('跨人W1','pp'),
    'cross_person_iqr_pp':('跨人IQR','pp'),
    'individual_density_mean_mae_pp':('个人预期均值MAE','pp'),
    'individual_density_iqr_mean_pp':('个人密度内部IQR','pp'),
    'probability_tv_pct':('十档概率总变差','概率百分点'),
    'q8_center_mae_pp':('Q8中心MAE','pp'),
    'q8_center_bias_pp':('Q8中心偏差','pp'),
    'q8_cross_section_w1_pp':('Q8跨人W1','pp'),
}


def build_data(source):
    s=read_json(Path(source)/'summary.json')
    for relative,digest in s['source_sha256'].items():
        if sha(ROOT/relative)!=digest:raise ValueError('Cached source changed')
    cases_path=next(ROOT/k for k in s['source_sha256'] if k.endswith('/evaluation/cases_private.json'))
    old_path=next(ROOT/k for k in s['source_sha256'] if k.endswith('/a82_reference_private.json'))
    cases=read_json(cases_path);old={(r['month'],r['agent_id']):r for r in read_json(old_path)}
    for row in cases:row['arms']['A82']=old[row['month'],row['agent_id']]['arms']['monthly_reconstruction']
    for view,extra in [('main',[]),('with_previous_truth',['copy_previous'])]:
        arms=['A82',*s['arms'],*extra]
        sup9=shared._common_person_months(cases,arms,[1,2],'q9')
        sup8=shared._common_person_months(cases,arms,[1,2],'q8')
        for arm in arms:
            source_cases=[r for r in cases if r['repeat']==1] if arm=='A82' else cases
            reps=[1] if arm=='A82' else [1,2]
            cells=shared._summarize_arm(source_cases,arm,s['months'],reps,sup9,sup8)['auxiliary_survey_weighted']
            for row in s[view][arm]['monthly']:
                m=row['month'];q8=[r for r in cells['q8']['cells'] if r['month']==m]
                row.update({k:float(np.mean([r[k] for r in q8])) for k in
                    ('q8_center_mae_pp','q8_center_bias_pp','q8_cross_section_w1_pp')})
                row['center_rmse_pp']=float(np.sqrt(np.mean(np.square(list(row['repeat_center_mae_pp'].values())))))
    # CPI x actual four news quotas is already observable without another call.
    parent=old_path.parent
    frozen=read_json(parent/'manifest.json')['prepared_file_sha256']
    for month in s['months']:
        name=f'{month}/contexts_private.json'
        if sha(parent/name)!=frozen[name]:raise ValueError('Frozen news quota context changed')
    contexts={month:read_json(parent/str(month)/'contexts_private.json') for month in s['months']}
    fixed9=shared._common_person_months(cases,['A82',*s['arms']],[1,2],'q9')
    fixed8=shared._common_person_months(cases,['A82',*s['arms']],[1,2],'q8')
    dose=[]
    for count in (4,8,16,32):
        subset=[r for r in cases if contexts[r['month']]['Q0'][r['agent_id']]['news_count']==count]
        for arm in ('Q0','Q3'):
            v=shared._summarize_arm(subset,arm,s['months'],[1,2],fixed9,fixed8)['auxiliary_survey_weighted']['q9']
            monthly=[]
            for month in s['months']:
                cells=[r for r in v['cells'] if r['month']==month]
                monthly.append({'month':month,'n':cells[0]['n_person_months'],
                    'mae_pp':float(np.mean([r['q9_center_mae_pp'] for r in cells]))})
            dose.append({'news_count':count,'arm':arm,'monthly':monthly,
                         'mae_pp':v['aggregate_equal_month_repeat_cells']['q9_center_mae_pp']})
    s['quantity_cpi_monthly']=dose
    s['regimes']={str(k):v for k,v in REGIMES.items()}
    s['trend_metrics']={k:{'label':v[0],'unit':v[1]} for k,v in METRIC_LABELS.items()}
    return s


def line_plot(s,view,keys,path,title):
    names=['A82',*s['arms']]+(['copy_previous'] if view=='with_previous_truth' else [])
    cols=2;rows=(len(keys)+1)//2
    fig,axes=plt.subplots(rows,cols,figsize=(15,4.5*rows),squeeze=False)
    x=np.arange(7)
    for ax,key in zip(axes.flat,keys):
        label,unit=METRIC_LABELS[key]
        for arm in names:
            c,marker,line=STYLES[arm]
            ax.plot(x,[r[key] for r in s[view][arm]['monthly']],color=c,marker=marker,linestyle=line,
                linewidth=2.3 if arm in ('Q0','Q3','copy_previous') else 1.35,
                markersize=5.5,label=(s['labels'][arm] if arm in ('A82','copy_previous') else arm+' '+s['labels'][arm]))
        truth={'model_center_pp':'truth_center_pp','cross_person_iqr_pp':'real_cross_person_iqr_pp',
               'individual_density_iqr_mean_pp':'real_individual_density_iqr_mean_pp'}.get(key)
        if truth:
            ax.plot(x,[r[truth] for r in s[view]['Q0']['monthly']],color='#111111',marker='*',
                    linewidth=2.3,label='真人同支持')
        if 'bias' in key:ax.axhline(0,color='#999999',linestyle=':',linewidth=1)
        ax.set_xticks(x,[f'{str(m)[:4]}-{str(m)[4:]}\n{REGIMES[m]}' for m in s['months']],fontsize=10)
        ax.set_xlabel('目标调查月份（离散选期）');ax.set_ylabel(label+f'（{unit}）')
        ax.set_title(label);ax.grid(axis='y',alpha=.13)
        if 'bias' not in key:ax.set_ylim(bottom=0)
    for ax in list(axes.flat)[len(keys):]:ax.remove()
    legend={}
    for ax in axes.flat:
        handles,labels=ax.get_legend_handles_labels()
        for handle,label in zip(handles,labels):legend.setdefault(label,handle)
    fig.suptitle(title+'；月份按类别等距排列，连线不代表未模拟月份',fontsize=13,y=.995)
    fig.legend(list(legend.values()),list(legend),ncol=4,loc='upper center',bbox_to_anchor=(.5,.95),fontsize=10,frameon=False)
    fig.tight_layout(rect=(0,0,1,.82 if rows==1 else .90));fig.savefig(path,dpi=170);plt.close(fig)


def quantity_plot(s,path):
    fig,axes=plt.subplots(2,2,figsize=(14,8.8));x=np.arange(7)
    for ax,count in zip(axes.flat,(4,8,16,32)):
        for arm in ('Q0','Q3'):
            row=next(r for r in s['quantity_cpi_monthly'] if r['news_count']==count and r['arm']==arm)
            ax.plot(x,[r['mae_pp'] for r in row['monthly']],color=STYLES[arm][0],marker=STYLES[arm][1],
                    linewidth=2.1,label=arm+' '+s['labels'][arm])
        ax.set_title(f'每人{count}篇：组内中心MAE')
        ax.set_xticks(x,[f'{str(m)[:4]}-{str(m)[4:]}' for m in s['months']],rotation=25,ha='right')
        ax.set_xlabel('目标调查月份（离散选期）');ax.set_ylabel('组内MAE（pp）');ax.grid(axis='y',alpha=.13);ax.set_ylim(bottom=0)
    fig.legend(*axes[0,0].get_legend_handles_labels(),ncol=2,loc='upper center',bbox_to_anchor=(.5,.96),frameon=False)
    fig.suptitle('已有Q0/Q3回答即可分析CPI加权×四档新闻量；每组月共同支持约20—24人',fontsize=13,y=.995)
    fig.tight_layout(rect=(0,0,1,.92));fig.savefig(path,dpi=170);plt.close(fig)


def make_canvas(s,path):
    data=json.dumps(s,ensure_ascii=False,separators=(',',':'))
    template='''import {H1,H2,Text,Stack,Grid,Stat,Select,LineChart,Callout,Divider,useState,useHostTheme} from "cursor/canvas";
const D=__DATA__;
const date=(m:number)=>String(m).slice(0,4)+"-"+String(m).slice(4);
export default function NewsTrends(){
 const theme=useHostTheme();const [view,setView]=useState("main");const [arm,setArm]=useState("Q3");const [metric,setMetric]=useState("q9_center_mae_pp");const [dose,setDose]=useState("8");
 const V=view==="main"?D.main:D.with_previous_truth;
 const choices=["A82","R0","Q1","Q2","Q3",...(view==="with_previous_truth"?["copy_previous"]:[])];
 const chosen=choices.includes(arm)?arm:"Q3";
 const title=D.trend_metrics[metric];const q0=V.Q0.monthly;const candidate=V[chosen].monthly;
 const truthKey=metric==="model_center_pp"?"truth_center_pp":metric==="cross_person_iqr_pp"?"real_cross_person_iqr_pp":metric==="individual_density_iqr_mean_pp"?"real_individual_density_iqr_mean_pp":null;
 const lines=[{name:"Q0 四档新闻量",data:q0.map(r=>r[metric]),tone:"info" as const},{name:chosen+" "+D.labels[chosen],data:candidate.map(r=>r[metric]),tone:"warning" as const},...(truthKey?[{name:"真人同支持",data:q0.map(r=>r[truthKey]),tone:"neutral" as const}]:[])];
 const dq0=D.quantity_cpi_monthly.find(r=>r.news_count===Number(dose)&&r.arm==="Q0");const dq3=D.quantity_cpi_monthly.find(r=>r.news_count===Number(dose)&&r.arm==="Q3");
 return <Stack gap={18} style={{padding:24,maxWidth:1160,margin:"0 auto",fontFamily:'"Times New Roman","Kaiti SC","STKaiti",serif',color:theme.text.primary,background:theme.bg.editor}}>
 <Text>SCE新闻机制 · 七期离散月份 · 2026-10-25 · 仅缓存分析</Text><H1>分月折线：机制改善发生在哪些时期？</H1>
 <Text>Q3已经是“四档量＋CPI加权”；Q1是“四档量＋警示”。二者联合及原三档量＋CPI尚未模拟，不能将已知单项收益直接相加。</Text>
 <Select value={view} onChange={setView} options={[{value:"main",label:"五组与A82：Q9共同641个人月"},{value:"with_previous_truth",label:"增加本人上期基线：Q9共同524个人月"}]}/>
 <Grid columns={2} gap={16}><Select value={metric} onChange={setMetric} options={Object.entries(D.trend_metrics).map(([value,v])=>({value,label:v.label+"（"+v.unit+"）"}))}/><Select value={chosen} onChange={setArm} options={choices.map(a=>({value:a,label:a+" "+D.labels[a]}))}/></Grid>
 <H2>{title.label}：Q0与所选配置</H2>
 <LineChart categories={D.months.map(m=>date(m)+" "+D.regimes[String(m)])} series={lines} height={370} valueSuffix={" "+title.unit} beginAtZero={!metric.includes("bias")} showValues referenceLines={metric.includes("bias")?[{value:0,label:"无系统偏差"}]:[]}/>
 <Text>横轴：目标调查月份及背景类型；纵轴：{title.label}（{title.unit}）。每点为该月两遍统计的等权均值；RMSE先对两遍误差平方取均值再开方，A82只有原一遍。Q8独立支持652／540个人月。来源：本批冻结评价。</Text>
 <Callout tone="info" title="月份标签用于阅读，不作为机制分配规则">疫情前、疫情期、通胀上行、高通胀和回落是背景描述。这只有七个选期，2021年三点也不等于完整上行阶段；连线不代表中间未模拟月份。</Callout>
 <H2>现有回答即可看：CPI加权×四档新闻量</H2>
 <Select value={dose} onChange={setDose} options={[4,8,16,32].map(n=>({value:String(n),label:"每人"+n+"篇"}))}/>
 <LineChart categories={D.months.map(date)} series={[{name:"Q0 未加CPI权重",data:dq0.monthly.map(r=>r.mae_pp),tone:"info"},{name:"Q3 CPI权重1.5倍",data:dq3.monthly.map(r=>r.mae_pp),tone:"warning"}]} height={290} valueSuffix=" pp"/>
 <Text>横轴：目标月份；纵轴：该新闻量档内的中心MAE（pp）。同档内Q0与Q3使用相同人；四档之间是不同人，各组月共同支持约20—24人。来源：已有回答重新分组，0新API。</Text>
 <Text>七期平均：4篇档0.806→0.886、8篇档0.642→0.473、16篇档0.693→0.695、32篇档0.944→0.921pp。不能把这些组内中位数误差按25%平均回总体中位数误差。</Text>
 <H2>交叉设计草稿：只补缺失的两组</H2>
 <Text>优先第一组“四档＋CPI×1.5＋警示×2”，补齐CPI与警示的2×2对照，只需924次新请求。第二组“原三档＋CPI×1.5”为可选扩展，另472次，用于比较旧三档与新四档的整体交互；查看四档内部差异不需要它。Fox暂缓。</Text>
 <Grid columns={3} gap={18}><Stat label="新组合的逻辑回答位置" value="2,688"/><Stat label="相同提示成功旧答可复用" value="1,288"/><Stat label="实际拟新增请求" value="1,396"/></Grid>
 <Text>另4个已尝试失败的位置保留缺失，不自动重发。估费约$1.38、保守预留$5.71、建议上限$6；仍为未授权输入草稿，缺官方干跑及新版执行、评价接线，当前新增API为0。</Text>
 <Callout tone="warning" title="联合效果尚未知">不能把两组MAE的变化直接相加。需观察联合组是否同时改善中心与分布，以及是否放大2022年高估。两项2×2仍不识别三因素的三重交互。</Callout>
 <Divider/><Text>旧结果及报告v0.4保留。交互页只含聚合数据，无网络、无个人答卷；Fox旧结果可查，后续研究暂缓。</Text>
 </Stack>;
}
'''
    Path(path).write_text(template.replace('__DATA__',data))


def publish(source,out,crossed):
    source,out,crossed=Path(source).resolve(),Path(out).resolve(),Path(crossed).resolve()
    original.publish(source,out)
    s=build_data(source)
    dump(out/'trend_data.json',s)
    line_plot(s,'main',['model_center_pp','q9_center_mae_pp'],out/'trend_center.png','同支持641个人月：预期水平与中心误差')
    line_plot(s,'main',['q9_center_bias_pp','cross_section_w1_pp','cross_person_iqr_pp','individual_density_mean_mae_pp'],out/'trend_distribution.png','同支持641个人月：偏差、分布与个人误差')
    line_plot(s,'main',['q8_center_mae_pp','q8_cross_section_w1_pp'],out/'trend_q8.png','Q8独立共同支持652个人月')
    line_plot(s,'with_previous_truth',['q9_center_mae_pp','cross_section_w1_pp'],out/'trend_baseline.png','本人真实上期共同支持524个人月：包含持续性基线')
    quantity_plot(s,out/'trend_quantity_cpi.png')
    make_canvas(s,out/'SCE-media-mechanism-trends-20261025.canvas.tsx')
    draft=read_json(crossed/'summary.json');dump(out/'crossed_draft_summary.json',draft)
    intro='''<h2>新增：各组随月份变化的折线图</h2><p>每条曲线是一种已运行配置；同月两遍等权，A82仍仅一遍。背景类型只帮助阅读，不用于事后分组筛选。横轴是七个离散选期，间隔等距；连线不代表中间月份已经模拟。</p><p><b>组别提醒：</b>Q3已经是四档量＋CPI加权，Q1是四档量＋警示；两种权重的联合组尚未运行。Fox旧结果保留，后续暂缓。</p><img src="trend_center.png" alt="全部组分月预期水平和中心MAE"><img src="trend_distribution.png" alt="全部组分月偏差、W1、IQR及个人误差"><details><summary>展开Q8分月折线（独立口径）</summary><img src="trend_q8.png" alt="Q8分月中心误差和分布距离"></details><details><summary>展开与照抄上期基线的分月折线（另用524支持）</summary><img src="trend_baseline.png" alt="基线共同支持下分月中心误差和W1"></details>'''
    plan=f'''<h2>下一轮草稿：用最少新增回答补齐交叉</h2><p><b>优先CPI×警示：</b>复用Q0、Q1、Q3，只增加“四档量＋CPI1.5倍＋警示2倍”，实际需924次新请求。<b>可选旧三档vs新四档：</b>复用R0、Q0、Q3，只增加“原三档量＋CPI1.5倍”，另472次；看现有四档内部的差异不需要新增这一组。两个2×2共用旧组，不再跑Fox。</p><p>联合权重对同时满足两条件文章的加权部分得分乘3；由于还有50%均匀抽样、概率归一化和不放回抽取，并不等于曝光概率乘3。不能把既有两组的MAE改善简单相加。</p><p>两组全做时，同样七期96人、两遍，共2,688个新组合回答位置；完全相同提示的成功旧回答可复用1,288个，4个旧失败位置保留缺失，实际拟新增1,396次。输入草稿估费<b>${draft['estimated_new_cost_usd']:.2f}</b>，保守预留${draft['conservative_new_reservation_usd']:.2f}，建议上限${draft['suggested_budget_cap_usd']}。当前新增API仍为0。</p><p class="note">尚需官方Core干跑、新版执行/评价接线和明确授权，不能把此输入草稿当成已可直接付费运行。七期探索性边界不变；交叉差分同时报告个人预期变化与损失指标，损失交互不等于真人经济机制的因果系数。</p>'''
    page=(out/'index.html').read_text()
    page=page.replace('<h2>1. 这轮究竟比较了什么</h2>',intro+plan+'<h2>原有结果及口径说明</h2>')
    page=page.replace('<img src="overall.png" alt="同支持配置的中心MAE、W1与IQR">','')
    page=page.replace('<img src="monthly.png" alt="各月中心偏差与CPI权重的增量收益">','')
    dose='''<h2>已有数据也能直接看：CPI加权×4／8／16／32篇</h2><p>如果“CPI加权×四档新闻”指不同新闻量档内的效果差异，Q0和Q3已经提供了所需回答，无需新调用。以下在同档同人中比较；四档之间不是同一批居民，不能把组内MAE按25%平均成总体中位数MAE。</p><img src="trend_quantity_cpi.png" alt="四个新闻量档内Q0与Q3分月MAE"><p>七期组内MAE平均：4篇档0.806→0.886、8篇档0.642→0.473、16篇档0.693→0.695、32篇档0.944→0.921pp。当前更明显的收益出现在8篇档，尚无“新闻越多、CPI权重越有效”的单调规律。每组月仅约20—24人，保留为探索性条件结果。</p>'''
    page=page.replace('<h2>下一轮草稿：用最少新增回答补齐交叉</h2>',dose+'<h2>下一轮草稿：用最少新增回答补齐交叉</h2>')
    (out/'index.html').write_text(page)
    dump(out/'manifest.json',{'source_summary_sha256':sha(source/'summary.json'),'new_api_calls':0,'new_q9_fits':0,
        'new_figure_count':5,'source_code_sha256':sha(__file__),
        'files_sha256':{f.name:sha(f) for f in out.iterdir() if f.is_file()}})
    return {'status':'monthly_line_report_written','path':str(out/'index.html'),'new_api_calls':0,'new_q9_fits':0}
