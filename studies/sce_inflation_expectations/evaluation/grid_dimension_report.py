"""Render frozen demographic-grid aggregates without inspecting private rows."""
from __future__ import annotations

from pathlib import Path
from html import escape
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from .grid_dimension_selection import LABELS, DOMAIN_NAMES

ENGLISH = {'education': 'Education', 'numeracy': 'Numeracy', 'income': 'Income', 'age': 'Age',
           'employment': 'Employment', 'gender': 'Gender', 'housing': 'Housing', 'region': 'Region'}
DOMAINS = ['Level', 'Individual IQR', 'Zero deflation', 'CDF shape']
COLORS = ['#777777', '#c76800', '#7437aa', '#0078b5']


def cn(fields):
    return ' × '.join(LABELS.get(f, '是否在职') for f in fields)


def render(source, out, *, joint=None, sensitivity=None):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('New report directory required')
    d = json.loads((source/'summary.json').read_text())
    out.mkdir(parents=True); figures = out/'figures'; figures.mkdir()
    models = {m['name']: m for m in d['candidates']}
    chosen = models[d['selection']['recommended']]
    best = models['education+numeracy+income+gender']
    old = models['education_x_attachment_6']; full = models['all_eight_additive']
    plt.rcParams.update({'font.family': 'serif', 'font.serif': ['Times New Roman', 'DejaVu Serif'],
                         'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    def save(fig, name):
        fig.savefig(figures/f'{name}.svg', bbox_inches='tight')
        fig.savefig(figures/f'{name}.png', dpi=160, bbox_inches='tight')
        plt.close(fig)
    a = d['associations']['development']; keys = a['variables']
    fig, ax = plt.subplots(figsize=(8, 6.4))
    matrix = np.array(a['weighted_cramers_v'])
    im = ax.imshow(matrix, cmap='Greys', vmin=0, vmax=1)
    ax.set_xticks(range(len(keys)), [ENGLISH[k] for k in keys], rotation=40, ha='right')
    ax.set_yticks(range(len(keys)), [ENGLISH[k] for k in keys])
    for i in range(len(keys)):
        for j in range(len(keys)):
            ax.text(j, i, f'{matrix[i,j]:.2f}', ha='center', va='center', color='white' if matrix[i,j]>.6 else 'black')
    ax.set_xlabel('Categorical feature'); ax.set_ylabel('Categorical feature')
    ax.set_title('Demographic association: survey-weighted Cramer V')
    fig.colorbar(im, ax=ax, label='Cramer V (0–1)')
    save(fig, 'association')

    fig, ax = plt.subplots(figsize=(10, 4.4))
    order = sorted(keys, key=lambda k: -np.mean(list(d['conditional_information'][k]['development_domain_loss_increase'].values())))
    x = np.arange(len(order)); width = .19
    for i, domain in enumerate(DOMAIN_NAMES):
        values = [100*d['conditional_information'][k]['development_domain_loss_increase'][domain] for k in order]
        ax.bar(x+(i-1.5)*width, values, width, color=COLORS[i], label=DOMAINS[i])
    ax.axhline(0, color='black', lw=.7)
    ax.set_xticks(x, [ENGLISH[k] for k in order], rotation=25, ha='right')
    ax.set_ylabel('Increase in normalized loss when removed (percentage points)')
    ax.set_xlabel('Removed categorical block; all other seven retained')
    ax.set_title('Conditional predictive information: respondent-grouped CV, 2019–2022')
    ax.legend(ncol=2, frameon=False)
    save(fig, 'conditional_information')

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for n, color, marker in [(3, '#777777', 'o'), (4, '#7437aa', '^')]:
        rows = [m for m in models.values() if m['role']=='candidate' and len(m['fields'])==n]
        ax.scatter([m['cartesian_cells'] for m in rows], [m['development_cv']['composite_gain']*100 for m in rows],
                   alpha=.6, color=color, marker=marker, s=28, label=f'{n} dimensions')
    ax.scatter([chosen['cartesian_cells']], [100*chosen['development_cv']['composite_gain']], color=COLORS[1], marker='*', s=220, label='Recommended candidate', zorder=5)
    ax.scatter([6], [100*old['development_cv']['composite_gain']], color='black', marker='D', s=65, label='Existing six-cell benchmark', zorder=5)
    ax.set_xlabel('Cartesian cells before empty-cell handling (count)')
    ax.set_ylabel('Composite within-month predictive gain (%)')
    ax.set_title('126 candidate grids: information retained versus fragmentation')
    ax.legend(frameon=False)
    save(fig, 'candidate_frontier')

    names = list(dict.fromkeys([old['name'], chosen['name'], best['name'], full['name']]))
    legends = {old['name']: 'Existing 6-cell', chosen['name']: 'Recommended', full['name']: 'All 8 (reference)'}
    if best['name'] != chosen['name']:
        legends[best['name']] = '4D: add income'
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), sharey=True)
    stages = [('development_cv', '2019–2022 grouped CV'), ('2023_2024', '2023–2024 temporal check'), ('2025_01_10', '2025 temporal check')]
    width = .8/len(names); x = np.arange(4)
    for ax, (stage, title) in zip(axes, stages):
        for i, name in enumerate(names):
            m = models[name]; scores = m['development_cv'] if stage=='development_cv' else m['temporal_checks'][stage]
            ax.bar(x+(i-(len(names)-1)/2)*width, [100*scores['domain_gain'][k] for k in DOMAIN_NAMES],
                   width, color=COLORS[i], label=legends[name])
        ax.axhline(0, color='black', lw=.6)
        ax.set_xticks(x, DOMAINS, rotation=30, ha='right'); ax.set_title(title)
        ax.set_xlabel('Response domain')
    axes[0].set_ylabel('Within-month predictive gain (%)')
    axes[-1].legend(frameon=False, loc='upper right')
    save(fig, 'temporal_domains')

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.1))
    for i, m in enumerate([old, chosen, best]):
        if m['name'] in [x['name'] for x in [old, chosen, best]][:i]:
            continue
        support = d['old_six_grid_support'] if m['name']==old['name'] else m['support']
        values = support['all_months']['core_projection']
        axes[0].plot([192,256,384,512], [100*values[str(b)]['mean_projected_mass_ess_ge_10'] for b in [192,256,384,512]],
                     marker=['o','s','^'][i], ls=['--','-','-.'][i], color=COLORS[i], label=legends.get(m['name'],'Best CV'))
    axes[0].set_xlabel('Planning Core budget (persons/month)')
    axes[0].set_ylabel('Population mass with projected cell ESS ≥ 10 (%)')
    axes[0].set_ylim(0, 103); axes[0].set_title('Support projection; no actual draw or power guarantee')
    axes[0].legend(frameon=False)
    inertia = np.array(a['mca']['raw_inertia_fraction'])[:12]*100
    axes[1].plot(np.arange(1,len(inertia)+1), inertia, color=COLORS[2], marker='o')
    axes[1].set_xlabel('MCA component number'); axes[1].set_ylabel('Raw demographic inertia (%)')
    axes[1].set_title('MCA scree: describes X, not survey-response accuracy')
    save(fig, 'support_and_mca')

    def score(m, stage='development_cv'):
        return m[stage]['composite_gain']*100 if stage=='development_cv' else m['temporal_checks'][stage]['composite_gain']*100
    gvif = a['within_month_block_gvif']
    pairs = sorted([(matrix[i,j], keys[i], keys[j]) for i in range(len(keys)) for j in range(i)], reverse=True)[:4]
    pair_text = '；'.join(f'{LABELS[i]}—{LABELS[j]} {v:.3f}' for v,i,j in pairs)
    rows = ''.join(f'<tr><td>{escape(cn(models[n]["fields"]))}</td><td>{models[n]["cartesian_cells"] or "不交叉"}</td><td>{score(models[n]):.2f}%</td><td>{score(models[n],"2023_2024"):.2f}%</td><td>{score(models[n],"2025_01_10"):.2f}%</td></tr>' for n in names)
    g_rows = ''.join(f'<tr><td>{LABELS[k]}</td><td>{gvif[k]["df"]}</td><td>{gvif[k]["adjusted_gvif"]:.3f}</td></tr>' for k in keys)
    coverage = d['coverage']; ex = coverage['temporal_exclusions']
    image = lambda name, caption: f'<figure><img src="figures/{name}.svg" alt="{escape(caption)}"><figcaption>{caption}</figcaption></figure>'
    support = chosen['support']['all_months']
    title = cn(chosen['fields'])
    extra = ''
    if joint is not None:
        j = json.loads((Path(joint)/'summary.json').read_text())
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
        xx = np.arange(3)
        for i, m in enumerate([old, chosen, best]):
            gain = [j['periods'][p]['core256_tau8'][m['name']]['composite_gain']*100 for p in ['development','2023_2024','2025_01_10']]
            w1 = [j['periods'][p]['core256_tau8'][m['name']]['w1_pp'] for p in ['development','2023_2024','2025_01_10']]
            axes[0].bar(xx+(i-1)*.24,gain,.24,color=COLORS[i],label=legends[m['name']])
            axes[1].plot(xx,w1,color=COLORS[i],marker=['o','s','^'][i],ls=['--','-','-.'][i],label=legends[m['name']])
        for ax in axes:
            ax.set_xticks(xx,['2019–2022','2023–2024','2025']);ax.set_xlabel('Calendar period')
        axes[0].set_ylabel('Composite held-out gain over Core mean (%)');axes[0].legend(frameon=False)
        axes[1].set_ylabel('Held-out cross-person W1 (percentage points)')
        axes[0].set_title('Joint-cell check: same 256 human Core, fixed tau=8')
        axes[1].set_title('Distribution gain remains small and mixed')
        save(fig,'joint_holdout')
        extra += '<h2>补充：不是只看加总式回归</h2><p>对预先选定的四套网格，按受访者留出，用相同256／512名真人Core、两种抽样种子比较联合格经验分布。Core只从其他折抽取；收缩强度固定8，另报0／24敏感性。保留整份答卷供体原子，没有将平均Q9发给所有人。</p>'
        extra += image('joint_holdout','这是使用当月其他真人答卷的统计可行性参考，不能当作LLM效果或严格事前预测。推荐12格的综合结构分数较旧六格好，但跨人W1改善很小、部分时期反向。未收缩的36／54格出现明显过拟合，说明四维细分需要层级汇聚。')
        extra += '<p>以256名Core、强度8为例，12格依赖父池的平均质量约28%，收入四维36格约49%；因此四维可保留作条件层，但不宜把每个小格视为有充分独立证据。此诊断没有确定生产扩展的先验或强度。</p>'
    if sensitivity is not None:
        v = json.loads((Path(sensitivity)/'summary.json').read_text())
        qr = v['q8_guardrail']; qrows = ''
        for m in [old,chosen,best]:
            raw=qr['untrimmed'][m['name']];cap=qr['cap_100_sensitivity'][m['name']]
            qrows += f'<tr><td>{escape(cn(m["fields"]))}</td><td>{raw["development_cv_within_r2"]*100:.3f}%</td><td>{cap["development_cv_within_r2"]*100:.3f}%</td><td>{cap["2025_01_10_within_r2"]*100:.3f}%</td></tr>'
        extra += '<h2>敏感性：推荐不是唯一正确的分法</h2><p>将框架支持门槛从90%提高到95%，开发推荐仍是学历×数理×性别；放宽到85%则转为数理×收入×年龄×性别四维。因此12格是当前支持与复杂度约定下的候选，不是统计证明的唯一最优。几个三维方案处于一个标准误范围内。</p>'
        extra += '<details><summary>展开：Q8独立保护检查</summary><div class="scroll"><table><thead><tr><th>网格</th><th>开发Q8原值月内R²</th><th>开发Q8截至±100敏感性</th><th>2025截至±100敏感性</th></tr></thead><tbody>'+qrows+'</tbody></table></div><p>原始Q8含最高10000的极端回答，原值仍为主、截尾只作敏感性。这里不是全国Q8中位数MAE；未据Q8重新选择推荐网格。</p></details>'
    html = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SCE人口网格维度选择 · 2026-10-23</title><style>
body{{margin:0;background:#faf8f3;color:#242323;font:18px/1.75 "Times New Roman","Kaiti SC","STKaiti","KaiTi",serif}}
main{{max-width:1120px;margin:40px auto;padding:0 24px 70px}}h1{{font-size:32px;line-height:1.4}}h2{{font-size:25px;margin-top:42px}}h3{{font-size:21px}}a{{color:#7437aa}}.lede{{border-left:5px solid #c76800;padding:12px 22px;background:#f5eee3}}
.meta,figcaption{{color:#666;font-size:15px}}figure{{margin:24px 0}}img{{width:100%;height:auto;background:white}}table{{border-collapse:collapse;width:100%;font-size:16px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #d5d1c8}}th{{background:#eeebe4}}.scroll{{overflow-x:auto}}details{{margin-top:22px}}.stats{{display:flex;gap:34px;flex-wrap:wrap;margin:24px 0}}.stat b{{display:block;font-size:28px}}code{{font-size:14px;overflow-wrap:anywhere}}li{{margin:7px 0}}
</style><main><p class="meta">水上挽月 · SCE · 人口分层与Core＋Normal方法准备 · 零新增API</p>
<h1>SCE人口网格：维度选择与验证</h1>
<div class="lede"><b>开发样本推荐：{escape(title)}，{chosen['cartesian_cells']}个理论格。</b><br>
这是带人口覆盖约束、按受访者分组验证后的候选建议。不是因果结论，不等于该网格已经改善LLM模拟，也没有改变任何默认配置或启动全量运行。</div>
<p><b>具体划分：</b>学历为高中及以下／部分大学教育／大学及以上；数理为官方High／Low；性别为公开问卷Male／Female。三项交叉为12格，任何缺失另入未知池。性别在此是观察性分组信息，不预设性别导致某种回答。若采用四维分类，收入三档可作为需要部分汇聚的第四层，形成36个细格；暂不要求每个细格独立估计。</p>
<div class="stats"><div class="stat"><b>82个月</b>2019-01—2025-10完整框架</div><div class="stat"><b>{coverage['all_frame_person_months']:,}</b>完整框架人月</div><div class="stat"><b>{coverage['model_common_person_months']:,}</b>统一建模支持人月</div><div class="stat"><b>126套</b>三维56套＋四维70套</div></div>
<h2>一、怎样选择，避免只凭直觉</h2><ol>
<li><b>可解释与可得：</b>比较学历、数理、收入、年龄、就业、性别、住房、地区八类特征。当前财务感受和既有信念作为状态机制另列，不用本期通胀答案定义人口类别。</li>
<li><b>冗余与条件增量分开：</b>用调查加权Cramer V衡量分类关联，用整块GVIF诊断共线性，再逐项移除变量检查其独有预测信息。相关较高不自动删除。</li>
<li><b>四个目标同看：</b>个人Q9均值、个人密度IQR、零通缩填法，以及跨人Q9均值的CDF结构。四个领域等权，避免某个量纲主导选择。</li>
<li><b>先开发、后检查：</b>2019—2022按受访者四折；2023—2024和2025-01—10剔除开发期出现过的人，分别作时间检查。所有时期此前已有研究，不能称全新盲测。</li>
<li><b>控制复杂度：</b>先要求平均至少90%人口质量落在框架N≥20且权重ESS≥10的格子，再在距最佳表现一个区块自助标准误内，优先选择理论格数更少的方案。阈值是透明分析约定，不是功效保证。</li></ol>
<p><b>评分的含义：</b>这里先去掉每月公共水平，检验不同人之间的回答结构能解释多少。正值代表优于“月内所有人相同”的参照；不是全国中位数MAE，更不能与之前0.2pp等模拟成绩相比较。</p>
<p>该分析选择的是稳定人口维度，未纳入本人历史来竞争维度名额；既有信念仍作为单独状态。条件增量和自助区间依赖所用加总模型及已筛选数据，不能按因果系数解释，开发区间也没有消除多候选搜索的乐观偏差。</p>
{image('candidate_frontier','开发期同支持比较。纵轴为四领域平均的月内损失改善，越高越好；横轴为理论格数。来源：已有SCE缓存；2019—2022。')}
<h2>二、推荐网格与既有六格相比</h2><div class="scroll"><table><thead><tr><th>维度</th><th>理论格数</th><th>开发分组CV</th><th>2023—2024</th><th>2025-01—10</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>表内为四领域综合月内预测改善百分比，越高越好，负值表示不如共同月度水平参照。开发推荐已在读取时间检查分数前保存；不按后两列重新挑赢家。</p>
{image('temporal_domains','四领域分开报告，避免综合分数掩盖预期水平或概率表达的退步。时间检查剔除与开发期重复的受访者。')}
<h2>三、哪些指标重复，哪些仍提供额外信息？</h2><p>开发期关联较强的几对：{pair_text}。这只是关联，不能解读为因果或可以直接互相替代。</p>
{image('association','每月调查权重归一化后合并计算的Cramer V；0表示无该种列联关联，1表示完全关联。不是连续变量Pearson相关。')}
{image('conditional_information','逐项移除后重新拟合，其他七类变量仍在。纵轴为相对无人口信息参照的标准化损失增量，百分点，不是通胀率百分点；负值表示移除反而略好。区块自助区间在聚合JSON中。')}
<details><summary>展开：整块共线性诊断</summary><table><thead><tr><th>变量</th><th>虚拟变量数</th><th>GVIF^(1/(2df))</th></tr></thead><tbody>{g_rows}</tbody></table><p>它衡量参数估计的共线性膨胀，不能替代预测检验。多分类变量整体处理，避免把某一类别的VIF当作整项指标的重要性。</p></details>
<h2>四、细分后有没有足够的Core支持？</h2><p>推荐网格在82月完整框架中，平均{support['mean_frame_supported_mass']*100:.1f}%的人口质量落在N≥20、ESS≥10的格子；新人子池中，平均{support['mean_newcomer_mass_in_cells_n_ge_10']*100:.1f}%的质量落在至少10名新人的格子。新人分池仍需要层级汇聚，不能套用全框架人数。</p>
{image('support_and_mca','左：按相同预算、每非空格最低3人的规划分配估算Core支持；不是实际抽样或功效分析。右：MCA原始惯量碎石图，只描述人口特征的结构，不能称它解释了相同比例的问卷差异。')}
<h2>五、怎样进入贝叶斯扩展</h2><ul>
<li>所选维度定义可解释的基础格；每个人完整画像仍保留其他变量，未入硬格不等于删除该信息。</li>
<li>新人／回访者单独条件化；本人历史、近期供体和信息截止规则仍沿各自契约，不给新人冒充真实本人上期。</li>
<li>格内对完整Q8＋Q9联合答卷建模并允许部分汇聚，不能把每格平均概率复制给全部Normal。</li>
<li>同月真人联合格留出检查已完成；正式接入仍需LLM Core回答扩展损失、权重与稀疏回退。统计维度有效不保证LLM已经按这些特征生成差异。</li></ul>
{extra}
<details open><summary>边界与复算</summary><p>官方提供的Q9均值／个人IQR用于这次维度分析，未调用我们近似密度计分器、未重新拟合Q9。原始回答和ID仅留ignored outputs，不进入公开报告或模型输入。</p>
<p>共同支持人月{coverage['model_common_person_months']:,}；开发{coverage['development_rows']:,}；2023—2024时间检查{ex['2023_2024']['rows_after']:,}（因身份重叠排除{ex['2023_2024']['excluded_rows']:,}）；2025检查{ex['2025_01_10']['rows_after']:,}。缺失造成的支持变化、模型依赖、相关特征共享信息、候选搜索与已见时期都限制结论。</p>
<p>复算：<code>python scripts/analyze_sce_grid_dimensions.py --out outputs/&lt;新目录&gt;</code><br>报告：<code>python scripts/report_sce_grid_dimensions.py --source outputs/&lt;分析目录&gt; --out docs/workstreams/20261021_fullperiod/&lt;新报告目录&gt;</code></p>
<p>聚合结果：<code>{escape(str(source/'summary.json'))}</code></p></details>
<h2>方法来源</h2><ul><li><a href="https://www150.statcan.gc.ca/n1/pub/71-526-x/2017001/chapt2-eng.htm">Statistics Canada：分层须结合调查目标、同质性与样本约束</a></li><li><a href="https://doi.org/10.1080/01621459.1992.10475190">Fox与Monette（1992）：整块共线性诊断</a></li><li><a href="https://arxiv.org/abs/1604.04173">Lei等：移除协变量后的预测信息比较</a></li><li><a href="https://scikit-learn.org/stable/modules/cross_validation.html#group-k-fold">按受访者分组验证</a></li></ul>
</main></html>'''
    (out/'index.html').write_text(html)
    return out/'index.html'
