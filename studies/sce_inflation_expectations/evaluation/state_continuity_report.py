"""Render the project's existing report style from completed cached statistics."""
from collections import defaultdict
from html import escape
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
import numpy as np

from . import cognition as shared
from .metrics import quantile
from ..experiments.frozen_batch import ROOT, read_json, dump

LABEL = {'observed_history': '每月真人历史', 'simulated_history': '自身模拟历史',
         'monthly_past_reference': '保留可用旧信念', 'human': '真人本期'}
COLOR = {'observed_history': '#777777', 'simulated_history': '#c76800',
         'monthly_past_reference': '#7437aa', 'human': '#111111'}
ARMS = ['observed_history', 'simulated_history']


def f(v): return '不可计算' if v is None else f'{v:.3f}'


def balanced_note(source, dest):
    path=Path(source)/'balanced_valid_cohort_sensitivity.json'
    if not path.exists():return ''
    data=read_json(path);cells=data['arms']['simulated_history']['cells']
    values=[float(np.mean([c['cross_person_iqr_pp'] for c in cells if c['month']==m])) for m in (202505,202506,202507)]
    (Path(dest)/path.name).write_bytes(path.read_bytes())
    return ('<p class="note">另限制为三个月Q9始终可计算的同一批'+str(data['unique_people'])+'人，'
            '自主链IQR仍为'+'→'.join(f'{v:.3f}' for v in values)+'pp。因而人际差异收缩不能仅用轮换或无效答案解释；'
            '这是事后支持敏感性，不是新的预登记主指标。<a href="'+path.name+'">完整敏感性结果</a>。</p>')


def publish(source, dest):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if dest.exists(): raise ValueError('Fresh report output required')
    s = read_json(source / 'summary.json')
    if s['status'] != 'completed' or not s['receipt']['actual_model_results']:
        raise ValueError('Completed real model results required')
    months = s['protocol']['months']; ints = list(map(int, months)); reps = [1, 2]
    primary = s['fixed_roster_operational']; metric = primary['design_weighted_primary']
    cases = read_json(source / 'operational_cases_private.json')
    dest.mkdir(parents=True); (dest / 'figures').mkdir()
    font = ROOT / 'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists(): font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC', 'STKaiti'], 'font.size': 11,
                         'axes.unicode_minus': False, 'axes.spines.top': False, 'axes.spines.right': False})
    dates = [m[:4] + '-' + m[-2:] for m in months]; x = np.arange(len(months))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    for ax, key, title in zip(axes, ['q9_center_mae_pp', 'cross_section_w1_pp', 'cross_person_iqr_pp'],
                             ['人群中位数误差', '跨人分布距离', '跨人四分位距']):
        vals = [metric[a]['q9']['aggregate_equal_month_repeat_cells'][key] for a in ARMS]
        bars = ax.bar([0, 1], vals, color=[COLOR[a] for a in ARMS]); ax.bar_label(bars, fmt='%.3f', padding=5)
        ax.set_xticks([0, 1], [LABEL[a] for a in ARMS]); ax.set_ylabel('百分点'); ax.set_xlabel('历史信念来源')
        ax.set_title(title); ax.margins(y=.25); ax.grid(axis='y', alpha=.12)
        if key == 'cross_person_iqr_pp':
            human = metric[ARMS[0]]['q9']['aggregate_equal_month_repeat_cells']['real_cross_person_iqr_pp']
            ax.axhline(human, color='black', linestyle='--', label=f'真人 {human:.3f}'); ax.legend()
    fig.suptitle('2025年5—7月：月内采用设计权重，再对三月与两遍等权')
    fig.tight_layout(); fig.savefig(dest / 'figures/overall.png', dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, key, title in zip(axes, ['q9_center_mae_pp', 'cross_section_w1_pp'], ['逐月人群中位数误差', '逐月跨人分布距离']):
        for arm, marker, line in [('observed_history', 's', '--'), ('simulated_history', 'o', '-')]:
            values = [s['by_month'][m]['design_weighted_primary'][arm]['q9']['aggregate_equal_month_repeat_cells'][key] for m in months]
            ax.plot(x, values, marker=marker, linestyle=line, color=COLOR[arm], label=LABEL[arm], linewidth=2)
            for xx, v in zip(x, values):
                if xx == 0 and arm == 'observed_history': continue
                ax.annotate(f'{v:.3f}', (xx, v), xytext=(3, 9 if arm == 'observed_history' else -16), textcoords='offset points', fontsize=9)
        ax.set_xticks(x, dates); ax.set_xlabel('目标调查月（连续三个月）'); ax.set_ylabel('误差（百分点，越低越好）')
        ax.set_title(title); ax.legend(); ax.grid(axis='y', alpha=.12); ax.margins(y=.2)
    fig.tight_layout(); fig.savefig(dest / 'figures/monthly.png', dpi=170); plt.close(fig)
    # All lines below use the SAME baseline-valid support, rather than mixing
    # medians from the full cohort with a smaller persistence-baseline cohort.
    support = shared._common_person_months(cases, [*ARMS, 'monthly_past_reference'], reps, 'q9')
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6)); moments = defaultdict(list)
    for month in ints:
        medians = defaultdict(list); iqrs = defaultdict(list)
        for rep in reps:
            rows = shared._cell_rows(cases, month, rep, support); w = [r['survey_weight'] for r in rows]
            if not rows: continue
            values = {'human': [r['real']['q9_mean'] for r in rows]}
            values.update({a: [r['arms'][a]['mean'] for r in rows] for a in [*ARMS, 'monthly_past_reference']})
            for a, v in values.items():
                medians[a].append(quantile(v, w, .5)); iqrs[a].append(quantile(v, w, .75) - quantile(v, w, .25))
        for a in [*ARMS, 'monthly_past_reference', 'human']:
            moments[a].append(dict(month=month, center=float(np.mean(medians[a])) if medians[a] else None,
                                   iqr=float(np.mean(iqrs[a])) if iqrs[a] else None))
    for a, marker, line in [('observed_history', 's', '--'), ('simulated_history', 'o', '-'),
                             ('monthly_past_reference', '^', '-.'), ('human', '*', ':')]:
        for ax, key in zip(axes, ['center', 'iqr']):
            ax.plot(x, [r[key] for r in moments[a]], marker=marker, linestyle=line, color=COLOR[a], label=LABEL[a], linewidth=2)
    for ax, title, unit in zip(axes, ['旧信念、模型与真人的总体水平', '人际差异是否被保留？'], ['人群中位数（%）', '跨人IQR（百分点）']):
        ax.set_xticks(x, dates); ax.set_xlabel('目标调查月'); ax.set_ylabel(unit); ax.set_title(title)
        ax.grid(axis='y', alpha=.12); ax.legend(fontsize=9, ncol=2)
    fig.tight_layout(); fig.savefig(dest / 'figures/levels_and_width.png', dpi=170); plt.close(fig)
    # A fixed selected cohort checks whether rotation alone explains narrowing.
    cohort=s['groups']['continuous_three_months']['design_weighted_primary']
    fig,axes=plt.subplots(1,2,figsize=(13,4.6));cohort_series={}
    for arm,marker,line in [('observed_history','s','--'),('simulated_history','o','-')]:
        cells=cohort[arm]['q9']['cells']
        vals=[float(np.mean([c['cross_person_iqr_pp'] for c in cells if c['month']==m])) for m in ints]
        cohort_series[arm]=vals
        axes[0].plot(x,vals,marker=marker,linestyle=line,color=COLOR[arm],label=LABEL[arm],linewidth=2)
    cells=cohort[ARMS[0]]['q9']['cells']
    human=[float(np.mean([c['real_cross_person_iqr_pp'] for c in cells if c['month']==m])) for m in ints]
    axes[0].plot(x,human,'k*:',label='同人群真人',linewidth=2)
    axes[0].set_ylabel('跨人IQR（百分点）');axes[0].set_title('连续三月入选者：个体差异仍收缩')
    entry_support=shared._common_person_months(cases,ARMS,reps,'q9');entry_numbers=[]
    for group,label,color,marker in [('human','真人新入组者','#111111','*'),('observed_history','模型新入组者','#c76800','o')]:
        vals=[]
        for m in ints:
            cellvals=[];n=0
            for rep in reps:
                rows=[r for r in cases if r['month']==m and r['repeat']==rep and r['survey_entry_status']=='entrant'
                      and (r['month'],r['userid']) in entry_support]
                n=len(rows);w=[r['survey_weight'] for r in rows]
                numbers=[r['real']['q9_mean'] if group=='human' else r['arms'][group]['mean'] for r in rows]
                if rows:cellvals.append(quantile(numbers,w,.5))
            vals.append(float(np.mean(cellvals)) if cellvals else None)
            if group=='human':entry_numbers.append(n)
        axes[1].plot(x,vals,color=color,marker=marker,label=label,linewidth=2)
    axes[1].set_ylabel('新入组者的群体中位数（%）');axes[1].set_title('新入组者：部分月份的水平未被重建')
    axes[0].set_xticks(x,dates);axes[1].set_xticks(x,[f'{d}\nN={n}' for d,n in zip(dates,entry_numbers)])
    for ax in axes:ax.set_xlabel('目标调查月');ax.grid(axis='y',alpha=.12);ax.legend(fontsize=9)
    fig.tight_layout();fig.savefig(dest/'figures/cohort_and_entrants.png',dpi=170);plt.close(fig)
    dump(dest / 'plot_series.json', dict(baseline_shared_person_months=len(support), series=dict(moments)))
    return refresh_text(source, dest)


def refresh_text(source, dest):
    """Revise prose in an existing report; keep figures and scored data unchanged."""
    source, dest = Path(source).resolve(), Path(dest).resolve()
    s = read_json(source / 'summary.json')
    if s['status'] != 'completed' or not s['receipt']['actual_model_results']:
        raise ValueError('Completed real model results required')
    if not (dest / 'figures/overall.png').exists():
        raise ValueError('Existing report figures required for a text-only refresh')
    primary = s['fixed_roster_operational']; metric = primary['design_weighted_primary']
    a, b = [metric[k]['q9']['aggregate_equal_month_repeat_cells'] for k in ARMS]
    verdict = f'改用自身模拟历史后，人群中位数MAE变化 {b["q9_center_mae_pp"]-a["q9_center_mae_pp"]:+.3f} pp，跨人W1变化 {b["cross_section_w1_pp"]-a["cross_section_w1_pp"]:+.3f} pp。负值表示更接近真人。'
    headers = ['中心MAE', '中心RMSE', '个人MAE', '跨人W1', '变化W1', '跨人IQR']
    def stats_row(arm, item):
        q = item['q9']['aggregate_equal_month_repeat_cells']; error = item['q9'].get('center_headline_errors')
        vals = [q['q9_center_mae_pp'], error['rmse_pp'] if error else None,
                q['individual_density_mean_mae_pp'], q['cross_section_w1_pp'], q['delta_w1_pp'], q['cross_person_iqr_pp']]
        return '<tr><td>' + LABEL[arm] + '</td>' + ''.join('<td>' + f(v) + '</td>' for v in vals) + '</tr>'
    main_rows = ''.join(stats_row(arm, metric[arm]) for arm in ARMS)
    local=primary['genuine_previous_only_support']
    scope_rows=''
    for title,n,items in [('全体本期可评价者',primary['q9_person_months'],metric),
                          ('真实相邻上月记录者',local['q9_person_months'],local['arms'])]:
        scope_rows+='<tr><td>'+title+'</td><td>'+str(n)+'</td>'+''.join('<td>'+f(items[arm]['q9']['aggregate_equal_month_repeat_cells']['cross_section_w1_pp'])+'</td>' for arm in ARMS)+'</tr>'
    reference = primary['monthly_past_reference_support']; baseline_rows = ''
    for arm, item in reference['arms'].items():
        q = item['q9']['aggregate_equal_month_repeat_cells']
        baseline_rows += '<tr><td>' + LABEL[arm] + '</td>' + ''.join('<td>' + f(q[k]) + '</td>' for k in ['q9_center_mae_pp', 'cross_section_w1_pp', 'delta_w1_pp']) + '</tr>'
    groups = []
    for key, name in [('continuous_three_months', '三个月均入选的71人')]:
        g = s['groups'][key]
        groups.append('<tr><td>' + name + '</td><td>' + str(g['q9_person_months']) + '</td>' + ''.join('<td>' +
            f(g['design_weighted_primary'][arm]['q9']['aggregate_equal_month_repeat_cells']['cross_section_w1_pp']) + '</td>' for arm in ARMS) + '</tr>')
    for value, name in [('entrant', '首次参加SCE'), ('returning', '相邻月回访'), ('gap_return', '间断回访')]:
        if value not in s['groups']['survey_entry_status']: continue
        g = s['groups']['survey_entry_status'][value]
        groups.append('<tr><td>' + name + '</td><td>' + str(g['q9_person_months']) + '</td>' + ''.join('<td>' +
            f(g['design_weighted_primary'][arm]['q9']['aggregate_equal_month_repeat_cells']['cross_section_w1_pp']) + '</td>' for arm in ARMS) + '</tr>')
    fee = s['receipt']; actual = s['paired_actual_outputs']; q8rows = ''
    balanced_html=balanced_note(source,dest)
    for arm in ARMS:
        q = metric[arm]['q8']['aggregate_equal_month_repeat_cells']
        q8rows += '<tr><td>' + LABEL[arm] + '</td>' + ''.join('<td>' + f(q[k]) + '</td>' for k in ['q8_center_mae_pp', 'q8_person_mae_pp', 'q8_cross_section_w1_pp']) + '</tr>'
    old = ROOT / 'docs/workstreams/20261021_fullperiod/news_matching_results/index.html'
    raw = old.read_text(); css = raw.split('<style>', 1)[1].split('</style>', 1)[0]
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>个人信念的三月接续验证</title><style>{css}</style><main>
<nav><a href="../state_continuity_run_card_20261022.md">实验配置与边界</a><a href="../news_matching_results/index.html">此前新闻机制验证</a><a href="summary.json">完整聚合统计</a></nav>
<h1>个人信念的跨月保持：三个月接续实验</h1>
<p class="lead"><strong>研究问题：不再每月补充真人最新的历史回答，模型还能持续模拟同一个居民的通胀预期吗？</strong><br>结果显示，总体中位数仍可接近真人，但个人之间的差异与排序逐渐丢失。两者需要分别评价。</p>
<h2>1. 这项实验研究项目的哪个环节？</h2>
<p>此前大多数实验每月向模型提供该居民真实的上期回答。这给了模型一个与本人有关的信念起点，但尚未检验：模型能否把自己生成的信念保留到下个月，并继续合理更新。</p>
<p>本轮主要检查<strong>个人信念的保存、传递与更新</strong>。在P/E/B框架中，它连接P中的动态信念与模型的回答机制f：即使人口和环境匹配已经完成，模型每次回答后仍可能丢失一部分个人差异。这里没有比较新的新闻或价格机制。</p>
<p class="note">三个“调查月”与“未来12个月预期”是两回事：模型分别回答2025年5、6、7月的SCE问卷，每次都预测从当时起未来12个月的通胀。我们重建的是居民回答，不是这三个月的实际CPI。</p>
<h2>2. 实验配置与对照是什么？</h2>
<ul><li><strong>人群与月份：</strong>2025年5/6/7月各96人，共120名不同受访者；71人三个月均入选。</li>
<li><strong>真人历史参照组（灰）：</strong>每月重新读取此前可用的本人真实Q8/Q9，以及更早历史的均值和次数摘要。历史缺失按已登记规则处理。</li>
<li><strong>自身历史递推组（橙）：</strong>首次进入本次模拟时与参照组使用同一起点，以后只接自己上次模拟的Q8/Q9及累计历史，不用新取得的真人回答刷新；间断后回来也保留原有模拟状态。</li>
<li><strong>其余保持相同：</strong>同一人的当月人口特征、食品价格、采购角色、政策、随机3/8/20篇新闻和问卷相同。均用DeepSeek V3.2、固定SiliconFlow路由、温度0.5，直接填写Q8和Q9；每组生成两遍。</li></ul>
<p>起点完全相同的回答共享请求，后续两组再分别接续。因此5月两组相同是设计结果，真正的接续比较从6月开始。变化的不仅是上期数字来源，也包括随之更新的历史摘要及信息先后标签；本轮检验的是整套接续方式。</p>
<p class="note">首次进入本次模拟不等于首次参加SCE。真实新入组者没有本人上期回答，按严格更早匿名供体分配合成起点，明确标注。没有向模型发送本人本期通胀答案。</p>
<h2>3. 实际得到多少数据？</h2>
<p>96人×3月形成288个“个人月”，不是288个不同的人。两组各两遍共1152个回答位置，共同起点复用后实际发送912次请求，其中5次连接失败。失败按预先规则保留该组输入状态，并另报真实可用回答的结果。</p>
<p>真人Q9可评价281个人月，Q8可评价288个人月；两组、两遍都有实际可用Q9回答的共同人群为275个人月。主结果在固定有效人群上比较，并使用调查权重/抽样入选概率；每月先计算指标，再对三个月与两遍等权平均。重复生成增加的是模型随机性的观察，不增加真人样本量。</p>
<h2>4. 重点指标表现如何，实际意味着什么？</h2>
<p><strong>{verdict}</strong> 这是本次抽样人群的结果，不是全国官方SCE指标的误差。</p>
<figure><img src="figures/overall.png" alt="三个月两组的中心误差、分布W1和跨人IQR"><figcaption>来源：本批完成的模型原答与独立真人评价，2025-05至07；设计权重，三月/两遍等权。IQR需接近真人，不能单看增大。</figcaption></figure>
<div class="scroll"><table><tr><th>历史来源</th>{''.join('<th>'+h+'</th>' for h in headers)}</tr>{main_rows}</table></div>
<p class="note">单位pp；Q9先由冻结方法从十档概率得到每个人的密度均值，再取跨人中位数。RMSE对各月/遍的中心误差平方后平均再开方。主口径包含明确标记的失败输入状态后备，Q9支持{primary['q9_person_months']}个人月；实际输出共同支持{actual['q9_person_months']}个人月，不能混用两种口径的最低值。</p>
<ul><li><strong>总体水平：</strong>中心MAE约0.421→0.404pp，RMSE约0.515→0.509pp。幅度很小，第二遍MAE并未改善，尚不能确认稳定收益。</li>
<li><strong>人与人之间的分布：</strong>跨人W1约1.600→2.061pp，两个生成重复均变差。这表示整个人群的预期分布更偏离真人，不能由中位数接近掩盖。</li>
<li><strong>个人差异与对应关系：</strong>跨人IQR约3.219→2.556pp，真人约5.114pp；个人排序与真人的相关性约0.527→0.418。模型不仅总体偏集中，对“谁应当预期更高”的区分也变弱。</li>
<li><strong>单个人是否准确：</strong>个人预期均值的MAE约3.188→3.423pp。总体中位数误差小，并不表示大部分个体都预测准确。</li></ul>
<p class="note">这里的跨人W1与IQR比较的是“不同人的预期中心”。它们不是同一个人在Q9十档中表达的不确定性；不能据此说每个人的十档概率都出现了相同程度的退步。Q8独立结果见下方详情。</p>
<h3>总体W1与真实回访者局部W1</h3>
<div class="scroll"><table><tr><th>评价范围</th><th>个人月</th><th>真人历史组W1</th><th>自身模拟历史组W1</th></tr>{scope_rows}</table></div>
<p>总体W1只需要本期真人与模型回答，不需要上月值，反映全体重建。局部W1限定在真实相邻上月与本期Q9均可评价的人，帮助分开观察有本人历史时的表现。预期变化W1进一步需要真实上月记录，不能用合成上期冒充。</p>
<p class="note">单位pp，均读取已完成缓存，无新增模拟。只能在每行的同人群内比较；总体W1不是分组W1的简单加权平均，不能用两行的差额直接计算初始化的“贡献”。</p>
<h2>5. 进一步分析：差距发生在哪里？</h2><h3>5.1 总体误差没有爆炸，但相对分布差距扩大</h3>
<figure><img src="figures/monthly.png" alt="两组逐月中位数MAE及W1"><figcaption>各点平均两遍各自的月误差；每月人群存在正常轮换，连续71人的独立分组也一并报告。</figcaption></figure>
<figure><img src="figures/levels_and_width.png" alt="同一基线支持下的真人、模型及旧信念中位数与人际IQR"><figcaption>这张图统一限制在可计算旧信念的{reference['q9_person_months']}个人月。图中数值不与上方完整主口径混称；各月先算加权统计，再平均两遍。</figcaption></figure>
<p>这里的“累积”主要体现在<strong>相对于每月补真人历史的分布差距</strong>：W1差从5月共同起点的0，增加到6月约0.539、7月约0.843pp。两个组的W1绝对值其实都下降，不能说自主链每个月的所有误差都变大。</p>
<details><summary>在同一可用旧信念人群上比较基线</summary><div class="scroll"><table><tr><th>配置</th><th>中心MAE</th><th>跨人W1</th><th>变化W1</th></tr>{baseline_rows}</table></div><p class="note">旧信念基线含明确的合成起点，不能全部称为“照抄本人上期”。只有真实相邻月记录的人，另有genuine_previous_only_support对照。变化W1只在有真实相邻上期Q9时计算。</p></details>
<h3>5.2 固定同一批人检查，避免把轮换误当机制</h3>
<div class="scroll"><table><tr><th>分组</th><th>可评价个人月</th><th>真人历史组W1</th><th>模拟历史组W1</th></tr>{''.join(groups)}</table></div><p class="note">分组只作描述，不解释为因果。新入组者在首次初始化时两组起点相同，本来就不应凭这个对照宣称初始化机制更好。部分组只覆盖部分月份，完整月/遍覆盖与缺失见JSON。</p>
<figure><img src="figures/cohort_and_entrants.png" alt="连续三月人群的IQR与各月新入组者的模型和真人中位数"><figcaption>左图保留连续三月均入选的71人，按各月各题有效性评价，共207个人月；不是每月完全相同的有效答案集合。右图新入组者仅16/13/5人，7月稀疏，不能据此认定新入组者总是预期更高。</figcaption></figure>
{balanced_html}
<p><strong>收缩本身不是错误的充分证据。</strong>真人之间的分歧也会随月变化。这里需要关注的是：在同一个月，与真人及真人历史参照组比较，自主链的W1和个人排序同时退步；固定人群的检查也保留了这个现象。</p>
<h3>5.3 新入组者暴露了信息不足，也改变了总体评价</h3>
<p>在相邻月回访者子样本中，每月补真人历史组的中心MAE约0.094pp；纳入新入组与间断回访者后，完整样本为0.421pp。这说明原先回访者的好成绩不能直接推广到全体居民。两个不同人群的误差之差不是可相加的“贡献率”，也不能据此把全部偏差归因于新入组。</p>
<p>5月新入组者的真人中位数约10%、模型约3.58%；6月两者接近；7月又有差距，但当月仅5人。这是需要继续检查的群体差距，不能据此认定新入组者总是预期更高，也不能证明供体初始化算法就是唯一原因——本轮没有对照不同的初始化方法。</p>
<h2>6. 应当怎样解释，哪些结论还不能下？</h2>
<p><strong>可支持的判断：</strong>当前系统每月获得真实历史补充时，比完全依靠自身输出更能维持与真人接近的微观结构。这定位了信念接续环节的不足，并不表示此前人口与环境建设没有价值。</p>
<p><strong>尚待验证的解释：</strong>模型可能每轮都向公共信息暗示的共同水平收缩，而个人经历、记忆与新冲击未被充分补回。反复输入自身回答会重复这种收缩。但本轮同时替换了个人历史及其摘要，尚未识别真实居民的心理更新系数，也不能区分信息缺失、历史表达和模型处理方式各自的因果贡献。</p>
<ul><li><strong>对照的含义：</strong>这是一项模拟系统内部的输入替换实验，不是对真人的随机干预。“每月真人历史”是有额外个人信息的参照，不能作为真实未来预测默认可得的资料。</li>
<li><strong>样本与时间：</strong>只有三个连续月、120人；新入组者仅16/13/5人。两遍不是六个独立月份，不能据小幅平均差异宣称长期稳定改善。</li>
<li><strong>新人的评价目标：</strong>没有本人历史时，合成先验不可能等于对该人真实信念的直接测量。应重点检验同类新人的分布和总体水平，不只要求逐人精确命中。</li>
<li><strong>宏观与微观：</strong>与上月值加权或线性校准可以另行改善总体指标，但不能据此宣布个人差异已被修复；增加随机性同样不能保证恢复正确的个人排序。</li></ul>
<details><summary>Q8点预期独立结果</summary><div class="scroll"><table><tr><th>历史来源</th><th>人群中位数MAE</th><th>个人MAE</th><th>跨人W1</th></tr>{q8rows}</table></div><p>Q8支持{primary['q8_person_months']}个人月；不因Q9无效删除有效Q8。</p></details>
<details><summary>失败、归一化、每遍及其他分组</summary><p>原答、错误与来源保存在私有账本；本页只给聚合。比例归一化、字段保留和密度失败后备的逻辑位置计数：</p><pre>{escape(json.dumps(s['quality'],ensure_ascii=False,indent=2))}</pre><p>两遍、首次进入Core/持续/间断分组，以及真实上期基线均见完整聚合JSON。首次共享请求的两个逻辑位置不能当作独立回答。</p></details>
<h2>7. 对下一步工作的含义</h2>
<ol><li>把“给定真实历史的重建能力”与“自主连续模拟能力”分别报告；本轮尚不能宣称B线已有效。</li>
<li>先用已有、严格更早的数据检查新入组供体的时期、匹配支持及分布；下一版规则不能根据本期个人答案反向配对。</li>
<li>独立冻结宏观组合的拟权/验证规则，再衔接连续月份主运行；保留微观差距，不以总体校准后的好成绩替代微观验证。</li></ol>
<details><summary>实际执行、费用与复现</summary><p>DeepSeek V3.2，OpenRouter→固定SiliconFlow FP8，温度0.5、JSON、关闭思考、最多1024输出token。本批{fee['attempts']}次请求，{fee['logical_positions']}逻辑位置，峰值{fee['peak_in_flight']}在途；API报告${fee['reported_cost_usd']:.4f}，含未知费用预留${fee['spent_or_reserved_usd']:.4f}，上限$5。调用约{fee['seconds']/60:.1f}分钟，自动重试{fee['automatic_retries']}次。</p>
<p>这是采用历史当期画像与月中信息截止的A线诊断；模型训练知识的时间风险仍在。三个月可以识别明显接线问题和短期漂移，不能证明长期误差稳定或全国预测成功。未按本轮成绩改提示、删人或重新选择供体。</p>
<p class="note">本页只重新组织说明，原答、统计与图形不变；0新增API、0额外密度拟合。源码与协议见冻结执行包。</p></details></main></html>'''
    (dest / 'index.html').write_text(page)
    dump(dest / 'summary.json', s)
    return dict(report=str(dest / 'index.html'), new_api_calls=0, new_q9_fits=0)
