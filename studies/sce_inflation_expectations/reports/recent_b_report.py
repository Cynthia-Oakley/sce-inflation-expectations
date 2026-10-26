"""Publish aggregate recent-B results as a local HTML report and inline canvas."""
from pathlib import Path
import argparse
import json
import shutil

from ..experiments.frozen_batch import ROOT, read_json, dump, sha
from ..evaluation.recent_b_readout import make_html, make_figures, VALUES


def canvas_data(s):
    ev=s['evaluation']
    return {'monthly':ev['monthly'], 'model':ev['model'], 'baseline':ev['persistence'],
            'wins':ev['model_win_months'], 'alpha':ev['combination_simulation_share'],
            'interval':s['paired_mae_interval']['interval_95'],
            'distributions':[{'month':r['month'],'sim_iqr':r['sim']['iqr_pp'],
                              'prior_iqr':r['prior']['iqr_pp'],'q25':r['sim']['q25_pp'],
                              'q75':r['sim']['q75_pp'],
                              'uncertainty':r['median_person_uncertainty_iqr_pp']} for r in s['monthly_distributions']],
            'groups':s['group_summary'],
            'group_months':[{'month':r['month'],'dimension':r['dimension'],'label':r['label'],
                             'supported':r['supported'],'n':r['n'],'ess':r['ess'],
                             'sim_median_pp':r['sim']['median_pp'],'prior_median_pp':r['prior']['median_pp'],
                             'sim_iqr_pp':r['sim']['iqr_pp'],'prior_iqr_pp':r['prior']['iqr_pp']}
                            for r in s['group_months']],
            'technical':s['technical'], 'mean_iqr':s['mean_monthly_sim_iqr_pp'],
            'prior_iqr':s['mean_monthly_prior_iqr_pp']}


def make_canvas(s,path):
    data=json.dumps(canvas_data(s),ensure_ascii=False,separators=(',',':'))
    source='''import {H1,H2,Text,Stack,Grid,Stat,Select,LineChart,BarChart,Table,Callout,Divider,useState,useHostTheme} from "cursor/canvas";
const D=__DATA__;
const F=(x:number,k=3)=>x.toFixed(k);
const month=(x:number|string)=>String(x).slice(0,4)+"-"+String(x).slice(4);
const dims={age_group:"年龄",education_group:"学历",household_income_band:"家庭收入",numeracy:"数理能力",employment_status:"就业",region:"地区",housing_tenure:"住房"};
export default function RecentB(){
 const theme=useHostTheme();
 const [tab,setTab]=useState("national"); const [dim,setDim]=useState("education_group");const [period,setPeriod]=useState("all");
 const groups=period==="all"?D.groups.filter(r=>r.dimension===dim).map(r=>({...r,n:r.n_person_months,ess:0})):
 D.group_months.filter(r=>r.dimension===dim&&r.month===period&&r.supported);
 const subtitle=period==="all"?"11期合格组月的等权平均":"本月各组加权统计";
 return <Stack gap={18} style={{padding:24,maxWidth:1120,margin:"0 auto",fontFamily:'"Times New Roman","Kaiti SC","STKaiti","KaiTi",serif',background:theme.bg.editor,color:theme.text.primary}}>
 <Text>SCE · 2025-11—2026-09 · 每期512代理家庭 · DeepSeek V3.2 / SiliconFlow FP8</Text>
 <H1>近期11个月：运行与模拟结果</H1>
 <Text>5,632份回答全部补齐。原评价索引缺少2026-09，已用官方首发资料离线恢复；未新增模拟调用。</Text>
 <Select value={tab} onChange={setTab} options={[{value:"national",label:"总体误差"},{value:"dispersion",label:"分布与人群"},{value:"run",label:"运行、费用与边界"}]}/>
 {tab==="national"&&<Stack gap={16}>
 <Grid columns={3} gap={20}><Stat label="模型MAE（pp）" value={F(D.model.mae_pp)}/><Stat label="持续性基线MAE（pp）" value={F(D.baseline.mae_pp)}/><Stat label="模型胜出月份" value={D.wins+" / 11"}/></Grid>
 <H2>全国指标与逐月误差</H2>
 <LineChart categories={D.monthly.map(r=>month(r.month))} series={[{name:"官方SCE首发值",data:D.monthly.map(r=>r.truth_pp),tone:"neutral"},{name:"模拟值",data:D.monthly.map(r=>r.sim_pp),tone:"info"},{name:"截止前最后公开值",data:D.monthly.map(r=>r.anchor_pp),tone:"warning"}]} height={310} beginAtZero={false} valueSuffix="%"/>
 <Text>横轴：目标调查月份；纵轴：一年期通胀预期（%）。来源：本次冻结回答与纽约联储首发新闻稿。基线为截止前最后公开值。</Text>
 <BarChart categories={D.monthly.map(r=>month(r.month))} series={[{name:"模型绝对误差",data:D.monthly.map(r=>Math.abs(r.sim_pp-r.truth_pp)),tone:"info"},{name:"基线绝对误差",data:D.monthly.map(r=>Math.abs(r.anchor_pp-r.truth_pp)),tone:"warning"}]} height={250} valueSuffix=" pp"/>
 <Text>横轴：目标调查月份；纵轴：绝对误差（pp，越小越好）。每个月等权，不按人月数量累计MAE。</Text>
 <Table headers={["指标","模拟","持续性基线"]} rows={[["MAE（pp）",F(D.model.mae_pp),F(D.baseline.mae_pp)],["RMSE（pp）",F(D.model.rmse_pp),F(D.baseline.rmse_pp)],["平均偏差（pp）",F(D.model.bias_pp),F(D.baseline.bias_pp)],["最大绝对误差（pp）",F(D.model.max_absolute_error_pp),F(D.baseline.max_absolute_error_pp)]]}/>
 <Callout tone="info" title="原始模拟与冻结组合分别报告">2019—2022年拟合的模拟权重为λ={D.alpha}，所以本期冻结组合等于基线，MAE为{F(D.baseline.mae_pp)}pp。这11个月不重新拟权。</Callout>
 <Text>探索性的3月区块配对MAE差95%区间：[{F(D.interval[0])}, {F(D.interval[1])}]pp。11个月较短，区间不包含全部输入或模型选择不确定性。</Text>
 </Stack>}
 {tab==="dispersion"&&<Stack gap={16}>
 <H2>不同人的预期有多分散？</H2>
 <Text>每月跨人IQR平均：模拟{F(D.mean_iqr,2)}pp，合成起点{F(D.prior_iqr,2)}pp。IQR比较个人Q9密度均值，和一个人自身的不确定性不是同一个量。</Text>
 <LineChart categories={D.distributions.map(r=>month(r.month))} series={[{name:"模拟跨人IQR",data:D.distributions.map(r=>r.sim_iqr),tone:"info"},{name:"合成起点跨人IQR",data:D.distributions.map(r=>r.prior_iqr),tone:"warning"}]} height={270} valueSuffix=" pp"/>
 <Text>横轴：目标调查月份；纵轴：加权Q75−Q25（pp）。来源：冻结模拟回答与其合成初始化；起点不是真人同期分布。</Text>
 <Divider/><H2>人口分组：{subtitle}</H2>
 <Select value={dim} onChange={setDim} options={Object.entries(dims).map(([value,label])=>({value,label}))}/>
 <Select value={period} onChange={setPeriod} options={[{value:"all",label:"11期合格组月平均"},...D.distributions.map(r=>({value:r.month,label:month(r.month)}))]}/>
 {groups.length>0&&<><BarChart categories={groups.map(r=>r.label)} series={[{name:"模拟组中位数",data:groups.map(r=>r.sim_median_pp),tone:"info"},{name:"合成起点组中位数",data:groups.map(r=>r.prior_median_pp),tone:"warning"}]} horizontal height={Math.max(240,groups.length*65)} valueSuffix="%"/>
 <Text>纵轴：人口类别；横轴：组内加权中位数（%）。全期视图对合格月份等权平均；各组支持月数可能不同。</Text>
 <BarChart categories={groups.map(r=>r.label)} series={[{name:"模拟组内IQR",data:groups.map(r=>r.sim_iqr_pp),tone:"info"},{name:"合成起点组内IQR",data:groups.map(r=>r.prior_iqr_pp),tone:"warning"}]} horizontal height={Math.max(240,groups.length*65)} valueSuffix=" pp"/>
 <Text>纵轴：人口类别；横轴：组内IQR（pp）。只呈现n≥20、ESS≥10的组月。来源：同一批代理人口的描述性统计。</Text></>}
 <Callout tone="warning" title="分散程度不是微观拟合成绩">没有近期真人个人Q9，不能计算个人误差、到真人的W1或真人IQR误差。图中的差异是模型行为；一次生成也不能区分稳定个体差异与抽样噪声。</Callout>
 </Stack>}
 {tab==="run"&&<Stack gap={16}>
 <H2>主批与补跑均完成</H2>
 <Table headers={["项目","结果"]} rows={[["主批尝试","5,632"],["原始技术失败",String(D.technical.main_technical_failures)],["自动补跑",String(D.technical.repair_attempts)],["最终技术完整",String(D.technical.final_technical_complete)],["最终Q8 / Q9缺失","0 / 0"],["实际API报告费用","$"+F(D.technical.generation_receipt.reported_cost_usd,4)],["未知费用保守预留","$"+F(D.technical.generation_receipt.spent_or_reserved_usd-D.technical.generation_receipt.reported_cost_usd,4)],["生成耗时",F(D.technical.generation_elapsed_minutes,1)+"分钟"]]}/>
 <Text>日志中的“原始技术失败20”是主批累计计数，补跑成功不会将它清零。最终缺失为0，已经不需要重跑。未知费用预留不是确认扣费。</Text>
 <H2>评价故障与恢复</H2>
 <Text>旧索引只到2026-08，查询2026-09触发KeyError。补入纽约联储2026-10-07首发值3.9%，保留旧失败收据，只离线评价。本轮没有修改模型回答或冻结输入。</Text>
 <H2>研究边界</H2>
 <Text>每人Q9十档拟合连续密度并取均值，再取人群加权中位数，与全国SCE比较。Q8独立；近期分组真值不可得。</Text>
 <Text>人口可得月按“调查月末加九个日历月”规则推定，源波次2025-01逐步推进至2025-10。先验仅对齐已公开历史全国值；人口进出、Normal代答和自主递推均未启用。</Text>
 <Text>这是回顾性时点回测。历史文件字节版本、新闻文本版本和模型知识截止未完全认证，不能称严格事前封存预测；不把本期结果当因果机制证据。</Text>
 </Stack>}
 <Divider/><Text>来源：sce_recent_b_overnight_20261025_v3冻结回答；readout_20261025_v2离线评价。交互页只含聚合结果，无网络、无个人记录。</Text>
 </Stack>;
}
'''.replace('__DATA__',data)
    Path(path).write_text(source)


def publish(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'docs/reports'):
        raise ValueError('Fresh local report directory required')
    s=read_json(source/'summary.json');out.mkdir(parents=True)
    for r in s['group_summary']+s['group_months']:
        r['label']=VALUES.get(r['value'],r['value'])
    dump(out/'summary.json',s)
    for name in ('monthly_national.csv',):
        shutil.copy2(source/name,out/name)
    make_figures(s,read_json(source/'individual_descriptive_private.json'),out)
    make_html(s,out)
    make_canvas(s,out/'SCE-recent-B-results-20261025.canvas.tsx')
    dump(out/'manifest.json',{'source_summary':str((source/'summary.json').relative_to(ROOT)),
                              'source_sha256':sha(source/'summary.json'), 'new_api_calls':0,
                              'files_sha256':{f.name:sha(f) for f in out.iterdir() if f.is_file()}})
    return {'status':'local_report_published','path':str(out/'index.html'),'new_api_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args();print(json.dumps(publish(a.source,a.out),ensure_ascii=False,indent=2))
