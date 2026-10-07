#!/usr/bin/env python3
"""Add rolling diagnostics and a portable, offline HTML view of completed runs."""
import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'studies/sce_inflation_expectations'))
from evaluation.metrics import headline_errors


def month_index(value):
    year, month = map(int, value.split('-'))
    return year * 12 + month - 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-run', type=Path, required=True)
    p.add_argument('--agent-review', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--html', type=Path, required=True)
    a = p.parse_args()
    if a.output_dir.exists() or a.html.exists():
        raise FileExistsError('Use new paths; do not overwrite prior artifacts')
    source = a.baseline_run / 'monthly_forecasts.csv'
    grouped = defaultdict(list)
    for row in csv.DictReader(source.open()):
        grouped[row['policy'], row['method']].append(dict(month=row['target_month'],
            prediction=float(row['prediction_pp']), truth=float(row['truth_pp'])))
    rolling = []
    for (policy, method), rows in sorted(grouped.items()):
        rows.sort(key=lambda x: x['month'])
        for window in (6, 12):
            for end in range(window, len(rows) + 1):
                part = rows[end-window:end]
                if any(month_index(y['month'])-month_index(x['month']) != 1 for x,y in zip(part,part[1:])):
                    continue
                rolling.append(dict(policy=policy, method=method, window_months=window,
                    first_month=part[0]['month'], last_month=part[-1]['month'],
                    **headline_errors([x['prediction'] for x in part], [x['truth'] for x in part])))
    agent = []
    agent_files = []
    for month in ('202105','202106'):
        file = a.agent_review / f'{month}_summary.json'; agent_files.append(file)
        x = json.loads(file.read_text())
        agent.append(dict(month=f'{month[:4]}-{month[4:]}',
            prediction=x['comparison']['q9']['normal_expanded_vs_full_truth']['simulated']['weighted_median_pp']))
    comparison = []
    policy = 'current_month_cpi_release_day_end'
    months = [x['month'] for x in agent]
    truth = [next(r['truth'] for r in grouped[policy,'persistence'] if r['month']==m) for m in months]
    chart_truth = [json.loads(f.read_text())['official_full_wave_reference']['q9_mean_weighted_median'] for f in agent_files]
    for method in ['agent_core_normal'] + sorted({m for pol,m in grouped if pol==policy}):
        values = [x['prediction'] for x in agent] if method=='agent_core_normal' else [next(r['prediction'] for r in grouped[policy,method] if r['month']==m) for m in months]
        comparison.append(dict(method=method, months=months, predictions=values, truth=truth,
            primary=headline_errors(values,truth), high_precision_official_sensitivity=headline_errors(values,chart_truth)))
    a.output_dir.mkdir(parents=True)
    result = dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
        headline_truth='official_first_release_one_decimal', rolling=rolling, agent_comparison=comparison,
        comparison_note='Same months and cutoff, not equal information or sampling: Agent has current A population but no historical SCE; baselines may use public historical SCE. Only headline comparison; no B forecasting claim.',
        input_sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [source]+agent_files},
        real_llm_calls=0, paid_mcp_calls=0)
    (a.output_dir/'diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    labels={'persistence':'最后已公布一期不变','mean12':'最近12期均值','ar1_expanding':'AR(1)：历史延续规律',
        'arx_sce_cpi':'ARX：历史SCE＋CPI','cpi_as_expectation':'直接把最新CPI当预期（价格对照）',
        'sticky_agent_0.1':'规则Agent：10%更新','sticky_agent_0.25':'规则Agent：25%更新',
        'sticky_agent_0.5':'规则Agent：50%更新','agent_core_normal':'300 Core＋Normal 主实验'}
    summary=json.loads((a.baseline_run/'summary.json').read_text())
    payload=dict(labels=labels, forecasts=summary['forecasts'], comparison=comparison,
        series=[dict(policy=pol,method=met,records=rs) for (pol,met),rs in grouped.items()],rolling=rolling)
    template='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>水上挽月 · SCE 评价与五年基线</title><style>
body{font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#252525;background:#fafafa;margin:0}main{max-width:1080px;margin:auto;padding:28px}h1{font-size:26px}h2{font-size:21px;margin-top:28px}select{font:inherit;padding:5px;margin:4px}table{width:100%;border-collapse:collapse;background:white;font-size:14px}th,td{padding:9px;text-align:left;border-bottom:1px solid #ddd}th{background:#f1f1f1}.note{font-size:14px;color:#555}.callout{padding:12px 18px;background:#edf3f8}svg{width:100%;height:auto;background:white}a{color:#245d8c}@media print{select{display:none}body{background:white}}</style>
<main><h1>水上挽月 · SCE 评价与五年基线</h1><p>基线窗口：2020年1月—2024年12月，共60个月。来自官方归档；此页完全离线，无API调用。</p>
<div class="callout"><b>A路线仍要检验全国指标：</b>没有输入当期SCE时，全国误差和人群结构都要看；已输入当期中位数时，先验约束满足仍须检验，独立证据则来自未用于校准的群体结构与月份。</div>
<h2>全国指标预测：按信息截止点比较</h2><select id="policy"><option value="current_month_cpi_release_day_end">当月CPI发布日结束（月中参照）</option><option value="previous_month_end">上月末预测下一期</option></select><div id="metrics"></div>
<p class="note">ARX和价格对照可能覆盖较短，表中列出共同月份的持续性基线，不能直接与60月均值排名。</p>
<h2>逐月与滚动区间</h2><select id="view"><option value="level">全国预期（%）</option><option value="monthly">逐月绝对误差（百分点）</option><option value="6">连续6个月滚动MAE（百分点）</option><option value="12">连续12个月滚动MAE（百分点）</option></select><div id="plot"></div>
<p id="caption" class="note"></p>
<h2>2021年5、6月：现有Agent与同月份基线</h2><div id="comparison"></div><p class="note">这里的真值统一为官方首发值4.0%/4.8%，不把旧实验的近似重算真值拼进本表。Agent输出仍由冻结近似计分器处理。月份/截止点一致，但信息与人口条件不同：Agent使用当期人口、未输入历史SCE；基线可使用公开历史SCE。因此是开发期全国数值参照，不能称严格事前预测或纯算法胜负。后来的20/48/50人小试另列，不充当全国主实验。</p>
<h2>怎样读这些指标？</h2><ul><li>MAE：平均差了多少，单位是百分点。作为全国预测主指标。</li><li>RMSE：更重罚大误差；与MAE一起识别是否在重大变化时失误。</li><li>偏差：长期偏高或偏低，不能单看抵消后的平均偏差。</li><li>全国中位数接近不代表人群结构可信；分布宽度、尾部和群体关系仍需独立验证。</li></ul>
<p class="note">本地2026-09-28下载的latest微观快照覆盖2025-01至2025-10；60月是本次选择的完整年度窗口，不是官方数据上限。后续扩展需单独固定版本与验证方案。</p>
<p><a href="SCE_BASELINE_RESULTS_20261007.md">完整结果报告</a> · <a href="SCE_EVALUATION_CONTRACT_V1.md">统一评价契约</a></p><p class="note">数据：纽约联储SCE；时点：BLS CPI发布日历。滚动窗口是新的诊断展示，未重新选择或拟合基线参数。</p></main>
<script id="data" type="application/json">PAYLOAD</script><script>
const D=JSON.parse(document.getElementById('data').textContent),fmt=x=>Number(x).toFixed(3);
function table(headers,rows){return '<table><thead><tr>'+headers.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
const methods=['persistence','ar1_expanding','sticky_agent_0.25'];
function render(){const policy=document.getElementById('policy').value,view=document.getElementById('view').value;
 document.getElementById('metrics').innerHTML=table(['方法','月份数','MAE（pp）','RMSE（pp）','同期持续性MAE（pp）'],D.forecasts.filter(x=>x.policy===policy).map(x=>[D.labels[x.method],x.primary.n_months,fmt(x.primary.mae_pp),fmt(x.primary.rmse_pp),fmt(x.matched_persistence.mae_pp)]));
 let series=methods.map(m=>({name:D.labels[m],points:view==='level'||view==='monthly'?D.series.find(x=>x.policy===policy&&x.method===m).records.map(x=>({month:x.month,value:view==='level'?x.prediction:Math.abs(x.prediction-x.truth)})):D.rolling.filter(x=>x.policy===policy&&x.method===m&&x.window_months===Number(view)).map(x=>({month:x.last_month,value:x.mae_pp}))}));
 if(view==='level'){const r=D.series.find(x=>x.policy===policy&&x.method==='persistence').records;series.unshift({name:'官方首发SCE',points:r.map(x=>({month:x.month,value:x.truth}))});}
 const months=series[0].points.map(x=>x.month),W=1000,H=350,L=62,R=24,T=28,B=70,colors=['#222','#286b9b','#777','#aaa'];let max=Math.max(...series.flatMap(x=>x.points.map(z=>z.value)))*1.08;
 const X=i=>L+i*(W-L-R)/(months.length-1),Y=v=>H-B-v*(H-T-B)/max;let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="SCE月度和滚动误差图">';
 for(let i=0;i<=4;i++){let v=max*i/4;svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y(v)+'" y2="'+Y(v)+'" stroke="#ddd"/><text x="8" y="'+(Y(v)+5)+'" font-size="13">'+v.toFixed(2)+'</text>';}
 months.forEach((m,i)=>{if(i%6===0||i===months.length-1)svg+='<text x="'+X(i)+'" y="'+(H-B+24)+'" font-size="12" text-anchor="middle">'+m+'</text>';});
 series.forEach((s,i)=>{svg+='<polyline fill="none" stroke="'+colors[i]+'" stroke-width="2" points="'+s.points.map((p,j)=>X(j)+','+Y(p.value)).join(' ')+'"/>';});
 svg+='<text x="'+L+'" y="18" font-size="13">'+(view==='level'?'全国预期（%）':'误差（百分点）')+'</text><text x="500" y="'+(H-10)+'" font-size="13" text-anchor="middle">目标调查月'+(view==='6'||view==='12'?'（窗口结束月）':'')+'</text></svg>';
 document.getElementById('plot').innerHTML=svg+'<div>'+series.map((s,i)=>'<span style="display:inline-block;margin-right:18px;color:'+colors[i]+'">— '+s.name+'</span>').join('')+'</div>';
 document.getElementById('caption').textContent='纽约联储SCE官方首发值；'+months[0]+'至'+months[months.length-1]+(view==='6'||view==='12'?'。每一点汇总截至该月的连续'+view+'个月。重叠窗口不能当作独立样本。':'。');
}
document.getElementById('comparison').innerHTML=table(['方法','5月预测（%）','6月预测（%）','两月MAE（pp）'],D.comparison.map(x=>[D.labels[x.method],...x.predictions.map(fmt),fmt(x.primary.mae_pp)]));
document.getElementById('policy').onchange=render;document.getElementById('view').onchange=render;render();
</script></html>'''
    a.html.parent.mkdir(parents=True,exist_ok=True)
    a.html.write_text(template.replace('PAYLOAD',json.dumps(payload,ensure_ascii=False).replace('</','<\\/')))
    print(json.dumps(comparison,ensure_ascii=False,indent=2))
    print(a.html)


if __name__ == '__main__':
    main()
