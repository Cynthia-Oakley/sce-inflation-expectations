"""Date-metadata-only readiness audit for person-specific A-line information."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..experiments.frozen_batch import ROOT, dump, sha

FRAME = ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
PARENT = ROOT/'outputs/sce_media_mechanism_v3_20261025_v1'
SALT_SOURCE = ROOT/'outputs/sce_fullperiod_materialized_20261022_v2/201905/population_state_private.json'
METHOD_URL = 'https://www.newyorkfed.org/medialibrary/media/research/epr/2017/epr_2017_survey-consumer-expectations_armantier.pdf'
QUESTIONNAIRE_URL = 'https://www.newyorkfed.org/medialibrary/Interactives/sce/sce/downloads/data/FRBNY-SCE-Survey-Core-Module-Public-Questionnaire.pdf?sc_lang=en'


def date_summary(frame, month, cutoff):
    days = frame.survey_date.dt.normalize()
    valid = days.notna()
    same_month = days.dt.strftime('%Y%m').eq(str(month))
    eligible = valid & same_month
    result = {'n':len(frame), 'missing_dates':int((~valid).sum()),
        'outside_target_month_dates':int((valid & ~same_month).sum()),
        'outside_target_month_date_counts':{str(k):int(v) for k,v in days.loc[valid & ~same_month].dt.strftime('%Y-%m-%d').value_counts().items()},
        'before_shared_cutoff':int((eligible & days.lt(cutoff)).sum()),
        'on_shared_cutoff':int((eligible & days.eq(cutoff)).sum()),
        'after_shared_cutoff':int((eligible & days.gt(cutoff)).sum()),
        'day1_10':int((eligible & days.dt.day.le(10)).sum()),
        'day11_20':int((eligible & days.dt.day.between(11,20)).sum()),
        'day21_end':int((eligible & days.dt.day.ge(21)).sum()),
        'min_date':str(days.loc[eligible].min().date()) if eligible.any() else None,
        'max_date':str(days.loc[eligible].max().date()) if eligible.any() else None,
        'day_counts':{str(int(k)):int(v) for k,v in days.loc[eligible].dt.day.value_counts().sort_index().items()}}
    assert sum(result[k] for k in ('before_shared_cutoff','on_shared_cutoff','after_shared_cutoff','missing_dates','outside_target_month_dates')) == len(frame)
    return result


def build(out):
    out = Path(out).resolve()
    if out.exists():raise ValueError('Fresh output required')
    # Do not project any current Q8/Q9 field.
    df = pd.read_parquet(FRAME, columns=['date','userid','survey_date'])
    df['survey_date'] = pd.to_datetime(df.survey_date, errors='coerce')
    if df.duplicated(['date','userid']).any():raise ValueError('Ambiguous source identity')
    salt = json.loads(SALT_SOURCE.read_text())['anon_salt']
    ids = {u:'sce_'+hashlib.sha256(f'{int(u)}|{salt}'.encode()).hexdigest()[:16] for u in df.userid.unique()}
    df['agent_id'] = df.userid.map(ids)
    links_path = PARENT/'evaluation_links_private.json'
    # The evaluation userid field is a local alias, not the source raw userid.
    # Join through the checked anonymous identity, never an ordinal alias.
    links = pd.DataFrame(json.loads(links_path.read_text()))[['month','agent_id']].rename(columns={'month':'date'})
    joined = links.merge(df[['date','agent_id','survey_date']], on=['date','agent_id'], how='left', validate='one_to_one', indicator=True)
    if len(joined)!=672 or not joined['_merge'].eq('both').all():raise ValueError('Exact selected identity join failed')
    coverage_path = PARENT/'coverage.json';rows=[]
    for r in json.loads(coverage_path.read_text()):
        month = r['month'];cutoff = pd.Timestamp(r['as_of']).tz_localize(None).normalize()
        selected = date_summary(joined.loc[joined.date.eq(month)], month, cutoff)
        whole = date_summary(df.loc[df.date.eq(month)], month, cutoff)
        rows.append({'month':month,'shared_cutoff_ny':r['as_of'], 'selected':selected,'full_source_wave':whole})
    june = next(r for r in rows if r['month']==202106)['full_source_wave']
    # Independent historical count recorded in the 2026-10-08 diagnosis.
    assert (june['n'],june['before_shared_cutoff'],june['on_shared_cutoff'],june['after_shared_cutoff']) == (1297,339,8,950)
    s={'status':'date_metadata_only_readiness_checked', 'new_api_calls':0,'new_q9_fits':0,
       'current_target_answer_columns_read':False,'source_columns_read':['date','userid','survey_date'],
       'selected_person_months':len(joined),'rows':rows,
       'official_evidence':{'method_url':METHOD_URL,'method_section':'3.2 Data Collection',
          'questionnaire_url':QUESTIONNAIRE_URL,'field':'Survey_date = date respondent completed survey; no hour',
          'verified_date':'2026-10-25','schedule_description':'Three invitation batches generally on days 2/11/20, collected until month end; nonuniform completion times.'},
       'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in (FRAME,links_path,coverage_path,SALT_SOURCE)},
       'limits':['Date resolution is one day; no exact response hour or certified timezone.',
          'One selected 202206 response is recorded as completed on 2022-07-01; keep it separately, not silently remapped.',
          'Real target-period completion dates are A-line reconstruction metadata, not B-line forecast inputs.',
          'Timing mismatch is established; its effect on MAE is not identified.',
          'No live simulation, input cutoff, original run or outcome has been changed.']}
    out.mkdir(parents=True);dump(out/'summary.json',s)
    return s


def publish(s,out):
    from matplotlib import pyplot as plt, font_manager
    out=Path(out).resolve()
    if out.exists():raise ValueError('Fresh report directory required')
    out.mkdir(parents=True)
    font=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':11,
                        'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    r=next(r for r in s['rows'] if r['month']==202106);x=np.arange(1,31)
    fig,ax=plt.subplots(figsize=(12.4,4.7))
    for name,key,color,marker in [('完整源波次','full_source_wave','#006da8','o'),('七期实验所选人群','selected','#d65f00','D')]:
        v=r[key];y=[100*v['day_counts'].get(str(day),0)/v['n'] for day in x]
        ax.plot(x,y,color=color,marker=marker,markersize=3.2,linewidth=1.8,label=f'{name}（N={v["n"]}）')
    ax.axvline(10,color='#555555',linestyle='--',label='原共同截止：6月10日')
    ax.set_xlabel('2021年6月完成问卷的日号');ax.set_ylabel('当日作答人数／该组全月人数（%）')
    ax.set_xticks([1,5,10,15,20,25,30]);ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.15)
    ax.set_title('实际作答日期有明显波峰，不能假定全月均匀')
    fig.legend(*ax.get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.5,.98),ncol=3,fontsize=10,frameon=False)
    fig.tight_layout(rect=(0,0,1,.87));fig.savefig(out/'response_dates_june2021.png',dpi=170);plt.close(fig)
    dump(out/'summary.json',s)
    template='''import {H1,H2,Text,Stack,Grid,Stat,Select,LineChart,Table,Callout,Divider,useState,useHostTheme} from "cursor/canvas";
const D=__DATA__;
const date=(m:number)=>String(m).slice(0,4)+"-"+String(m).slice(4);
export default function ResponseTiming(){
 const t=useHostTheme();const [month,setMonth]=useState("202106");const r=D.rows.find(x=>String(x.month)===month);const n=new Date(Number(month.slice(0,4)),Number(month.slice(4)),0).getDate();const days=Array.from({length:n},(_,i)=>i+1);
 return <Stack gap={18} style={{padding:24,maxWidth:1120,margin:"0 auto",fontFamily:'"Times New Roman","Kaiti SC","STKaiti",serif',color:t.text.primary,background:t.bg.editor}}>
 <Text>SCE信息时间设计 · 2026-10-25 · 仅日期元数据 · 0新API</Text><H1>把共同月中截面改为个人作答日期</H1>
 <Text>官方方法说明为全月分批收集，而非固定一天。当前可证明信息时间不匹配，尚不能证明它解释了多少MAE。</Text>
 <Grid columns={3} gap={16}><Stat label="2021-06在6月10日之后作答" value="950 / 1,297"/><Stat label="占完整源波次" value="73.2%"/><Stat label="七期所选日期核查" value="672 个人月"/></Grid>
 <Select value={month} onChange={setMonth} options={D.rows.map(x=>({value:String(x.month),label:date(x.month)}))}/>
 <H2>月内完成日期的实际分布</H2>
 <LineChart categories={days.map(d=>String(d))} series={[{name:"完整源波次占比",data:days.map(d=>100*(r.full_source_wave.day_counts[String(d)]||0)/r.full_source_wave.n),tone:"info"},{name:"七期所选人群占比",data:days.map(d=>100*(r.selected.day_counts[String(d)]||0)/r.selected.n),tone:"warning"}]} height={320} valueSuffix="%"/>
 <Text>横轴：该月日号；纵轴：当天完成人数占全月人数比例（%），未加调查权重。来源：本地SCE survey_date，未读本期Q8/Q9。原共同截止为{r.shared_cutoff_ny.slice(0,10)}。日期无小时和明确时区；目标月外日期单列，不进入日号曲线。</Text>
 <Table headers={["月份","所选N","截止前","同日","截止后","缺失日期","标称月外"]} rows={D.rows.map(x=>[date(x.month),String(x.selected.n),String(x.selected.before_shared_cutoff),String(x.selected.on_shared_cutoff),String(x.selected.after_shared_cutoff),String(x.selected.missing_dates),String(x.selected.outside_target_month_dates)])}/>
 <Text>672份所选记录均有日期，其中671份在标称月份内；2022-06有1份完成日期记为2022-07-01，需单独核实，不擅自修改原月标签或视为没有日期。</Text>
 <H2>建议修改：按个人日期生成可见环境</H2>
 <Text>A线有真实完成日期，直接用它；初版保守取前一日纽约时间结束，只纳入之前已发表/发布的新闻、CPI/食品价格和政策。新公告的选择、重要新闻路由与先后标签一起重新生成；不能只改日期字符串。</Text>
 <Text>每个代理仍只回答一次或既定两遍，不需要每天调用模型。资料按“月份×截止日”缓存，同一天多人共用；原七期人口、权重、数量档、CPI权重和模型保持。生成/评价引擎复用，主要改输入组装与验收。</Text>
 <H2>随机日期何时使用？</H2>
 <Text>A线真实日期齐全时无需随机。日期未知的代理，从严格更早可得样本估计日号/批次经验分布；不默认连续均匀分布，更不随机未来新闻。预测在固定D封存时，任何代理均不得获取D之后的真实信息。</Text>
 <Callout tone="info" title="建议单独检验时间因素">先比较Q3共同月中截止与Q3个人日期；警示权重保持关闭。若同时检验警示，则补齐时间×警示的2×2，各时间方案内警示只改一项。旧结果不覆盖；当前没有新输入执行包或授权。</Callout>
 <Divider/><Text>官方依据：纽约联储2017方法说明3.2节及公开问卷Survey_date定义。旧方案是登记的月中参照，新方案是按实际日期重建；前者存在近似误差，不等于已经发现执行bug。</Text>
 </Stack>;
}
'''
    name='SCE-response-timing-20261025.canvas.tsx'
    (out/name).write_text(template.replace('__DATA__',json.dumps(s,ensure_ascii=False,separators=(',',':'))))
    dump(out/'manifest.json',{'source_sha256':s['source_sha256'],'source_code_sha256':sha(__file__),
        'new_api_calls':0,'file_sha256':{p.name:sha(p) for p in out.iterdir() if p.is_file()}})
    return {'status':'date_readiness_and_figure_written','path':str(out),'new_api_calls':0}
