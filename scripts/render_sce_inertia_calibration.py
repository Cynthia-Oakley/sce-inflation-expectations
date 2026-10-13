#!/usr/bin/env python3
"""Render fixed-weight offline diagnostics into the existing SCE reading page."""
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

ARMS = ('no_prior', 'own_previous', 'permuted_previous')
NAMES = {'no_prior': '无个人先验', 'own_previous': '本人先验', 'permuted_previous': '置换先验'}
LABELS = {'no_prior': 'No personal prior', 'own_previous': 'Own prior', 'permuted_previous': 'Permuted prior'}
COLORS = {'no_prior': '#b16a45', 'own_previous': '#236a89', 'permuted_previous': '#806383'}


def render(source, out, update_page=False):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('fresh ignored report output required')
    s = json.loads(source.read_text())
    if s['status'] != 'completed_offline_fixed_weight_diagnostic' or s['weight_selection_performed']:
        raise ValueError('fixed-weight completed diagnostic required')
    out.mkdir(parents=True)
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 8), constrained_layout=True)
    for ax, scope, title in zip(axes, ('same_sample', 'public_anchor_reference'),
            ('Same selected people: past-sample median anchor', 'National headline reference: latest published SCE anchor')):
        b = s['scopes'][scope]
        weights = s['fixed_sensitivity_weights']
        for arm in ARMS:
            ax.plot(weights, [b['weights'][f'{w:.1f}'][arm]['mae_pp'] for w in weights],
                    marker='o', label=LABELS[arm], color=COLORS[arm])
        ax.axhline(b['persistence']['mae_pp'], color='#555555', linestyle='--', label='Historical anchor only')
        ax.axvline(.4, color='#aaaaaa', linestyle=':', label='Fixed 40% history setting')
        ax.set_xlabel('Weight on historical anchor (0 = raw Agent, 1 = anchor only)')
        ax.set_ylabel('Mean absolute error (percentage points)')
        ax.set_title(title, loc='left', fontsize=12)
        ax.set_xticks(weights)
        ax.grid(axis='y', color='#e4e4e4')
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].legend(fontsize=9, ncol=2)
    fig.suptitle('Fixed-weight sensitivity: 4 development periods, 2 generations each', fontsize=13)
    fig.supxlabel('Source: frozen prior trial, 2026-10-13; survey periods 2022-03/09, 2023-03, 2024-03', fontsize=9)
    fig.savefig(out / 'calibration_weights.png', dpi=160)
    fig.savefig(out / 'calibration_weights.svg')
    plt.close(fig)
    a, b = s['scopes']['same_sample'], s['scopes']['public_anchor_reference']
    variance = s['heterogeneity']['mean_variance_pp_squared']
    noise = s['two_generation_variance']
    lines = ['# 行为惯性加权离线试算（2026-10-13）', '',
        '复用刚完成的288份回答，无新API/费用，未改原问卷、计分器、人口或模拟配置。固定采用40%历史值＋60%模拟值，并列0/20/40/60/80/100%历史权重作敏感性检查，没有挑选SCE最佳权重。', '',
        '## 1. 与上一轮同口径：同一批人的中位数', '',
        '锚是同一批真人上月Q9的中位数，目标是同一批真人本月中位数，双方同一近似计分器。这是A线条件重建的样本诊断，历史微观当时未公开，不能称实时B预测。', '']
    for arm in ARMS:
        raw, cal = a['weights']['0.0'][arm], a['weights']['0.4'][arm]
        lines.append(f"- {NAMES[arm]}：MAE {raw['mae_pp']:.3f}→{cal['mae_pp']:.3f}pp；RMSE {raw['rmse_pp']:.3f}→{cal['rmse_pp']:.3f}pp。")
    lines += [f"- 直接沿用同批人上期中位数：MAE {a['persistence']['mae_pp']:.3f}pp；RMSE {a['persistence']['rmse_pp']:.3f}pp。", '',
        'MAE是四期两遍分别评价后等权平均；RMSE将对应平方误差先平均再开方。重复生成不增加独立月份。借用40%并非SCE最优参数；更高固定权重结果留在曲线中，不据开发结果选胜者。', '',
        '## 2. 官方全国指标参照：最近已公布的SCE', '',
        '同一个12人样本的模拟中位数作为粗略全国信号，锚取信息截止前最近公开的官方首发SCE，目标为当期官方首发指标。它与第1项的人口/真值不同，两套误差不能直接混比；12人年龄平衡小样尚无全国代表性。公开锚合规也不能消除原实验真实上期微观的前视限制，所以这不是严格B回测。', '']
    for arm in ARMS:
        raw, cal = b['weights']['0.0'][arm], b['weights']['0.4'][arm]
        lines.append(f"- {NAMES[arm]}：MAE {raw['mae_pp']:.3f}→{cal['mae_pp']:.3f}pp；RMSE {raw['rmse_pp']:.3f}→{cal['rmse_pp']:.3f}pp。")
    lines += [f"- 最近公开值直接延续：MAE {b['persistence']['mae_pp']:.3f}pp；RMSE {b['persistence']['rmse_pp']:.3f}pp。", '',
        '本人先验加权的0.409pp仍略高于延续的0.400pp：可降低原始模型误差，但未显示稳定的额外预测价值。置换组反而被40%校准拉差，不能称校准普遍有效。', '', '公开锚的日期核查：', '']
    for c in s['cells'][::2]:
        anchor = c['public_anchor']
        lines.append(f"- {c['month']}：截止{c['as_of'][:10]}，使用{anchor['reference_period']} SCE={anchor['value_pp']:.1f}%，发布{anchor['published_date']}；当前目标={c['public_truth_pp']:.1f}%。")
    lines += ['', '2022-03截止3月10日时，2月SCE尚未发布，必须用1月值5.8%，不能直接套“上一调查月”。', '',
        '## 3. 方差要区分对象', '',
        f"人际方差（各期的描述性方差再平均，ddof=0，单位百分点²）：真人{variance['real']:.3f}；无先验{variance['no_prior']:.3f}；本人先验{variance['own_previous']:.3f}；置换{variance['permuted_previous']:.3f}。", '',
        f"本次只校准总指标，个人回答不改，故本人先验人际方差仍为{variance['own_previous']:.3f}。对应中间一半人的预期跨度仍为{s['heterogeneity']['mean_IQR_pp']['own_previous']:.3f}pp，真人{s['heterogeneity']['mean_IQR_pp']['real']:.3f}pp。没有重建出新的个人Q9分布。", '',
        '若为展示把所有个人均值统一平移，方差也不变。若把同一个全国锚直接与每人的值作40/60混合，方差会乘0.36，反而进一步收窄；这不是本轮采用的宏观校准。', '',
        f"同输入两次生成的总指标方差（两遍样本方差ddof=1，再跨四期平均）：本人先验{noise['raw_pp_squared']['own_previous']:.4f}→{noise['calibrated_04_pp_squared']['own_previous']:.4f}pp²。固定历史锚时理论上乘0.6²=0.36。只有两遍，是粗略条件诊断，不是稳定的不确定性估计。", '',
        '## 4. 先平均两遍再评价的敏感性', '',
        f"全国参照：本人先验先平均两遍总指标，MAE {b['average_two_generations_before_scoring']['0.0']['own_previous']['mae_pp']:.3f}→{b['average_two_generations_before_scoring']['0.4']['own_previous']['mae_pp']:.3f}pp，改善明显缩小。40%加权的收益有一部分来自抑制生成波动，不能全部解释为信念机制更真实。主表继续保留逐遍评价，没有替换口径。", '',
        '## 5. 曲线与结论', '', '![固定历史权重与误差](calibration_weights.png)', '',
        '上图同样本口径，下图全国参照；虚线为只用历史值。权重按事先固定网格展示，不是新LLM实验或已训练的SCE参数。', '',
        '结论：宏观组合可研究，与微观行为真实性分别验收。下一步需要代表性人口与更长/独立时期检验增量；四期12人结果不足冻结权重。', '',
        f"完整聚合复算：{source.relative_to(ROOT)}。依据：ConsumerSim §4.6及附录§11、项目统一评价契约和既有官方SCE发布台账。"]
    (out / 'report.md').write_text('\n'.join(lines) + '\n')
    if update_page:
        page = ROOT / 'docs/literature/sce/news_selection/news_review_20261011.html'
        text = page.read_text()
        marker = 'id="inertia-calibration-20261013"'
        shutil.copy2(page, out / 'reading_page_before.html')
        image = os.path.relpath(out / 'calibration_weights.png', page.parent)
        report = os.path.relpath(out / 'report.md', page.parent)
        rows = ''.join(f'<tr><td>{NAMES[arm]}</td><td>{a["weights"]["0.0"][arm]["mae_pp"]:.3f} → {a["weights"]["0.4"][arm]["mae_pp"]:.3f}</td><td>{b["weights"]["0.0"][arm]["mae_pp"]:.3f} → {b["weights"]["0.4"][arm]["mae_pp"]:.3f}</td></tr>' for arm in ARMS)
        section = f'<section {marker} style="padding:28px;max-width:1100px;margin:28px auto;line-height:1.65"><h2>40%历史＋60%模拟：离线试算</h2><p>复用288份回答，新增费用$0；只调整总体输出，不改个人Q9。四个开发时期各12人，两遍生成，权重未训练。</p><div style="overflow-x:auto"><table style="width:100%;table-layout:auto"><thead><tr><th>原模拟组</th><th>同批真人目标：MAE前→后（pp）</th><th>全国指标参照：MAE前→后（pp）</th></tr></thead><tbody>{rows}</tbody></table></div><p>两套真值不同，不能把左边1.318与右边0.409直接比较。左边直接延续上期MAE 0.850；右边直接延续最近公开SCE为0.400。右边只是12人小样的全国参照，尚非代表性预测，原真实上期微观也不符合B实时可得性。</p><p><strong>人群差异未解决：</strong>本人先验人际方差仍{variance["own_previous"]:.3f}pp²，真人{variance["real"]:.3f}；中间一半人的跨度仍0.974pp，对真人5.502。重复生成的波动会缩小，这是另一个方差对象。</p><img src="{html.escape(image)}" alt="历史权重敏感性：同样本与全国参照分开" style="display:block;width:100%;height:auto"><p>40%以外的权重只是固定敏感性比较，不在四个已看过时期中选最佳权重。先平均两遍再对全国评价，MAE只从0.417降到0.409，说明收益部分来自压低生成波动。</p><p><a href="{html.escape(report)}">完整试算、发布日期与方差说明</a></p></section>\n'
        if marker in text:
            start = text.index('<section ' + marker)
            end = text.index('</section>', start) + len('</section>')
            page.write_text(text[:start] + section + text[end:])
        else:
            page.write_text(text.replace('</body>', section + '</body>', 1))
    return {'report': str((out / 'report.md').relative_to(ROOT)), 'new_api_calls': 0}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--update-reading-page', action='store_true')
    args = p.parse_args()
    print(json.dumps(render(args.source, args.out, args.update_reading_page), ensure_ascii=False))
