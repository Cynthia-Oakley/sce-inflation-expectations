#!/usr/bin/env python3
"""Render aggregate scientific figures and append results to the existing reading page."""
from pathlib import Path
import argparse
import html
import json
import os
import shutil

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR', '/tmp/sce_prior_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ARMS = ('no_prior', 'own_previous', 'permuted_previous')
NAMES = {'no_prior': '无先验', 'own_previous': '本人先验', 'permuted_previous': '置换先验'}
ENGLISH = {'no_prior': 'No prior', 'own_previous': 'Own prior', 'permuted_previous': 'Permuted prior'}
COLORS = {'no_prior': '#b16a45', 'own_previous': '#236a89', 'permuted_previous': '#806383'}


def render(source, dest, update_page=False):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if dest.exists() or not dest.is_relative_to(ROOT / 'outputs'):
        raise ValueError('fresh ignored report output required')
    result = json.loads(source.read_text())
    if result['status'] != 'completed_offline_analysis' or result['actual_calls'] != 288:
        raise ValueError('only completed actual trial results may be shown')
    dest.mkdir(parents=True)
    months = list(result['months'])
    x = np.arange(len(months))
    fig, axes = plt.subplots(2, 1, figsize=(11.5, 8.5), constrained_layout=True)
    for ax, key, title in ((axes[0], 'median_pp', 'One-year inflation expectation: sample median'),
                           (axes[1], 'cross_person_iqr_pp', 'Differences between people: interquartile range')):
        for offset, arm in zip((-.14, 0., .14), ARMS):
            values = np.array([[result['months'][m]['repeats'][str(r)]['Q9']['arms'][arm]['distribution'][key]
                                for m in months] for r in (1, 2)])
            mean = values.mean(axis=0)
            ax.errorbar(x + offset, mean, yerr=[mean-values.min(axis=0), values.max(axis=0)-mean],
                        marker='o', linestyle='none', capsize=4, color=COLORS[arm], label=ENGLISH[arm])
        real = [result['months'][m]['repeats']['1']['Q9']['real'][key] for m in months]
        prior = [result['months'][m]['repeats']['1']['Q9']['prior_persistence_common_sample']['distribution'][key] for m in months]
        ax.scatter(x, real, marker='x', s=75, color='#202020', label='Real same-sample SCE', zorder=4)
        ax.scatter(x + .27, prior, marker='^', color='#888888', s=45, label='Carry forward own prior', zorder=4)
        ax.set_xticks(x, [m[:4]+'-'+m[4:] for m in months])
        ax.set_xlabel('Survey month (four separate development periods)')
        ax.set_ylabel('Percentage points')
        ax.set_title(title, fontsize=13, loc='left')
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', color='#e4e4e4')
    axes[0].legend(fontsize=9, ncol=3, loc='best')
    fig.suptitle('Observed prior trial: 12 selected people per period, 3 groups, 2 generations', fontsize=14)
    fig.savefig(dest / 'prior_comparison.png', dpi=160)
    fig.savefig(dest / 'prior_comparison.svg')
    plt.close(fig)
    averages = {}
    for arm in ARMS + ('own_prior_persistence',):
        averages[arm] = {k: float(np.mean([s[arm][k] for s in result['across_months_by_repeat'].values()]))
                        for k in ('median_absolute_error_pp', 'distribution_W1_pp', 'IQR_absolute_gap_pp')}
    lines = ['# 本人先验实验结果（2026-10-13）', '',
        'A线条件重建诊断；四期各12人、每年龄组4人、三组各两次。保持原人口、价格/新闻/政策、合成篮子与信心不变。不是全国预测或独立留出检验。', '',
        f"完成{result['actual_calls']}次真实请求；按高峰未命中缓存价格估算费用${result['conservative_cost_usd']:.6f}，授权上限$1；不是厂商账单。", '',
        '## 四期两遍的平均误差', '']
    for arm in ARMS + ('own_prior_persistence',):
        a = averages[arm]
        label = NAMES.get(arm, '直接延续本人上期回答（免费基线）')
        lines.append(f"- {label}：总体中位数绝对误差{a['median_absolute_error_pp']:.3f}pp；分布距离{a['distribution_W1_pp']:.3f}pp；人际IQR差距{a['IQR_absolute_gap_pp']:.3f}pp。")
    lines += ['', '以上是各期分别评价后取平均，不是逐人MAE。真人与三组使用同一近似计分器、共同有效样本；Q9采用项目既有经验中位数，不能与先前np.median准备简诊断直接混比。', '',
              '## 图示', '', '![总体预期与人际分散程度](prior_comparison.png)', '',
              '点为两次生成的平均，短线为两次生成的最小到最大，不是置信区间。黑叉为同批真人，灰三角为原样延续上期。四个时期分开处理，没有连续状态。', '',
              '## 各时期与更新核查', '']
    for month in months:
        lines += [f"### {month[:4]}-{month[4:]}", '']
        for r in (1, 2):
            cell = result['months'][month]['repeats'][str(r)]['Q9']
            update = cell['updates_and_copying']['own_previous']
            copy = update['supplied_prior_raw_copying']
            errors = '；'.join(f"{NAMES[a]} {cell['arms'][a]['median_absolute_error_pp']:.3f}" for a in ARMS)
            lines.append(f"- 第{r}遍，共同有效{cell['n_common']}人，总体中位数误差（pp）：{errors}。本人先验逐档照抄{copy['exact_copy_n']}/{copy['n']}；平均预期变化{update['mean_signed_update_pp']:.3f}pp，真人{update['real_mean_signed_update_pp']:.3f}pp。")
        lines.append('')
    lines += ['## 结论边界', '',
        f"事先约定的继续检验门槛：{'通过' if result['candidate_continue_gate_passed'] else '未通过'}。该门槛只要求两遍的平均中心误差/分布距离改善且至少3/4期同向，不能代替身份价值、更新或独立时期验证。", '',
        '完整提醒可能帮助保持已有差异；还需判断本人是否优于置换、能否优于原样延续。概率改动不等于真实学习，模型理由只作线索。全部结果保留，不自动更换正式机制。', '',
        f"完整聚合结果：{source.relative_to(ROOT)}。个人问卷/提示/关联/配对评价仅存忽略的本地输出。"]
    sensitivity_path = source.parent / 'median_definition_sensitivity.json'
    if sensitivity_path.exists():
        sensitivity = json.loads(sensitivity_path.read_text())
        alt = sensitivity['averages']
        lines += ['', '## 小样本中位数定义的补充检查', '',
            f"项目冻结口径采用经验分位数；另用常见的中间两人取平均，仅作事后敏感性检查：无先验{alt['no_prior']:.3f}pp、本人先验{alt['own_previous']:.3f}pp、置换先验{alt['permuted_previous']:.3f}pp、直接延续{alt['own_prior']:.3f}pp。", '',
            '本人相对无先验的改善、置换中心误差更小及分布仍集中的结论保持；本人和直接延续的总体中位数误差排序会变化。直接延续的分布距离仍更小，不能笼统宣称某方法在所有指标上更好。原先免费准备基线使用中间两人取平均，差异不是重新运行数据。', '',
            '本人对无先验、本人对置换的八个逐期/逐遍中心误差差值重抽样区间均跨0：小样本还不足以确认换一批人后仍稳定改善。主口径未替换，未调参、未新增API。']
    (dest / 'report.md').write_text('\n'.join(lines)+'\n')
    safe = {'status': result['status'], 'source': str(source.relative_to(ROOT)), 'actual_calls': result['actual_calls'],
            'conservative_cost_usd': result['conservative_cost_usd'], 'averages': averages,
            'continue_gate': result['candidate_continue_gate_passed'], 'no_individual_rows': True}
    (dest / 'aggregate_summary.json').write_text(json.dumps(safe, ensure_ascii=False, indent=2)+'\n')
    if update_page:
        page = ROOT / 'docs/literature/sce/news_selection/news_review_20261011.html'
        text = page.read_text()
        marker = 'id="observed-prior-results-20261013"'
        if '</body>' not in text:
            raise ValueError('page structure changed')
        shutil.copy2(page, dest / 'reading_page_before.html')
        image = os.path.relpath(dest / 'prior_comparison.png', page.parent)
        report_link = os.path.relpath(dest / 'report.md', page.parent)
        items = ''.join('<li>'+html.escape(line[2:])+'</li>' for line in lines if line.startswith('- ') and '逐档照抄' not in line)
        section = f'<section {marker} style="padding:28px;max-width:1100px;margin:28px auto;line-height:1.65"><h2>本人先验实验 · 2026-10-13</h2><p>四个开发时期各12人，三组各生成两次。真实请求288次，按高峰价估算${result["conservative_cost_usd"]:.4f}，上限$1。新闻仍为3篇共同＋5篇个人，其他输入保持。</p><ul style="display:block">{items}</ul><p>这是同一小样本的总体中位数误差和分布距离，单位百分点；不代表全国预测。仅给模型真实上期回答，没有给本期答案。</p><img src="{html.escape(image)}" alt="四期总体预期和人际分散程度" style="display:block;width:100%;height:auto"><p>模型点为两遍平均，短线为生成范围，不是置信区间。黑叉同批真人，灰三角直接延续上期。门槛{ "通过" if result["candidate_continue_gate_passed"] else "未通过" }仍需结合身份与更新核查，不能自动升级。</p><p>当前人际IQR仍不足真人的五分之一；置换先验的中心误差也更小，个人身份价值尚未确认。逐期/逐遍中心改善区间仍跨0。12人小样的中位数定义会影响本人与直接延续的中心误差排序；分布距离上直接延续仍更好，详见完整记录。</p><p><a href="{html.escape(report_link)}">完整实验记录与逐期说明</a></p></section>\n'
        if marker in text:
            start = text.index('<section ' + marker)
            end = text.index('</section>', start) + len('</section>')
            page.write_text(text[:start] + section + text[end:])
        else:
            page.write_text(text.replace('</body>', section+'</body>', 1))
    return safe


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--update-reading-page', action='store_true')
    args = p.parse_args()
    print(json.dumps(render(args.source, args.out, args.update_reading_page), ensure_ascii=False))
