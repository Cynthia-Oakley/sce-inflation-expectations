"""Plot cached household/Q8 diagnostics and append to the existing reading page."""
from pathlib import Path
import argparse
from html import escape
import hashlib
import json
import os

os.environ.setdefault('MPLCONFIGDIR','/tmp/sce_advisor_mpl_20261019')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/sce_advisor_xdg_20261019')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.font_manager import fontManager
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'docs/workstreams/20261019_advisor_followup'
TARGET=ROOT/'docs/workstreams/20261013_behavior/codex_expansion_diagnostic_20261014.html'
KEY='household-grid-q8-20261019'
AGE={'Under 40':'较年轻组','40 to 60':'中间年龄组','Over 60':'较年长组'}
EDU={'high_school':'高中及以下','some_college':'部分大学教育','college':'大学及以上'}
TEAL,GOLD,INK,GREY='#087f80','#aa762f','#18343d','#cfd9d9'


def label(grid):return AGE[grid['age']]+'／'+EDU[grid['education']]


def main(source):
    source=source.resolve();dest=PUBLIC/'diagnostic_readout_v1'
    if dest.exists() or f'id="{KEY}"' in TARGET.read_text():raise ValueError('Fresh result location required')
    g=json.loads((source/'grid_summary.json').read_text());q=json.loads((source/'q8_summary.json').read_text())
    evidence=ROOT/'data/raw/mcp_checks/2026-10-19_advisor_free_v1/evidence.json'
    m=json.loads(evidence.read_text());tool=next(t for t in m['tools'] if t['name']=='run_user_pool_distribution_simulation')
    cap={'checked_at_utc':m['checked_at_utc'],'server':m['initialize'].get('serverInfo'),
       'registered_model':m['capability'].get('llm',{}).get('model'),'mock_enabled':m['capability'].get('llm',{}).get('mock_enabled'),
       'simulation_fields':sorted(tool['inputSchema']['properties']),
       'required_fields':tool['inputSchema'].get('required'),'paid_calls':0,
       'source_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest(),
       'limitation':'Registry and supported top-level schema only; no actual model or paid questionnaire tested. Arbitrary questionnaire properties do not establish individual P/E or history support.'}
    dest.mkdir(parents=True);figdir=dest/'figures';figdir.mkdir()
    cn=ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if cn.exists():fontManager.addfont(cn)
    plt.rcParams.update({'font.family':['Times New Roman','Kaiti SC','STKaiti'],'font.size':12,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.unicode_minus':False,'svg.fonttype':'none'})
    def save(fig,name):
        fig.savefig(figdir/(name+'.png'),dpi=165,bbox_inches='tight',facecolor='white')
        fig.savefig(figdir/(name+'.svg'),bbox_inches='tight',facecolor='white');plt.close(fig)
    grids=list(g['grids'].values())
    fig,ax=plt.subplots(figsize=(13,6.2));a=np.array([[{'sparse':0,'weak':1,'strong':2}[c['support']] for c in r['monthly']] for r in grids])
    ax.imshow(a,cmap=ListedColormap(['#e5eaea','#e9d9ba','#b7d2ce']),vmin=0,vmax=2,aspect='auto')
    for i,r in enumerate(grids):
        for j,c in enumerate(r['monthly']):ax.text(j,i,f"{c['n']} / {c['ess']:.1f}",ha='center',va='center',fontsize=9,color=INK)
    ax.set_xticks(range(12),[str(x)[2:4]+'.'+str(x)[4:] for x in g['months']]);ax.set_yticks(range(9),[label(r) for r in grids])
    ax.set_xlabel('预选调查月（非连续）；每格显示真实人数 n / 加权有效人数 ESS')
    ax.set_ylabel('年龄×学历');ax.set_title('九类家庭的逐月支持：灰=n<10，浅褐=ESS<10，浅绿=n与ESS均≥10',pad=14)
    fig.text(.02,.015,'来源：十二期既有轨迹；2,284个共同人月。生成两遍不使人数翻倍；未知画像不硬分到任一格。',fontsize=10,color=INK)
    fig.tight_layout(rect=(0,.035,1,1));save(fig,'grid_support')
    complete=[r for r in grids if r['strong_scope']['coverage_complete']]
    fig,axes=plt.subplots(1,2,figsize=(12.7,5.5));yy=np.arange(len(complete))
    for field,name,color,offset in [('truth','真人',INK,-.16),('model_average_of_month_repeat_metrics','模型',TEAL,.16)]:
        axes[0].barh(yy+offset,[r['strong_scope'][field]['cross_person_iqr_pp'] for r in complete],height=.30,label=name,color=color)
    axes[0].set_yticks(yy,[label(r) for r in complete]);axes[0].invert_yaxis();axes[0].set_xlabel('跨人IQR（pp）');axes[0].set_ylabel('十二期均有足够支持的五类家庭')
    axes[0].set_title('同类家庭内部仍明显过窄');axes[0].legend(frameon=False)
    for field,name,color,offset in [('cross_section_w1_pp','原始分布',INK,-.16),('centered_w1_pp','各自去中位数后',TEAL,.16)]:
        axes[1].barh(yy+offset,[r['strong_scope']['model_average_of_month_repeat_metrics'][field] for r in complete],height=.30,label=name,color=color)
    axes[1].set_yticks(yy,[label(r) for r in complete]);axes[1].invert_yaxis();axes[1].set_xlabel('模型与真人W1（pp，越低越好）');axes[1].set_ylabel('年龄×学历');axes[1].set_title('去掉位置差异后仍有分布差距');axes[1].legend(frameon=False)
    fig.text(.02,.015,'来源：2020—2025十二个预选月，设计权重；各月/遍先计算再等权平均。其余四类覆盖不足，未参与此图的横向比较。',fontsize=10,color=INK)
    fig.tight_layout(rect=(0,.045,1,1));save(fig,'within_grid_distribution')
    v=g['variance_decomposition']['equal_month_means'];fig,ax=plt.subplots(figsize=(8,4.7))
    within=[v[k]['within_grid_variance_pp2'] for k in ['truth','model']];between=[v[k]['between_grid_variance_pp2'] for k in ['truth','model']]
    ax.bar(['真人','模型'],within,color=TEAL,label='格内方差');ax.bar(['真人','模型'],between,bottom=within,color=GOLD,label='格间方差')
    ax.set_ylabel('个人预期方差（pp²）');ax.set_xlabel('十二期月等权平均；模型先逐遍计算');ax.set_title('模型缺失的方差主要发生在年龄×学历格内');ax.legend(frameon=False)
    for i,k in enumerate(['truth','model']):ax.text(i,within[i]+between[i]+.7,f"{v[k]['total_variance_pp2']:.2f}",ha='center',color=INK)
    fig.text(.04,.015,'来源：十二期同支持；未知画像单列。恒等分解包含极端值；不是MAE分解，也不是因果贡献。',fontsize=10,color=INK)
    fig.tight_layout(rect=(0,.04,1,1));save(fig,'variance_parts')
    s=q['scopes']['q8_only_common']['equal_people']['metrics'];fig,axes=plt.subplots(1,3,figsize=(12,4.4))
    for ax,field,title in zip(axes,['center_mae_pp','personal_mae_pp','w1_pp'],['群体中位数MAE','个人MAE','跨人分布W1']):
        vals=[s[k][field] for k in ['direct','revision']];ax.bar(['直接填本期','填变化值'],vals,color=[INK,TEAL],width=.55)
        for i,val in enumerate(vals):ax.text(i,val+max(vals)*.035,f'{val:.3f}',ha='center')
        ax.set_ylim(0,max(vals)*1.22);ax.set_ylabel('误差（pp，越低越好）');ax.set_xlabel('旧四期的回答格式');ax.set_title(title)
    fig.text(.02,.015,'来源：2020-04、2021-05/11、2022-03，各24人×两遍；Q8单独合法支持192/192，等人/月/遍。原提示同时改变Q8和Q9，尚非Q8单改因果对照。',fontsize=9,color=INK)
    fig.tight_layout(rect=(0,.07,1,1));save(fig,'q8_recovery')
    def table(headers,rows):
        return '<div style="overflow-x:auto"><table><thead><tr>'+''.join('<th>'+escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    support_rows=[]
    for r in grids:
        p=r['persistence_strong_cells'];gs=r['strong_scope'];mm=gs['model_average_of_month_repeat_metrics'];tt=gs['truth']
        f=lambda x:'—' if x is None else f'{x:.3f}'
        support_rows.append([label(r),r['n_common_person_months'],gs['n_months_reported'],f(mm.get('q9_center_mae_pp')),f(gs['copy_previous'].get('q9_center_mae_pp')),f(mm.get('cross_person_iqr_pp')),f(tt.get('cross_person_iqr_pp')),f(p['model_on_prior_slope']),f(p['truth_on_prior_slope'])])
    update_rows=[]
    for r in complete:
        st=r['strong_scope'];yt=st['truth'];mt=st['model_average_of_month_repeat_metrics'];ct=st['copy_previous']
        update_rows.append([label(r)]+[f'{v:.3f}' for v in [yt['delta_iqr_pp'],mt['delta_iqr_pp'],mt['delta_w1_pp'],ct['delta_w1_pp']]]+[f"{100*yt['update_abs_le_0_25_share']:.1f}%",f"{100*mt['update_abs_le_0_25_share']:.1f}%"])
    qprior=q['scopes']['q8_with_prior_common']['equal_people']['metrics']
    qrows=[[{'direct':'直接填本期','revision':'填变化值','previous':'照抄本人上期'}[a]]+[f'{z[k]:.3f}' for k in ['center_mae_pp','personal_mae_pp','w1_pp','delta_w1_pp','iqr_pp']] for a,z in qprior.items()]
    monthly=[]
    for mth in sorted({c['month'] for c in q['scopes']['q8_only_common']['equal_people']['cells']}):
        cc=[c for c in q['scopes']['q8_only_common']['equal_people']['cells'] if c['month']==mth]
        monthly.append([mth]+[f"{np.mean([c['metrics'][a]['center_mae_pp'] for c in cc]):.3f}" for a in ['direct','revision']])
    def image(name,caption):
        rel=Path(__import__('os').path.relpath(figdir/(name+'.png'),TARGET.parent)).as_posix()
        return f'<figure><img style="max-width:100%;height:auto" src="{rel}" alt="{escape(caption)}"><figcaption>{escape(caption)}</figcaption></figure>'
    fragment=f'''<section id="{KEY}" style="font-family:'Times New Roman','Kaiti SC',STKaiti,serif;border-bottom:1px solid #d5e1e2;padding:20px 0 36px;line-height:1.8">
    <h1>九类家庭与Q8独立复算：同类人内部差异仍是主要缺口</h1>
    <p>2026-10-19。复用十二期和旧四期原始回答，未新增LLM调用、未重新拟合Q9、未改旧配置。平台仅做免费元数据核查，付费调用0。</p>
    <h2>结论与下一步</h2><ol>
    <li><b>网格化可以改善抽样和评价，但不能独自恢复异质性。</b>年龄×学历分组下，真人总方差约{v['truth']['total_variance_pp2']:.2f}、模型{v['model']['total_variance_pp2']:.2f} pp²；方差缺口中约{v['within_share_of_variance_deficit']:.1%}发生在格内。这里只说明这套粗分组，不代表所有人口信息都不重要。</li>
    <li><b>高中及以下的三个年龄格最需补真实样本。</b>较年轻、中间年龄组都没有一个月份同时达到n≥10和ESS≥10；较年长组仅3/12期。不能从现在的数据给它们稳定排名。先定向补足Core，而非扩大复制出的Normal。</li>
    <li><b>变化值回答值得一次简化小试。</b>74份因Q9失败而被旧联合评价丢弃的Q8均可恢复；完整Q8同支持中位数MAE从{s['direct']['center_mae_pp']:.3f}降到{s['revision']['center_mae_pp']:.3f}，W1从{s['direct']['w1_pp']:.3f}降到{s['revision']['w1_pp']:.3f} pp。但四月中一月恶化、一月持平，且个人和分布仍落后同支持照抄；这不是主Q9指标的改善。</li>
    <li><b>平台仍未提供已确认的同输入GPT-4o入口。</b>免费登记仍为{escape(str(cap['registered_model']))}，当前顶层参数要求平台人口池，未见逐人自带P/E/本人先验和模型选择参数。没有执行问卷测试，不把别名目录当作可切换模型的证据。</li></ol>
    <h2>1. 九格覆盖：哪里需要增加真实模拟人数？</h2>
    <p>沿用原始三年龄组和三学历组，不因误差挑分组；未知画像另记。2,304个计划人月中2,284共同可评分，未知交叉画像{g['unclassified_common_person_months']}人月。n&lt;10隐藏指标；ESS&lt;10标弱支持。以下组均值仅使用强支持月份，覆盖不同的行不直接排名。</p>
    {image('grid_support','每格为人数/加权有效人数；两遍没有使人数翻倍。')}
    {table(['年龄／学历','共同人月','强支持月/12','模型中心MAE','照抄中心MAE','模型IQR','真人IQR','模型历史斜率','真人历史斜率'],support_rows)}
    <p>历史斜率为各月/格内去均值后的协方差比，跨月等权汇总；它是描述关联，不是可直接部署的心理权重。五个全十二期有支持的格中，模型历史斜率均低于真人。</p>
    <h3>同一家庭从上期到本期的变化</h3><p>以下五类均覆盖十二期。“更新”是本期个人Q9密度均值减本人真实上期值，不是把相隔数月的两个模拟月份相减。照抄的变化恒为0，所以它可以保住截面，却不能重建实际更新。变化W1比较整组更新分布；它较低也不证明模型判断对了哪一个人会改变。</p>
    {table(['年龄／学历','真人更新IQR','模型更新IQR','模型变化W1','照抄变化W1','真人变动≤0.25pp','模型变动≤0.25pp'],update_rows)}
    <p>所有十二期完整支持格中，模型的旧信念关联斜率都低于真人；但更新宽度和小改动比例需要分组看，不能概括为“所有人都更新过多”或“所有人都更新不足”。这些是现象定位，不是新的因果识别。</p>
    <h2>2. 差距主要是整体位置错，还是格内仍过窄？</h2>
    {image('within_grid_distribution','只比较全十二期都有足够支持的五类；去中心后的W1不是原W1的可加组成。')}
    <p>这五类人的模型IQR均明显低于真人；去掉每组中位数位置差异后，W1仍保留大部分差距。因此，只调整各类人口的比例或给每格统一加常数，难以恢复完整分布。某些组中心优于照抄，不等于全国中位数一定改善：中位数不能线性加总。</p>
    {image('variance_parts','总方差=格间＋格内；原始值未截尾。极端回答和测量噪声也会进入方差，不能全部解释为真实信念。')}
    <h2>3. Q8变化值：把被Q9失败遮住的回答补回评价</h2>
    <p>同一旧实验384个请求，192直接＋192差值。按Q8自身判断后，两组192/192均合法；缺上期Q8的一人按原协议报绝对值，不补造先验。使用旧运行相同四位精度，旧115条Q9共同子样本的Q8结果复算一致。Q9完整差值有效率仍为118/192，旧失败结论不改。</p>
    {image('q8_recovery','完整96个人月×两遍；Q8等人主口径，逐月/遍计算后平均。不可与十二期Q9的0.459相比较。')}
    {table(['月份','直接Q8中心MAE','差值Q8中心MAE'],monthly)}
    <p>两次生成的等人中心效果反转：第1遍0.675→0.825pp，第2遍0.825→0.550pp。这是值得小试的信号，不是稳定胜者。</p>
    <p>调查加权辅助Q8中心MAE为1.038→0.738pp，与等人方向一致；不据更好数字改换主口径。两遍中心误差差异和四期覆盖仍有限，没有据此宣称独立稳健成功。</p>
    <h3>同支持上，与照抄比较</h3><p>有真实上期Q8的95个人月、190次生成，以下均为同支持等人/月/遍。个人和分布误差仍未胜照抄，说明仅改变表达方式尚未提供足够增量。</p>
    {table(['方法','中心MAE','个人MAE','W1','变化W1','人际IQR'],qrows)}
    <h2>4. 只选一项新对照：Q8报变化，Q9仍直接填本期</h2>
    <p>优先准备简化更新格式的独立候选：共同P/E和真实上期信念不变，对照直接报Q8/Q9，候选只把Q8改为变化值、Q9直接填绝对概率。先用旧四个开发月的小样、两遍作机制筛选；新批次同时重生成对照。主Q9中心、W1及合法率保留，Q8改善只作次要收益，不因格式信号直接升级主配置。</p>
    <p>同时保留采购角色→可见价格的已备原型。现有菜单缺单独的清洁纸品/护理价格，食品主题路由也稀疏，下一轮不把这些尚未补齐的内容同时塞入格式实验。Q8若有收益而Q9无变化，只能报告Q8接口收益；主Q9仍需其他机制，采购角色—价格方向保留，不重试同一概率差值。</p>
    <p>后续先冻结新批次输入、名单、模型和预算，再完成共用引擎干跑并申请明确外发授权。本轮没有启动新的付费模拟。随机新闻量另登记独立时期/种子，B递推和Q2扩展不挤掉主线验证。</p>
    <details><summary>方法、来源及局限</summary><p>统计量均复用共享evaluation模块；没有因结果合并格或改变权重。方差分解不能分解中位数MAE，年龄×学历格内仍可能有收入、数理、私人信息和测量差异。四期Q8的原提示同时改变两题，因此需要Q8单改的真实对照来识别接口作用。所有这些月份已看过，只能作开发。</p>
    <p>权威新输出：outputs/sce_advisor_diagnostic_20261019_v2/；v1为分位数边界与旧口径对齐前的草稿，不用于结论。平台免费证据：data/raw/mcp_checks/2026-10-19_advisor_free_v1/。原个人记录与回包只留本地。</p></details></section>'''
    styles=f'<style>#{KEY} table{{width:100%;border-collapse:collapse;table-layout:auto;font-size:16px}}#{KEY} th,#{KEY} td{{padding:9px 12px;border-bottom:1px solid #d5e1e2;text-align:left;min-width:88px}}#{KEY} th:first-child,#{KEY} td:first-child{{min-width:200px}}#{KEY} h2{{margin-top:30px}}#{KEY} p,#{KEY} li{{font-size:18px}}#{KEY} figcaption{{font-size:15px;color:#526970}}</style>'
    target=TARGET.read_text()
    if '<main>' not in target:raise ValueError('Reading-page insertion target not found')
    TARGET.write_text(target.replace('<main>','<main>'+styles+fragment,1))
    (dest/'reading_section.html').write_text(styles+fragment)
    (dest/'grid_summary.json').write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
    (dest/'q8_summary.json').write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    (dest/'platform_capability_summary.json').write_text(json.dumps(cap,ensure_ascii=False,indent=2)+'\n')
    md=f'''# 九类家庭与Q8独立复算结果

2026-10-19。新LLM调用0、Q9新拟合0；仅完成平台免费目录/能力查询，付费调用0。

## 主要发现

- 十二期共同2,284人月。年龄×学历九格中，五格有完整十二期强支持；年轻/中间年龄的高中及以下组均没有强支持月份，较年长高中组仅3期。未知交叉画像{g['unclassified_common_person_months']}共同人月另记，不强行分格。
- 原始加权总方差：真人{v['truth']['total_variance_pp2']:.3f}、模型{v['model']['total_variance_pp2']:.3f}pp²；方差缺口约{v['within_share_of_variance_deficit']:.1%}来自格内。这只针对当前粗网格，不是所有P无效的证明，也不是MAE/因果分解。五个完整支持格去中心后W1仍高、IQR仍窄，支持不是单纯群体位置错误。
- 旧完整概率差值实验74份Q9失败回包，其Q8均可合法恢复。Q8单独两臂均192/192有效。完整等人Q8中心MAE {s['direct']['center_mae_pp']:.3f}→{s['revision']['center_mae_pp']:.3f}、个人MAE {s['direct']['personal_mae_pp']:.3f}→{s['revision']['personal_mae_pp']:.3f}、W1 {s['direct']['w1_pp']:.3f}→{s['revision']['w1_pp']:.3f}pp。四期一月恶化、一月持平；两遍中心排序反转（第1遍0.675→0.825、第2遍0.825→0.550）。不能称普遍收益，更不改十二期Q9主成绩。
- 有真实上期Q8的95个人月同支持上，差值个人MAE和W1仍落后照抄；旧Q9差值有效率失败保持原结论。原提示同时改变Q8/Q9，需要单改Q8的候选才能区分作用。
- 平台免费回查仍登记gpt-4o-mini，问卷接口要求平台人口池；没有已确认的逐人自带P/E/先验或模型选择入口。只记录服务元数据，未运行付费问卷。

## 下一项

优先准备两组简化格式对照：直接Q8/Q9 vs Q8变化值＋Q9绝对概率。只改一项格式，共同输入与先验保持，重生成同期对照；四个旧开发月做筛选，后续新月份再验证。不能仅因Q8次要指标改善升级主配置。平台模型对照暂不具备同输入条件，采购角色—价格方向保留、先补材料。

## 图与复算

阅读页：[打开本次章节](../20261013_behavior/codex_expansion_diagnostic_20261014.html#{KEY})。

图表与逐格聚合：[diagnostic_readout_v1](diagnostic_readout_v1/)。

```text
python scripts/analyze_sce_advisor_diagnostics.py --out outputs/<fresh_output>
python -m pytest tests/test_sce_advisor_diagnostics.py -q
```

权威输出：`outputs/sce_advisor_diagnostic_20261019_v2/`；v1为对齐偶数样本分位边界前的草稿，未用于最终报告。新恢复值按旧运行4位精度，旧Q9共同子样本Q8误差逐项对齐；旧数据、计分、运行包均未改。追加阅读页需新章节标识，不重复覆盖本次章节。
'''
    (PUBLIC/'diagnostic_results.md').write_text(md)
    print(json.dumps({'reading_page':str(TARGET)+'#'+KEY,'public_summary':str(dest),'new_llm_calls':0},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);main(p.parse_args().source)
