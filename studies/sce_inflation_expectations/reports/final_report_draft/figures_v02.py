"""Typesetting figures from frozen aggregates plus a labeled teaching example.

No regressions, respondent records, density fits, simulation or API calls.
"""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, Rectangle
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/sce_research_report_figures_20261024_v02"
GRID = ROOT / "outputs/sce_grid_dimensions_20261023_v1/summary.json"
NEWS = ROOT / "docs/workstreams/20261021_fullperiod/news_matching_results/summary.json"
C = {"ink": "#242424", "muted": "#757575", "orange": "#c76800", "blue": "#0078b5", "purple": "#7437aa"}


def setup():
    font_manager.fontManager.addfont(str(ROOT / "outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf"))
    plt.rcParams.update({"font.family": ["Times New Roman", "Kaiti SC"],
                         "font.size": 13, "axes.unicode_minus": False,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.facecolor": "white"})


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=210, bbox_inches="tight")
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def q9_example():
    fig = plt.figure(figsize=(9, 4.0))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, .33], hspace=.9, wspace=.27)
    ax = fig.add_subplot(gs[0, 0]); density = fig.add_subplot(gs[0, 1])
    labels = ['≤−12', '−12至−8', '−8至−4', '−4至−2', '−2至0', '0至2', '2至4', '4至8', '8至12', '≥12']
    p = [0, 0, 0, 0, 0, 50, 50, 0, 0, 0]
    ax.bar(np.arange(10), p, color=[C['orange'] if x else '#d5d5d5' for x in p], width=.7)
    ax.set_xticks(np.arange(10), labels, rotation=60, ha='right', fontsize=10.5)
    ax.set_ylim(0, 66); ax.set_ylabel('所分配概率（%）', fontsize=12)
    ax.set_xlabel('未来12个月通胀率区间（%）', fontsize=12)
    ax.set_title('Q9：十档概率，总和100%', fontsize=14)
    ax.text(5.5,52,'各50%',ha='center',fontsize=12)
    x = np.linspace(0,4,301); y = np.where(x<=2,x/4,(4-x)/4)
    density.plot(x,y,color=C['blue'],linewidth=2)
    density.fill_between(x,y,alpha=.12,color=C['blue'])
    density.axvline(2,color=C['orange'],linestyle='--',linewidth=1.4)
    density.text(2.13,.41,'密度均值\n2.0%',color=C['orange'],fontsize=12)
    density.set_xlim(-.25,4.4);density.set_ylim(0,.59)
    density.set_xlabel('未来12个月通胀率（%）',fontsize=12)
    density.set_ylabel('概率密度（每百分点）',fontsize=12)
    density.set_title('本例：相邻两档→三角密度',fontsize=14)
    bottom=fig.add_subplot(gs[1,:]);bottom.axis('off')
    bottom.text(0, .75,'Q8示例：直接填写3%（独立点判断）',fontsize=13,color=C['ink'])
    bottom.text(0,.02,'跨人聚合示例：均值[1, 2, 3, 5, 8] + 权重[.1, .2, .4, .2, .1] → 加权中位数3%',fontsize=12,color=C['ink'])
    save(fig,'q9_explanation')
    return {'example_only':True,'q8_point_pct':3,'q9_probabilities_ascending_pct':p,
            'density':'symmetric triangular on [0,4]','density_mean_pct':2,
            'illustrative_person_means_pct':[1,2,3,5,8],
            'illustrative_weights':[.1,.2,.4,.2,.1],'weighted_median_pct':3,
            'not_used_in_prompts_or_scores':True}


def grid_evidence(s):
    variables=['numeracy','education','age','income','gender','employment','housing','region']
    labels=['数理','学历','年龄','收入','性别','就业','住房','地区']
    domains=['level','uncertainty','reporting','distribution']
    data=np.array([[100*s['conditional_information'][v]['development_domain_loss_increase'][d]
                    for d in domains] for v in variables])
    fig,(ax,sc)=plt.subplots(1,2,figsize=(9.1,3.9),gridspec_kw={'width_ratios':[1.45,1]},layout='constrained')
    im=ax.imshow(data,cmap='RdBu_r',vmin=-3.3,vmax=3.3,aspect='auto')
    ax.set_xticks(range(4),['预期水平','个人IQR','零通缩填法','跨人CDF'],fontsize=11)
    ax.set_yticks(range(8),labels,fontsize=12)
    for i in range(8):
        for j in range(4):
            ax.text(j,i,f'{data[i,j]:.2f}',ha='center',va='center',fontsize=11,
                    color='white' if abs(data[i,j])>2 else C['ink'])
    ax.set_title('移除变量后，留出损失增加多少？',fontsize=13)
    ax.set_xlabel('标准化损失百分点；正值表示该项有增量',fontsize=11)
    mca=np.array(s['associations']['development']['mca']['raw_inertia_fraction'][:8])*100
    sc.plot(np.arange(1,9),mca,'o-',color=C['purple'],linewidth=1.7,markersize=4)
    sc.set_xticks([1,2,4,6,8]);sc.set_ylim(0,15)
    sc.set_xlabel('MCA成分序号',fontsize=12)
    sc.set_ylabel('人口特征原始惯量占比（%）',fontsize=11)
    sc.set_title('碎石图：描述人口X，不预测答案Y',fontsize=12)
    sc.grid(axis='y',alpha=.17)
    save(fig,'grid_evidence')
    return {'removed_blocks':variables,'domains':domains,'loss_increase_percentage_points':data.tolist(),
            'mca_first_eight_raw_inertia_pct':mca.tolist(),
            'interpretation':'Grouped respondent CV, development 2019-2022; not national MAE or causal effect.'}


def information_routes():
    fig,ax=plt.subplots(figsize=(9,2.3));ax.set_xlim(0,1);ax.set_ylim(0,1);ax.axis('off')
    cols=[(.00,.26),(.36,.28),(.74,.26)]
    rows=[(.64,['人口/经济处境','新闻关注、理解与主题关联','可见新闻量与主题']),
          (.18,['家庭结构/年龄','采购责任与反复价格接触','可见食品价格细项'])]
    for y,words in rows:
        for (left,width),text in zip(cols,words):
            ax.add_patch(Rectangle((left,y),width,.23,facecolor='#f2f4f5',edgecolor='#a7a7a7',linewidth=.7))
            ax.text(left+width/2,y+.115,text,ha='center',va='center',fontsize=12)
        for x1,x2 in [(.27,.35),(.65,.73)]:
            ax.add_patch(FancyArrowPatch((x1,y+.115),(x2,y+.115),arrowstyle='->',mutation_scale=11,color=C['ink']))
    ax.text(.5,.51,'两条接触途径分别建模；共同作用于旧信念的保留与更新 → Q8/Q9',ha='center',fontsize=12,color=C['orange'])
    ax.text(.5,.02,'文献提供传导动机；CE/ATUS与关注资料仅提供代理分配，不等于本人真实接触记录。',ha='center',fontsize=11,color=C['muted'])
    save(fig,'information_routes')


def news_evidence(s):
    pair=s['actual_pair_support']['random_quantity_minus_fixed_8']
    # Read the exact existing pair; no new support selection or statistics.
    fig,axes=plt.subplots(1,2,figsize=(9,1.6),layout='constrained')
    arms=['fixed_8','random_quantity']
    for ax,metric,title,xmax in zip(axes,['center_mae_pp','w1_pp'],
                                  ['中心MAE（pp）','跨人W1（pp）'],[.36,1.6]):
        values=[pair['metrics'][a][metric] for a in arms]
        ax.barh([1,0],values,color=[C['muted'],C['orange']],height=.48)
        ax.set_yticks([1,0],['固定8篇','随机3/8/20篇'],fontsize=12)
        ax.set_xlim(0,xmax);ax.set_ylim(-.6,1.65)
        ax.set_title(title+'：越低越好',fontsize=13)
        ax.tick_params(axis='x',labelsize=10)
        for y,value in zip([1,0],values):ax.text(value+xmax*.025,y,f'{value:.3f}',va='center',fontsize=12)
    save(fig,'news_evidence')
    return {k:pair[k] for k in ['person_months','unique_persons','metrics']}


def main():
    OUT.mkdir(parents=True,exist_ok=True);setup()
    s=json.loads(GRID.read_text());n=json.loads(NEWS.read_text())
    evidence={'q9_illustration':q9_example(),'grid':grid_evidence(s),
              'news_pair_existing':news_evidence(n),'new_api_calls':0,
              'new_regressions':0,'new_density_fits':0}
    information_routes()
    (OUT/'figure_data.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print(str(OUT))


if __name__=='__main__':main()
