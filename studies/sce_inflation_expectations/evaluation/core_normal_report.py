"""Readable implementation/validation report from frozen existing scores."""
from collections import defaultdict
from html import escape
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from .grid_dimension_selection import ROOT, dump, sha
from .core_normal_validation import atom, q9_metrics

COLORS=['#777777','#7437aa','#c76800']
PERIOD_LABEL={'development':'2019–2022 开发期','2023_2024':'2023–2024 时间检查','2025_01_10':'2025年1–10月 时间检查'}


def full_llm_human():
    source=ROOT/'outputs/sce_v32_news_matching_evaluation_20261022_v2/cases_private.json'
    groups=defaultdict(list)
    for r in json.loads(source.read_text()):groups[(r['month'],r['repeat'])].append(r)
    cells=[]
    for (month,repeat),rows in groups.items():
        pred=[];actual=[];weights=[]
        for r in rows:
            v=r['arms']['random_quantity'];a=r['real']
            x=atom(str(r['userid']),v['q9_bins'],v['mean'],v['iqr'],v['point'])
            y=atom(str(r['userid']),a['q9_bins'],a['q9_mean'],a['q9_iqr'],a['q8_point'])
            if x is not None and y is not None:
                pred.append(x);actual.append(y);weights.append(r['design_survey_weight'])
        cells.append({'month':int(month),'repeat':int(repeat),**q9_metrics(pred,weights,actual,weights)})
    return {'monthly':cells,'mean':{k:float(np.mean([c[k] for c in cells])) for k in ['median_mae_pp','w1_pp']}}


def render(human,cached,pilot,out):
    human,cached,pilot,out=map(lambda x:Path(x).resolve(),(human,cached,pilot,out))
    if out.exists():raise ValueError('New report directory required')
    h=json.loads((human/'summary.json').read_text());c=json.loads((cached/'summary.json').read_text())
    p=json.loads((pilot/'summary.json').read_text());monthly=json.loads((cached/'monthly_private.json').read_text())
    full=full_llm_human();out.mkdir(parents=True);figures=out/'figures';figures.mkdir()
    data={'human':{},'cache_preservation':{},'cache_human':{},'full_llm_human':full['mean'],
          'pilot':p['months'],'maximum_pilot_calls':p['maximum_calls_before_exact_prompt_reuse'],
          'new_api_calls':0,'q9_refits':0}
    for period,bs in h['periods'].items():
        data['human'][period]={b:{m:{k:v['all_q9'][k] for k in ['median_mae_pp','w1_pp']}
            for m,v in methods.items()} for b,methods in bs.items()}
    for m,r in c['methods'].items():
        data['cache_preservation'][m]={scope:{k:r[scope][k] for k in ['median_mae_pp','w1_pp']} for scope in ['all_q9','normal_q9']}
        rows=[r['human_comparison_same_saved_valid_support']['all_q9'] for r in monthly if r['method']==m]
        data['cache_human'][m]={k:float(np.mean([r[k] for r in rows])) for k in ['median_mae_pp','w1_pp']}
    plt.rcParams.update({'font.family':'serif','font.serif':['Times New Roman','DejaVu Serif'],
                         'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    def save(fig,name):
        fig.savefig(figures/f'{name}.png',dpi=160,bbox_inches='tight')
        fig.savefig(figures/f'{name}.svg',bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(13.2,4.1),sharey=True)
    for ax,(period,label) in zip(axes,PERIOD_LABEL.items()):
        for method,color,text in [('poststratified_Core_only',COLORS[0],'Core weighted'),('joint_tau24',COLORS[2],'Core + Normal (tau=24)')]:
            y=[data['human'][period][str(b)][method]['median_mae_pp'] for b in [256,384,512]]
            ax.plot([256,384,512],y,marker='o' if method.startswith('post') else 's',color=color,label=text)
            other='joint_tau24' if method.startswith('post') else 'poststratified_Core_only'
            for x,v in zip([256,384,512],y):
                other_y=data['human'][period][str(x)][other]['median_mae_pp']
                dy=8 if v>=other_y else -16
                ax.annotate(f'{v:.3f}',(x,v),xytext=(0,dy),textcoords='offset points',ha='center',fontsize=9)
        ax.set_title({'development':'2019–2022 development','2023_2024':'2023–2024 check','2025_01_10':'2025 Jan–Oct check'}[period])
        ax.set_xlabel('Different Core people / month');ax.set_xticks([256,384,512]);ax.set_ylim(.04,.26);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Full-frame median approximation MAE (pp)');axes[-1].legend(fontsize=9)
    fig.suptitle('Human Core statistical reference: NOT simulated LLM accuracy',fontsize=14)
    fig.tight_layout();save(fig,'human_sampling')
    methods=['poststratified_Core_only','joint_tau0','joint_tau24'];names=['Core weighted','Normal, no shrink','Normal, shrink 24']
    fig,axes=plt.subplots(1,2,figsize=(10,4.2))
    for ax,metric,title in zip(axes,['median_mae_pp','w1_pp'],['Median offset from full saved LLM','W1 to full saved LLM']):
        y=[data['cache_preservation'][m]['all_q9'][metric] for m in methods]
        bars=ax.bar(names,y,color=COLORS)
        for b,v in zip(bars,y):ax.text(b.get_x()+b.get_width()/2,v,f'{v:.3f}',ha='center',va='bottom')
        ax.set_title(title);ax.set_ylabel('Approximation error (pp), lower is better');ax.set_ylim(0,max(y)*1.28);ax.tick_params(axis='x',labelrotation=12)
    fig.suptitle('Saved V3.2 answers: 64/96 or 128/192 Core, eight months',fontsize=13)
    fig.tight_layout();save(fig,'cached_preservation')
    methods2=['full','poststratified_Core_only','joint_tau24'];human_values={**data['cache_human'],'full':full['mean']}
    fig,axes=plt.subplots(1,2,figsize=(10,4.2))
    for ax,metric,title in zip(axes,['median_mae_pp','w1_pp'],['Median MAE against humans','W1 against humans']):
        y=[human_values[m][metric] for m in methods2]
        bars=ax.bar(['All saved LLM','Reduced Core weighted','Reduced Core + Normal'],y,color=['#222222',COLORS[0],COLORS[2]])
        for b,v in zip(bars,y):ax.text(b.get_x()+b.get_width()/2,v,f'{v:.3f}',ha='center',va='bottom')
        ax.set_title(title);ax.set_ylabel('Error (pp), lower is better');ax.set_ylim(0,max(y)*1.25);ax.tick_params(axis='x',labelrotation=12)
    fig.suptitle('Same saved roster: expansion is not an automatic fit improvement',fontsize=13)
    fig.tight_layout();save(fig,'cached_human')
    rows=''.join(f'<tr><td>{r["month"]}</td><td>{r["frame_n"]}</td><td>{r["core_n"]}</td><td>{r["audit_n"]}</td><td>{r["core_entry_counts"].get("newcomer",0)}</td></tr>' for r in p['months'])
    baseline=data['cache_preservation']['poststratified_Core_only']['all_q9'];candidate=data['cache_preservation']['joint_tau24']['all_q9']
    content=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Core＋Normal机制落地与离线验证</title>
<style>body{{margin:0;background:#faf9f5;color:#252525;font-family:"Times New Roman","Kaiti SC","STKaiti","KaiTi",serif;line-height:1.8}}main{{max-width:1080px;margin:auto;padding:34px 24px}}h1{{font-size:29px}}h2{{font-size:23px;margin-top:36px}}aside{{background:#f4ede0;border-left:4px solid #c76800;padding:14px 20px}}img{{width:100%;height:auto}}small,.note{{color:#555}}table{{border-collapse:collapse;width:100%}}td,th{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}pre{{overflow:auto;background:#eee;padding:15px}}a{{color:#7437aa}}.scroll{{overflow:auto}}code{{font-size:.9em}}</style></head><body><main>
<p>SCE · 水上挽月 · 2026-10-23 · 本轮新增API 0／Q9重新拟合 0</p>
<h1>Core＋Normal：机制已可运行，调用节省与拟合代价仍需验证</h1>
<aside><strong>完成：</strong>54格过采样、经验贝叶斯式联合答卷收缩、Core保留本人答卷、Normal概率积分及加权中位数。完成82月真人Core留出和8个月已有V3.2回答留出。<br><strong>当前判断：</strong>具备离线可执行入口，但尚未证明替代全LLM后的拟合代价足够小，不直接启动全量。</aside>
<h2>1．本版到底怎么扩展</h2>
<p>学历3档×数理2档×年龄3档×收入3档＝54个已知画像格；未知信息保留，新人／回访者分池。小格过采样；格内已有回答少时，向同入组类型、人口特征最接近的其他格借信息。年龄与收入的匹配地位对称，不预先指定哪个一定更重要。</p>
<p>每份供体保留完整十档Q9及原有Q8；不把平均概率复制给所有人。先用现有冻结口径取得个人Q9密度均值，再对跨人分布取加权中位数。Q8另用独立有效回答库，避免Q9失败连带删除Q8。</p>
<p><strong>有限人口汇总：</strong>已取得的Core答卷按原人口质量保留，只扩Normal和明确标注的Core缺失字段。Core的抽样校正权重用于估计条件分布，不再作为另一份完整人口重复加入。全员都是合法Core时，必须精确还原原答卷分布。</p>
<p>局部答卷频率p、相近格经验先验H、有效Core人数n_eff对应α＝n_eff·p＋τ·H。主结果用归一化α直接积分答卷权重。因为采用调查权重有效人数和经验先验，这是加权经验贝叶斯／伪Dirichlet估计，不是完整的精确抽样似然；不能把Normal人数当新增独立证据。</p>
<h2>2．真人Core留出：统计扩展本身会损失多少</h2>
<p>2019-01—2025-10，82个月，每月256／384／512个Core、两个抽样种子。先按人口抽Core，再读取所选人的当前回答；剩余Normal才是留出对象。这里的Core使用<strong>真人答卷作为理想化统计参照</strong>，完全不是LLM输入或项目最终拟合成绩。</p>
<img src="figures/human_sampling.png" alt="三段时期下真人Core的总体中位数近似误差随Core规模变化">
<p class="note">τ只在2019—2022开发期资料的Normal留出上按既定W1＋中心代价规则选择，三种规模均选择24；后期不再调参。各时期已有研究，非全新盲测。同一人可跨月出现，不能将这些人月视为独立样本。</p>
<p>增加Core通常降低对完整波次的近似误差，但收缩对后期总体中位数没有一致收益。总体汇总与Normal局部误差应分开看，不能用已知Core掩盖Normal预测不足。</p>
<h2>3．已有V3.2回答留出：不付费检查是否保留原模型分布</h2>
<p>八个月、两遍分别评价，从旧96／192人框架中抽64／128人作为Core，最低名额1。其余已保存的LLM回答仅用于检查扩展，不参与估计。这个小框架与全SCE波次的256人设计不同，不能替代真实小试。</p>
<img src="figures/cached_preservation.png" alt="相对完整既有LLM回答的中位数偏移和W1">
<p>仅Core加权→收缩扩展，对完整已保存LLM分布的W1为<strong>{baseline['w1_pp']:.3f}→{candidate['w1_pp']:.3f}pp</strong>；月中位数绝对偏移<strong>{baseline['median_mae_pp']:.3f}→{candidate['median_mae_pp']:.3f}pp</strong>。这是扩展近似误差，不能直接加到原有模型MAE上。</p>
<img src="figures/cached_human.png" alt="完整LLM、缩小Core加权和Core加Normal分别对真人的误差">
<p><strong>真人对照必须披露：</strong>对同一已保存人群的真人，Core＋Normal没有显示总体拟合改善。它的价值首先是节省调用、提供可标注来源的统计人口扩展；目前不能声称它提高模型本身的行为真实性。正常人群的本人先验依赖及逐人排序没有被该人口分布方法自动恢复。</p>
<h2>4．下一步三月LLM小试：Core与审计人群分开</h2>
<div class="scroll"><table><thead><tr><th>月份</th><th>有效权重人口框架</th><th>Core调用</th><th>留出审计调用</th><th>Core内新人</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>共最多<strong>{p['maximum_calls_before_exact_prompt_reuse']}次</strong>，每人一遍。64人从Normal中另抽，仍属于Normal，只额外取得LLM答卷作审计，<strong>不加入Core估计</strong>。由此区分“LLM本来就不像真人”和“统计扩展又损失了什么”。同一批Core可离线比较多个τ，不重复调用。</p>
<p>已准备角色名册与权重；尚需接近期历史信念、完整P/E提示、精确缓存去重、官方Core干跑与预算授权。当前状态是<strong>roles_ready_not_prompt_or_api_ready</strong>。未启动小试或82月大批次，未承诺最终Core人数。</p>
<h2>5．可复用入口与当前边界</h2>
<pre>python scripts/validate_sce_core_normal.py --out outputs/&lt;新目录&gt;
python scripts/validate_sce_core_normal_cached.py --out outputs/&lt;新目录&gt;
python scripts/expand_sce_core_normal.py --population &lt;人口.json&gt; --core &lt;Core名册.json&gt; \
  --answers &lt;已计分Core回答.json&gt; --tau 24 --out outputs/&lt;新目录&gt;
python scripts/prepare_sce_core_normal_pilot.py --out outputs/&lt;新目录&gt;</pre>
<p>扩展入口不接受当期真人真值，不调用API或重新拟合Q9；已用缓存V3.2答卷跑通一次实际文件输入→人口分布输出。旧六格名单、默认模型输入和全部旧账本保持原版本。第一版全格后验预测已保留，有限人口版本增加了Core保留与全员Core还原检查，结果不覆盖。</p>
<details><summary>冻结结果与复算证据</summary><ul><li>{escape(str(human.relative_to(ROOT)))}</li><li>{escape(str(cached.relative_to(ROOT)))}</li><li>{escape(str(pilot.relative_to(ROOT)))}</li></ul><p>源哈希在各summary中；缓存LLM与真人采用同一原有冻结计分，真人统计参照使用已有官方派生均值/IQR。没有用本期答案调人口权重。</p></details>
<p><a href="README.md">完整技术说明</a> · <a href="interface_contract.md">给Kimi的接口契约</a> · <a href="../../NEXT_ACTIONS.md">当前任务板</a></p>
</main></body></html>'''
    (out/'index.html').write_text(content,encoding='utf-8');dump(out/'readout.json',data)
    canvas='''import {H1,H2,Text,Stack,Select,BarChart,Table,useState,useHostTheme} from "cursor/canvas";
const D=__DATA__;
export default function CoreNormal(){const t=useHostTheme();const[stage,setStage]=useState("2025_01_10");const rows=D.human[stage as keyof typeof D.human];
return <Stack gap={18} style={{padding:24,maxWidth:1100,margin:"0 auto",background:t.bg.editor,color:t.text.primary,fontFamily:'"Times New Roman","Kaiti SC","STKaiti","KaiTi",serif'}}>
<Text>SCE · 2026-10-23 · 本轮新增API 0</Text><H1>Core＋Normal：实现与近似代价</H1>
<div style={{borderLeft:`4px solid ${t.accent.primary}`,padding:16,background:t.fill.quaternary}}><H2>Core保留实际答卷，Normal扩展分布</H2><Text>54格＋新老受访者分池＋相近格经验先验。权重保持原人口比例，完整Q8/Q9不被平均复制。机制可离线运行，尚未证明足以替代全LLM。</Text></div>
<H2>真人Core统计参照：不是LLM拟合成绩</H2><Select value={stage} onChange={setStage} options={[{value:"development",label:"2019–2022 开发"},{value:"2023_2024",label:"2023–2024 时间检查"},{value:"2025_01_10",label:"2025年1–10月 时间检查"}]}/>
<Text>横轴：每月不同Core人数；纵轴：完整波次中位数近似MAE（pp，越低越好）。两抽样种子，每月等权。τ只在开发期选择。</Text>
<BarChart categories={["256人","384人","512人"]} series={[{name:"仅Core设计加权",data:["256","384","512"].map(b=>rows[b as keyof typeof rows].poststratified_Core_only.median_mae_pp),tone:"neutral"},{name:"Core＋Normal，τ24",data:["256","384","512"].map(b=>rows[b as keyof typeof rows].joint_tau24.median_mae_pp)}]} height={280} valueSuffix="pp" showValues={true}/>
<Text>来源：2019-01—2025-10既有SCE答卷、82月。真人Core只作评价用理想参照，未发送LLM。后期已看，非盲测。</Text>
<H2>缓存V3.2：保留原LLM分布的近似误差</H2><Text>八个月，64/96或128/192 Core，两遍分别评价；不能替代全波次256人小试。</Text>
<Table headers={["方法","月中位数绝对偏移pp","W1至完整LLM分布pp"]} rows={["poststratified_Core_only","joint_tau0","joint_tau24"].map((m,i)=>[["Core加权","不收缩扩展","收缩扩展τ24"][i],D.cache_preservation[m as keyof typeof D.cache_preservation].all_q9.median_mae_pp.toFixed(3),D.cache_preservation[m as keyof typeof D.cache_preservation].all_q9.w1_pp.toFixed(3)])}/>
<Text>扩展可降低部分分布偏差，但中心有额外近似损失；对真人没有总体拟合改善证据。Normal数量不增加独立信息，不能把上述偏移直接加到模型MAE上。</Text>
<H2>下一步：三个月，最多960次新调用</H2><Table headers={["月份","人口框架","Core","留出审计","Core新人"]} rows={D.pilot.map(r=>[String(r.month),String(r.frame_n),String(r.core_n),String(r.audit_n),String(r.core_entry_counts.newcomer)])}/>
<Text>审计64人来自Normal，只检验扩展，不进入Core估计。名册已准备；完整历史/P/E提示、干跑与预算尚待接入。82月全量继续暂停。</Text>
<a style={{color:t.text.link}} href="/Users/wushuyue/Documents/科研/DISC/socioverse_challenge/docs/workstreams/20261023_core_normal/index.html">完整图文、接口与复算</a></Stack>}
'''.replace('__DATA__',json.dumps(data,ensure_ascii=False))
    (out/'SCE-core-normal-20261023.canvas.tsx').write_text(canvas,encoding='utf-8')
    return data
