#!/usr/bin/env python3
"""Publish an aggregate-only sampling diagnostic beside the existing price report."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def report(source, dest):
    if dest.exists():
        raise ValueError('Fresh publication directory required')
    s = json.loads((source/'summary.json').read_text())
    if s['status'] != 'finite_frame_sampling_diagnostic_complete':
        raise ValueError('Completed sampling diagnostic required')
    dest.mkdir(parents=True)
    font = ROOT/'outputs/sce_progress_report_20261015_v2/assets/kaiti_sc.ttf'
    if font.exists():
        font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family': ['Times New Roman', 'Kaiti SC', 'STKaiti'],
                         'font.size': 11, 'axes.unicode_minus': False,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.9))
    x = np.arange(3)
    bars = axes[0].bar(x, [s['pooled_equal_month'][str(n)]['mean_absolute_deviation_pp']
                           for n in (48, 96, 192)], color=['#959ba2', '#783caf', '#df7400'], width=.6)
    axes[0].bar_label(bars, fmt='%.3f', padding=5)
    axes[0].set_xticks(x, ['48人', '96人', '192人'])
    axes[0].set_xlabel('每月计划抽取人数'); axes[0].set_ylabel('平均绝对偏移（通胀百分点）')
    axes[0].set_title('样本真人中位数偏离合格回访者总体的程度'); axes[0].set_ylim(0, .72)
    rows = s['monthly']; x = np.arange(len(rows))
    lo = [r['sampling']['96']['signed_deviation_central_95_pp'][0] for r in rows]
    hi = [r['sampling']['96']['signed_deviation_central_95_pp'][1] for r in rows]
    axes[1].vlines(x, lo, hi, color='#a9aeb4', linewidth=8, label='96人重复抽样偏移的中间95%范围')
    axes[1].scatter(x, [r['current_minus_eligible_pp'] for r in rows], color='#783caf', marker='D', s=48, label='本轮实际样本偏移', zorder=3)
    axes[1].axhline(0, color='#25282c', linewidth=1)
    axes[1].set_xticks(x, [f"{r['month']//100}-{r['month']%100:02}" for r in rows], rotation=28)
    axes[1].set_xlabel('非连续调查月份'); axes[1].set_ylabel('样本中位数 − 合格总体中位数（百分点）')
    axes[1].set_title('96人的抽样波动随月份变化'); axes[1].legend(fontsize=8)
    fig.text(.02, .015, '来源：六期已有SCE；每期1000次重抽，复现分层192→96设计与逆概率权重。范围不含模型生成噪声或未来月份不确定性。', fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, 1)); fig.savefig(dest/'sampling_scale.png', dpi=165); plt.close(fig)
    details = ''.join(f"<li>{r['month']//100}-{r['month']%100:02}：合格总体{r['eligible_frame_n']}人；本轮有效{r['current_scorable_n']}人、权重有效样本量{r['current_weight_ess']:.1f}；重复抽样平均偏移{r['sampling']['96']['mean_absolute_deviation_pp']:.3f}pp，本轮实际偏移{r['current_minus_eligible_pp']:+.3f}pp。</li>" for r in rows)
    html = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>模型差距与96人抽样波动</title>
<style>body{{margin:0;background:#f6f5f1;color:#25282c;font:19px/1.75 "Times New Roman","Kaiti SC","STKaiti","KaiTi",serif}}main{{max-width:1120px;margin:auto;padding:32px 24px 70px}}h1{{font-size:32px;line-height:1.4}}h2{{font-size:25px;margin-top:32px}}img{{width:100%;height:auto}}figure{{margin:26px 0;background:white;padding:12px}}figcaption,.meta{{font-size:16px;color:#62676d}}li{{margin:9px 0}}a{{color:#783caf}}.finding{{padding:16px 22px;background:white;border-left:4px solid #783caf}}code{{overflow-wrap:anywhere;font-size:15px}}</style>
<main><p class="meta">SCE · 2026-10-21 · 已有数据离线分析 · 新API调用0</p><h1>模型差距与96人抽样波动，应分开判断</h1>
<div class="finding">模型能力可能影响结果，但本轮“增加两项价格统计后变差”发生在同一个Qwen和同一批人上，不能由参数量差异解释。96人确实带来可观的中位数波动，也不能消除本轮配对比较中观察到的分布收缩。</div>
<h2>1. 参数量是否可能是原因？</h2><p>可能是因素之一，但现在没有证据将差距归于参数量。官方V4.1-Flash披露552B骨干MoE参数，输入／输出每token激活约8B／16B；Qwen2.5-72B披露72.7B参数。两种架构不能按总参数倍率推断能力，实际托管权重与版本还存在不确定性。训练数据、后训练、指令理解和多段信息的使用同样可能影响输出。</p>
<p>来源：<a href="https://api-docs.deepseek.com/news/news260910/">DeepSeek官方架构说明</a>、<a href="https://huggingface.co/Qwen/Qwen2.5-72B-Instruct">Qwen官方模型卡</a>，核查日2026-10-21。公开模型说明不构成对每次API实际权重的独立验证。</p>
<h2>2. 现有证据能区分什么？</h2><ul><li><strong>同输入的小批模型比较：</strong>三期共同65个人月，中心MAE DeepSeek1.563、Qwen1.644，差0.081pp；各月有输有赢，不能认定稳定的模型差距。样本小、旧DeepSeek回答非同期、无效概率带来支持选择，均需保留限制。<a href="../../20261019_advisor_followup/qwen_migration_results.md">原结果</a>。</li>
<li><strong>六期DeepSeek与Qwen对比：</strong>环境统计与输出框架也有变化，不是纯换模型；旧同支持分析中Qwen的中心较差，但跨人宽度部分改善，不能概括为所有能力都下降。<a href="../qwen_conditional_gap_results.md">条件差距分析</a>。</li>
<li><strong>最新同Qwen价格对照：</strong>只增加总体CPI与能源同比，中心MAE0.634→0.877，W1 2.177→2.952；六期W1都变差。上期≥8%的人群，真人本期组均值12.024%，模型7.438%→4.762%。支持“公共数字压过个人信念”的解释，但未单独识别内容、显著性、长度和位置。<a href="../price_background_results_20261021.md">本轮结果</a>。</li></ul>
<h2>3. 每月96人，大概能波动多少？</h2><p>本次把六期已观察到的合格回访者总体固定住，每期重复抽样1000次。先按年龄×收入抽192人，再分层抽96人，沿用两步逆概率与调查权重。比较每次样本真人中位数与该月合格总体中位数；没有生成新的模型回答。</p>
<p><strong>96人：平均绝对偏移{s['pooled_equal_month']['96']['mean_absolute_deviation_pp']:.3f}pp；不同月份{min(r['sampling']['96']['mean_absolute_deviation_pp'] for r in rows):.3f}—{max(r['sampling']['96']['mean_absolute_deviation_pp'] for r in rows):.3f}pp。</strong>六期等权合并的抽样偏移，中间95%范围约为{s['pooled_equal_month']['96']['signed_deviation_central_95_pp'][0]:+.3f}至{s['pooled_equal_month']['96']['signed_deviation_central_95_pp'][1]:+.3f}pp，95%的绝对偏移不超过{s['pooled_equal_month']['96']['absolute_deviation_p95_pp']:.3f}pp；这不是每个月都相同的范围。48人平均偏移{s['pooled_equal_month']['48']['mean_absolute_deviation_pp']:.3f}pp，192人为{s['pooled_equal_month']['192']['mean_absolute_deviation_pp']:.3f}pp。</p>
<figure><img src="sampling_scale.png" alt="48、96、192人样本中位数抽样偏移，以及各月96人偏移范围"><figcaption>纵轴都是通胀百分点。左图只衡量真人样本构成；右图灰线是有限已观察总体中的重复抽样范围，不是模型MAE置信区间。</figcaption></figure>
<ul>{details}</ul>
<h2>4. 对当前结论有什么影响？</h2><p>权重不均使本轮96人的权重有效样本量只有约55—69；这是权重集中程度的指标，不是中位数精度的严格等价人数。2022-06和2025-03的本轮真人样本中位数比合格总体分别高0.616、0.577pp，会影响对全国水平的描述。</p>
<p><strong>不能把0.381pp当作模型不可突破的误差下限，也不能从模型MAE中直接扣除它。</strong>我们的主比较是模型与同一批真人，样本构成效应可以共同抵消，照抄本人上期也共享这批人。原配对重抽样中，增加统计相对食品背景的W1差为+0.776pp，95%区间[+0.541,+0.921]；中心MAE差+0.243pp的区间[−0.005,+0.475]仍跨0。这些结论条件于已选六个开发月。</p>
<h2>5. 下一步的实际选择</h2><p>96人适合筛选机制，不适合凭单月0.1—0.2pp的中心改善判成功。应保留同人配对、分布与先验分组分析；对有希望的机制，再用更多真人和未参与调整的月份验证。扩大人数能减少抽样波动，不能自动修复高先验者被拉向公共锚点。若检验模型能力，只改变模型、统一输入和概率归一化，避免同时改变环境。</p>
<p class="meta">边界：固定的SCE回访者总体不是全美人口总体；不包括调查自身代表性误差、未来时期差异或新人的模型输出。行级缓存命中{s['fitting']['cached_row_hits']}次，另以冻结口径计分{s['fitting']['uncached_bin_vectors_fit']}种未缓存十档向量；分析用时{s['seconds']:.1f}秒。原样本、原输入、原答和参考配置均未改。</p>
<p><a href="sampling_summary.json">聚合结果与来源哈希</a> · <a href="../price_background_results_v1/index.html">最新价格背景实验</a></p></main></html>'''
    (dest/'index.html').write_text(html)
    (dest/'sampling_summary.json').write_text(json.dumps(s, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True); p.add_argument('--dest', type=Path, required=True)
    a = p.parse_args(); report(a.source.resolve(), a.dest.resolve())
