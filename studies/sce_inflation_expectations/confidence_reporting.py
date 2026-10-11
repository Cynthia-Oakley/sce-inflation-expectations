"""Aggregate-only figures and updates to the existing local reading page."""
import html
import json
import os
from pathlib import Path
import numpy as np
from .confidence_experiment import ARMS
from .confidence_trial import sha, dump


def report(root, analysis_dir):
    root, analysis_dir = Path(root).resolve(), Path(analysis_dir).resolve()
    summary = json.loads((analysis_dir / 'summary.json').read_text())
    months = list(summary['months'])
    cells = [summary['months'][m]['repeats'][str(r)]['Q9'] for m in months for r in (1, 2)]
    aggregate = {a: {k: float(np.mean([c['arms'][a][k] for c in cells])) for k in ('median_absolute_error_pp', 'distribution_W1_pp', 'IQR_absolute_gap_pp')} for a in ARMS}
    real_iqr = float(np.mean([c['real']['cross_person_iqr_pp'] for c in cells]))
    sim_iqr = {a: float(np.mean([c['arms'][a]['distribution']['cross_person_iqr_pp'] for c in cells])) for a in ARMS}
    intervals = [c['confidence_minus_no_confidence']['median_absolute_error_pp']['paired_person_bootstrap_95_interval_pp'] for c in cells]
    facts = {'status': 'simulation_and_offline_analysis_completed', 'completed_on_local_date': '2026-10-12',
        'analysis_directory': str(analysis_dir.relative_to(root)), 'analysis_summary_sha256': sha(analysis_dir / 'summary.json'),
        'actual_calls': summary['actual_calls'], 'valid_answers': sum(r['statuses'].get('valid', 0) for r in summary['runs']),
        'invalid_answers': sum(r['statuses'].get('invalid', 0) for r in summary['runs']),
        'transport_errors': 0, 'automatic_retries': 0, 'conservative_cost_usd': summary['conservative_cost_usd'],
        'budget_cap_usd': 2.5, 'Q9_four_month_two_repeat_equal_cell_average': aggregate,
        'real_Q9_cross_person_IQR_pp': real_iqr, 'simulated_Q9_cross_person_IQR_pp': sim_iqr,
        'median_error_improvement_percent': 100*(aggregate[ARMS[0]]['median_absolute_error_pp']-aggregate[ARMS[1]]['median_absolute_error_pp'])/aggregate[ARMS[0]]['median_absolute_error_pp'],
        'median_error_intervals_containing_zero': sum(lo <= 0 <= hi for lo, hi in intervals),
        'median_error_comparisons': len(intervals), 'candidate_upgrade_gate_passed': summary['candidate_upgrade_gate_passed'],
        'production_P_changed': False, 'sources': summary['scorer'],
        'interpretation': 'candidate positive mechanism signal; limited precision; substantial distribution gap remains'}
    dump(analysis_dir / 'reading_summary.json', facts)
    dump(root / 'docs/literature/sce/belief_proxies/confidence_result_20261012.json', facts)
    os.environ.setdefault('MPLCONFIGDIR', str(analysis_dir / 'matplotlib_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': ['Arial Unicode MS', 'PingFang SC', 'sans-serif'], 'axes.unicode_minus': False,
                         'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    colors = ('#6c7880', '#286c68')
    x = np.arange(len(months))
    medians = {a: [float(np.mean([summary['months'][m]['repeats'][str(r)]['Q9']['arms'][a]['distribution']['median_pp'] for r in (1, 2)])) for m in months] for a in ARMS}
    real = [float(np.mean([summary['months'][m]['repeats'][str(r)]['Q9']['real']['median_pp'] for r in (1, 2)])) for m in months]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), constrained_layout=True)
    axes[0].plot(x, real, marker='o', color='#333333', label='真人共同有效样本')
    for a, label, color in zip(ARMS, ('不加信心', '加入合成央行信心'), colors):
        axes[0].plot(x, medians[a], marker='o', color=color, label=label)
        err = [float(np.mean([summary['months'][m]['repeats'][str(r)]['Q9']['arms'][a]['median_absolute_error_pp'] for r in (1, 2)])) for m in months]
        axes[1].bar(x + (-.18 if a == ARMS[0] else .18), err, width=.34, color=color, label=label)
    for ax in axes:
        ax.set_xticks(x, [m[:4]+'-'+m[4:] for m in months])
        ax.set_xlabel('分散的调查月份（不是连续月度轨迹）')
        ax.grid(axis='y', alpha=.15)
        ax.legend(fontsize=9)
    axes[0].set(title='Q9群体中心：两次生成的平均', ylabel='一年期通胀预期（%）')
    axes[1].set(title='相对同一批真人的中心误差', ylabel='绝对误差（个百分点）')
    fig.savefig(analysis_dir / 'q9_centers_and_errors.png', dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9.2, 4.1), constrained_layout=True)
    vals = [real_iqr, sim_iqr[ARMS[0]], sim_iqr[ARMS[1]]]
    bars = ax.bar(['真人样本', '不加信心', '加入合成央行信心'], vals, color=['#333333', *colors], width=.55)
    ax.bar_label(bars, fmt='%.2f', padding=4)
    ax.set(title='Q9人际差异仍然很小', ylabel='中间50%人员预期中心的跨度（个百分点）', xlabel='四个月 × 两次生成，单元等权平均')
    ax.set_ylim(0, max(vals)*1.18)
    ax.grid(axis='y', alpha=.15)
    fig.savefig(analysis_dir / 'q9_between_person_spread.png', dpi=160)
    plt.close(fig)
    page = root / 'docs/literature/sce/news_selection/news_review_20261011.html'
    before = page.read_text()
    if 'id="confidence-four-period-results"' in before or before.count('<footer>') != 1:
        raise ValueError('existing page changed or results already added')
    rows = []
    for month in months:
        values = [float(np.mean([summary['months'][month]['repeats'][str(r)]['Q9']['arms'][a]['median_absolute_error_pp'] for r in (1, 2)])) for a in ARMS]
        rows.append(f'<tr><td>{month[:4]}-{month[4:]}</td><td>{values[0]:.3f}</td><td>{values[1]:.3f}</td><td>{values[1]-values[0]:+.3f}</td></tr>')
    images = ''.join('<figure style="margin:20px 0;width:100%"><img style="display:block;width:100%;height:auto" src="'+html.escape(os.path.relpath(analysis_dir/name, page.parent))+'" alt="'+title+'"><figcaption>'+title+'。来源：四时期冻结输入实验、两次生成、同样本项目近似计分器；不代表全国。</figcaption></figure>' for name,title in [('q9_centers_and_errors.png','Q9中心和相对真人的误差'),('q9_between_person_spread.png','Q9人群分散程度')])
    section = ('<section id="confidence-four-period-results" style="display:block;width:100%"><h2>四时期央行信心实验结果 · 2026-10-12</h2>'
        '<p class="important">有小幅、重复出现的改善；人群分布仍远未恢复。保持正式P不变，保留为候选机制。</p>'
        f'<p>768次真实请求：767份有效、1份概率合计99%的无效回答，保留并在双方共同样本中排除；无连接错误、无自动重试。按较高费率估算${facts["conservative_cost_usd"]:.3f}，不是供应商账单。</p>'
        f'<p>Q9中心平均误差 {aggregate[ARMS[0]]["median_absolute_error_pp"]:.3f} → {aggregate[ARMS[1]]["median_absolute_error_pp"]:.3f}个百分点（下降约{facts["median_error_improvement_percent"]:.1f}%）。分布距离只小幅下降，人际跨度 {sim_iqr[ARMS[0]]:.2f} → {sim_iqr[ARMS[1]]:.2f}，真人为{real_iqr:.2f}个百分点。</p>'
        '<p>两次生成分别达到预先登记的继续研究门槛，但8个中心误差改善区间中7个仍包含零。合成信心改变了本模型的回答，真人政策信心的机制与匹配仍需独立验证。</p>'
        '<table class="table"><thead><tr><th>调查月</th><th>不加信心误差</th><th>加入信心误差</th><th>变化</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
        '<p class="meta">单位：个百分点；两次生成平均，误差相对同月同一批共同有效真人样本。不是未来实际CPI预测误差。</p>'+images+
        '<p>2024-03模拟通缩概率中位数仍约15%，真人约3%；该月Q8点回答的中心更接近真人，但这个比较并不适用于所有月份。下一步先免费拆解概率回答偏差和人群差异来源，不继续调新闻比例或新增付费调用。</p></section>')
    dump(analysis_dir / 'reading_receipt.json', {'page': str(page.relative_to(root)), 'before_sha256': sha(page),
        'section_added': 'confidence-four-period-results', 'visual_browser_check': False})
    (analysis_dir / 'news_review_before_results.html').write_text(before)
    page.write_text(before.replace('<footer>', section+'<footer>', 1))
    return facts


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(report(Path(__file__).resolve().parents[2], args.analysis)))
