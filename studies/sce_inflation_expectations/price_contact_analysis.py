"""Post-run evaluation only. Never imported by a simulation provider."""
import json
from pathlib import Path
import duckdb
import numpy as np
from .price_contact import ARMS
from .household_state_analysis import density, distribution
from .scoring.sce_q9_frozen import provenance
from .spending_audit import sha

CONTRASTS = [('national','baseline'),('matched','national'),('matched','shuffled')]
LABELS = {'real':'同一小样真实回答','baseline':'原有信息','national':'近期全国价格','matched':'地区匹配','shuffled':'地区随机分配'}


def metrics(rows):
    valid=[r for r in rows if all(r[k] is not None and np.isfinite(r[k]) for k in ('real',)+ARMS)]
    result={'selected_n':len(rows),'common_valid_n':len(valid),'excluded_n':len(rows)-len(valid),'arms':{},'contrasts':{}}
    if not valid:return result
    truth=np.array([r['real'] for r in valid]);real=distribution(truth);result['real']=real
    for arm in ARMS:
        pred=np.array([r[arm] for r in valid]);d=distribution(pred)
        result['arms'][arm]={'distribution':d,'median_absolute_error_pp':abs(d['median']-real['median']),
                            'distribution_W1_pp':float(np.mean(abs(np.sort(pred)-np.sort(truth)))),
                            'IQR_absolute_gap_pp':abs(d['iqr']-real['iqr']),
                            'individual_MAE_auxiliary_pp':float(np.mean(abs(pred-truth))),
                            'padd_groups':{g:{'n':sum(r['padd']==g for r in valid),
                                 'real':distribution([r['real'] for r in valid if r['padd']==g]),
                                 'simulated':distribution([r[arm] for r in valid if r['padd']==g]),
                                 'interpretation':'Descriptive only; tiny groups cannot validate geographic mechanism'} for g in sorted({r['padd'] for r in valid})}}
    rng=np.random.default_rng(42);index=rng.integers(0,len(valid),size=(2000,len(valid)))
    def score(pred,actual):
        return np.array([abs(np.median(pred)-np.median(actual)),np.mean(abs(np.sort(pred)-np.sort(actual)))])
    for treatment,control in CONTRASTS:
        a=np.array([r[treatment] for r in valid]);b=np.array([r[control] for r in valid]);delta=score(a,truth)-score(b,truth)
        bs=np.array([score(a[i],truth[i])-score(b[i],truth[i]) for i in index]);interval=np.quantile(bs,[.025,.975],axis=0)
        result['contrasts'][f'{treatment}-{control}']={
            'median_error_change_pp':float(delta[0]),'W1_change_pp':float(delta[1]),
            'median_error_paired_resampling_95_interval_pp':interval[:,0].tolist(),
            'W1_paired_resampling_95_interval_pp':interval[:,1].tolist(),
            'scope':'Negative means improvement. Conditional person resampling, not repeated-model uncertainty or national inference.'}
    return result


def analyze(root,folder):
    root,folder=Path(root),Path(folder);out=folder/'analysis';out.mkdir(exist_ok=False)
    manifest=folder/'trial_manifest.json';plan=json.loads(manifest.read_text())
    if plan['status']!='completed' or any(j['status']!='completed' for j in plan['jobs']):raise ValueError('Completed genuine runs required')
    truthpath=root/'data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json'
    truth={(int(r['date']),int(r['userid'])):r for r in json.loads(truthpath.read_text())['per_person']}
    link=json.loads((folder/'private_evaluation_link.json').read_text())
    result={'trial_id':plan['trial_id'],'model_requested':plan['model'],'estimated_cost_usd':plan['estimated_cost_usd'],
            'new_calls':plan['max_calls'],'scorer':provenance(),'months':{},'sources':{str(manifest):sha(manifest),str(truthpath):sha(truthpath)},
            'estimand':'Equal-weight existing 20-person diagnostic samples, with paired common-case truth re-scored from raw Q9 bins. Not national SCE headline.'}
    if not result['scorer']['live_matches_pinned']:raise ValueError('Scorer drift')
    detailed=[]
    for month in plan['months']:
        links=[r for r in link if r['date']==int(month)];by_arm={};reasons={}
        for arm in ARMS:
            jobs=[j for j in plan['jobs'] if j['month']==month and j['arm']==arm]
            if len(jobs)!=1:raise ValueError('Missing/duplicate cell')
            d=Path(jobs[0]['output_dir']);run=json.loads((d/'run_manifest.json').read_text())
            if run['llm_kind']!='openai' or run['run_id']!=jobs[0]['run_id']:raise ValueError('Run identity')
            for name,h in run['effective_artifact_sha256'].items():
                if sha(d/name)!=h:raise ValueError('Effective inputs changed')
            with duckdb.connect(run['store_path'],read_only=True) as db:
                data=db.execute('select agent_id,action_payload from panel where step=1 order by agent_id').fetchall()
            if len(data)!=len(links) or {a for a,_ in data}!={r['agent_id'] for r in links}:raise ValueError('Coverage')
            by_arm[arm]={a:json.loads(p) if isinstance(p,str) else p for a,p in data}
            # Keyword counts are descriptive text diagnostics, not measures of causal attention.
            calls=[json.loads(x) for x in (d/'llm_calls.jsonl').read_text().splitlines()]
            reasons[arm]={key:sum(key in c.get('raw_response_text','').lower() for c in calls) for key in ['gasoline','milk','grocery','temporary','transitory','fed']}
            result['sources'][str(d/'run_manifest.json')]=sha(d/'run_manifest.json')
            result['sources'][run['store_path']]=sha(run['store_path'])
        centers=[];points=[];uncertainties=[];fitcounts={}
        for r in links:
            real=truth[(int(month),r['userid'])];aid=r['agent_id']
            fits={'real':density([real.get(f'Q9_bin{i}') for i in range(1,11)]),
                  **{arm:density([by_arm[arm][aid].get(f'q9_bin{i}') for i in range(1,11)]) for arm in ARMS}}
            base={k:r[k] for k in ['agent_id','padd','food_share']}
            centers.append({**base,**{k:v['mean'] for k,v in fits.items()}})
            uncertainties.append({**base,**{k:v['iqr'] for k,v in fits.items()}})
            q8=real.get('Q8v2part2');valid=type(q8) in (float,int) and np.isfinite(q8) and abs(q8)<=100
            points.append({**base,'real':q8 if valid else None,**{arm:by_arm[arm][aid]['point_pct'] for arm in ARMS}})
            for k,v in fits.items():fitcounts[k+':'+v['status']]=fitcounts.get(k+':'+v['status'],0)+1
        result['months'][month]={'Q9_center':metrics(centers),'Q8_secondary':metrics(points),
                                'personal_Q9_uncertainty':metrics(uncertainties),'fit_status_counts':fitcounts,
                                'reason_keyword_counts':reasons}
        detailed.extend({'month':month,'Q9':a,'Q8':b,'uncertainty':c} for a,b,c in zip(centers,points,uncertainties))
    result['limitations']=plan['limitations']+['Same frozen approximate density scorer on both raw-bin sets; not exact official fit.',
        'Two development months, one stochastic draw each; improvements require longer independent evaluation.',
        'Old macro table remains, so a null result does not refute the broader household-experience hypothesis.',
        'Source release dates checked, downloaded archive bytes not independently proved to be original first release.']
    write=lambda path,x:path.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    write(out/'summary.json',result);write(out/'paired_evaluation_private.json',detailed)
    render(out,result,detailed,plan)
    print(json.dumps({'analysis':str(out),'cost':result['estimated_cost_usd'],
                      'Q9':{m:v['Q9_center'] for m,v in result['months'].items()}},ensure_ascii=False))
    return result


def render(out,result,detailed,plan):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.family']=['PingFang SC','Arial Unicode MS','DejaVu Sans']
    colors={'real':'#111111','baseline':'#777777','national':'#247a9c','matched':'#3a6a42','shuffled':'#9b6532'}
    fig,axs=plt.subplots(1,2,figsize=(12,4.4),sharex=True,sharey=True)
    for ax,month in zip(axs,plan['months']):
        rows=[r['Q9'] for r in detailed if r['month']==month]
        rows=[r for r in rows if all(r[k] is not None for k in ('real',)+ARMS)]
        for key in ('real',)+ARMS:
            values=np.sort([r[key] for r in rows]);ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',label=LABELS[key],color=colors[key])
        ax.set_title(f'{month[:4]}-{month[4:]}：Q9个人均值分布');ax.set_xlabel('未来12个月通胀预期（%）');ax.set_ylabel('累计人数比例');ax.grid(alpha=.18)
    axs[1].legend(fontsize=8);fig.text(.02,.01,'来源：本轮SocioVerse真实LLM轨迹＋同一20人小样真实Q9，双方使用冻结近似计分器；等权，不代表全国。',fontsize=8)
    fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(out/'q9_distribution.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,4.4))
    names=[LABELS[a] for a in ARMS]
    for ax,month in zip(axs,plan['months']):
        m=result['months'][month]['Q9_center'];x=np.arange(4);w=.35
        ax.bar(x-w/2,[m['arms'][a]['median_absolute_error_pp'] for a in ARMS],w,label='小样中位数误差',color='#247a9c')
        ax.bar(x+w/2,[m['arms'][a]['distribution_W1_pp'] for a in ARMS],w,label='分布W1距离',color='#888888')
        ax.set_xticks(x,names,fontsize=9);ax.set_ylabel('误差（百分点，越低越好）');ax.set_title(month[:4]+'-'+month[4:]);ax.legend(fontsize=8)
    fig.text(.02,.01,'来源：同一完整配对小样；误差参照该小样真实分布，不是全国SCE headline误差。',fontsize=8)
    fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(out/'q9_errors.png',dpi=170);plt.close(fig)
    import html
    rows=''
    for month,m in result['months'].items():
        q=m['Q9_center']
        for arm in ARMS:
            a=q['arms'][arm];d=a['distribution']
            rows+=f'<tr><td>{month}</td><td>{LABELS[arm]}</td><td>{d["median"]:.3f}</td><td>{a["median_absolute_error_pp"]:.3f}</td><td>{a["distribution_W1_pp"]:.3f}</td><td>{d["iqr"]:.3f}</td></tr>'
    text=f'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>近期价格体验实验</title><style>body{{max-width:1000px;margin:35px auto;font-family:system-ui;line-height:1.7;padding:0 20px;color:#222}}img{{width:100%}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:7px;text-align:left}}h2{{margin-top:35px}}a{{color:#247a9c}}</style>
<h1>近期价格与地域匹配：两月开发试验</h1><p>20人／月 × 2月 × 4组；温度0.5；请求模型 deepseek-flash。160次真实调用，按保守公开费率估计费用 ${result['estimated_cost_usd']:.4f}（不是供应商账单）。</p>
<p>原有信息→补充近期全国食品/汽油→汽油按州匹配PADD→地区随机分配。四组保留相同合成篮子、宏观表与新闻。这里的“匹配”是地域规则，不是已知个人消费经历。</p>
<h2>是否更接近真实分布？</h2><img src="q9_distribution.png"><img src="q9_errors.png"><table><tr><th>月份</th><th>组别</th><th>模拟中位数%</th><th>中位数误差pp</th><th>分布W1 pp</th><th>跨人IQR pp</th></tr>{rows}</table>
<h2>怎样读结果</h2><p>优先看误差和整个分布是否同时改善。仅方差变大不代表成功；仅某个月改进也不代表稳定机制。比较对象是这些家庭自己的真实回答，不是全国headline。</p>
<h2>输入与限制</h2><ul>{''.join('<li>'+html.escape(x)+'</li>' for x in result['limitations'])}</ul>
<p><a href="summary.json">完整统计与来源哈希</a> · <a href="../trial_manifest.json">运行配置、费用与版本</a></p></html>'''
    (out/'index.html').write_text(text)
