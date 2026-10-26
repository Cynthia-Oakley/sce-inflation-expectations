"""Add an offline-initialization section to the existing project reading page."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
import numpy as np

from ..experiments.state_continuity import ROOT

START, END = '<!-- recent-entry-preflight:start -->', '<!-- recent-entry-preflight:end -->'


def publish(source, report):
    source, report = Path(source), Path(report)
    data = json.loads((source / 'summary.json').read_text())
    if data['new_api_calls'] != 0 or data['new_model_answers'] != 0:
        raise ValueError('An offline initialization preflight is required')
    page = report / 'index.html'
    if not page.exists():
        raise ValueError('Existing report required; do not create a second results page')
    font = ROOT / 'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():
        font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC', 'STKaiti'], 'font.size': 11,
                         'axes.unicode_minus': False, 'axes.spines.top': False, 'axes.spines.right': False})
    small = [u for u in data['units'] if u['probe_n'] == 96]
    large = [u for u in data['units'] if u['probe_n'] == 512]
    dates = [u['month'][:4] + '-' + u['month'][4:] for u in small]
    fig, axes = plt.subplots(1, 2, figsize=(13.8, 4.9))
    x = np.arange(len(small)); width = .34
    for off, values, color, label in [(-width/2, [u['old_synthetic_field_age_months']['max'] for u in small], '#777777', '原方案：最远供体'),
                                      (width/2, [u['max_new_donor_age_months'] for u in small], '#c76800', '近期方案：最远供体')]:
        bars = axes[0].bar(x+off, values, width, color=color, label=label)
        axes[0].bar_label(bars, fmt='%.0f', padding=4)
    axes[0].set(title='供体时期：原96人诊断中的旧分配 vs 新规则', ylabel='距目标调查月的时间（月）', xlabel='目标调查月')
    axes[0].set_xticks(x, dates); axes[0].legend(fontsize=9); axes[0].margins(y=.2)
    past = np.array([u['references']['q9']['past_reference']['median_pp'] for u in large])
    current = np.array([u['calibrated_mixture']['q9']['median_pp'] for u in large])
    lo, hi = np.array([u['assignment_sensitivity']['soft_calibrated']['q9']['central_95_assignment_range_pp'] for u in large]).T
    axes[1].plot(x, past, 's--', color='#777777', label='上月完整调查波次', linewidth=2)
    axes[1].errorbar(x, current, yerr=np.stack([current-lo, hi-current]), fmt='o-', color='#c76800', capsize=5,
                     label='补齐后的起点；100个分配种子的95%范围', linewidth=2)
    for j, value in enumerate(current):
        axes[1].annotate(f'{value:.3f}', (j, value), xytext=(5, -18), textcoords='offset points')
    axes[1].set_xticks(x, dates)
    axes[1].set(title='512人支持检查：起点中位数，不是模型本期预测', ylabel='Q9密度均值的跨人中位数（%）', xlabel='目标调查月（参照上一月）')
    axes[1].legend(fontsize=9); axes[1].margins(y=.3)
    for ax in axes:
        ax.grid(axis='y', alpha=.12)
    fig.tight_layout()
    (report / 'figures').mkdir(exist_ok=True)
    fig.savefig(report / 'figures/recent_entry_preflight.png', dpi=170); plt.close(fig)
    (report / 'entry_preflight_summary.json').write_bytes((source / 'summary.json').read_bytes())
    support = data['historical_support']; n = sum(u['entrant_n'] for u in support)
    sparse_full = sum(u['matching_support']['age_education_income']['fewer_than_five'] for u in support)
    sparse_broad = sum(u['matching_support']['age_income']['fewer_than_five'] for u in support)
    rows = ''
    for u in large:
        q = u['calibrated_mixture']['q9']; p = u['references']['q9']['past_reference']['median_pp']
        rows += (f'<tr><td>{u["month"][:4]}-{u["month"][4:]}</td><td>{u["probe_n"]}</td>'
                 f'<td>{u["synthetic_people"]}</td><td>{u["raw_weight_valid_n"]}</td>'
                 f'<td>{p:.3f}</td><td>{q["median_pp"]:.3f}</td>'
                 f'<td>{q["w1_to_past_reference_pp"]:.3f}</td></tr>')
    block = f'''{START}
<section id="recent-entry-preflight"><h2>新进展：新受访者的近期信念起点（零API）</h2>
<p class="lead"><strong>旧供体确实可能太远：本次96人旧输入中，最远距目标月94个月。近期方案的六个检查单元均从相邻上月选到了供体。</strong><br>检查的是“调查前怎样初始化”，没有生成新的模型回答，不能据此宣称本期预测误差改善。下方原三月模拟成绩保持不变。</p>
<h3>1. 新规则如何工作？</h3><ol>
<li>保留本人近三个月内的合法实答，Q8/Q9分别处理；更早实答保留原日期作为较旧记忆，不冒充本人上月回答。</li>
<li>缺失或需要近期合成起点时，先找上月同类供体。优先年龄×学历×收入，候选不足时依次放宽；上月仍无支持才扩至近三个月，之后停止并报缺口，不静默跨年。</li>
<li>真实新人参考历史新人；间断/缺失回访者参考历史回访者；无法确认身份者另标。按供体调查权重抽取一次，保留联合Q8与十档Q9，不继承供体的家庭收入、就业或评价权重。</li>
<li>先检查合并起点与上期总体是否大致一致；有必要才小幅调整合成供体的抽取概率。本人实答和评价权重不改，不用本期SCE答案调分配。</li></ol>
<p class="note">本版支持保护值为至少5个候选、供体有效样本量至少3；概率校准相对原抽取概率限于1/4至4倍。它们是公开记录的工程保护值，不是从本期误差估计出的经济学系数，最终运行时随配置登记。</p>
<h3>2. 数据检查发现什么？</h3>
<p>2019-01—2025-10共{len(support)}期、{n:,}个真实新人个人月的原题合法性覆盖检查中，年龄×学历×收入有{sparse_full/n:.1%}的新人对应上月候选少于5人；放宽到年龄×收入后降至{sparse_broad/n:.1%}。这支持<strong>近期优先、有限放宽人口匹配</strong>，无需为了维持三项精确匹配而借很早的信念。</p>
<figure><img src="figures/recent_entry_preflight.png" alt="旧供体时距与近期方案起点总体检查"><figcaption>左：2025年5—7月旧96人输入与新规则中，供体距目标月的最大时距。右：512人SRS支持检查，保留真实旧答并合成补缺后的Q9起点分布；不是新LLM输出。来源：仅严格过去问卷、当期白名单人口及本地评价权重。</figcaption></figure>
<div class="scroll"><table><tr><th>目标月</th><th>保留名单</th><th>需合成者</th><th>原始权重有效</th><th>上期Q9中位数</th><th>补齐后起点</th><th>起点对上期W1</th></tr>{rows}</table></div>
<p>三月×96/512人共六个单元，近期方案在校准前均落入过去调查的抽样波动带，因此没有额外倾斜概率。512人Q9起点对上期总体的中位数偏差约0.09—0.43pp；这说明<strong>不必强行精确相等</strong>，也不表示整个分布已完全匹配。上表W1只比较初始信念与过去总体，不是本期模拟W1。</p>
<h3>3. 统计上应如何理解？</h3>
<p>软约束容差来自“从上月波次反复抽相同人数，中位数自然会波动多少”。这是固定过去资料下的抽样敏感性，不是全国设计置信区间。另用100个供体分配种子检查有限抽取波动：512人6月的Q9有96%分配落入容差，其他单元为100%；概率分布合格不保证每次有限抽取都严格命中。</p>
<p>概率校准约束Q8/Q9各自的总体中位数，不能据此识别新人的真实个人信念、尾部或完整联合分布。个人合成起点的W1、IQR及供体复用另行记录；下一轮模型增量必须与“直接保留这个起点”的基线比较。</p>
<h3>4. 当前可用范围与下一步</h3>
<p>本版是A线历史初始化的可复用实现与支持检查，旧批次输入和成绩不改。512人采用稳定优先级SRS，只用于覆盖检查；最终六格抽样确定后按同一设计登记容差。7月512人中1人的原始调查权重缺失：保留并初始化，未用默认1参与加权统计；权重来源仍需修复。</p>
<p>严格未来预测可能尚拿不到上月微观，必须另用截止前已公开旧微观与公开总体构造近期合成状态，不能调用本版未发布上月答卷。当前不为这项初始化单独追加付费模拟；随全量输入接入，再评价本期总体W1、真实回访者局部W1及新人条件分布。</p>
<details><summary>配置、复算与输入措辞</summary><p>公开聚合：<a href="entry_preflight_summary.json">本轮完整离线统计</a>；详细说明：<a href="../entry_initialization_and_remaining_plan_20261022.md">初始化与主线清单</a>。原题、供体身份和逐人输入只留本地outputs。</p>
<pre>python scripts/prepare_sce_entry_initialization.py --out outputs/&lt;新的离线目录&gt;
python -m pytest tests/test_sce_entry_initialization.py -q</pre>
<p>模型侧只写“参考2025年4月同类居民分配的合成起始信念，并非你真实的上月作答”，随后列Q8/Q9；不写供体身份或权重，不伪造本人历史均值/次数。完整英文样例已保存于离线输出目录。</p></details></section>
{END}'''
    html = page.read_text()
    if START in html:
        left, remainder = html.split(START, 1)
        _, right = remainder.split(END, 1)
        html = left + block + right
    else:
        anchor = '<h2>1. 这项实验研究项目的哪个环节？</h2>'
        if anchor not in html:
            raise ValueError('Existing report structure changed; explicit attachment target required')
        html = html.replace(anchor, block + '\n' + anchor, 1)
    page.write_text(html)
    return {'report': str(page), 'new_api_calls': 0, 'old_model_results_unchanged': True}
